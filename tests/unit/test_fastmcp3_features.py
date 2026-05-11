"""FastMCP 3.x 新特性测试 — 原生 timeout / tags / streamable-http / Context 注入

TDD 红阶段：验证当前代码缺少这些 3.x 特性
"""

import asyncio
import inspect

import pytest

from crawl4ai_mcp.fastmcp_server import mcp


def _get_tool(name: str):
    tools = asyncio.run(mcp.list_tools())
    for t in tools:
        if t.name == name:
            return t
    raise AssertionError(f"Tool '{name}' not found")


# ============================================================
# P0-1: 原生 @mcp.tool(timeout=N) 装饰器
# ============================================================


class TestNativeToolTimeout:
    """验证每个工具通过原生装饰器配置了 timeout"""

    # 基于 benchmark P95 数据 × 3x 安全倍数校准的超时值（秒）
    EXPECTED_TIMEOUTS = {
        "extract_url": 15,
        "crawl_single": 120,
        "crawl_site": 300,
        "crawl_batch": 300,
        "search_text": 30,
        "search_news": 20,
        "search_books": 20,
        "search_videos": 20,
        "search_images": 30,
    }

    @pytest.mark.parametrize("tool_name,expected", list(EXPECTED_TIMEOUTS.items()))
    def test_tool_has_native_timeout(self, tool_name, expected):
        """每个工具应通过 @mcp.tool(timeout=N) 配置原生超时"""
        tool = _get_tool(tool_name)
        assert tool.timeout == expected, (
            f"{tool_name}: expected timeout={expected}s, got {tool.timeout}"
        )

    def test_no_tool_has_none_timeout(self):
        """所有工具都不应有 None timeout"""
        tools = asyncio.run(mcp.list_tools())
        none_timeout = [t.name for t in tools if t.timeout is None]
        assert not none_timeout, f"以下工具缺少原生 timeout: {none_timeout}"


# ============================================================
# P1-3: 工具标签 tags 分组
# ============================================================


class TestToolTags:
    """验证工具按功能分组添加了 tags"""

    CRAWL_TOOLS = {"crawl_single", "crawl_batch", "crawl_site"}
    SEARCH_TOOLS = {
        "extract_url",
        "search_text",
        "search_news",
        "search_books",
        "search_videos",
        "search_images",
    }

    @pytest.mark.parametrize("tool_name", list(CRAWL_TOOLS))
    def test_crawl_tools_have_crawl_tag(self, tool_name):
        """爬取类工具应有 tags={'crawl'}"""
        tool = _get_tool(tool_name)
        assert tool.tags is not None, f"{tool_name}: tags is None"
        assert "crawl" in tool.tags, f"{tool_name}: expected 'crawl' in {tool.tags}"

    @pytest.mark.parametrize("tool_name", list(SEARCH_TOOLS))
    def test_search_tools_have_search_tag(self, tool_name):
        """搜索类工具应有 tags={'search'}"""
        tool = _get_tool(tool_name)
        assert tool.tags is not None, f"{tool_name}: tags is None"
        assert "search" in tool.tags, f"{tool_name}: expected 'search' in {tool.tags}"


# ============================================================
# P1-4: 长耗时工具注入 Context 进度报告
# ============================================================


class TestContextInjection:
    """验证长耗时工具支持 ctx: Context 参数注入"""

    LONG_RUNNING_TOOLS = ["crawl_batch", "crawl_site"]

    @pytest.mark.parametrize("tool_name", LONG_RUNNING_TOOLS)
    def test_long_running_tool_accepts_context(self, tool_name):
        """长耗时工具函数签名应包含 ctx 参数（用于进度报告）"""
        tool = _get_tool(tool_name)
        sig = inspect.signature(tool.fn)
        assert "ctx" in sig.parameters, (
            f"{tool_name}: 缺少 ctx 参数，无法使用 report_progress()"
        )


# ============================================================
# P0-2: streamable-http 传输协议
# ============================================================


class TestStreamableHttpTransport:
    """验证服务器支持 streamable-http 传输协议"""

    def test_main_function_uses_streamable_http(self):
        """main() 函数的 HTTP 模式应使用 streamable-http 而非 http"""
        from crawl4ai_mcp.fastmcp_server import main
        import inspect

        source = inspect.getsource(main)
        # 不应出现旧的 transport="http"
        assert 'transport="http"' not in source, (
            "仍使用旧版 http 传输协议，应升级为 streamable-http"
        )
        # 应包含 streamable-http
        assert "streamable-http" in source, "未使用 streamable-http 传输协议"
