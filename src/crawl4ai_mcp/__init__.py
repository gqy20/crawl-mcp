"""crawl_mcp: 基于 crawl4ai 和 FastMCP 的 MCP 服务器"""

from importlib.metadata import version as _get_version

from crawl4ai_mcp.crawler import Crawler
from crawl4ai_mcp.fastmcp_server import mcp
from crawl4ai_mcp.llm_config import LLMConfig, get_llm_config
from crawl4ai_mcp.searcher import Searcher

try:
    __version__ = _get_version("crawl_mcp")
except Exception:
    __version__ = "0.0.0"
__all__ = ["Crawler", "mcp", "LLMConfig", "get_llm_config", "Searcher"]
