"""crawl CLI — 复用 MCP 同一套爬取/搜索核心，供终端和脚本直接调用

用法:
    crawl <url>                # 单页，Markdown 打到 stdout
    crawl <url1> <url2> ...    # 多 URL 并行批量，输出 JSON
    crawl --browser <url>      # 强制浏览器渲染（跳过快速提取）
    crawl site <url>           # 站内递归爬取（快速 BFS 优先），输出 JSON
    crawl search <query>       # 网页搜索，只返回摘要和链接
    crawl search --news <query>  # 新闻搜索（--books / --videos 同理）
    crawl images <query> --download  # 图片搜索+下载，输出本地路径供多模态模型查看
"""

import argparse
import json
import os
import sys
from contextlib import redirect_stdout
from importlib.metadata import version as _pkg_version


def _fmt_size(n: int) -> str:
    return f"{n / 1048576:.1f}MB" if n >= 1048576 else f"{n / 1024:.0f}KB"


def _crawl(argv):
    parser = argparse.ArgumentParser(
        prog="crawl",
        description="爬取网页正文（自动降级：快速提取 → Cloud → 浏览器）",
        epilog=(
            "子命令:\n"
            "  crawl site <url>       站内递归爬取\n"
            "  crawl search <query>   网页搜索（--news/--books/--videos 换类型）\n"
            "  crawl images <query>   图片搜索（--download 下载到本地）\n"
            "\n"
            "示例:\n"
            "  crawl https://example.com        单页，Markdown 输出到 stdout\n"
            "  crawl a.com b.com                多 URL，输出 JSON 数组\n"
            "  crawl --json https://example.com  完整 JSON（含 title/method）\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"crawl {_pkg_version('crawl_mcp')}"
    )
    parser.add_argument("urls", nargs="+", help="一个或多个 URL")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--browser", action="store_true", help="跳过快速提取，强制本地浏览器渲染"
    )
    mode.add_argument(
        "--cloud",
        action="store_true",
        help="强制走 Crawl4AI Cloud（需 CRAWL4AI_API_KEY）",
    )
    parser.add_argument(
        "--json", action="store_true", help="输出完整 JSON（含 title/method 等字段）"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="不打印浏览器进度日志（只留错误）"
    )
    sel = parser.add_argument_group("正文范围（只在浏览器路径生效）")
    sel.add_argument("--css", help="只提取匹配元素内的正文，如 article / #content")
    sel.add_argument(
        "--exclude-css",
        help="排除匹配的元素（逗号分隔），如 nav,footer,aside",
    )
    sel.add_argument(
        "--full-page",
        action="store_true",
        help="滚动加载整页再提取（无限滚动/长列表页）",
    )
    args = parser.parse_args(argv)

    from crawl4ai_mcp.crawler import Crawler

    crawler = Crawler()
    prefer_fast = not args.browser

    if args.cloud:
        return _crawl_cloud(crawler, args)

    # crawl4ai 进度日志走 stdout，导到 stderr，保证 stdout 只有正文/JSON；
    # --quiet 时连 stderr 也不刷，只留失败信息
    if len(args.urls) == 1:
        with redirect_stdout(open(os.devnull, "w") if args.quiet else sys.stderr):
            result = crawler.crawl_single(
                args.urls[0],
                prefer_fast=prefer_fast,
                css_selector=args.css,
                excluded_selector=args.exclude_css,
                scan_full_page=args.full_page,
            )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result["success"]:
            print(result["markdown"])
        else:
            _report_failure(result)
        return 0 if result["success"] else 1

    # 多 URL：Markdown 混排有歧义，统一输出 JSON
    with redirect_stdout(open(os.devnull, "w") if args.quiet else sys.stderr):
        results = crawler.crawl_batch(
            args.urls,
            prefer_fast=prefer_fast,
            css_selector=args.css,
            excluded_selector=args.exclude_css,
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r["success"] for r in results) else 1


def _report_failure(result: dict) -> None:
    """打印失败原因，并给出下一步建议（error_code → 人话建议）"""
    from crawl4ai_mcp.content import suggest_action

    print(f"爬取失败: {result.get('error')}", file=sys.stderr)
    hint = suggest_action(result.get("error_code"))
    if hint:
        print(f"  建议: {hint}", file=sys.stderr)


def _crawl_cloud(crawler, args):
    """强制走 Crawl4AI Cloud 抓取"""
    results = [crawler.crawl_cloud(url) for url in args.urls]

    if len(args.urls) == 1:
        result = results[0]
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result["success"]:
            print(result["markdown"])
        else:
            _report_failure(result)
        return 0 if result["success"] else 1

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r["success"] for r in results) else 1


def _site(argv):
    parser = argparse.ArgumentParser(
        prog="crawl site",
        description="从入口页递归爬取站内页面（快速 BFS 优先，SPA 退回浏览器）",
    )
    parser.add_argument("url", help="起始 URL")
    parser.add_argument("--depth", type=int, default=2, help="最大链接深度（默认 2）")
    parser.add_argument("--pages", type=int, default=10, help="最大页面数（默认 10）")
    parser.add_argument(
        "--concurrent", type=int, default=3, help="并发爬取数（默认 3）"
    )
    args = parser.parse_args(argv)

    from crawl4ai_mcp.crawler import Crawler

    with redirect_stdout(sys.stderr):
        result = Crawler().crawl_site(
            args.url, depth=args.depth, pages=args.pages, concurrent=args.concurrent
        )
    # 多页结果与批量同理，统一 JSON
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["successful_pages"] == result["total_pages"] else 1


