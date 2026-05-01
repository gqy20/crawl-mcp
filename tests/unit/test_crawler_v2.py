"""Crawler v2 升级后测试 — TDD 红阶段

覆盖范围：
- 公共工具函数 (_run_async 提取到 utils)
- Crawler 核心爬取（两阶段架构）
- 浏览器实例复用（重试时复用）
- 批量爬取 + LLM 后处理
- 整站深度爬取（BFSDeepCrawlStrategy + arun）
- 无死代码验证
- Searcher 使用公共 utils
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ============================================================
# 1. 公共 _run_async 工具函数
# ============================================================


class TestRunAsyncUtility:
    """测试提取到公共模块的 _run_async"""

    def test_run_async_creates_new_loop_when_none(self):
        """没有事件循环时应创建新的"""
        from crawl4ai_mcp.utils import run_async

        async def dummy():
            return "ok"

        result = run_async(dummy())
        assert result == "ok"

    def test_run_async_handles_existing_loop(self):
        """已有事件循环时应使用 nest_asyncio"""
        from crawl4ai_mcp.utils import run_async

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:

            async def inner():
                return "nested_ok"

            result = run_async(inner())
            assert result == "nested_ok"
        finally:
            loop.close()
            asyncio.set_event_loop(None)


# ============================================================
# 2. crawl_single — 两阶段架构
# ============================================================


class TestCrawlSingleTwoPhase:
    """测试单页爬取的两阶段设计：先爬取，再可选 LLM 后处理"""

    @pytest.mark.asyncio
    async def test_crawl_single_returns_markdown_without_llm(self):
        """不传 llm_config 时只返回原始 Markdown"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="# Hello\n\nWorld"),
            metadata={"title": "Test"},
        )

        with patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls:
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = mock_result
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single("https://example.com")

        assert result["success"] is True
        assert result["markdown"] == "# Hello\n\nWorld"
        assert result["title"] == "Test"
        assert "llm_summary" not in result
        assert "llm_data" not in result

    @pytest.mark.asyncio
    async def test_crawl_single_with_llm_postprocess(self):
        """传 llm_config 时执行两阶段：爬取 + LLM 后处理"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="# Article\n\nLong content..."),
            metadata={"title": "Article"},
        )

        with (
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
            patch.object(
                crawler,
                "_postprocess_with_llm",
                return_value={"success": True, "summary": "Summary text"},
            ) as mock_llm,
        ):
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = mock_result
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single(
                "https://example.com",
                llm_config={"instruction": "Summarize this"},
            )

            assert result["success"] is True
            assert result["markdown"] == "# Article\n\nLong content..."
            assert result["llm_summary"] == "Summary text"
            mock_llm.assert_called_once_with(
                "# Article\n\nLong content...", "Summarize this", None
            )

    @pytest.mark.asyncio
    async def test_crawl_single_llm_error_recorded(self):
        """LLM 失败时记录错误但不影响原始爬取结果"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="Content"),
            metadata={},
        )

        with (
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
            patch.object(
                crawler,
                "_postprocess_with_llm",
                return_value={"success": False, "error": "LLM failed"},
            ),
        ):
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = mock_result
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single(
                "https://example.com", llm_config={"instruction": "Summarize"}
            )

        assert result["success"] is True
        assert result["llm_error"] == "LLM failed"

    @pytest.mark.asyncio
    async def test_crawl_single_llm_skipped_when_crawl_fails(self):
        """爬取失败时不执行 LLM 后处理"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()

        with (
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
            patch.object(crawler, "_postprocess_with_llm") as mock_llm,
        ):
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = MagicMock(
                success=False,
                markdown=MagicMock(raw_markdown=""),
                metadata={},
                error_message="Timeout",
            )
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single(
                "https://example.com", llm_config={"instruction": "Summarize"}
            )

        assert result["success"] is False
        mock_llm.assert_not_called()


# ============================================================
# 3. 浏览器实例复用（重试优化）
# ============================================================


class TestBrowserReuse:
    """测试重试机制中浏览器实例的复用"""

    @pytest.mark.asyncio
    async def test_retry_reuses_browser_instance(self):
        """网络错误重试时应复用同一个 AsyncWebCrawler 实例"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        call_count = [0]

        def make_failing_then_success():
            async def _inner(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise Exception("ERR_NETWORK_CHANGED")
                return MagicMock(
                    success=True,
                    markdown=MagicMock(raw_markdown="Retry OK"),
                    metadata={"title": "OK"},
                )

            return _inner

        failing_then_success = make_failing_then_success()

        with patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.arun = failing_then_success
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            result = await crawler._crawl("https://example.com")

        assert result["success"] is True
        assert mock_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_non_network_error_does_not_retry(self):
        """非网络错误不应重试，直接抛出异常"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()

        with patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.arun.side_effect = ValueError("Bad URL")
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__.return_value = False  # 不抑制异常
            mock_cls.return_value = mock_cm

            with pytest.raises(ValueError, match="Bad URL"):
                await crawler._crawl("https://bad.url")


# ============================================================
# 4. crawl_batch — 并行爬取 + LLM 后处理
# ============================================================


class TestCrawlBatchV2:
    """测试批量爬取升级版"""

    @pytest.mark.asyncio
    async def test_batch_crawls_all_urls_in_parallel(self):
        """批量爬取应并行处理所有 URL"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        urls = ["https://a.com", "https://b.com", "https://c.com"]

        mock_results = [
            MagicMock(
                success=True,
                markdown=MagicMock(raw_markdown=f"Content {i}"),
                metadata={"title": f"Page {i}"},
            )
            for i in range(3)
        ]

        with patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.arun_many.return_value = mock_results
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            results = await crawler._crawl_batch(urls, concurrent=3)

        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert results[0]["markdown"] == "Content 0"
        mock_instance.arun_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_empty_urls_returns_empty(self):
        """空 URL 列表返回空结果"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        results = await crawler._crawl_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_with_llm_postprocess(self):
        """带 LLM 配置的批量爬取应对成功结果做并行 LLM 后处理"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        urls = ["https://a.com", "https://b.com"]

        mock_results = [
            MagicMock(
                success=True,
                markdown=MagicMock(raw_markdown=f"Data {i}"),
                metadata={"title": f"P{i}"},
            )
            for i in range(2)
        ]

        with (
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
            patch.object(
                crawler,
                "_postprocess_batch_with_llm",
                return_value=[
                    {"summary": "S0", "__index__": 0},
                    {"summary": "S1", "__index__": 1},
                ],
            ) as mock_llm,
        ):
            mock_instance = AsyncMock()
            mock_instance.arun_many.return_value = mock_results
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            results = await crawler._crawl_batch(
                urls,
                concurrent=2,
                llm_config={"instruction": "Summarize"},
                llm_concurrent=2,
            )

            assert len(results) == 2
            assert results[0]["llm_summary"] == "S0"
            assert results[1]["llm_summary"] == "S1"
            mock_llm.assert_called_once()


# ============================================================
# 5. crawl_site — 深度爬取（BFSDeepCrawlStrategy + arun）
# ============================================================


class TestCrawlSiteV2:
    """测试整站深度爬取 — 使用 BFSDeepCrawlStrategy + arun()"""

    @pytest.mark.asyncio
    async def test_crawl_site_uses_deep_crawl_strategy(self):
        """整站爬取应通过 config.deep_crawl_strategy 使用 BFSDeepCrawlStrategy"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="# Home\nContent"),
            metadata={"title": "Home Page"},
        )

        with (
            patch("crawl4ai_mcp.crawler.BFSDeepCrawlStrategy") as mock_strategy_cls,
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
        ):
            mock_strategy_cls.return_value = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.arun.return_value = mock_result
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            result = await crawler._crawl_site(
                "https://example.com", depth=2, pages=10, concurrent=3
            )

        mock_strategy_cls.assert_called_once()
        call_kwargs = (
            mock_strategy_cls.call_args[1] if mock_strategy_cls.call_args else {}
        )
        assert call_kwargs.get("max_depth") == 2
        assert call_kwargs.get("max_pages") == 10
        assert result["successful_pages"] == 1
        assert result["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_crawl_site_respects_page_limit(self):
        """整站爬取应通过 max_pages 限制页面数"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="Page content"),
            metadata={"title": "Page"},
        )

        with (
            patch("crawl4ai_mcp.crawler.BFSDeepCrawlStrategy") as mock_strategy_cls,
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
        ):
            mock_strategy_cls.return_value = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.arun.return_value = mock_result
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            result = await crawler._crawl_site(
                "https://example.com", depth=3, pages=5, concurrent=2
            )

        call_kwargs = (
            mock_strategy_cls.call_args[1] if mock_strategy_cls.call_args else {}
        )
        assert call_kwargs.get("max_pages") == 5
        assert result["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_crawl_site_handles_failure(self):
        """爬取失败时应返回错误信息"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=False,
            markdown=MagicMock(raw_markdown=""),
            error_message="Timeout",
            metadata={},
        )

        with (
            patch("crawl4ai_mcp.crawler.BFSDeepCrawlStrategy") as mock_strategy_cls,
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
        ):
            mock_strategy_cls.return_value = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.arun.return_value = mock_result
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            result = await crawler._crawl_site("https://example.com")

        assert result["successful_pages"] == 0
        assert result["total_pages"] == 1
        assert result["success_rate"] == "0.0%"


# ============================================================
# 6. 无死代码验证
# ============================================================


class TestNoDeadCode:
    """验证旧版死代码已被清理"""

    def test_no_add_llm_strategy_method(self):
        """_add_llm_strategy 方法不应存在"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        assert not hasattr(crawler, "_add_llm_strategy")

    def test_no_direct_llm_extraction_imports(self):
        """crawler.py 不应使用旧的 Crawl4AILLMConfig 别名"""
        import crawl4ai_mcp.crawler as crawler_module

        source = getattr(crawler_module, "__file__")
        if source:
            with open(source) as f:
                code = f.read()
            # 允许使用原生 LLMExtractionStrategy（复用设计）
            assert "from crawl4ai import LLMConfig as Crawl4AILLMConfig" not in code


# ============================================================
# 7. Searcher 使用公共 utils
# ============================================================


class TestSearcherUsesSharedUtils:
    """验证 Searcher 使用公共 _run_async 而非自实现"""

    def test_searcher_has_no_duplicate_run_async(self):
        """searcher.py 不应有自己的 _run_async 定义"""
        import crawl4ai_mcp.searcher as searcher_module

        source = getattr(searcher_module, "__file__")
        if source:
            with open(source) as f:
                code = f.read()
            assert "_run_async" not in code or "def _run_async" not in code
