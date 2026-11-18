"""Benchmark：跑一遍代表性渠道，更新 docs/BENCHMARK.md

用法:
    uv run python scripts/bench.py             # quick 模式（默认），更新文档
    uv run python scripts/bench.py --full      # 完整 URL 集
    uv run python scripts/bench.py --no-cloud  # 不走 Cloud 兜底
    uv run python scripts/bench.py --no-write  # 只打印结果，不写文件

数据集来自 ~/.claude 历史会话里高频出现的真实渠道（政府政策、学术期刊、代码托管、
微信公众号），每个 URL 都能命中降级链路的不同分支。
"""

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "BENCHMARK.md"
HISTORY = ROOT / "docs" / "bench-history.jsonl"
STAMP = ROOT / ".bench-stamp"

# ── 数据集 ────────────────────────────────────────────────
#
# 用例写在 scripts/bench.yml（改数据不动代码），加载成
# (渠道, URL, 预期, 关键内容) 四元组：
#   预期为 None            → 期望成功，正文 ≥ MIN_CHARS 字
#   预期为 ("error", code) → 期望失败，且 error_code 等于 code
#                             （已知问题站点的回归用例，防止判定逻辑退化）
#   关键内容非空           → 成功时正文必须包含这些短语（借鉴 Firecrawl
#                             数据集的 truth_text 思路：抓到了 ≠ 抓对了）
#
# 「已知问题」用例不是要跑通，而是要保证「失败得对」——error_code 变了就是回归。

MIN_CHARS = 200

DATASET = Path(__file__).parent / "bench.yml"


def _load_dataset() -> tuple[list, list, list, list]:
    import yaml

    data = yaml.safe_load(DATASET.read_text(encoding="utf-8"))

    def case(d: dict) -> tuple:
        expect = d.get("expect")
        text = d.get("expect_text")
        texts = (text,) if isinstance(text, str) else tuple(text or ())
        if expect is None:
            expect_parsed = None
        else:
            codes = tuple(expect) if isinstance(expect, list) else (expect,)
            expect_parsed = ("error", codes)
        return (d["group"], d["url"], expect_parsed, texts)

    quick = [case(d) for d in data["quick"]]
    full = quick + [case(d) for d in data.get("full_extra", [])]
    queries = [
        (q["kind"], q["query"], q.get("region", "wt-wt")) for q in data["queries"]
    ]
    sites = [
        (d["group"], d["url"], d.get("depth", 1), d.get("pages", 5))
        for d in data.get("sites", [])
    ]
    return quick, full, queries, sites


QUICK_CASES, FULL_CASES, QUERIES, SITES = _load_dataset()


# ── 采集 ──────────────────────────────────────────────────

SITE_MIN_OK = 3  # crawl_site 用例成功页低于这个数算退化


