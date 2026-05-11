"""TimeoutMiddleware — 基于 FastMCP 中间件体系的工具级超时控制"""

import asyncio
import logging
from typing import Any

from fastmcp.server.middleware.middleware import (
    CallNext,
    Middleware,
    MiddlewareContext,
)

logger = logging.getLogger(__name__)


class TimeoutMiddleware(Middleware):
    """工具调用超时控制中间件。

    遵循 FastMCP 中间件设计模式（与 TimingMiddleware / ErrorHandlingMiddleware 同构），
    通过 on_call_tool 钩子对每个工具调用施加超时限制。

    超时后抛出 asyncio.TimeoutError，可被上游 ErrorHandlingMiddleware 自动转换为 McpError。

    Example:
        mcp = FastMCP("my-server")
        mcp.add_middleware(TimeoutMiddleware(
            default_timeout=30,
            per_tool={"extract_url": 15, "crawl_single": 120},
        ))
    """

    def __init__(
        self,
        default_timeout: float = 30,
        per_tool: dict[str, float] | None = None,
    ):
        self.default_timeout = default_timeout
        self.per_tool = per_tool or {}

    def _get_timeout(self, tool_name: str) -> float:
        return self.per_tool.get(tool_name, self.default_timeout)

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        tool_name = context.message.name
        timeout = self._get_timeout(tool_name)

        if timeout <= 0:
            return await call_next(context)

        try:
            return await asyncio.wait_for(call_next(context), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Tool '%s' timed out after %.1fs", tool_name, timeout)
            raise
