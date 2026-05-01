"""Crawler 类 - 核心爬虫逻辑

两阶段设计：
  阶段 1：快速爬取（始终执行，返回原始 Markdown）
  阶段 2：可选 LLM 后处理（仅当提供 llm_config 时执行）
"""

import asyncio
import json
from typing import List, Dict, Any, Optional

from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    DefaultMarkdownGenerator,
    BFSDeepCrawlStrategy,
    SemaphoreDispatcher,
)
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.types import create_llm_config

from .llm_config import get_default_llm_config
from .utils import run_async


def _calculate_success_rate(results: List[Dict[str, Any]]) -> str:
    """计算成功率"""
    if not results:
        return "0%"
    successful = sum(1 for r in results if r["success"])
    return f"{successful / len(results) * 100:.1f}%"


def _parse_llm_config(llm_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """解析 llm_config，兼容字符串和字典两种格式"""
    if llm_config is None:
        return None
    if isinstance(llm_config, dict):
        return llm_config
    if isinstance(llm_config, str):
        try:
            return json.loads(llm_config)
        except json.JSONDecodeError:
            return {"instruction": llm_config}
    return {"instruction": str(llm_config)}


def _build_llm_config():
    """创建 crawl4ai LLMConfig（从环境变量读取）"""

    cfg = get_default_llm_config()
    return create_llm_config(
        provider=f"openai/{cfg.model}",
        api_token=cfg.api_key,
        base_url=cfg.base_url,
    )


class Crawler:
    """统一的爬虫类，整合单页、整站、批量爬取功能"""

    def _create_config(self, enhanced: bool = False) -> CrawlerRunConfig:
        """创建爬虫配置"""
        markdown_generator = DefaultMarkdownGenerator(
            options={
                "citations": False,
                "body_width": None,
                "ignore_links": False,
            }
        )
        return CrawlerRunConfig(
            markdown_generator=markdown_generator,
            page_timeout=60000,
            delay_before_return_html=5.0 if not enhanced else 15.0,
        )

    async def _crawl(
        self,
        url: str,
        enhanced: bool = False,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """内部异步爬取方法（浏览器实例复用版）"""
        config = self._create_config(enhanced)
        max_retries = 3

        async with AsyncWebCrawler(verbose=False) as crawler:
            for attempt in range(max_retries + 1):
                try:
                    result = await crawler.arun(url=url, config=config)
                    return {
                        "success": result.success,
                        "markdown": result.markdown.raw_markdown
                        if result.success
                        else "",
                        "title": result.metadata.get("title", "")
                        if result.success
                        else "",
                        "error": result.error_message if not result.success else None,
                    }
                except Exception as e:
                    error_msg = str(e)
                    is_network_error = any(
                        err in error_msg
                        for err in [
                            "ERR_NETWORK_CHANGED",
                            "ERR_INTERNET_DISCONNECTED",
                            "ERR_CONNECTION_RESET",
                            "ERR_TIMED_OUT",
                        ]
                    )
                    if is_network_error and attempt < max_retries:
                        await asyncio.sleep(2**attempt)
                        continue
                    raise

    def _postprocess_with_llm(
        self, markdown: str, instruction: str, schema=None
    ) -> Dict:
        """使用原生 LLMExtractionStrategy 做后处理"""
        if not instruction or not instruction.strip():
            return {"success": True, "original_markdown": markdown, "skipped": True}

        kw = dict(
            llm_config=_build_llm_config(),
            instruction=instruction,
            extraction_type="schema" if schema else "block",
        )
        if schema:
            kw["schema"] = schema

        strategy = LLMExtractionStrategy(**kw)
        blocks = strategy.extract(url="", ix=0, html=markdown)

        if not blocks:
            return {
                "success": False,
                "error": "LLM returned empty results",
                "content": markdown,
            }

        if blocks[0].get("error"):
            return {"success": False, "error": "Extraction error", "content": markdown}

        # schema 模式：返回结构化数据
        if schema:
            item = {k: v for k, v in blocks[0].items() if k != "error"}
            return {"success": True, "data": item}

        # block 模式：合并所有 block 的 content 作为摘要
        parts = []
        for b in blocks:
            if b.get("content"):
                parts.extend(
                    b["content"] if isinstance(b["content"], list) else [b["content"]]
                )
        summary = "\n\n".join(parts)
        return {"success": True, "summary": summary}

    async def _postprocess_batch_with_llm(
        self, items: List[Dict], instruction: str, schema=None, max_concurrent=3
    ) -> List[Dict]:
        """使用原生 LLMExtractionStrategy 并行做批量后处理"""
        import concurrent.futures

        llm_cfg = _build_llm_config()
        extraction_type = "schema" if schema else "block"
        kw = dict(
            llm_config=llm_cfg, instruction=instruction, extraction_type=extraction_type
        )
        if schema:
            kw["schema"] = schema

        def process_one(item):
            strategy = LLMExtractionStrategy(**kw)
            blocks = strategy.extract(url="", ix=0, html=item.get("markdown", ""))
            if not blocks or blocks[0].get("error"):
                return {"__index__": items.index(item), "__error__": True}
            b = blocks[0]
            if schema:
                return {
                    **{k: v for k, v in b.items() if k != "error"},
                    "__index__": items.index(item),
                }
            content_parts = (
                b.get("content", [])
                if isinstance(b.get("content"), list)
                else [b.get("content", "")]
            )
            return {
                "summary": "\n\n".join(str(p) for p in content_parts),
                "__index__": items.index(item),
            }

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrent
        ) as executor:
            futures = [executor.submit(process_one, item) for item in items]
            results = [f.result() for f in futures]

        # 按 __index__ 排序回原顺序
        results.sort(key=lambda x: x.pop("__index__"))
        return results

    # ================================================================
    # 公开 API — 单页爬取
    # ================================================================

    def crawl_single(
        self,
        url: str,
        enhanced: bool = False,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """爬取单个网页（两阶段架构）"""
        parsed = _parse_llm_config(llm_config)

        # 第一阶段：快速爬取
        result = run_async(self._crawl(url, enhanced))

        # 第二阶段：LLM 后处理
        if parsed and result["success"]:
            llm_result = self._postprocess_with_llm(
                result["markdown"],
                parsed.get("instruction", ""),
                parsed.get("schema"),
            )
            if llm_result.get("success"):
                for key in ("summary", "data", "content"):
                    if key in llm_result:
                        result[f"llm_{key}"] = llm_result[key]
            else:
                result["llm_error"] = llm_result.get("error", "Unknown error")

        return result

    # ================================================================
    # 公开 API — 整站深度爬取
    # ================================================================

    async def _crawl_site(
        self, url: str, depth: int = 2, pages: int = 10, concurrent: int = 3
    ) -> Dict[str, Any]:
        """整站深度爬取（使用 BFSDeepCrawlStrategy）"""
        config = self._create_config()
        config.deep_crawl_strategy = BFSDeepCrawlStrategy(
            max_depth=depth, max_pages=pages
        )

        async with AsyncWebCrawler(verbose=False) as crawler:
            raw_result = await crawler.arun(url=url, config=config)

        # BFSDeepCrawlStrategy 返回列表，普通爬取返回单个结果
        results_list = raw_result if isinstance(raw_result, list) else [raw_result]

        formatted = [
            {
                "success": r.success,
                "markdown": r.markdown.raw_markdown if r.success else "",
                "title": r.metadata.get("title", "") if r.success else "",
                "error": r.error_message if not r.success else None,
            }
            for r in results_list
        ]

        return {
            "successful_pages": sum(1 for r in formatted if r["success"]),
            "total_pages": len(formatted),
            "success_rate": _calculate_success_rate(formatted),
            "results": formatted,
        }

    def crawl_site(
        self, url: str, depth: int = 2, pages: int = 10, concurrent: int = 3
    ) -> Dict[str, Any]:
        """爬取整个网站（同步封装）"""
        return run_async(
            self._crawl_site(url, depth=depth, pages=pages, concurrent=concurrent)
        )

    # ================================================================
    # 公开 API — 批量爬取
    # ================================================================

    async def _crawl_batch(
        self,
        urls: List[str],
        concurrent: int = 3,
        llm_config: Optional[Dict[str, Any]] = None,
        llm_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """批量爬取（先并行爬取，再可选 LLM 后处理）"""
        if not urls:
            return []

        config = self._create_config(enhanced=False)
        dispatcher = SemaphoreDispatcher(semaphore_count=concurrent)

        async with AsyncWebCrawler(verbose=False) as crawler:
            raw_results = await crawler.arun_many(
                urls=urls, config=config, dispatcher=dispatcher
            )

        formatted_results = [
            {
                "success": r.success,
                "markdown": r.markdown.raw_markdown if r.success else "",
                "title": r.metadata.get("title", "") if r.success else "",
                "error": r.error_message if not r.success else None,
            }
            for r in raw_results
        ]

        # 第二阶段：LLM 后处理
        parsed = _parse_llm_config(llm_config)
        if parsed and parsed.get("instruction"):
            successful = [
                (i, r) for i, r in enumerate(formatted_results) if r["success"]
            ]
            if successful:
                llm_results = await self._postprocess_batch_with_llm(
                    [r for _, r in successful],
                    parsed["instruction"],
                    parsed.get("schema"),
                    max_concurrent=llm_concurrent,
                )
                for idx, (original_index, _) in enumerate(successful):
                    lr = llm_results[idx]
                    if lr.pop("__error__", None):
                        formatted_results[original_index]["llm_error"] = lr.get(
                            "error", "Unknown"
                        )
                    for key in ("summary", "data"):
                        if key in lr:
                            formatted_results[original_index][f"llm_{key}"] = lr[key]

        return formatted_results

    def crawl_batch(
        self,
        urls: List[str],
        concurrent: int = 3,
        llm_config: Optional[Dict[str, Any]] = None,
        llm_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """批量爬取多个网页（同步封装）"""
        return run_async(
            self._crawl_batch(
                urls,
                concurrent=concurrent,
                llm_config=llm_config,
                llm_concurrent=llm_concurrent,
            )
        )
