"""Crawler 类 - 核心爬虫逻辑

三级设计：
  阶段 0：快速提取（ddgs.extract，~0.5s，静态页首选）
  阶段 1：浏览器渲染爬取（Playwright，SPA/动态页）
  阶段 2：可选 LLM 后处理（仅当提供 llm_config 且 CRAWL_MCP_API_KEY 已配置时执行）

crawl_single / crawl_batch 自动降级：先尝试阶段 0，失败或内容不足时 fallback 到阶段 1。
"""

import asyncio
import json
import re
from dataclasses import dataclass
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
from .searcher import Searcher
from .utils import run_async


# ── 常量 ────────────────────────────────────────────────────────

MIN_CONTENT_LENGTH_DEFAULT = 200  # 快速提取结果低于此阈值触发降级

SPA_INDICATORS = [
    '<div id="app"',
    '<div id="root"',
    "__next_data__",  # Next.js
    "nuxt-app",  # Nuxt.js
    '<div id="vue"',  # Vue.js
    "ng-app",  # Angular
]


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
    """创建 crawl4ai LLMConfig（从环境变量读取）

    Returns:
        crawl4ai LLMConfig 对象，或 None（当 API Key 未配置时）
    """
    cfg = get_default_llm_config()
    if cfg is None:
        return None
    return create_llm_config(
        provider=f"openai/{cfg.model}",
        api_token=cfg.api_key,
        base_url=cfg.base_url,
    )


def _llm_available() -> bool:
    """检查 LLM 功能是否可用（API Key 是否已配置）

    Returns:
        True 如果 CRAWL_MCP_API_KEY 已配置
    """
    return get_default_llm_config() is not None


@dataclass(frozen=True)
class _FastExtractDecision:
    """快速提取后的下一步动作。"""

    should_fallback: bool
    fallback_reason: Optional[str] = None
    should_enhance: bool = False


