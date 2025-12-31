"""Crawler 类 - 核心爬虫逻辑"""

import asyncio
from typing import List, Dict, Any, Optional
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from .llm_config import get_llm_config


def _run_async(coro):
    """
    运行异步函数的辅助函数，兼容已有事件循环的环境
    使用 nest_asyncio 允许嵌套事件循环
    """
    try:
        asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.get_event_loop().run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _calculate_success_rate(results: List[Dict[str, Any]]) -> str:
    """计算成功率"""
    if not results:
        return "0%"
    successful = sum(1 for r in results if r["success"])
    return f"{successful / len(results) * 100:.1f}%"


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
        llm_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        内部异步爬取方法

        Args:
            url: 目标 URL
            enhanced: 是否使用增强模式 (更长等待时间)
            llm_config: LLM 配置字典（可选）

        Returns:
            包含 success, markdown, title, (可选) llm_result 的字典
        """
        config = self._create_config(enhanced)

        # 如果有 LLM 配置，添加 LLM 提取策略
        if llm_config:
            from crawl4ai.extraction_strategy import LLMExtractionStrategy
            from crawl4ai import LLMConfig as Crawl4AILLMConfig

            llm = get_llm_config(llm_config)
            crawl4ai_llm_config = Crawl4AILLMConfig(
                provider="openai",
                api_token=llm.api_key,
                base_url=llm.base_url,
                model=llm.model,
            )

            extraction_strategy = LLMExtractionStrategy(
                llm_config=crawl4ai_llm_config,
                instruction=llm.instruction or "Extract and summarize the main content",
                schema=llm.schema,
            )
            config.extraction_strategy = extraction_strategy

        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url, config=config)

            response = {
                "success": result.success,
                "markdown": result.markdown.raw_markdown if result.success else "",
                "title": result.metadata.get('title', '') if result.success else '',
                "error": result.error_message if not result.success else None,
            }

            # 如果使用了 LLM 提取，添加结果
            if llm_config and result.success and result.extracted_content:
                try:
                    import json
                    response["llm_result"] = json.loads(result.extracted_content)
                except (json.JSONDecodeError, TypeError):
                    response["llm_result"] = {"raw": result.extracted_content}

            return response

    def crawl_single(
        self,
        url: str,
        enhanced: bool = False,
        llm_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        爬取单个网页 (同步封装)

        Args:
            url: 网页 URL
            enhanced: 是否使用增强 SPA 模式
            llm_config: LLM 配置字典（可选）

        Returns:
            爬取结果字典
        """
        return _run_async(self._crawl(url, enhanced, llm_config))

    async def _crawl_site(
        self,
        url: str,
        depth: int = 2,
        pages: int = 10,
        concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        内部整站爬取方法

        Args:
            url: 起始 URL
            depth: 最大爬取深度
            pages: 最大页面数
            concurrent: 并发数

        Returns:
            爬取统计信息
        """
        # TODO: 整合 async_crawler.py 的 AsyncParallelCrawler 逻辑
        # 暂时返回模拟结果
        visited = set()
        results = []

        async def crawl_with_depth(target_url: str, current_depth: int):
            if current_depth > depth or len(results) >= pages:
                return
            if target_url in visited:
                return

            visited.add(target_url)
            result = await self._crawl(target_url)
            results.append(result)

        await crawl_with_depth(url, 0)

        successful = sum(1 for r in results if r["success"])

        return {
            "successful_pages": successful,
            "total_pages": len(results),
            "success_rate": _calculate_success_rate(results),
            "results": results,
        }

    def crawl_site(
        self,
        url: str,
        depth: int = 2,
        pages: int = 10,
        concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        爬取整个网站 (同步封装)

        Args:
            url: 起始 URL
            depth: 最大爬取深度
            pages: 最大页面数
            concurrent: 并发数

        Returns:
            爬取统计信息
        """
        return _run_async(self._crawl_site(url, depth=depth, pages=pages, concurrent=concurrent))

    async def _crawl_batch(
        self,
        urls: List[str],
        concurrent: int = 3,
        llm_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        内部批量爬取方法

        Args:
            urls: URL 列表
            concurrent: 并发数
            llm_config: LLM 配置字典（可选）

        Returns:
            爬取结果列表
        """
        if not urls:
            return []

        # 简化实现：顺序爬取
        # 完整实现需要使用 asyncio.Semaphore 控制并发
        results = []
        for url in urls:
            result = await self._crawl(url, llm_config=llm_config)
            results.append(result)

        return results

    def crawl_batch(
        self,
        urls: List[str],
        concurrent: int = 3,
        llm_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        批量爬取多个网页 (同步封装)

        Args:
            urls: URL 列表
            concurrent: 并发数
            llm_config: LLM 配置字典（可选）

        Returns:
            爬取结果列表
        """
        return _run_async(self._crawl_batch(urls, concurrent=concurrent, llm_config=llm_config))
