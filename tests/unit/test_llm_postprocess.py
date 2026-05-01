"""LLM 后处理功能测试 - 对已爬取的 Markdown 进行处理"""

import pytest
from unittest.mock import patch, MagicMock
from crawl4ai_mcp.crawler import Crawler


class TestLLMPostProcess:
    """测试 LLM 对 Markdown 的后处理功能"""

    def test_postprocess_with_instruction(self):
        """测试使用 instruction 对 Markdown 进行后处理"""
        crawler = Crawler()
        markdown = "# Example\n\nThis is a test page with some content."
        instruction = "总结这个页面"

        mock_response = [
            {
                "index": 0,
                "tags": ["summary"],
                "content": ["这是一个测试页面"],
                "error": False,
            }
        ]

        with (
            patch("crawl4ai_mcp.crawler._build_llm_config", return_value=MagicMock()),
            patch("crawl4ai_mcp.crawler.LLMExtractionStrategy") as MockStrategy,
        ):
            mock_instance = MagicMock()
            mock_instance.extract.return_value = mock_response
            MockStrategy.return_value = mock_instance

            result = crawler._postprocess_with_llm(markdown, instruction)

        assert result["success"] is True
        assert "summary" in result
        assert "这是一个测试页面" in result["summary"]

    def test_postprocess_with_schema(self):
        """测试使用 schema 提取结构化数据"""
        crawler = Crawler()
        markdown = "Product: iPhone 15, Price: $999"
        instruction = "提取产品信息"
        schema = {
            "type": "object",
            "properties": {"product": {"type": "string"}, "price": {"type": "string"}},
        }

        mock_response = [{"product": "iPhone 15", "price": "$999", "error": False}]

        with (
            patch("crawl4ai_mcp.crawler._build_llm_config", return_value=MagicMock()),
            patch("crawl4ai_mcp.crawler.LLMExtractionStrategy") as MockStrategy,
        ):
            mock_instance = MagicMock()
            mock_instance.extract.return_value = mock_response
            MockStrategy.return_value = mock_instance

            result = crawler._postprocess_with_llm(markdown, instruction, schema)

        assert result["success"] is True
        assert "data" in result
        assert result["data"]["product"] == "iPhone 15"

    def test_postprocess_empty_instruction(self):
        """测试空 instruction 应该返回原 Markdown"""
        crawler = Crawler()
        markdown = "# Example\nContent"

        result = crawler._postprocess_with_llm(markdown, "")

        assert result["success"] is True
        assert result.get("skipped") is True

    def test_postprocess_none_instruction(self):
        """测试 None instruction 应该返回原 Markdown"""
        crawler = Crawler()
        markdown = "# Example\nContent"

        result = crawler._postprocess_with_llm(markdown, None)

        assert result["success"] is True
        assert result.get("skipped") is True


class TestCrawlSingleWithPostProcess:
    """测试 crawl_single 与 LLM 后处理的组合"""

    @pytest.mark.asyncio
    async def test_crawl_single_without_llm_is_fast(self):
        """测试不使用 LLM 时，crawl_single 快速返回"""
        crawler = Crawler()

        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": True,
                "markdown": "# Example\n\nContent",
                "title": "Example",
                "error": None,
            }

        with patch.object(crawler, "_crawl", side_effect=mock_crawl_impl):
            result = crawler.crawl_single("https://example.com")

        assert result["success"] is True
        assert "markdown" in result

    @pytest.mark.asyncio
    async def test_crawl_single_with_llm_string_does_postprocess(self):
        """测试使用字符串 llm_config 时，先爬取后处理"""
        crawler = Crawler()
        markdown_content = "# Example\n\nPage content here"

        async def mock_crawl_impl(url, enhanced, llm_config=None):
            return {
                "success": True,
                "markdown": markdown_content,
                "title": "Example",
                "error": None,
            }

        mock_llm_result = {"success": True, "summary": "Page summary"}

        with (
            patch.object(crawler, "_crawl", side_effect=mock_crawl_impl),
            patch.object(
                crawler, "_postprocess_with_llm", return_value=mock_llm_result
            ) as mock_post,
        ):
            result = crawler.crawl_single("https://example.com", llm_config="总结页面")

        assert result["success"] is True
        assert result["markdown"] == markdown_content
        assert result["llm_summary"] == "Page summary"
        mock_post.assert_called_once_with(markdown_content, "总结页面", None)