def _search(argv):
    parser = argparse.ArgumentParser(
        prog="crawl search", description="网页搜索（只返回摘要和链接）"
    )
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument(
        "-n", "--max-results", type=int, default=10, help="结果数量（默认 10）"
    )
    parser.add_argument(
        "--backend",
        help="指定搜索引擎引擎（逗号分隔），如 brave,startpage；默认自动挑选",
    )
    parser.add_argument("--page", type=int, default=1, help="结果页码（默认 1）")
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
    result = getattr(Searcher(), method)(
        args.query,
        max_results=args.max_results,
        page=args.page,
        backend=args.backend,
    )
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
    parser.add_argument(
        "-n", "--max-results", type=int, default=10, help="图片数量（默认 10）"
    )
    parser.add_argument(
        "--download", action="store_true", help="下载到本地，输出文件路径"
    )
    parser.add_argument(
        "--backend", help="指定搜索引擎引擎（逗号分隔），如 duckduckgo；默认自动挑选"
    )
    parser.add_argument("--page", type=int, default=1, help="结果页码（默认 1）")
    parser.add_argument(
        "--license-image",
        help="授权过滤 (any/public/share/sharecommercially/modify/modifycommercially)",
    )
    parser.add_argument(
        "--output-dir",
        default="./downloads/images",
        help="下载目录（默认 ./downloads/images）",
    )
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args(argv)

    from crawl4ai_mcp.searcher import Searcher

    result = Searcher().search_images(
        args.query,
        max_results=args.max_results,
        page=args.page,
        backend=args.backend,
        license_image=args.license_image,
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


def _auth(argv):
    parser = argparse.ArgumentParser(
        prog="crawl auth",
        description="登录态管理（~/.crawl_mcp/auth/，每站点一个 storage_state 文件）",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="列出已配置的登录态（域名/cookie 数/更新时间）")

    p_check = sub.add_parser(
        "check", help="验证登录态是否有效（对登录后页面发真实请求）"
    )
    p_check.add_argument("name", help="登录态名称（文件名去 .json）")
    p_check.add_argument(
        "--url", required=True, help="一个登录后才能看的页面 URL，用于探测"
    )

    p_imp = sub.add_parser("import", help="从本地已登录浏览器导入 cookie")
    p_imp.add_argument(
        "--from",
        dest="browser",
        required=True,
        choices=["chrome", "chromium", "firefox"],
        help="浏览器（chrome 的 v11 加密需解锁 keyring）",
    )
    p_imp.add_argument(
        "--site",
        action="append",
        help="只导这些站点（子串匹配，可重复，如 --site zhihu --site github）",
    )
    args = parser.parse_args(argv)

    import logging

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    from crawl4ai_mcp import auth_store

    if args.action == "list":
        auths = auth_store.list_auths()
        if not auths:
            print(f"登录态目录为空: {auth_store.auth_dir()}")
            print("导入: crawl auth import --from chrome --site <域名>")
            return 0
        import time as _time

        print(f"{'名称':16} {'cookie':>6}  {'更新时间':16} 域名")
        for a in auths:
            if "error" in a:
                print(f"{a['name']:16} [损坏] {a['error']}")
                continue
            when = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(a["mtime"]))
            print(
                f"{a['name']:16} {a['cookies']:>6}  {when:16} "
                f"{','.join(a['domains'][:4])}{'…' if len(a['domains']) > 4 else ''}"
            )
        return 0

    if args.action == "check":
        path = auth_store.auth_dir() / f"{args.name}.json"
        if not path.is_file():
            print(f"没有这个登录态: {path}", file=sys.stderr)
            return 1
        # 临时把该文件作为全局登录态注入（CLI 是一次性进程，改 env 无妨）
        os.environ["CRAWL_MCP_STORAGE_STATE"] = str(path)
        from crawl4ai_mcp import cache
        from crawl4ai_mcp.crawler import Crawler

        cache.clear()
        print(f"探测 {args.url} …", file=sys.stderr)
        result = Crawler().crawl_single(args.url, prefer_fast=False)
        code = result.get("error_code")
        if result.get("success"):
            print(f"{args.name}: 有效 ✓ ({len(result.get('markdown') or '')} 字正文)")
            return 0
        if code == "login_wall":
            print(f"{args.name}: 已失效（登录墙）✗ —— 重新导入或重新导出 storage_state")
            return 1
        print(f"{args.name}: 探测失败（{code or result.get('error')}），无法判定")
        return 1

    # import
    summary = auth_store.import_from_browser(args.browser, args.site)
    if not summary["imported"]:
        print(
            f"没有导入任何登录态：{summary.get('reason') or '没有匹配的 cookie'}",
            file=sys.stderr,
        )
        return 1
    for f in summary["files"]:
        print(f"已导入 {f['site']:20} {f['cookies']:>4} cookies → {f['path']}")
    print(f"共 {summary['imported']} 个站点。注意：文件是明文登录态，保管好目录权限。")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    from crawl4ai_mcp.utils import load_env

    load_env()

    if argv and argv[0] == "search":
        return _search(argv[1:])
    if argv and argv[0] == "site":
        return _site(argv[1:])
    if argv and argv[0] == "images":
        return _images(argv[1:])
    if argv and argv[0] == "auth":
        return _auth(argv[1:])
    return _crawl(argv)


if __name__ == "__main__":
    sys.exit(main())
