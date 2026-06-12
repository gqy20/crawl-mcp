"""FastMCP 服务器实现"""

from typing import List, Dict, Any, Optional, Union
from fastmcp import FastMCP, Context
from crawl4ai_mcp.crawler import Crawler
from crawl4ai_mcp.searcher import Searcher
from crawl4ai_mcp.middleware.timeout import TimeoutMiddleware

# 读取包版本
try:
    from importlib.metadata import version as get_version

    __version__ = get_version("crawl_mcp")
except Exception:
    __version__ = "0.2.0"

# 创建 FastMCP 实例
mcp = FastMCP(name="crawl-mcp", version=__version__)

# 注册超时中间件：按工具类型配置不同超时限制
mcp.add_middleware(
    TimeoutMiddleware(
        default_timeout=60,
        per_tool={
            "search_text": 30,
            "search_news": 20,
            "search_books": 20,
            "search_videos": 20,
            "search_images": 30,
            "crawl_single": 75,
            "crawl_batch": 180,
            "crawl_site": 120,
        },
    )
)

# 创建搜索器实例（单例）
_searcher = Searcher()

# 创建爬虫实例（单例，注入共享 searcher 用于快速提取降级）
_crawler = Crawler(searcher=_searcher)


@mcp.tool(timeout=75, tags={"crawl"})
def crawl_single(
    url: str,
    enhanced: bool = False,
    llm_config: Optional[Union[Dict[str, Any], str]] = None,
    prefer_fast: bool = True,
    min_content_length: int = 200,
) -> Dict[str, Any]:
    """
    爬取单个网页（自动降级：快速提取 → 浏览器渲染）

    适用于已经知道一个明确 URL、需要提取该页面正文 Markdown 的场景。
    默认先尝试轻量级快速提取（适合静态文章/文档页），失败、内容过短或检测到 SPA 骨架页时
    自动切换到浏览器渲染。若要从一个入口页继续发现站内链接，请使用 crawl_site；
    若已有多个明确 URL，请使用 crawl_batch。

    参数组合：
    - 默认 prefer_fast=True：先快提取，必要时 fallback 到浏览器。
    - prefer_fast=False：跳过快速提取，强制直接使用浏览器。
    - enhanced=True：只影响浏览器路径的等待时间；不会单独跳过快速提取。
      如需强制浏览器增强模式，请同时设置 prefer_fast=False, enhanced=True。

    Args:
        url: 要爬取的网页 URL
        enhanced: 浏览器增强模式。适用于 SPA/慢加载页面，等待时间更长；仅在浏览器路径生效。
        llm_config: [实验性] LLM 后处理配置（可选），需设置 CRAWL_MCP_API_KEY 才生效。
            支持三种格式:
            - 字典: {"instruction": "总结", "schema": {...}}
            - JSON 字符串: '{"instruction": "总结"}'
            - 纯文本: "总结页面内容"（自动作为 instruction）
            未设置 API Key 时传此参数会优雅跳过，结果中包含 llm_skipped 提示。
        prefer_fast: 是否优先尝试快速提取（默认 True）。设为 False 时强制浏览器爬取。
        min_content_length: 快速提取结果的最小内容长度阈值（默认 200 字符）

    Returns:
        {
            success: bool,
            markdown: str,
            title: str,
            error: str | None,
            method?: "fast_extract" | "browser_fallback",
                # prefer_fast=True 时返回；prefer_fast=False 的纯浏览器路径可能不存在
            fallback_reason?: str,
                # 仅浏览器 fallback 时返回，说明快速提取失败或内容不足的原因
            llm_summary?/llm_data?/llm_skipped?/llm_error?: ...
                # 仅传入 llm_config 时可能出现
        }
    """
    return _crawler.crawl_single(
        url, enhanced, llm_config, prefer_fast, min_content_length
    )


@mcp.tool(timeout=120, tags={"crawl"})
def crawl_site(
    url: str,
    depth: int = 2,
    pages: int = 10,
    concurrent: int = 3,
    ctx: Context | None = None,
) -> Dict[str, Any]:
    """
    从入口页开始递归爬取站内页面（浏览器 + BFS 深度爬取）

    适用于只有一个网站入口、希望沿站内链接抓取若干页面的场景。
    与 crawl_batch 不同，本工具会从起始页发现链接；与 crawl_single/crawl_batch 不同，
    本工具不走快速提取自动降级，也不支持 LLM 后处理。

    Args:
        url: 起始 URL
        depth: 最大链接深度（默认 2）。数值越大，可能访问更多站内页面。
        pages: 最大页面数（默认 10）。用于限制递归爬取规模。
        concurrent: 浏览器爬取并发数（默认 3）。

    Returns:
        {
            successful_pages: int,
            total_pages: int,
            success_rate: str,
            results: [
                {success: bool, markdown: str, title: str, error: str | None},
                ...
            ]
        }
    """
    if ctx:
        ctx.info(f"开始爬取站点: {url} (深度={depth}, 最大页面={pages})")
    result = _crawler.crawl_site(url, depth=depth, pages=pages, concurrent=concurrent)
    if ctx:
        ctx.info(
            f"站点爬取完成: {result.get('successful_pages', 0)}/{result.get('total_pages', 0)} 页成功"
        )
    return result


