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
from openai import AsyncOpenAI

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
        """内部异步爬取方法（浏览器实例复用版）

        关键优化：AsyncWebCrawler 在重试循环外部创建，
        网络错误时复用同一浏览器实例，避免每次重试都启动/关闭浏览器。
        """
        config = self._create_config(enhanced)

        max_retries = 3

        async with AsyncWebCrawler(verbose=False) as crawler:
            for attempt in range(max_retries + 1):
                try:
                    result = await crawler.arun(url=url, config=config)

                    response = {
                        "success": result.success,
                        "markdown": result.markdown.raw_markdown
                        if result.success
                        else "",
                        "title": result.metadata.get("title", "")
                        if result.success
                        else "",
                        "error": result.error_message if not result.success else None,
                    }
                    return response

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

    def _call_llm(
        self, content: str, instruction: str, schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """调用 LLM 处理文本内容（同步）"""
        from openai import OpenAI

        llm_cfg = get_default_llm_config()
        client = OpenAI(api_key=llm_cfg.api_key, base_url=llm_cfg.base_url)

        messages = [
            {"role": "system", "content": "你是一个专业的文本处理助手。"},
            {"role": "user", "content": f"指令：{instruction}\n\n内容：\n{content}"},
        ]

        if schema:
            messages[0]["content"] += f"\n\n请按照以下 JSON Schema 返回结果：{schema}"

        try:
            response = client.chat.completions.create(
                model=llm_cfg.model,
                messages=messages,
                temperature=0.3,
            )
            result_text = response.choices[0].message.content

            if schema:
                try:
                    return {"success": True, "data": json.loads(result_text)}
                except json.JSONDecodeError:
                    return {"success": True, "content": result_text}
            return {"success": True, "summary": result_text}

        except Exception as e:
            return {"success": False, "error": str(e), "content": content}

    async def _call_llm_batch(
        self,
        items: List[Dict[str, Any]],
        instruction: str,
        schema: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """并行调用 LLM 处理多个文本内容"""
        llm_cfg = get_default_llm_config()
        client = AsyncOpenAI(api_key=llm_cfg.api_key, base_url=llm_cfg.base_url)

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_item(item: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                content = item.get("markdown", "")
                messages = [
                    {"role": "system", "content": "你是一个专业的文本处理助手。"},
                    {
                        "role": "user",
                        "content": f"指令：{instruction}\n\n内容：\n{content}",
                    },
                ]
                if schema:
                    messages[0]["content"] += (
                        f"\n\n请按照以下 JSON Schema 返回结果：{schema}"
                    )

                try:
                    response = await client.chat.completions.create(
                        model=llm_cfg.model, messages=messages, temperature=0.3
                    )
                    result_text = response.choices[0].message.content

                    if schema:
                        try:
                            return {"success": True, "data": json.loads(result_text)}
                        except json.JSONDecodeError:
                            return {"success": True, "content": result_text}
                    return {"success": True, "summary": result_text}

                except Exception as e:
                    return {"success": False, "error": str(e)}

        tasks = [process_item(item) for item in items]
        results = await asyncio.gather(*tasks)
        return list(results)

    def _call_llm_batch_sync(
        self,
        items: List[Dict[str, Any]],
        instruction: str,
        schema: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """并行调用 LLM 处理多个文本内容（同步封装）"""
        return run_async(
            self._call_llm_batch(items, instruction, schema, max_concurrent)
        )

    def postprocess_markdown(
        self, markdown: str, instruction: str, schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """对 Markdown 内容进行 LLM 后处理"""
        if not instruction or not instruction.strip():
            return {
                "success": True,
                "original_markdown": markdown,
                "skipped": "No instruction provided",
            }
        return self._call_llm(markdown, instruction, schema)

    # ================================================================
    # 公开 API — 单页爬取
    # ================================================================

    def crawl_single(
        self,
        url: str,
        enhanced: bool = False,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """爬取单个网页（两阶段架构）

        阶段 1：快速爬取 Markdown
        阶段 2：如有 llm_config，对 Markdown 做 LLM 后处理
        """
        parsed_llm_config = _parse_llm_config(llm_config)

        # 第一阶段：快速爬取
        crawl_result = run_async(self._crawl(url, enhanced, llm_config=None))

        # 第二阶段：LLM 后处理
        if parsed_llm_config and crawl_result["success"]:
            instruction = parsed_llm_config.get("instruction", "")
            schema = parsed_llm_config.get("schema")

            if instruction:
                llm_result = self.postprocess_markdown(
                    crawl_result["markdown"], instruction, schema
                )
                if llm_result.get("success"):
                    if "summary" in llm_result:
                        crawl_result["llm_summary"] = llm_result["summary"]
                    if "data" in llm_result:
                        crawl_result["llm_data"] = llm_result["data"]
                    if "content" in llm_result:
                        crawl_result["llm_content"] = llm_result["content"]
                else:
                    crawl_result["llm_error"] = llm_result.get("error", "Unknown error")

        return crawl_result

    # ================================================================
    # 公开 API — 整站深度爬取
    # ================================================================

    async def _crawl_site(
        self, url: str, depth: int = 2, pages: int = 10, concurrent: int = 3
    ) -> Dict[str, Any]:
        """整站深度爬取（使用 BFSDeepCrawlStrategy）"""
        config = self._create_config()
        strategy = BFSDeepCrawlStrategy(max_depth=depth, url=url)
        dispatcher = SemaphoreDispatcher(semaphore_count=concurrent)

        async with AsyncWebCrawler(verbose=False) as crawler:
            results = await crawler.arun_many(
                urls=[url], config=config, dispatcher=dispatcher, strategy=strategy
            )

        formatted = []
        for r in results:
            formatted.append(
                {
                    "success": r.success,
                    "markdown": r.markdown.raw_markdown if r.success else "",
                    "title": r.metadata.get("title", "") if r.success else "",
                    "error": r.error_message if not r.success else None,
                }
            )

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

        formatted_results = []
        for r in raw_results:
            formatted_results.append(
                {
                    "success": r.success,
                    "markdown": r.markdown.raw_markdown if r.success else "",
                    "title": r.metadata.get("title", "") if r.success else "",
                    "error": r.error_message if not r.success else None,
                }
            )

        # 第二阶段：LLM 后处理
        parsed_llm_config = _parse_llm_config(llm_config)
        if parsed_llm_config and parsed_llm_config.get("instruction"):
            instruction = parsed_llm_config["instruction"]
            schema = parsed_llm_config.get("schema")

            successful = [
                (i, r) for i, r in enumerate(formatted_results) if r["success"]
            ]

            if successful:
                llm_results = await self._call_llm_batch(
                    [{"markdown": r["markdown"]} for _, r in successful],
                    instruction,
                    schema,
                    max_concurrent=llm_concurrent,
                )

                for idx, (original_index, _) in enumerate(successful):
                    llm_result = llm_results[idx]
                    if llm_result.get("success"):
                        if "summary" in llm_result:
                            formatted_results[original_index]["llm_summary"] = (
                                llm_result["summary"]
                            )
                        if "data" in llm_result:
                            formatted_results[original_index]["llm_data"] = llm_result[
                                "data"
                            ]
                        if "content" in llm_result:
                            formatted_results[original_index]["llm_content"] = (
                                llm_result["content"]
                            )
                    else:
                        formatted_results[original_index]["llm_error"] = llm_result.get(
                            "error", "Unknown error"
                        )

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
