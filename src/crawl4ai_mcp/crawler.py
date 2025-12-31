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

    def _add_llm_strategy(
        self,
        config: CrawlerRunConfig,
        llm_config: Optional[Dict[str, Any]]
    ) -> CrawlerRunConfig:
        """
        为配置添加 LLM 提取策略

        Args:
            config: 基础爬虫配置
            llm_config: LLM 配置字典（可选）

        Returns:
            添加了 LLM 策略的配置（原地修改或返回原配置）
        """
        if not llm_config:
            return config

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
        return config

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
        config = self._add_llm_strategy(config, llm_config)

        # 重试机制：最多重试 3 次，只对网络错误重试
        max_retries = 3
        last_error = None

        for attempt in range(max_retries + 1):  # +1 因为第一次不是重试
            try:
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

            except Exception as e:
                last_error = e
                error_msg = str(e)

                # 只对 ERR_NETWORK_CHANGED 相关错误重试
                is_network_error = (
                    "ERR_NETWORK_CHANGED" in error_msg or
                    "ERR_INTERNET_DISCONNECTED" in error_msg or
                    "ERR_CONNECTION_RESET" in error_msg or
                    "ERR_TIMED_OUT" in error_msg
                )

                # 如果是网络错误且还有重试次数，等待后重试
                if is_network_error and attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)  # 指数退避: 1s, 2s, 4s
                    continue

                # 其他错误或重试用尽，抛出异常
                raise

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
        内部批量爬取方法 - 使用 arun_many 实现真正的异步并行

        Args:
            urls: URL 列表
            concurrent: 并发数
            llm_config: LLM 配置字典（可选）

        Returns:
            爬取结果列表
        """
        if not urls:
            return []

        from crawl4ai.async_dispatcher import SemaphoreDispatcher
        import json

        # 创建配置（包含 LLM 策略）
        config = self._create_config(enhanced=False)
        config = self._add_llm_strategy(config, llm_config)

        # 创建并发控制器
        dispatcher = SemaphoreDispatcher(semaphore_count=concurrent)

        # 使用 arun_many 实现真正的并行爬取
        async with AsyncWebCrawler(verbose=False) as crawler:
            results = await crawler.arun_many(
                urls=urls,
                config=config,
                dispatcher=dispatcher
            )

        # 将 CrawlResultContainer 转换为我们的格式
        formatted_results = []
        for r in results:
            response = {
                "success": r.success,
                "markdown": r.markdown.raw_markdown if r.success else "",
                "title": r.metadata.get('title', '') if r.success else '',
                "error": r.error_message if not r.success else None,
            }

            # 如果使用了 LLM 提取，添加结果
            if llm_config and r.success and r.extracted_content:
                try:
                    response["llm_result"] = json.loads(r.extracted_content)
                except (json.JSONDecodeError, TypeError):
                    response["llm_result"] = {"raw": r.extracted_content}

            formatted_results.append(response)

        return formatted_results

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
