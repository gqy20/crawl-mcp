"""FastMCP 服务器实现"""

from typing import List, Dict, Any, Optional, Union
from fastmcp import FastMCP
from crawl4ai_mcp.crawler import Crawler
from crawl4ai_mcp.searcher import Searcher

# 读取包版本
try:
    from importlib.metadata import version as get_version

    __version__ = get_version("crawl_mcp")
except Exception:
    __version__ = "0.1.3"

# 创建 FastMCP 实例
mcp = FastMCP(name="crawl-mcp", version=__version__)

# 创建爬虫实例（单例）
_crawler = Crawler()

# 创建搜索器实例（单例）
_searcher = Searcher()


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
    llm_concurrent: int = 3,
) -> List[Dict[str, Any]]:
    """
    批量爬取多个网页（异步并行）

    Args:
        urls: URL 列表
        concurrent: 网页爬取并发数（默认：3）
        llm_config: LLM 配置（可选），格式同 crawl_single
        llm_concurrent: LLM 处理并发数（默认：3）

    Returns:
        爬取结果列表
    """
    return _crawler.crawl_batch(urls, concurrent, llm_config, llm_concurrent)


@mcp.tool
def search_text(
    query: str,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    搜索网页内容（通用搜索）

    适用于搜索技术文档、百科、博客、论坛、教程等静态内容。

    Args:
        query: 搜索关键词
        region: 区域代码
            - wt-wt: 无区域限制（默认）
            - us-en: 美国（英语）
            - cn-zh: 中国（中文）
            - uk-en: 英国（英语）
            - jp-jp: 日本（日语）
        safesearch: 安全搜索 (on/moderate/off)
        timelimit: 时间限制 (d=天, w=周, m=月, y=年)
        max_results: 最大结果数（默认：10）

    Returns:
        包含搜索结果的字典，格式：
        {
            "success": True,
            "query": "搜索关键词",
            "count": 5,
            "results": [
                {"title": "...", "href": "...", "body": "..."},
                ...
            ]
        }
    """
    return _searcher.search_text(query, region, safesearch, timelimit, max_results)


@mcp.tool
def search_news(
    query: str,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    搜索新闻内容

    适用于搜索突发新闻、时事、财经、体育等时效性内容。

    Args:
        query: 搜索关键词
        region: 区域代码（同 search_text）
        safesearch: 安全搜索 (on/moderate/off)
        timelimit: 时间限制 (d=天, w=周, m=月)
        max_results: 最大结果数（默认：10）

    Returns:
        包含新闻搜索结果的字典，格式：
        {
            "success": True,
            "query": "搜索关键词",
            "count": 3,
            "results": [
                {
                    "date": "2024-07-03T16:25:22+00:00",
                    "title": "...",
                    "body": "...",
                    "url": "...",
                    "image": "...",
                    "source": "..."
                },
                ...
            ]
        }
    """
    return _searcher.search_news(query, region, safesearch, timelimit, max_results)


@mcp.tool
def search_images(
    query: str,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
    size: Optional[str] = None,
    color: Optional[str] = None,
    type_image: Optional[str] = None,
    layout: Optional[str] = None,
    download: bool = False,
    download_count: Optional[int] = None,
    output_dir: str = "./downloads/images",
    analyze: bool = False,
    analysis_prompt: str = "详细描述这张图片的内容",
    analyze_concurrent: int = 3,
) -> Dict[str, Any]:
    """
    搜索图片（支持下载和分析）

    === 基础搜索 ===
    query: 搜索关键词
    max_results: 搜索结果数量（默认：10）

    === 搜索过滤 ===
    region: 区域代码 (wt-wt/us-en/cn-zh等)
    size: 图片尺寸 (Small/Medium/Large/Wallpaper)
    color: 颜色过滤 (如 "Red", "Monochrome")
    type_image: 类型 (photo/clipart/gif/transparent/line)
    layout: 布局 (Square/Tall/Wide)

    === 下载选项 ===
    download: 是否下载到本地（默认：False）
    download_count: 下载数量（默认：全部）
    output_dir: 下载目录（默认：./downloads/images）

    === 分析选项 ===
    analyze: 是否使用图片模型分析（默认：False）
    analysis_prompt: 分析提示词
    analyze_concurrent: 图片分析并发数（默认：3）

    === 返回格式 ===
    {
        "success": True,
        "query": "butterfly",
        "search_results": {
            "count": 10,
            "results": [
                {
                    "title": "...",
                    "image": "https://...",
                    "thumbnail": "https://...",
                    "width": 1920,
                    "height": 1080,
                    "source": "Bing"
                },
                ...
            ]
        },
        "download_results": {          # 仅当 download=True 时
            "total": 5,
            "downloaded": 5,
            "output_dir": "./downloads/images"
        },
        "analysis_results": {          # 仅当 analyze=True 时
            "count": 5,
            "results": [
                {
                    "image": "...",
                    "type": "local",
                    "analysis": "这是一张..."
                }
            ]
        }
    }
    """
    return _searcher.search_images(
        query=query,
        region=region,
        safesearch=safesearch,
        timelimit=timelimit,
        max_results=max_results,
        size=size,
        color=color,
        type_image=type_image,
        layout=layout,
        download=download,
        download_count=download_count,
        output_dir=output_dir,
        analyze=analyze,
        analysis_prompt=analysis_prompt,
        analyze_concurrent=analyze_concurrent,
    )


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
