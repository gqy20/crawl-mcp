"""Crawler 类单元测试"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
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

        async def mock_crawl_impl(url, enhanced):
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
        mock_crawl.assert_called_once_with(url, False)

    @pytest.mark.asyncio
    async def test_crawl_single_with_enhanced_mode(self):
        """测试增强模式爬取"""
        # Arrange
        crawler = Crawler()
        url = "https://spa-example.com"

        async def mock_crawl_impl(url, enhanced):
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
        mock_crawl.assert_called_once_with(url, True)

    @pytest.mark.asyncio
    async def test_crawl_single_failure(self):
        """测试爬取失败"""
        # Arrange
        crawler = Crawler()
        url = "https://invalid-url-that-fails.com"

        async def mock_crawl_impl(url, enhanced):
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
        mock_crawl.assert_called_once_with(url, False, llm_config=llm_config)

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
        mock_crawl.assert_called_once_with(url, False, llm_config=None)

    @pytest.mark.asyncio
    async def test_crawl_batch_with_llm_config(self):
        """测试带 LLM 配置的批量爬取"""
        # Arrange
        crawler = Crawler()
        urls = ["https://example.com/page1"]
        llm_config = {"instruction": "Extract products"}

        mock_results = [
            {"success": True, "markdown": "Product info", "llm_result": {"products": []}}
        ]

        # Act
        with patch.object(crawler, '_crawl_batch', return_value=mock_results) as mock_batch:
            results = crawler.crawl_batch(urls, llm_config=llm_config)

        # Assert
        assert len(results) == 1
        assert "llm_result" in results[0]
        mock_batch.assert_called_once_with(urls, concurrent=3, llm_config=llm_config)
