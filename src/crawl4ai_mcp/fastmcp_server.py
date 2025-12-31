"""FastMCP 服务器实现"""

from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from crawl4ai_mcp.crawler import Crawler

# 创建 FastMCP 实例
mcp = FastMCP(name="crawl-mcp")

# 创建爬虫实例（单例）
_crawler = Crawler()


@mcp.tool
def crawl_single(
    url: str,
    enhanced: bool = False,
    llm_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    爬取单个网页，返回 Markdown 格式内容

    Args:
        url: 要爬取的网页 URL
        enhanced: 是否使用增强模式（适用于 SPA 网站）
        llm_config: LLM 配置（可选），支持:
            - api_key: API 密钥（默认从环境变量 OPENAI_API_KEY 获取）
            - base_url: API 基础 URL（默认: https://api.openai.com/v1）
            - model: 模型名称（默认: gpt-4o-mini）
            - instruction: 提示词
            - schema: JSON Schema 用于结构化提取

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
    llm_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    爬取整个网站，支持深度和页面数限制

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
    llm_config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    批量爬取多个网页

    Args:
        urls: URL 列表
        concurrent: 并发请求数（默认：3）
        llm_config: LLM 配置（可选），格式同 crawl_single

    Returns:
        爬取结果列表
    """
    return _crawler.crawl_batch(urls, concurrent, llm_config)


# CLI 入口点
if __name__ == "__main__":
    import sys

    # 默认使用 STDIO，但支持通过参数指定 HTTP
    if "--http" in sys.argv:
        mcp.run(transport="http", host="0.0.0.0", port=8001)
    else:
        mcp.run()
