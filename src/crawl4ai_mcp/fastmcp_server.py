"""FastMCP 服务器实现"""

from typing import List, Dict, Any, Optional, Union
from fastmcp import FastMCP
from crawl4ai_mcp.crawler import Crawler

# 读取包版本
try:
    from importlib.metadata import version as get_version

    __version__ = get_version("crawl_mcp")
except Exception:
    __version__ = "0.1.1"

# 创建 FastMCP 实例
mcp = FastMCP(name="crawl-mcp", version=__version__)

# 创建爬虫实例（单例）
_crawler = Crawler()


@mcp.tool
def crawl_single(
    url: str,
    enhanced: bool = False,
    llm_config: Optional[Union[Dict[str, Any], str]] = None,
) -> Dict[str, Any]:
    """
    爬取单个网页，返回 Markdown 格式内容

    Args:
        url: 要爬取的网页 URL
        enhanced: 是否使用增强模式（适用于 SPA 网站，等待时间更长）
        llm_config: LLM 配置（可选），支持三种格式:
            - 字典: {"instruction": "总结", "schema": {...}}
            - JSON 字符串: '{"instruction": "总结"}'
            - 纯文本: "总结页面内容"（自动作为 instruction）

    Returns:
        包含 success, markdown, title, error, (可选) llm_result 的字典
    """
    return _crawler.crawl_single(url, enhanced, llm_config)


@mcp.tool
def crawl_site(
    url: str,
    depth: int = 2,
    pages: int = 10,
    concurrent: int = 3,
    llm_config: Optional[Union[Dict[str, Any], str]] = None,
) -> Dict[str, Any]:
    """
    递归爬取整个网站

    Args:
        url: 起始 URL
        depth: 最大爬取深度（默认：2）
        pages: 最大页面数（默认：10）
        concurrent: 并发请求数（默认：3）
        llm_config: LLM 配置（可选），格式同 crawl_single

    Returns:
        包含 successful_pages, total_pages, success_rate, results 的字典
    """
    return _crawler.crawl_site(url, depth, pages, concurrent)


@mcp.tool
def crawl_batch(
    urls: List[str],
    concurrent: int = 3,
    llm_config: Optional[Union[Dict[str, Any], str]] = None,
) -> List[Dict[str, Any]]:
    """
    批量爬取多个网页（异步并行）

    Args:
        urls: URL 列表
        concurrent: 并发请求数（默认：3）
        llm_config: LLM 配置（可选），格式同 crawl_single

    Returns:
        爬取结果列表
    """
    return _crawler.crawl_batch(urls, concurrent, llm_config)


def main():
    """CLI 入口点"""
    import sys

    # 默认使用 STDIO，但支持通过参数指定 HTTP
    if "--http" in sys.argv:
        mcp.run(transport="http", host="0.0.0.0", port=8001)
    else:
        mcp.run()


# CLI 入口点
if __name__ == "__main__":
    main()