@mcp.tool(timeout=180, tags={"crawl"})
def crawl_batch(
    urls: List[str],
    concurrent: int = 3,
    llm_config: Optional[Union[Dict[str, Any], str]] = None,
    llm_concurrent: int = 3,
    prefer_fast: bool = True,
    min_content_length: int = 200,
    ctx: Context | None = None,
) -> List[Dict[str, Any]]:
    """
    批量爬取多个网页（自动降级版）

    适用于已经有一组明确 URL、需要并行抓取多个页面的场景。
    默认对所有 URL 并行快速提取；只有失败、内容过短或 SPA 骨架页才进入浏览器 fallback。
    若只有一个 URL，请使用 crawl_single；若只有入口页并希望发现站内链接，请使用 crawl_site。

    参数组合：
    - prefer_fast=True：静态页走快速路径，失败项才走浏览器 fallback。
    - prefer_fast=False：所有 URL 都直接走浏览器，不返回 fast/fallback 方法标记。
    - min_content_length 只影响快速提取是否被认为足够完整。

    Args:
        urls: URL 列表
        concurrent: 网页爬取并发数（默认：3）
        llm_config: [实验性] LLM 后处理配置（可选），需设置 CRAWL_MCP_API_KEY 才生效
        llm_concurrent: LLM 处理并发数（默认：3）
        prefer_fast: 是否优先尝试快速提取（默认 True）
        min_content_length: 快速提取最小内容长度阈值（默认 200 字符）

    Returns:
        [
            {
                success: bool,
                markdown: str,
                title: str,
                error: str | None,
                method?: "fast_extract" | "browser_fallback",
                    # prefer_fast=True 时可能出现
                fallback_reason?: str,
                    # 仅 browser_fallback 项出现
                llm_summary?/llm_data?/llm_skipped?/llm_error?: ...
            },
            ...
        ]
    """
    if ctx:
        ctx.info(f"开始批量爬取: {len(urls)} 个 URL (并发={concurrent})")
    result = _crawler.crawl_batch(
        urls, concurrent, llm_config, llm_concurrent, prefer_fast, min_content_length
    )
    if ctx:
        success_count = sum(1 for r in result if r.get("success"))
        ctx.info(f"批量爬取完成: {success_count}/{len(result)} 个成功")
    return result


@mcp.tool(timeout=30, tags={"search"})
def search_text(
    query: str,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    搜索网页内容（通用搜索）

    适用于搜索技术文档、百科、博客、论坛、教程等网页内容。
    只返回搜索结果摘要和链接，不抓取页面正文；如需正文，请对结果 URL 再调用 crawl_single/crawl_batch。

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


@mcp.tool(timeout=20, tags={"search"})
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
    只返回新闻搜索结果摘要和来源链接，不抓取全文；如需全文，请对结果 URL 再调用 crawl_single。

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


@mcp.tool(timeout=20, tags={"search"})
def search_books(
    query: str,
    region: str = "wt-wt",
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    搜索图书

    适用于查找技术书籍、学术资料、电子书等。

    Args:
        query: 搜索关键词
        region: 区域代码（同 search_text）
        max_results: 最大结果数（默认：10）

    Returns:
        包含搜索结果的字典。results 的字段由 ddgs 返回，通常包含 title、url/href、body 等，
        具体字段会随来源变化。
    """
    return _searcher.search_books(query, region, max_results)


@mcp.tool(timeout=20, tags={"search"})
def search_videos(
    query: str,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    搜索视频

    适用于查找教程视频、演示视频、课程录像等。

    Args:
        query: 搜索关键词
        region: 区域代码（同 search_text）
        safesearch: 安全搜索 (on/moderate/off)
        timelimit: 时间限制 (d=天, w=周)
        max_results: 最大结果数（默认：10）

    Returns:
        包含搜索结果的字典。results 的字段由 ddgs 返回，通常包含 title、url/content/duration 等，
        具体字段会随来源变化。
    """
    return _searcher.search_videos(query, region, safesearch, timelimit, max_results)


@mcp.tool(timeout=30, tags={"search"})
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
    safesearch: 安全搜索 (on/moderate/off)
    timelimit: 时间限制 (d=天, w=周)
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
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
    else:
        mcp.run()


# CLI 入口点
if __name__ == "__main__":
    main()
