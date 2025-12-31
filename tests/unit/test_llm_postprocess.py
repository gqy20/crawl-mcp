"""LLM 后处理功能测试 - 对已爬取的 Markdown 进行处理"""

import pytest
from unittest.mock import patch, MagicMock
from crawl4ai_mcp.crawler import Crawler


class TestLLMPostProcess:
    """测试 LLM 对 Markdown 的后处理功能"""

    def test_postprocess_markdown_with_instruction(self):
        """测试使用 instruction 对 Markdown 进行后处理"""
        # Arrange
        crawler = Crawler()
        markdown = "# Example\n\nThis is a test page with some content."
        instruction = "总结这个页面"

        mock_llm_response = {
            "success": True,
            "summary": "这是一个测试页面，包含一些内容。"
        }

        # Act
        with patch.object(crawler, '_call_llm', return_value=mock_llm_response) as mock_llm:
            result = crawler.postprocess_markdown(markdown, instruction)

        # Assert
        assert result["success"] is True
        assert "summary" in result
        assert result["summary"] == "这是一个测试页面，包含一些内容。"
        mock_llm.assert_called_once()

    def test_postprocess_markdown_with_schema(self):
        """测试使用 schema 提取结构化数据"""
        # Arrange
        crawler = Crawler()
        markdown = "Product: iPhone 15, Price: $999"
        instruction = "提取产品信息"
        schema = {
            "type": "object",
            "properties": {
                "product": {"type": "string"},
                "price": {"type": "string"}
            }
        }

        mock_llm_response = {
            "success": True,
            "data": {"product": "iPhone 15", "price": "$999"}
        }

        # Act
        with patch.object(crawler, '_call_llm', return_value=mock_llm_response):
            result = crawler.postprocess_markdown(markdown, instruction, schema)

        # Assert
        assert result["success"] is True
        assert "data" in result
        assert result["data"]["product"] == "iPhone 15"
        assert result["data"]["price"] == "$999"

    def test_postprocess_markdown_empty_instruction(self):
        """测试空 instruction 应该返回原 Markdown"""
        # Arrange
        crawler = Crawler()
        markdown = "# Example\n\nContent"

        # Act
        result = crawler.postprocess_markdown(markdown, "")

        # Assert
        assert result["success"] is True
        assert result["original_markdown"] == markdown

    def test_postprocess_markdown_none_instruction(self):
        """测试 None instruction 应该返回原 Markdown"""
        # Arrange
        crawler = Crawler()
        markdown = "# Example\n\nContent"

        # Act
        result = crawler.postprocess_markdown(markdown, None)

        # Assert
        assert result["success"] is True
        assert result["original_markdown"] == markdown


class TestCrawlSingleWithPostProcess:
    """测试 crawl_single 与 LLM 后处理的组合"""

    @pytest.mark.asyncio
    async def test_crawl_single_without_llm_is_fast(self):
        """测试不使用 LLM 时，crawl_single 快速返回"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"

        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": True,
                "markdown": "# Example\n\nContent",
                "title": "Example",
                "error": None
            }

        # Act
        with patch.object(crawler, '_crawl', side_effect=mock_crawl_impl) as mock_crawl:
            result = crawler.crawl_single(url, enhanced=False, llm_config=None)

        # Assert
        assert result["success"] is True
        assert "markdown" in result
        # 验证没有调用 LLM（因为 llm_config=None）

    @pytest.mark.asyncio
    async def test_crawl_single_with_llm_string_does_postprocess(self):
        """测试使用字符串 llm_config 时，先爬取后处理"""
        # Arrange
        crawler = Crawler()
        url = "https://example.com"
        markdown_content = "# Example\n\nPage content here"

        # Mock _crawl 返回纯爬取结果
        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": True,
                "markdown": markdown_content,
                "title": "Example",
                "error": None
            }

        # Mock postprocess_markdown 返回 LLM 处理结果
        mock_llm_result = {
            "success": True,
            "summary": "Page summary"
        }

        # Act
        with patch.object(crawler, '_crawl', side_effect=mock_crawl_impl) as mock_crawl, \
             patch.object(crawler, 'postprocess_markdown', return_value=mock_llm_result) as mock_post:
            result = crawler.crawl_single(url, llm_config="总结页面")

        # Assert
        assert result["success"] is True
        assert result["markdown"] == markdown_content  # 原始 Markdown
        assert result["llm_summary"] == "Page summary"  # LLM 处理结果
        mock_crawl.assert_called_once()  # _crawl 被调用
        mock_post.assert_called_once_with(markdown_content, "总结页面", None)