def _versions() -> dict[str, str]:
    """采集依赖版本，写进文档便于判断结果差异"""
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for pkg in ("crawl4ai", "fastmcp", "ddgs", "httpx"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "-"
    return out


def run_crawls(
    cases: list[tuple[str, str, tuple | None, tuple]], label: str = ""
) -> list[dict]:
    """逐个 URL 跑完整降级链路，记录命中路径、分段耗时和是否符合预期"""
    from crawl4ai_mcp.crawler import Crawler

    crawler = Crawler()
    rows = []
    for group, url, expect, texts in cases:
        t0 = time.perf_counter()
        try:
            r = crawler.crawl_single(url)
        except Exception as e:  # 单个站点异常不该中断整轮
            r = {"success": False, "error": f"{type(e).__name__}: {e}"}
        dt = time.perf_counter() - t0
        md = r.get("markdown") or ""
        chars = len(md)
        timings = r.get("timings") or {}
        row = {
            "group": group,
            "url": url,
            "ok": bool(r.get("success")),
            "method": r.get("method") or "-",
            "sec": round(dt, 1),
            "chars": chars,
            "title": bool(r.get("title")),
            "error_code": r.get("error_code"),
            "err": (r.get("error") or "")[:100],
            "timings": {k: timings.get(k) for k in ("fast", "cloud", "browser")},
            "expect": expect,
            "expect_texts": texts,
            "missing_texts": [t for t in texts if t not in md],
            "cached": bool(r.get("cached")),
        }
        row["verdict"], row["detail"] = _judge(row)
        print(
            f"  {row['method']:16s} {dt:6.1f}s {chars:8d}字  "
            f"{row['verdict']}  {label}{group}",
            flush=True,
        )
        rows.append(row)
    return rows


def _judge(row: dict) -> tuple[str, str]:
    """判定结果是否符合预期。

    返回 (标记, 说明)。预期成功却失败、预期失败却成功、error_code 变了、
    关键内容缺失，都算不符合预期——这类偏差比单纯的失败更值得报警。
    """
    expect = row["expect"]
    if expect is None:
        if not row["ok"]:
            return "✗", row["error_code"] or "失败"
        if row["chars"] < MIN_CHARS:
            return "✗", "正文过短"
        missing = row.get("missing_texts") or []
        if missing:
            return "✗", f"缺关键内容: {'; '.join(missing[:2])}"
        return "✓", ""
    kind, code = expect
    if kind != "error":
        return "?", "未知预期"
    codes = tuple(code) if isinstance(code, (tuple, list)) else (code,)
    if not row["ok"] and row["error_code"] in codes:
        return "✓", ""
    if row["ok"]:
        return "✗", f"预期失败({'/'.join(codes)})，实际成功"
    return "✗", f"预期 {'/'.join(codes)}，实际 {row['error_code'] or 'unknown'}"


def run_searches(queries: list[tuple[str, str, str]], repeat: int = 1) -> list[dict]:
    """跑搜索查询，记录命中数和耗时

    搜索后端不稳，单次结果说明不了问题：repeat>1 时看命中率。
    """
    from crawl4ai_mcp.searcher import Searcher

    s = Searcher()
    rows = []
    for kind, query, region in queries:
        hits = 0
        total = 0
        err = ""
        n = 0
        t0 = time.perf_counter()
        for _ in range(max(1, repeat)):
            try:
                r = s.search_text(query, region=region, max_results=5)
            except Exception as e:
                r = {"success": False, "error": str(e), "results": []}
            results = r.get("results") or []
            total += 1
            if r.get("success") and results:
                hits += 1
                n = len(results)
            else:
                err = (r.get("error") or "")[:100]
        dt = time.perf_counter() - t0
        rows.append(
            {
                "kind": kind,
                "query": query,
                "region": region,
                "ok": hits > 0,
                "n": n,
                "hits": hits,
                "runs": total,
                "rate": hits / total if total else 0.0,
                "sec": round(dt, 1),
                "err": err,
            }
        )
        print(
            f"  n={rows[-1]['n']:2d} {dt:6.1f}s  {kind}  {query[:40]}"
            + (f"  ({hits}/{total})" if total > 1 else ""),
            flush=True,
        )
    return rows


def run_batch_throughput(
    cases: list[tuple[str, str, tuple | None]], serial_rows: list[dict]
) -> dict:
    """批量吞吐：同样一批 URL，一次 crawl_batch 跑完，和逐个跑的总耗时对比

    批量前先清缓存——要测的是真实抓取吞吐，不是缓存命中速度。
    """
    from crawl4ai_mcp import cache as cache_mod
    from crawl4ai_mcp.crawler import Crawler

    # 只挑走快速提取的 URL：批量和逐个要在同一条路径上比，
    # 否则 Cloud 路径的限速会把对比搅乱
    fast_urls = [r["url"] for r in serial_rows if r["method"] == "fast_extract"]
    picked = fast_urls[:5]
    if len(picked) < 2:
        return {}
    urls = picked

    cache_mod.clear()
    crawler = Crawler()
    t0 = time.perf_counter()
    results = crawler.crawl_batch(urls)
    batch_sec = time.perf_counter() - t0

    serial_sec = sum(r["sec"] for r in serial_rows if r["url"] in urls)
    ok = sum(1 for r in results if r.get("success"))
    print(
        f"  批量 {len(urls)} 个 URL：{batch_sec:.1f}s"
        f"（逐个跑合计 {serial_sec:.1f}s，加速 {serial_sec / batch_sec:.1f}x）",
        flush=True,
    )
    return {
        "n": len(urls),
        "batch_sec": round(batch_sec, 1),
        "serial_sec": round(serial_sec, 1),
        "speedup": round(serial_sec / batch_sec, 2) if batch_sec else 0.0,
        "ok": ok,
    }


def run_sites(sites: list[tuple[str, str, int, int]]) -> list[dict]:
    """crawl_site 站内爬取：清缓存跑快速 BFS，看能收多少页、多久"""
    from crawl4ai_mcp import cache as cache_mod
    from crawl4ai_mcp.crawler import Crawler

    crawler = Crawler()
    rows = []
    for group, url, depth, pages in sites:
        cache_mod.clear()  # 站内爬取内部会带缓存，先清掉看冷启动
        t0 = time.perf_counter()
        try:
            r = crawler.crawl_site(url, depth=depth, pages=pages)
        except Exception as e:  # 单个站点异常不该中断整轮
            r = {"successful_pages": 0, "total_pages": 0}
            r["error"] = f"{type(e).__name__}: {e}"
        dt = time.perf_counter() - t0
        ok_pages = r.get("successful_pages", 0)
        row = {
            "group": group,
            "url": url,
            "depth": depth,
            "ok_pages": ok_pages,
            "pages": r.get("total_pages", 0),
            "sec": round(dt, 1),
            "err": (r.get("error") or "")[:100],
        }
        row["verdict"] = "✓" if ok_pages >= SITE_MIN_OK else "✗"
        row["detail"] = "" if row["verdict"] == "✓" else (row["err"] or "成功页过少")
        print(
            f"  {ok_pages}/{row['pages']}页 {dt:6.1f}s  {row['verdict']}  {group}",
            flush=True,
        )
        rows.append(row)
    return rows


# ── 渲染 ──────────────────────────────────────────────────


def _summary(crawls: list[dict], searches: list[dict]) -> dict:
    ok_crawl = sum(1 for r in crawls if r["verdict"] == "✓")
    real_ok = sum(1 for r in crawls if r["ok"])
    expected_fail = sum(1 for r in crawls if r["expect"] is not None)
    ok_search = sum(1 for r in searches if r["ok"])
    times = sorted(r["sec"] for r in crawls)
    return {
        "crawl_total": len(crawls),
        "crawl_ok": ok_crawl,
        "crawl_real_ok": real_ok,
        "crawl_expected_fail": expected_fail,
        "search_total": len(searches),
        "search_ok": ok_search,
        "median_sec": round(times[len(times) // 2], 1) if times else 0.0,
        "methods": {
            m: sum(1 for r in crawls if r["method"] == m)
            for m in sorted({r["method"] for r in crawls})
        },
    }


def _history() -> list[dict]:
    if not HISTORY.exists():
        return []
    rows = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def render(run: dict, history: list[dict]) -> str:
    """把一次运行渲染成完整文档"""
    s = run["summary"]
    env = run["env"]
    lines = [
        "# Benchmark",
        "",
        "<!-- 本文件由 `scripts/bench.py` 自动生成，勿手改 -->",
        "",
        "跑一次：`uv run python scripts/bench.py`（quick）/ `--full`（完整数据集）。",
        "提交代码时 pre-commit hook 会自动重跑并更新本文件。",
        "每次运行前会清空本地缓存，保证数字是冷启动、可横向比较。",
        "",
        "## 最近一次运行",
        "",
        f"- 时间：{run['ts']}",
        f"- 模式：`{run['mode']}`",
        f"- 环境：Python {env['python']} / crawl4ai {env['crawl4ai']} / "
        f"fastmcp {env['fastmcp']} / ddgs {env['ddgs']}",
        f"- Cloud 兜底：{run['cloud']}",
        "",
        "### 爬取",
    ]
    # 与上次同模式运行的逐行对比：标出变慢/变快的条目
    prev_secs = _prev_secs(history, run["mode"])

    for channel, items in _by_channel(run["crawls"]).items():
        lines += ["", f"**{channel}**", ""]
        lines.append(
            "| 条目 | 预期 | 路径 | 分段耗时 | 总耗时 | 对比上次 | 字数 | 结果 |"
        )
        lines.append(
            "|------|------|------|----------|--------|----------|------|------|"
        )
        for r, name in items:
            expect = r["expect"]
            if expect is None:
                expect_txt = "成功·含关键内容" if r.get("expect_texts") else "成功"
            else:
                codes = (
                    expect[1] if isinstance(expect[1], (tuple, list)) else (expect[1],)
                )
                expect_txt = "失败·" + "/".join(codes)
            status = "✓" if r["verdict"] == "✓" else f"✗ {r['detail']}"
            lines.append(
                f"| {name} | {expect_txt} | `{r['method']}` | "
                f"{_fmt_timings(r.get('timings'))} | {r['sec']}s | "
                f"{_fmt_delta(prev_secs.get(r['group']), r['sec'])} | "
                f"{r['chars']} | {status} |"
            )

    lines += [
        "",
        "### 搜索",
        "",
        "| 主题 | query | 区域 | 命中 | 命中率 | 耗时 | 结果 |",
        "|------|-------|------|------|--------|------|------|",
    ]
    for r in run["searches"]:
        status = "✓" if r["ok"] else f"✗ {r['err']}"
        rate = f"{r['rate']:.0%}" if r.get("runs", 1) > 1 else "—"
        lines.append(
            f"| {r['kind']} | {r['query']} | `{r['region']}` | {r['n']} | {rate} | "
            f"{r['sec']}s | {status} |"
        )

    warm = run.get("warm")
    if warm:
        lines += [
            "",
            "### 缓存命中（同一批 URL 重跑）",
            "",
            "| 条目 | 冷启动 | 命中缓存 | 节省 |",
            "|------|--------|----------|------|",
        ]
        for w in warm:
            save = round(w["cold_sec"] - w["warm_sec"], 1)
            lines.append(
                f"| {w['group']} | {w['cold_sec']}s | {w['warm_sec']}s | {save}s |"
            )

    batch = run.get("batch")
    if batch:
        lines += [
            "",
            "### 批量吞吐",
            "",
            f"- `crawl_batch` 一次抓 {batch['n']} 个 URL：**{batch['batch_sec']}s**"
            f"（成功 {batch['ok']}/{batch['n']}）",
            f"- 同样这批逐个抓合计 {batch['serial_sec']}s → "
            f"**加速 {batch['speedup']}x**",
        ]

    sites = run.get("sites")
    if sites:
        lines += [
            "",
            "### 站内爬取（`crawl_site` 快速 BFS）",
            "",
            "| 条目 | 深度 | 成功页 | 耗时 | 结果 |",
            "|------|------|--------|------|------|",
        ]
        for r in sites:
            status = "✓" if r["verdict"] == "✓" else f"✗ {r['detail']}"
            lines.append(
                f"| {r['group']} | {r['depth']} | {r['ok_pages']}/{r['pages']} | "
                f"{r['sec']}s | {status} |"
            )

    lines += [
        "",
        "### 汇总",
        "",
        f"- 爬取符合预期 **{s['crawl_ok']}/{s['crawl_total']}**"
        f"（其中实际成功 {s['crawl_real_ok']}，"
        f"已知问题按预期失败 {s['crawl_expected_fail']}），中位耗时 {s['median_sec']}s",
        f"- 搜索命中 **{s['search_ok']}/{s['search_total']}**",
        "- 路径分布：" + "、".join(f"{k} {v}" for k, v in s["methods"].items()),
    ]

    # 只和同模式的历史比：quick 是 9 个用例，full 是 20 个，跨模式比没有意义
    same_mode = [h for h in history if h.get("mode") == run["mode"]]
    if same_mode:
        prev = same_mode[-1]
        d_ok = s["crawl_ok"] - prev["summary"]["crawl_ok"]
        d_med = round(s["median_sec"] - prev["summary"]["median_sec"], 1)
        sign = "+" if d_ok >= 0 else ""
        lines.append(
            f"- 较上次同模式（{prev['ts']}）：符合预期 {sign}{d_ok}，中位耗时 {d_med:+}s"
        )

    lines += [
        "",
        "## 历史",
        "",
        "| 时间 | 模式 | 爬取 | 搜索 | 中位耗时 |",
        "|------|------|------|------|----------|",
    ]
    for h in [*history, run][-15:][::-1]:
        hs = h["summary"]
        lines.append(
            f"| {h['ts']} | `{h['mode']}` | {hs['crawl_ok']}/{hs['crawl_total']} | "
            f"{hs['search_ok']}/{hs['search_total']} | {hs['median_sec']}s |"
        )
    lines.append("")
    return "\n".join(lines)


def _by_channel(crawls: list[dict]) -> dict[str, list[tuple[dict, str]]]:
    """按渠道分组（渠道 = "政府-国务院政策" 里的 "政府"），保持首次出现顺序

    full 数据集是 quick + 追加，同渠道会分两段出现，这里合并成一段。
    """
    out: dict[str, list[tuple[dict, str]]] = {}
    for r in crawls:
        channel, _, name = r["group"].partition("-")
        out.setdefault(channel, []).append((r, name or channel))
    return out


def _prev_secs(history: list[dict], mode: str) -> dict[str, float]:
    """上一次同模式运行里，每个条目的耗时（用于逐行对比）"""
    same = [h for h in history if h.get("mode") == mode]
    if not same:
        return {}
    return {r["group"]: r["sec"] for r in same[-1].get("crawls", [])}


def _fmt_delta(prev: float | None, cur: float) -> str:
    """和上次对比：变慢标 ↑，变快标 ↓，没数据留空"""
    if prev is None or prev <= 0:
        return "—"
    ratio = (cur - prev) / prev
    if abs(ratio) < 0.2:
        return "持平"
    arrow = "↑" if ratio > 0 else "↓"
    return f"{arrow} {abs(ratio):.0%}"


def _fmt_timings(timings: dict | None) -> str:
    """分段耗时渲染成 fast/cloud/browser 三格，没发生的阶段留空"""
    t = timings or {}
    parts = []
    for key, label in (("fast", "f"), ("cloud", "c"), ("browser", "b")):
        v = t.get(key)
        parts.append(f"{label}{v:.1f}" if isinstance(v, (int, float)) else f"{label}-")
    return " ".join(parts)


def _atomic_write(path: Path, content: str) -> None:
    """原子写：先写临时文件再 rename，避免中断留下半截文档"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _src_hash() -> str:
    """源码指纹，用于判断自上次 benchmark 后有没有改动

    包含 bench.py 自身和 bench.yml：改数据集/判定逻辑也要触发重跑
    """
    h = hashlib.sha256()
    for p in sorted((ROOT / "src").rglob("*.py")):
        h.update(p.read_bytes())
    h.update(Path(__file__).read_bytes())
    h.update(DATASET.read_bytes())
    return h.hexdigest()


def _src_changed() -> bool:
    """源码自上次运行后是否变过"""
    current = _src_hash()
    if STAMP.exists() and STAMP.read_text(encoding="utf-8").strip() == current:
        return False
    return True


# ── 入口 ──────────────────────────────────────────────────


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="跑基准测试并更新 docs/BENCHMARK.md")
    parser.add_argument("--full", action="store_true", help="跑完整数据集")
    parser.add_argument("--no-cloud", action="store_true", help="禁用 Cloud 兜底")
    parser.add_argument("--no-write", action="store_true", help="不写文件，只打印")
    parser.add_argument(
        "--repeat", type=int, default=1, help="每个搜索 query 跑几次（看命中率）"
    )
    parser.add_argument(
        "--if-changed",
        action="store_true",
        help="源码自上次运行没变过就跳过（给自动触发用）",
    )
    args = parser.parse_args(argv)

    if args.if_changed and not _src_changed():
        print("[bench] 源码未变，跳过")
        return 0

    if args.no_cloud:
        os.environ["CRAWL4AI_CLOUD_FALLBACK"] = "0"

    sys.path.insert(0, str(ROOT / "src"))
    from crawl4ai_mcp.utils import load_env

    load_env()

    from crawl4ai_mcp.cloud import cloud_enabled, get_cloud_key

    key = get_cloud_key()
    cloud = "启用" if cloud_enabled() else "未启用（无 key 或已关闭）"
    if key:
        cloud += f"（key …{key[-4:]}）"

    # 清空本地缓存，保证每次运行的数字都是冷启动、可横向比较
    from crawl4ai_mcp import cache

    removed = cache.clear()
    if removed:
        print(f"[bench] 清空本地缓存 {removed} 条")

    cases = FULL_CASES if args.full else QUICK_CASES
    mode = "full" if args.full else "quick"

    print(f"[bench] 模式={mode} Cloud={cloud}")
    print("[bench] 爬取（冷启动）：")
    crawls = run_crawls(cases)

    print("[bench] 爬取（缓存命中）：")
    warm_rows = run_crawls(cases, label="[热] ")
    warm = [
        {
            "group": c["group"],
            "cold_sec": c["sec"],
            "warm_sec": w["sec"],
            "cached": w.get("cached"),
        }
        for c, w in zip(crawls, warm_rows)
    ]

    print("[bench] 批量吞吐：")
    batch = run_batch_throughput(cases, crawls)

    sites: list[dict] = []
    if SITES:
        print("[bench] 站内爬取：")
        sites = run_sites(SITES)

    print("[bench] 搜索：")
    searches = run_searches(QUERIES, repeat=args.repeat)

    run = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": mode,
        "env": {"python": platform.python_version(), **_versions()},
        "cloud": cloud,
        "crawls": crawls,
        "searches": searches,
        "warm": warm,
        "batch": batch,
        "sites": sites,
        "summary": _summary(crawls, searches),
    }

    history = _history()
    if not args.no_write:
        keep = [*history, run][-100:]  # 历史文件封顶，避免无限增长
        _atomic_write(
            HISTORY, "\n".join(json.dumps(h, ensure_ascii=False) for h in keep) + "\n"
        )
        _atomic_write(DOC, render(run, history))
        _atomic_write(STAMP, _src_hash())
        print(f"[bench] 已更新 {DOC.relative_to(ROOT)}")

    s = run["summary"]
    print(
        f"[bench] 爬取符合预期 {s['crawl_ok']}/{s['crawl_total']}，"
        f"搜索 {s['search_ok']}/{s['search_total']}，中位 {s['median_sec']}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
