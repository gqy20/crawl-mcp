"""TimeoutMiddleware 单元测试 — TDD 红阶段"""

import asyncio
import time

import pytest
from fastmcp.server.middleware.middleware import MiddlewareContext
from mcp.types import CallToolRequestParams

from crawl4ai_mcp.middleware.timeout import TimeoutMiddleware


def _make_call_tool_context(
    tool_name: str, arguments: dict | None = None
) -> MiddlewareContext[CallToolRequestParams]:
    """构造 tools/call 请求上下文（包装为 MiddlewareContext）"""
    return MiddlewareContext(
        message=CallToolRequestParams(
            name=tool_name,
            arguments=arguments or {},
        ),
    )


class TestTimeoutMiddlewareBasic:
    """基础行为测试"""

    def test_slow_tool_times_out(self):
        """超过超时限制的工具调用应被取消"""
        middleware = TimeoutMiddleware(default_timeout=1)

        async def slow_tool(context):
            await asyncio.sleep(10)
            return "should not reach here"

        context = _make_call_tool_context("slow_tool")

        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(middleware.on_call_tool(context, slow_tool))

    def test_fast_tool_completes_normally(self):
        """在超时限制内完成的工具应正常返回"""
        middleware = TimeoutMiddleware(default_timeout=5)

        async def fast_tool(context):
            await asyncio.sleep(0.1)
            return {"success": True}

        context = _make_call_tool_context("fast_tool")
        result = asyncio.run(middleware.on_call_tool(context, fast_tool))

        assert result == {"success": True}

    def test_zero_timeout_means_no_limit(self):
        """timeout=0 表示不设超时限制"""
        middleware = TimeoutMiddleware(default_timeout=0)

        async def normal_tool(context):
            await asyncio.sleep(0.2)
            return "ok"

        context = _make_call_tool_context("normal_tool")
        result = asyncio.run(middleware.on_call_tool(context, normal_tool))

        assert result == "ok"

    def test_negative_timeout_means_no_limit(self):
        """timeout<0 表示不设超时限制"""
        middleware = TimeoutMiddleware(default_timeout=-1)

        async def normal_tool(context):
            return "ok"

        context = _make_call_tool_context("normal_tool")
        result = asyncio.run(middleware.on_call_tool(context, normal_tool))

        assert result == "ok"


class TestTimeoutMiddlewarePerTool:
    """按工具名配置不同超时"""

    def test_per_tool_timeout_overrides_default(self):
        """单个工具的超时配置覆盖默认值"""
        middleware = TimeoutMiddleware(
            default_timeout=10,
            per_tool={"extract_url": 1},
        )

        async def slow_extract(context):
            await asyncio.sleep(10)
            return "should not reach here"

        context = _make_call_tool_context("extract_url")

        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(middleware.on_call_tool(context, slow_extract))

    def test_other_tool_uses_default_timeout(self):
        """未单独配置的工具使用默认超时"""
        middleware = TimeoutMiddleware(
            default_timeout=5,
            per_tool={"extract_url": 1},
        )

        async def crawl_single(context):
            await asyncio.sleep(0.2)
            return {"markdown": "# Test"}

        context = _make_call_tool_context("crawl_single")
        result = asyncio.run(middleware.on_call_tool(context, crawl_single))

        assert result["markdown"] == "# Test"

    def test_unknown_tool_uses_default_timeout(self):
        """不在 per_tool 配置中的工具使用默认超时"""
        middleware = TimeoutMiddleware(
            default_timeout=1,
            per_tool={"extract_url": 30},
        )

        async def unknown_tool(context):
            await asyncio.sleep(10)
            return "should not reach here"

        context = _make_call_tool_context("unknown_tool")

        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(middleware.on_call_tool(context, unknown_tool))


class TestTimeoutMiddlewareEdgeCases:
    """边界情况测试"""

    def test_sync_tool_also_respects_timeout(self):
        """同步阻塞工具也应受超时控制（通过线程池执行）"""
        middleware = TimeoutMiddleware(default_timeout=1)

        def blocking_sync():
            time.sleep(10)
            return "should not reach here"

        async def sync_wrapper(context):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, blocking_sync)

        context = _make_call_tool_context("blocking_tool")

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            asyncio.run(middleware.on_call_tool(context, sync_wrapper))

    def test_exception_propagates_without_timeout(self):
        """工具本身的异常应在超时前正常抛出"""
        middleware = TimeoutMiddleware(default_timeout=10)

        async def failing_tool(context):
            raise ValueError("tool error")

        context = _make_call_tool_context("failing_tool")

        with pytest.raises(ValueError, match="tool error"):
            asyncio.run(middleware.on_call_tool(context, failing_tool))

    def test_exact_timeout_boundary(self):
        """恰好在超时边界完成的工具应正常返回"""
        middleware = TimeoutMiddleware(default_timeout=2)

        async def boundary_tool(context):
            await asyncio.sleep(1.5)
            return "just in time"

        context = _make_call_tool_context("boundary_tool")
        result = asyncio.run(middleware.on_call_tool(context, boundary_tool))

        assert result == "just in time"


class TestTimeoutMiddlewareIntegration:
    """与 FastMCP 集成测试"""

    def test_middleware_registered_on_server(self):
        """中间件可以正确注册到 FastMCP 实例"""
        from crawl4ai_mcp.fastmcp_server import mcp

        middleware = TimeoutMiddleware(default_timeout=30)
        mcp.add_middleware(middleware)

        assert middleware in mcp.middleware

    def test_server_has_timeout_middleware_with_extract_url_config(self):
        """服务器预配置了 extract_url 的短超时（15s）"""
        from crawl4ai_mcp.fastmcp_server import mcp

        timeout_mw = None
        for mw in mcp.middleware:
            if isinstance(mw, TimeoutMiddleware):
                timeout_mw = mw
                break

        assert timeout_mw is not None
        assert timeout_mw.per_tool.get("extract_url") == 15
        assert timeout_mw.per_tool.get("crawl_single") == 120

    def test_server_default_timeout_is_60s(self):
        """服务器默认超时为 60 秒"""
        from crawl4ai_mcp.fastmcp_server import mcp

        timeout_mw = next(
            (mw for mw in mcp.middleware if isinstance(mw, TimeoutMiddleware)), None
        )
        assert timeout_mw is not None
        assert timeout_mw.default_timeout == 60
