"""FastMCP 服务器单元测试 — 全工具注册 + 函数行为验证"""

import asyncio
import inspect
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

    def test_crawl_single_has_selector_and_full_page_params(self):
        tool = _get_tool("crawl_single")
        sig = inspect.signature(tool.fn)
        for param in ("css_selector", "excluded_selector", "scan_full_page"):
            assert param in sig.parameters
        # 参数描述要说清「只在浏览器路径生效」，避免调用方以为 fast 路径也吃选择器
        props = tool.parameters["properties"]
        assert "浏览器路径" in props["css_selector"]["description"]
        assert "浏览器路径" in props["excluded_selector"]["description"]
        assert "浏览器路径" in props["scan_full_page"]["description"]

    def test_crawl_site_has_depth_pages_concurrent(self):
        tool = _get_tool("crawl_site")
        sig = inspect.signature(tool.fn)
        # crawl_site 已移除 llm_config 参数（整站爬取不支持 LLM 后处理）
        for param in ("url", "depth", "pages", "concurrent"):
            assert param in sig.parameters
        # 确认 llm_config 不在签名中
        assert "llm_config" not in sig.parameters

    def test_crawl_batch_has_urls_concurrent_llm(self):
        tool = _get_tool("crawl_batch")
        sig = inspect.signature(tool.fn)
        for param in ("urls", "concurrent", "llm_config", "llm_concurrent"):
            assert param in sig.parameters


class TestSearchToolSchemas:
    """搜索类工具参数 schema 验证"""

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


class TestToolDescriptions:
    """工具描述应给大模型足够的选择依据"""

    def test_crawl_single_description_explains_fast_and_enhanced_modes(self):
        desc = _get_tool("crawl_single").description

        assert "crawl_batch" in desc
        assert "crawl_site" in desc
        assert "prefer_fast=False" in desc
        assert "enhanced=True" in desc
        # enhanced 的剪枝语义、图片取舍、只作用于浏览器路径，都要向调用方说清
        assert "剪" in desc and "图片" in desc
        assert "只影响浏览器路径" in desc or "浏览器路径生效" in desc

    def test_crawl_batch_description_distinguishes_known_urls_from_site_crawl(self):
        desc = _get_tool("crawl_batch").description

        assert "一组明确 URL" in desc
        assert "crawl_single" in desc
        assert "crawl_site" in desc
        assert "prefer_fast=False" in desc

    def test_crawl_site_description_states_fast_first_and_no_llm(self):
        desc = _get_tool("crawl_site").description

        assert "发现链接" in desc
        assert "快速" in desc
        assert "不支持 LLM 后处理" in desc

    def test_search_descriptions_say_results_are_not_full_content(self):
        assert "不抓取页面正文" in _get_tool("search_text").description
        assert "不抓取全文" in _get_tool("search_news").description

    def test_search_images_description_lists_safesearch_and_timelimit(self):
        # FastMCP 把 docstring 的 Args 段拆进参数 schema，描述改查 schema
        props = _get_tool("search_images").parameters["properties"]

        assert props["safesearch"]["description"]
        assert props["timelimit"]["description"]


class TestCrawlToolFunctions:
    """爬取工具函数行为验证"""

    def test_crawl_single_returns_result(self):
        from crawl4ai_mcp.fastmcp_server import _crawler

        def mock(
            url,
            enhanced,
            llm_config=None,
            prefer_fast=True,
            min_content_length=200,
            css_selector=None,
            excluded_selector=None,
            scan_full_page=False,
        ):
            return {"success": True, "markdown": "# T", "title": "T"}

        with patch.object(_crawler, "crawl_single", side_effect=mock):
            result = _get_tool("crawl_single").fn("https://example.com")
        assert result["success"] is True

    def test_crawl_site_returns_stats(self):
        from crawl4ai_mcp.fastmcp_server import _crawler

        def mock(url, depth=2, pages=10, concurrent=3):
            return {"successful_pages": 3, "total_pages": 5, "success_rate": "60%"}

        with patch.object(_crawler, "crawl_site", side_effect=mock):
            result = _get_tool("crawl_site").fn("https://example.com")
        assert result["successful_pages"] == 3

    def test_crawl_batch_returns_list(self):
        from crawl4ai_mcp.fastmcp_server import _crawler

        def mock(
            urls,
            concurrent=3,
            llm_config=None,
            llm_concurrent=3,
            prefer_fast=True,
            min_content_length=200,
            css_selector=None,
            excluded_selector=None,
        ):
            return [{"success": True, "markdown": "# A"}]

        with patch.object(_crawler, "crawl_batch", side_effect=mock):
            result = _get_tool("crawl_batch").fn(["https://a.com"])
        assert len(result) == 1


class TestSearchToolFunctions:
    """搜索工具函数行为验证"""

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
