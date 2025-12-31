"""Crawler 类单元测试"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, call
from crawl4ai_mcp.crawler import Crawler
from crawl4ai_mcp.llm_config import LLMConfig


class TestCrawlerSingle:
    """测试单页爬取功能"""

    @pytest.mark.asyncio
    async def test_crawl_single_success(self):
        """测试成功爬取单个页面"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"

        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": True,
                "markdown": "# Example\n\nContent here",
                "title": "Example Domain",
                "error": None
            }

        # Act
        with patch.object(crawler, '_crawl', side_effect=mock_crawl_impl) as mock_crawl:
            result = crawler.crawl_single(url, enhanced=False)

        # Assert
        assert result["success"] is True
        assert result["markdown"] == "# Example\n\nContent here"
        assert result["title"] == "Example Domain"

    @pytest.mark.asyncio
    async def test_crawl_single_with_enhanced_mode(self):
        """测试增强模式爬取"""
        # Arrange
        crawler = Crawler()
        url = "https://spa-example.com"

        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": True,
                "markdown": "# SPA Content",
                "title": "SPA Page",
                "error": None
            }

        # Act
        with patch.object(crawler, '_crawl', side_effect=mock_crawl_impl) as mock_crawl:
            result = crawler.crawl_single(url, enhanced=True)

        # Assert
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_crawl_single_failure(self):
        """测试爬取失败"""
        # Arrange
        crawler = Crawler()
        url = "https://invalid-url-that-fails.com"

        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": False,
                "markdown": "",
                "title": "",
                "error": "Connection failed"
            }

        # Act
        with patch.object(crawler, '_crawl', side_effect=mock_crawl_impl):
            result = crawler.crawl_single(url, enhanced=False)

        # Assert
        assert result["success"] is False


class TestCrawlerSite:
    """测试整站爬取功能"""

    @pytest.mark.asyncio
    async def test_crawl_site_with_defaults(self):
        """测试使用默认参数爬取网站"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"

        mock_stats = {
            "successful_pages": 5,
            "total_pages": 5,
            "success_rate": "100%"
        }

        # Act
        with patch.object(crawler, '_crawl_site', return_value=mock_stats):
            result = crawler.crawl_site(url, depth=2, pages=10, concurrent=3)

        # Assert
        assert result["successful_pages"] == 5

    @pytest.mark.asyncio
    async def test_crawl_site_with_custom_params(self):
        """测试自定义参数爬取网站"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"

        mock_stats = {
            "successful_pages": 20,
            "total_pages": 20,
            "success_rate": "100%"
        }

        # Act
        with patch.object(crawler, '_crawl_site', return_value=mock_stats) as mock_crawl:
            result = crawler.crawl_site(url, depth=3, pages=50, concurrent=5)

        # Assert
        assert result["successful_pages"] == 20
        mock_crawl.assert_called_once_with(url, depth=3, pages=50, concurrent=5)


class TestCrawlerBatch:
    """测试批量爬取功能"""

    @pytest.mark.asyncio
    async def test_crawl_batch_multiple_urls(self):
        """测试批量爬取多个URL"""
        # Arrange
        crawler = Crawler()
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3"
        ]

        mock_results = [
            {"success": True, "markdown": "Content 1"},
            {"success": True, "markdown": "Content 2"},
            {"success": True, "markdown": "Content 3"}
        ]

        # Act
        with patch.object(crawler, '_crawl_batch', return_value=mock_results):
            results = crawler.crawl_batch(urls, concurrent=3)

        # Assert
        assert len(results) == 3
        assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_crawl_batch_empty_list(self):
        """测试空URL列表"""
        # Arrange
        crawler = Crawler()
        urls = []

        # Act
        results = crawler.crawl_batch(urls, concurrent=3)

        # Assert
        assert results == []


