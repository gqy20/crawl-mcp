"""crawl CLI — 复用 MCP 同一套爬取/搜索核心，供终端和脚本直接调用

用法:
    crawl <url>                # 单页，Markdown 打到 stdout
    crawl <url1> <url2> ...    # 多 URL 并行批量，输出 JSON
    crawl --browser <url>      # 强制浏览器渲染（跳过快速提取）
    crawl site <url>           # 站内递归爬取（浏览器 + BFS），输出 JSON
    crawl search <query>       # 网页搜索，只返回摘要和链接
    crawl search --news <query>  # 新闻搜索（--books / --videos 同理）
    crawl images <query> --download  # 图片搜索+下载，输出本地路径供多模态模型查看
"""

import argparse
import json
import sys
from contextlib import redirect_stdout
from importlib.metadata import version as _pkg_version


def _fmt_size(n: int) -> str:
    return f"{n / 1048576:.1f}MB" if n >= 1048576 else f"{n / 1024:.0f}KB"


def _crawl(argv):
    parser = argparse.ArgumentParser(
        prog="crawl", description="爬取网页正文（快速提取 → 浏览器自动降级）"
    )
    parser.add_argument(
        "--version", action="version", version=f"crawl {_pkg_version('crawl_mcp')}"
    )
    parser.add_argument("urls", nargs="+", help="一个或多个 URL")
    parser.add_argument(
        "--browser", action="store_true", help="跳过快速提取，强制浏览器渲染"
    )
    parser.add_argument(
        "--json", action="store_true", help="输出完整 JSON（含 title/method 等字段）"
    )
    args = parser.parse_args(argv)

    from crawl4ai_mcp.crawler import Crawler

    crawler = Crawler()
    prefer_fast = not args.browser

    # crawl4ai 进度日志走 stdout，导到 stderr，保证 stdout 只有正文/JSON
    if len(args.urls) == 1:
        with redirect_stdout(sys.stderr):
            result = crawler.crawl_single(args.urls[0], prefer_fast=prefer_fast)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result["success"]:
            print(result["markdown"])
        else:
            print(f"爬取失败: {result.get('error')}", file=sys.stderr)
        return 0 if result["success"] else 1

    # 多 URL：Markdown 混排有歧义，统一输出 JSON
    with redirect_stdout(sys.stderr):
        results = crawler.crawl_batch(args.urls, prefer_fast=prefer_fast)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r["success"] for r in results) else 1


def _site(argv):
    parser = argparse.ArgumentParser(
        prog="crawl site", description="从入口页递归爬取站内页面（浏览器 + BFS）"
    )
    parser.add_argument("url", help="起始 URL")
    parser.add_argument("--depth", type=int, default=2, help="最大链接深度（默认 2）")
    parser.add_argument("--pages", type=int, default=10, help="最大页面数（默认 10）")
    args = parser.parse_args(argv)

    from crawl4ai_mcp.crawler import Crawler

    with redirect_stdout(sys.stderr):
        result = Crawler().crawl_site(args.url, depth=args.depth, pages=args.pages)
    # 多页结果与批量同理，统一 JSON
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["successful_pages"] == result["total_pages"] else 1


def _search(argv):
    parser = argparse.ArgumentParser(
        prog="crawl search", description="网页搜索（只返回摘要和链接）"
    )
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("-n", "--max-results", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--news", action="store_true", help="新闻搜索")
    group.add_argument("--books", action="store_true", help="图书搜索")
    group.add_argument("--videos", action="store_true", help="视频搜索")
    args = parser.parse_args(argv)

    from crawl4ai_mcp.searcher import Searcher

    method = (
        "search_news"
        if args.news
        else "search_books"
        if args.books
        else "search_videos"
        if args.videos
        else "search_text"
    )
    result = getattr(Searcher(), method)(args.query, max_results=args.max_results)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["success"]:
        for r in result["results"]:
            # news/videos 用 url/content 字段，text 用 href/body
            link = r.get("href") or r.get("url", "")
            body = r.get("body") or r.get("content", "")
            print(f"{r.get('title', '')}\n{link}\n{body}\n")
    else:
        print(f"搜索失败: {result.get('error')}", file=sys.stderr)
    return 0 if result["success"] else 1


def _images(argv):
    parser = argparse.ArgumentParser(
        prog="crawl images",
        description="图片搜索，可下载到本地（供多模态模型/CLI 直接查看）",
    )
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("-n", "--max-results", type=int, default=10)
    parser.add_argument(
        "--download", action="store_true", help="下载到本地，输出文件路径"
    )
    parser.add_argument("--output-dir", default="./downloads/images")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args(argv)

    from crawl4ai_mcp.searcher import Searcher

    result = Searcher().search_images(
        args.query,
        max_results=args.max_results,
        download=args.download,
        output_dir=args.output_dir,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not result["success"]:
        print(f"搜索失败: {result.get('error')}", file=sys.stderr)
    elif args.download:
        for r in result.get("download_results", {}).get("results", []):
            if r["success"]:
                print(f"{r['filepath']} ({_fmt_size(r['size'])})")
            else:
                print(f"下载失败: {r['url']} ({r['error']})", file=sys.stderr)
    else:
        for img in result["search_results"]["results"]:
            print(img.get("image", ""))

    if not result["success"]:
        return 1
    if args.download and result.get("download_results", {}).get("failed"):
        return 1
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "search":
        return _search(argv[1:])
    if argv and argv[0] == "site":
        return _site(argv[1:])
    if argv and argv[0] == "images":
        return _images(argv[1:])
    return _crawl(argv)


if __name__ == "__main__":
    sys.exit(main())
