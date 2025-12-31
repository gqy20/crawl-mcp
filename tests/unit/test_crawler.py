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


class TestCrawlerBatchLLMIntegration:
    """测试批量爬取的 LLM 后处理功能"""

    @pytest.mark.asyncio
    async def test_crawl_batch_with_llm_config(self):
        """测试带 LLM 配置的批量爬取 - 新设计：先爬取后处理"""
        # Arrange
        crawler = Crawler()
        urls = ["https://example.com/page1", "https://example.com/page2"]
        llm_config = {"instruction": "提取标题"}

        # Act - Mock _call_llm 来测试 LLM 后处理逻辑
        with patch.object(crawler, '_call_llm') as mock_llm:
            # 模拟 LLM 返回结构化数据
            mock_llm.side_effect = [
                {"success": True, "data": {"title": "Page 1"}},
                {"success": True, "data": {"title": "Page 2"}},
            ]

            # 同时需要 mock 底层爬取，避免实际网络请求
            mock_results = [
                MagicMock(success=True, markdown=MagicMock(raw_markdown="# Page 1\n\nContent 1"), metadata={'title': 'Page 1'}),
                MagicMock(success=True, markdown=MagicMock(raw_markdown="# Page 2\n\nContent 2"), metadata={'title': 'Page 2'}),
            ]

            async def mock_arun_many(*args, **kwargs):
                return mock_results

            with patch('crawl4ai_mcp.crawler.AsyncWebCrawler') as mock_crawler_class:
                mock_crawler = MagicMock()
                mock_crawler.arun_many = mock_arun_many
                mock_crawler_class.return_value.__aenter__.return_value = mock_crawler

                results = crawler.crawl_batch(urls, llm_config=llm_config)

        # Assert
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[0]["markdown"] == "# Page 1\n\nContent 1"  # 原始 Markdown
        assert results[0]["llm_data"]["title"] == "Page 1"  # LLM 处理结果
        assert results[1]["llm_data"]["title"] == "Page 2"
        # 验证 _call_llm 被调用了两次（每个成功页面一次）
        assert mock_llm.call_count == 2