class TestCrawlerLLMIntegration:
    """测试 LLM 集成功能"""

    @pytest.mark.asyncio
    async def test_crawl_single_with_llm_config(self):
        """测试带 LLM 配置的单页爬取"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"
        llm_config = {
            "api_key": "sk-test",
            "model": "gpt-4o-mini",
            "instruction": "Summarize this page"
        }

        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": True,
                "markdown": "# Summary\n\nThis is a summary",
                "title": "Example Domain",
                "error": None,
                "llm_result": {"summary": "Page summary"}
            }

        # Act
        with patch.object(crawler, '_crawl', side_effect=mock_crawl_impl) as mock_crawl:
            result = crawler.crawl_single(url, enhanced=False, llm_config=llm_config)

        # Assert
        assert result["success"] is True
        assert result["llm_result"] == {"summary": "Page summary"}
        # 验证调用参数（位置参数）
        assert mock_crawl.call_args[0] == (url, False, llm_config)

    @pytest.mark.asyncio
    async def test_crawl_single_without_llm_config(self):
        """测试不带 LLM 配置的单页爬取"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"

        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": True,
                "markdown": "# Content\n\nRaw content",
                "title": "Example Domain",
                "error": None
            }

        # Act
        with patch.object(crawler, '_crawl', side_effect=mock_crawl_impl) as mock_crawl:
            result = crawler.crawl_single(url)

        # Assert
        assert result["success"] is True
        assert "llm_result" not in result
        # 验证调用参数（位置参数）
        assert mock_crawl.call_args[0] == (url, False, None)

    @pytest.mark.asyncio
    async def test_crawl_batch_with_llm_config(self):
        """测试带 LLM 配置的批量爬取"""
        # Arrange
        crawler = Crawler()
        urls = ["https://example.com/page1"]
        llm_config = {"instruction": "Extract products"}

        async def mock_batch_impl(urls, concurrent=3, llm_config=None):
            return [
                {"success": True, "markdown": "Product info", "llm_result": {"products": []}}
            ]

        # Act
        with patch.object(crawler, '_crawl_batch', side_effect=mock_batch_impl) as mock_batch:
            results = crawler.crawl_batch(urls, llm_config=llm_config)

        # Assert
        assert len(results) == 1
        assert "llm_result" in results[0]
        # 验证 _crawl_batch 被调用，且参数包含 llm_config
        assert mock_batch.called
        assert mock_batch.call_args.kwargs.get("llm_config") == llm_config


class TestCrawlerRetryMechanism:
    """测试网络错误重试机制"""

    @pytest.mark.asyncio
    async def test_retry_on_network_changed_error(self):
        """测试遇到 ERR_NETWORK_CHANGED 时自动重试"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"
        call_count = 0

        async def mock_arun(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Failed on navigating ACS-GOTO: net::ERR_NETWORK_CHANGED")
            # 第二次成功
            result = MagicMock()
            result.success = True
            result.markdown.raw_markdown = "# Success"
            result.metadata = {"title": "Test"}
            result.error_message = None
            result.extracted_content = None
            return result

        # Act
        with patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = MagicMock()
            mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
            mock_crawler.__aexit__ = AsyncMock(return_value=None)
            mock_crawler.arun = mock_arun
            mock_crawler_class.return_value = mock_crawler

            result = crawler.crawl_single(url)

        # Assert
        assert result["success"] is True
        assert call_count == 2  # 失败1次，重试成功

    @pytest.mark.asyncio
    async def test_no_retry_on_other_errors(self):
        """测试非网络错误不重试"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"
        call_count = 0

        async def mock_arun(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ValueError("Some other error")

        # Act & Assert
        with patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = MagicMock()
            mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
            mock_crawler.__aexit__ = AsyncMock(return_value=None)
            mock_crawler.arun = mock_arun
            mock_crawler_class.return_value = mock_crawler

            with pytest.raises(ValueError, match="Some other error"):
                crawler.crawl_single(url)

        # 只调用一次，没有重试
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_exhausted_gives_up(self):
        """测试重试次数用尽后放弃"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"
        call_count = 0

        async def mock_arun(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("net::ERR_NETWORK_CHANGED")

        # Act & Assert
        with patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_crawler_class:
            mock_crawler = MagicMock()
            mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
            mock_crawler.__aexit__ = AsyncMock(return_value=None)
            mock_crawler.arun = mock_arun
            mock_crawler_class.return_value = mock_crawler

            with pytest.raises(RuntimeError, match="ERR_NETWORK_CHANGED"):
                crawler.crawl_single(url)

        # 重试3次，共4次调用
        assert call_count == 4
