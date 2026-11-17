"""crawl_mcp: 基于 crawl4ai 和 FastMCP 的 MCP 服务器"""

from importlib import import_module
from importlib.metadata import version as _get_version

# 懒导出（PEP 562）：import 包本身不连带 crawl4ai/fastmcp 等重依赖，
# 只有实际访问某个导出名时才加载对应模块。公开 API 不变。
_LAZY_EXPORTS = {
    "Crawler": "crawl4ai_mcp.crawler",
    "Searcher": "crawl4ai_mcp.searcher",
    "mcp": "crawl4ai_mcp.fastmcp_server",
    "LLMConfig": "crawl4ai_mcp.llm_config",
    "get_llm_config": "crawl4ai_mcp.llm_config",
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        return getattr(import_module(_LAZY_EXPORTS[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


try:
    __version__ = _get_version("crawl_mcp")
except Exception:
    __version__ = "0.0.0"
__all__ = ["Crawler", "LLMConfig", "Searcher", "get_llm_config", "mcp"]
