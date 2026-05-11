"""FastMCP 服务器单元测试 — 全工具注册 + 函数行为验证"""

import asyncio
import inspect

import pytest
from unittest.mock import patch
from crawl4ai_mcp.fastmcp_server import mcp


def _get_tool(name: str):
    tools = asyncio.run(mcp.list_tools())
    for t in tools:
        if t.name == name:
            return t
    raise AssertionError(f"Tool '{name}' not found")


def _get_tool_names() -> list[str]:
    return [t.name for t in asyncio.run(mcp.list_tools())]


class TestAllToolsRegistered:
    """验证全部 9 个工具已注册"""

    def test_all_expected_tools_present(self):
        expected = {
            "extract_url",
            "crawl_single",
            "crawl_site",
            "crawl_batch",
            "search_text",
            "search_news",
            "search_books",
            "search_videos",
            "search_images",
        }
        actual = set(_get_tool_names())
        missing = expected - actual
        assert not missing, f"Missing tools: {missing}"

    def test_no_extra_tools(self):
        expected = {
            "extract_url",
            "crawl_single",
            "crawl_site",
            "crawl_batch",
            "search_text",
            "search_news",
            "search_books",
            "search_videos",
            "search_images",
        }
        actual = set(_get_tool_names())
        extra = actual - expected
        assert not extra, f"Unexpected tools: {extra}"


class TestCrawlToolSchemas:
    """爬取类工具参数 schema 验证"""

    def test_crawl_single_has_url_enhanced_llm_config(self):
        tool = _get_tool("crawl_single")
        sig = inspect.signature(tool.fn)
        for param in ("url", "enhanced", "llm_config"):
            assert param in sig.parameters

    def test_crawl_site_has_depth_pages_concurrent(self):
        tool = _get_tool("crawl_site")
        sig = inspect.signature(tool.fn)
        for param in ("url", "depth", "pages", "concurrent", "llm_config"):
            assert param in sig.parameters

    def test_crawl_batch_has_urls_concurrent_llm(self):
        tool = _get_tool("crawl_batch")
        sig = inspect.signature(tool.fn)
        for param in ("urls", "concurrent", "llm_config", "llm_concurrent"):
            assert param in sig.parameters


class TestSearchToolSchemas:
    """搜索类工具参数 schema 验证"""

    def test_extract_url_has_url_and_fmt(self):
        tool = _get_tool("extract_url")
        sig = inspect.signature(tool.fn)
        assert "url" in sig.parameters
        assert "fmt" in sig.parameters

    def test_search_text_has_query_and_max_results(self):
        tool = _get_tool("search_text")
        sig = inspect.signature(tool.fn)
        assert "query" in sig.parameters
        assert "max_results" in sig.parameters

    def test_search_images_has_download_and_analyze(self):
        tool = _get_tool("search_images")
        sig = inspect.signature(tool.fn)
        for param in ("query", "download", "analyze", "analysis_prompt"):
            assert param in sig.parameters


class TestCrawlToolFunctions:
    """爬取工具函数行为验证"""

    @pytest.mark.asyncio
    async def test_crawl_single_returns_result(self):
        from crawl4ai_mcp.fastmcp_server import _crawler

        async def mock(url, enhanced, llm_config=None):
            return {"success": True, "markdown": "# T", "title": "T"}

        with patch.object(_crawler, "crawl_single", side_effect=mock):
            result = await _get_tool("crawl_single").fn("https://example.com")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_crawl_site_returns_stats(self):
        from crawl4ai_mcp.fastmcp_server import _crawler

        async def mock(url, depth, pages, concurrent):
            return {"successful_pages": 3, "total_pages": 5, "success_rate": "60%"}

        with patch.object(_crawler, "crawl_site", side_effect=mock):
            result = await _get_tool("crawl_site").fn("https://example.com")
        assert result["successful_pages"] == 3

    @pytest.mark.asyncio
    async def test_crawl_batch_returns_list(self):
        from crawl4ai_mcp.fastmcp_server import _crawler

        async def mock(urls, concurrent, llm_config=None, llm_concurrent=3):
            return [{"success": True, "markdown": "# A"}]

        with patch.object(_crawler, "crawl_batch", side_effect=mock):
            result = await _get_tool("crawl_batch").fn(["https://a.com"])
        assert len(result) == 1


class TestSearchToolFunctions:
    """搜索工具函数行为验证"""

    def test_extract_url_returns_content(self):
        from crawl4ai_mcp.fastmcp_server import _searcher

        with patch.object(
            _searcher,
            "extract_url",
            return_value={
                "success": True,
                "content": "<h1>Hi</h1>",
                "fmt": "text_markdown",
            },
        ):
            result = _get_tool("extract_url").fn("https://example.com")
        assert result["content"] == "<h1>Hi</h1>"

    def test_search_text_returns_results(self):
        from crawl4ai_mcp.fastmcp_server import _searcher

        with patch.object(
            _searcher,
            "search_text",
            return_value={"success": True, "count": 2, "results": []},
        ):
            result = _get_tool("search_text").fn("python")
        assert result["count"] == 2

    def test_search_images_returns_search_results(self):
        from crawl4ai_mcp.fastmcp_server import _searcher

        mock_val = {
            "success": True,
            "query": "cat",
            "search_results": {"count": 0, "results": []},
        }
        with patch.object(_searcher, "search_images", return_value=mock_val):
            result = _get_tool("search_images").fn("cat")
        assert "search_results" in result