class Crawler:
    """统一的爬虫类，整合单页、整站、批量爬取功能

    自动降级策略：
      - 默认先尝试快速提取（ddgs.extract, ~0.5s）
      - 失败或内容不足时自动 fallback 到浏览器渲染（Playwright, ~15-23s）
      - LLM 后处理为可选插件功能
    """

    def __init__(self, searcher: Optional[Searcher] = None):
        self._searcher = searcher or Searcher()

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _looks_like_spa(content: str) -> bool:
        """启发式 SPA 检测：从快速提取的原始内容判断是否为 SPA 骨架页"""
        if len(content) > 1000:
            return False  # 长内容大概率是真实内容
        lower = content.lower()
        return any(indicator in lower for indicator in SPA_INDICATORS)

    @staticmethod
    def _extract_title_from_html(content: str) -> str:
        """从 HTML/Markdown 内容中提取 <title> 标签文本"""
        match = re.search(
            r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE
        )
        if match:
            return match.group(1).strip()
        return ""

    def _normalize_fast_result(self, extract_result: Dict[str, Any]) -> Dict[str, Any]:
        """将 extract_url 的输出格式标准化为 crawl_single 格式

        映射：content → markdown, 新增 title / method 字段
        """
        content = extract_result.get("content", "")
        return {
            "success": extract_result.get("success", False),
            "markdown": content,
            "title": self._extract_title_from_html(content),
            "error": extract_result.get("error"),
            "method": "fast_extract",
        }

    def _decide_fast_extract_next_step(
        self, extract_result: Dict[str, Any], min_content_length: int
    ) -> _FastExtractDecision:
        """判断快速提取结果是否需要浏览器降级，以及是否启用 enhanced。"""
        content = extract_result.get("content", "")
        if extract_result.get("success") and len(content) >= min_content_length:
            return _FastExtractDecision(should_fallback=False)

        if not extract_result.get("success"):
            reason = f"Fast extraction failed: {extract_result.get('error', 'unknown')}"
        else:
            content_len = len(content)
            reason = (
                f"Fast extraction returned insufficient content "
                f"({content_len} chars < {min_content_length} min)"
            )

        return _FastExtractDecision(
            should_fallback=True,
            fallback_reason=reason,
            should_enhance=self._looks_like_spa(content),
        )

    def _apply_llm_postprocess(
        self, result: Dict[str, Any], parsed_llm: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对成功的爬取结果应用 LLM 后处理（统一 fast / browser 路径）"""
        if not _llm_available():
            result["llm_skipped"] = (
                "CRAWL_MCP_API_KEY 未配置，已跳过 LLM 处理。"
                "如需使用 LLM 后处理，请设置环境变量 CRAWL_MCP_API_KEY"
            )
            return result

        llm_result = self._postprocess_with_llm(
            result["markdown"],
            parsed_llm.get("instruction", ""),
            parsed_llm.get("schema"),
        )
        if llm_result.get("success"):
            for key in ("summary", "data", "content"):
                if key in llm_result:
                    result[f"llm_{key}"] = llm_result[key]
        else:
            result["llm_error"] = llm_result.get("error", "Unknown error")

        return result

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
        """使用原生 LLMExtractionStrategy 做后处理

        .. deprecated::
            此方法保留供 Python SDK 高级用户使用。
            MCP 工具层已将 LLM 降级为可选插件，未配置 API Key 时自动跳过。
        """
        if not instruction or not instruction.strip():
            return {"success": True, "original_markdown": markdown, "skipped": True}

        llm_cfg = _build_llm_config()
        if llm_cfg is None:
            return {
                "success": False,
                "error": "CRAWL_MCP_API_KEY 未配置",
                "content": markdown,
            }

        kw = dict(
            llm_config=llm_cfg,
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
        """使用原生 LLMExtractionStrategy 并行做批量后处理

        .. deprecated::
            此方法保留供 Python SDK 高级用户使用。
            MCP 工具层已将 LLM 降级为可选插件。
        """
        if not items:
            return []

        import concurrent.futures

        llm_cfg = _build_llm_config()
        if llm_cfg is None:
            return [{"__index__": i, "__error__": True} for i in range(len(items))]

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
        prefer_fast: bool = True,
        min_content_length: int = MIN_CONTENT_LENGTH_DEFAULT,
    ) -> Dict[str, Any]:
        """爬取单个网页（自动降级：快速提取 → 浏览器渲染）

        默认先尝试轻量级提取（~0.5s），失败或内容不足时自动切换到浏览器模式（~15-23s）。
        如需强制使用浏览器（如已知目标为 SPA），设置 prefer_fast=False。

        Args:
            url: 要爬取的网页 URL
            enhanced: 是否使用增强模式（适用于 SPA 网站）
            llm_config: [实验性] LLM 后处理配置（可选）
            prefer_fast: 是否优先尝试快速提取（默认 True，设为 False 强制用浏览器）
            min_content_length: 快速提取结果的最小内容长度阈值（默认 200 字符）
        """
        parsed_llm = _parse_llm_config(llm_config)

        # ── Phase 1: 快速提取（如果启用）────────────────────
        if prefer_fast:
            fast_result = self._searcher.extract_url(url)
            decision = self._decide_fast_extract_next_step(
                fast_result, min_content_length
            )

            if not decision.should_fallback:
                # 快速路径成功 → 标准化 + LLM 后处理
                result = self._normalize_fast_result(fast_result)
                if parsed_llm and result["success"]:
                    result = self._apply_llm_postprocess(result, parsed_llm)
                return result

            # SPA 自动检测：如果快速结果看起来像 SPA 骨架，自动提升到 enhanced
            if not enhanced and decision.should_enhance:
                enhanced = True
            fallback_reason = decision.fallback_reason

        # ── Phase 1b: 浏览器渲染降级 ─────────────────────────
        result = run_async(self._crawl(url, enhanced))
        if prefer_fast:
            result["method"] = "browser_fallback"
            result["fallback_reason"] = fallback_reason

        # ── Phase 2: LLM 后处理（可选插件）────────────────────
        if parsed_llm and result["success"]:
            result = self._apply_llm_postprocess(result, parsed_llm)

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
        dispatcher = SemaphoreDispatcher(semaphore_count=concurrent)

        async with AsyncWebCrawler(verbose=False) as crawler:
            raw_result = await crawler.arun(
                url=url, config=config, dispatcher=dispatcher
            )

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

    @staticmethod
    def _format_crawl4ai_result(raw) -> Dict[str, Any]:
        """将 crawl4ai 原始结果标准化为统一字典格式"""
        return {
            "success": raw.success,
            "markdown": raw.markdown.raw_markdown if raw.success else "",
            "title": raw.metadata.get("title", "") if raw.success else "",
            "error": raw.error_message if not raw.success else None,
        }

    async def _parallel_fast_extract(self, urls: List[str]) -> List[Dict[str, Any]]:
        """并行快速提取多个 URL（ThreadPoolExecutor，DDGS 是同步的）"""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(urls), 10)
        ) as executor:
            futures = [executor.submit(self._searcher.extract_url, url) for url in urls]
            return [f.result() for f in futures]

    async def _browser_crawl_subset(
        self,
        urls: List[str],
        enhanced_flags: List[bool],
        concurrent: int,
    ) -> List[Dict[str, Any]]:
        """仅对子集 URL 执行浏览器爬取，按 enhanced 标志分组"""
        if len(urls) != len(enhanced_flags):
            raise ValueError("urls and enhanced_flags must have the same length")

        normal_urls = [
            (i, u) for i, (u, e) in enumerate(zip(urls, enhanced_flags)) if not e
        ]
        enhanced_urls = [
            (i, u) for i, (u, e) in enumerate(zip(urls, enhanced_flags)) if e
        ]

        all_results: list = [None] * len(urls)

        async def crawl_group(url_list, is_enhanced):
            if not url_list:
                return []
            config = self._create_config(enhanced=is_enhanced)
            _, group_urls = zip(*url_list)
            dispatcher = SemaphoreDispatcher(semaphore_count=concurrent)
            async with AsyncWebCrawler(verbose=False) as crawler:
                raw = await crawler.arun_many(
                    urls=list(group_urls), config=config, dispatcher=dispatcher
                )
            return [self._format_crawl4ai_result(r) for r in raw]

        if normal_urls:
            norm_results = await crawl_group(normal_urls, False)
            for (orig_idx, _), r in zip(normal_urls, norm_results):
                all_results[orig_idx] = r
        if enhanced_urls:
            enh_results = await crawl_group(enhanced_urls, True)
            for (orig_idx, _), r in zip(enhanced_urls, enh_results):
                all_results[orig_idx] = r

        return all_results

    async def _crawl_batch(
        self,
        urls: List[str],
        concurrent: int = 3,
        llm_config: Optional[Dict[str, Any]] = None,
        llm_concurrent: int = 3,
        prefer_fast: bool = True,
        min_content_length: int = MIN_CONTENT_LENGTH_DEFAULT,
    ) -> List[Dict[str, Any]]:
        """批量爬取（三阶段：并行快提取 → 选浏览器 → LLM 后处理）

        Phase 1: 并行快速提取所有 URL（~0.5s each）
        Phase 2: 对失败/短内容的 URL 子集执行浏览器爬取（~15-23s each）
        Phase 3: 可选 LLM 批量后处理
        """
        if not urls:
            return []

        results: List[Optional[Dict[str, Any]]] = [None] * len(urls)

        # ── Phase 1: 并行快速提取 ─────────────────────────────
        if prefer_fast:
            fast_results = await self._parallel_fast_extract(urls)

            # 分离成功与需降级
            fallback_indices: List[int] = []
            decisions: List[_FastExtractDecision] = []
            for i, fr in enumerate(fast_results):
                decision = self._decide_fast_extract_next_step(fr, min_content_length)
                decisions.append(decision)
                if not decision.should_fallback:
                    results[i] = self._normalize_fast_result(fr)
                else:
                    fallback_indices.append(i)

            # 全部快速成功 → 直接进入 LLM 阶段
            if not fallback_indices:
                pass  # results 已填满，继续到 Phase 3
            else:
                # ── Phase 2: 浏览器降级子集 ───────────────────────
                fallback_urls = [urls[i] for i in fallback_indices]
                # SPA 检测决定是否用 enhanced
                enhanced_flags = [decisions[i].should_enhance for i in fallback_indices]
                browser_results = await self._browser_crawl_subset(
                    fallback_urls, enhanced_flags, concurrent
                )

                for idx, br in zip(fallback_indices, browser_results):
                    br["method"] = "browser_fallback"
                    br["fallback_reason"] = decisions[idx].fallback_reason
                    results[idx] = br
        else:
            # prefer_fast=False：全部走浏览器
            config = self._create_config(enhanced=False)
            dispatcher = SemaphoreDispatcher(semaphore_count=concurrent)
            async with AsyncWebCrawler(verbose=False) as crawler:
                raw_results = await crawler.arun_many(
                    urls=urls, config=config, dispatcher=dispatcher
                )
            results = [self._format_crawl4ai_result(r) for r in raw_results]

        # ── Phase 3: LLM 批量后处理（可选插件）──────────────────
        parsed = _parse_llm_config(llm_config)
        if parsed and parsed.get("instruction"):
            if not _llm_available():
                for r in results:
                    if r and r["success"]:
                        r["llm_skipped"] = "CRAWL_MCP_API_KEY 未配置，已跳过 LLM 处理"
                return results  # type: ignore[return-value]

            successful = [(i, r) for i, r in enumerate(results) if r and r["success"]]
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
                        results[original_index]["llm_error"] = lr.get(
                            "error", "Unknown"
                        )
                    for key in ("summary", "data"):
                        if key in lr:
                            results[original_index][f"llm_{key}"] = lr[key]

        return results  # type: ignore[return-value]

    def crawl_batch(
        self,
        urls: List[str],
        concurrent: int = 3,
        llm_config: Optional[Dict[str, Any]] = None,
        llm_concurrent: int = 3,
        prefer_fast: bool = True,
        min_content_length: int = MIN_CONTENT_LENGTH_DEFAULT,
    ) -> List[Dict[str, Any]]:
        """批量爬取多个网页（自动降级版）

        默认对每个 URL 先尝试快速提取，失败或内容不足时自动 fallback 到浏览器渲染。
        设置 prefer_fast=False 可退化到纯浏览器模式。

        Args:
            urls: URL 列表
            concurrent: 爬取并发数
            llm_config: [实验性] LLM 后处理配置（可选）
            llm_concurrent: LLM 处理并发数
            prefer_fast: 是否优先尝试快速提取（默认 True）
            min_content_length: 快速提取最小内容长度阈值（默认 200 字符）
        """
        return run_async(
            self._crawl_batch(
                urls,
                concurrent=concurrent,
                llm_config=llm_config,
                llm_concurrent=llm_concurrent,
                prefer_fast=prefer_fast,
                min_content_length=min_content_length,
            )
        )
