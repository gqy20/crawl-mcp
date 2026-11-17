"""Crawl4AI Cloud 兜底客户端

本地快速提取（ddgs.extract）拿不到内容时，作为备选路径调用 Crawl4AI Cloud 的
`/scrape` 接口：云端自动选引擎（缓存 → fetch → 浏览器），约 1-2s 返回 Markdown。

未配置 `CRAWL4AI_API_KEY` 时本模块不会发起任何请求。

多 key 支持：`CRAWL4AI_API_KEY` 可写逗号分隔的多个 key，调用按轮询分配，
某个 key 额度耗尽（402）或被限速（429）时自动换下一个重试。

接口参考: https://crawl4ai.com/docs/
"""

from __future__ import annotations

import itertools
import os
import threading
import time
from typing import Any

CLOUD_API_URL = "https://api.crawl4ai.com"

#: 单次请求超时（秒）。Cloud 侧 timeout 留 5s 余量，避免客户端先断。
REQUEST_TIMEOUT = 30.0
CLOUD_TIMEOUT = 25

#: 兜底路径的整段预算（秒）。降级链路里 Cloud 只是中间一环，后面还排着浏览器，
#: 让它无限等会拖垮整体：实测 Cloud 正常 1.6-5.5s，偶尔 20s+（排队/限速）。
#: 给了预算就超时退出，交给浏览器路径，比干等划算。
#: 可用 CRAWL4AI_CLOUD_BUDGET 覆盖（站点不同、预算不同）。
FALLBACK_BUDGET = 10.0


def fallback_budget() -> float:
    """本次调用实际使用的 Cloud 兜底预算（秒）"""
    raw = os.getenv("CRAWL4AI_CLOUD_BUDGET")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return FALLBACK_BUDGET


#: 轮询计数器（多 key 轮换用）
_key_counter = itertools.count()
_key_lock = threading.Lock()


def get_cloud_keys() -> list[str]:
    """读取一个或多个 Cloud API key（逗号/分号分隔），未配置返回空列表"""
    raw = os.getenv("CRAWL4AI_API_KEY") or os.getenv("CRAWL4AI_CLOUD_KEY") or ""
    return [k.strip() for k in raw.replace(";", ",").split(",") if k.strip()]


def get_cloud_key() -> str | None:
    """轮询取下一个 key（单 key 时等价于直接读取）"""
    keys = get_cloud_keys()
    if not keys:
        return None
    with _key_lock:
        idx = next(_key_counter)
    return keys[idx % len(keys)]


def _ordered_keys(keys: list[str]) -> list[str]:
    """从轮询位置开始排列所有 key，保证调用量均摊到各账号"""
    with _key_lock:
        start = next(_key_counter)
    n = len(keys)
    return [keys[(start + i) % n] for i in range(n)]


def cloud_enabled() -> bool:
    """Cloud 兜底是否可用：配了 key，且没被 CRAWL4AI_CLOUD_FALLBACK=0 关掉"""
    if os.getenv("CRAWL4AI_CLOUD_FALLBACK", "1").lower() in ("0", "false", "no"):
        return False
    return bool(get_cloud_keys())


def _key_hint(key: str) -> str:
    """key 脱敏标识，用于报错信息（只留末 4 位）"""
    return f"...{key[-4:]}" if len(key) > 4 else key


def _scrape_with_key(key: str, url: str, timeout: float) -> dict[str, Any]:
    """用指定 key 调一次 /scrape"""
    import httpx

    try:
        resp = httpx.post(
            f"{CLOUD_API_URL}/scrape",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"url": url, "format": "both", "timeout": CLOUD_TIMEOUT},
            timeout=timeout,
        )
    except Exception as exc:  # 网络错误不应中断本地降级链路
        return {
            "success": False,
            "markdown": "",
            "html": "",
            "error": f"Cloud 请求失败: {exc}",
        }

    if resp.status_code != 200:
        detail = resp.text[:200].strip()
        return {
            "success": False,
            "markdown": "",
            "html": "",
            "error": f"Cloud 返回 HTTP {resp.status_code}: {detail}",
        }

    try:
        data = resp.json()
    except ValueError:
        return {
            "success": False,
            "markdown": "",
            "html": "",
            "error": "Cloud 返回非 JSON 响应",
        }

    if not data.get("ok"):
        return {
            "success": False,
            "markdown": "",
            "html": "",
            "error": f"Cloud 抓取失败: {data.get('error', 'unknown')}",
        }

    markdown = data.get("markdown") or ""
    if not markdown.strip():
        return {
            "success": False,
            "markdown": "",
            "html": data.get("html") or "",
            "error": "Cloud 返回空内容",
        }

    return {
        "success": True,
        "markdown": markdown,
        "html": data.get("html") or "",
        "error": None,
    }


def _is_retryable(error: str | None) -> bool:
    """额度耗尽（402）或被限速（429）时换 key 重试才有意义"""
    if not error:
        return False
    return "HTTP 402" in error or "HTTP 429" in error


def cloud_scrape(
    url: str, timeout: float = REQUEST_TIMEOUT, budget: float | None = None
) -> dict[str, Any]:
    """抓取单个 URL

    多 key 时按轮询顺序尝试；某个 key 额度耗尽（402）或被限速（429）就换下一个。

    Args:
        url: 目标 URL
        timeout: 单个 key 的请求超时
        budget: 整段（含换 key 重试）的总预算；超了就停手，交给下一级降级

    Returns:
        {"success": bool, "markdown": str, "html": str, "error": str | None}
    """
    keys = get_cloud_keys()
    if not keys:
        return {
            "success": False,
            "markdown": "",
            "html": "",
            "error": "CRAWL4AI_API_KEY 未配置",
        }

    deadline = time.monotonic() + budget if budget else None
    last_error = "unknown"
    for key in _ordered_keys(keys):
        attempt_timeout = timeout
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_error = f"[{_key_hint(key)}] Cloud 兜底超时（预算 {budget}s 用尽）"
                break
            attempt_timeout = min(timeout, remaining)
        result = _scrape_with_key(key, url, attempt_timeout)
        if result["success"]:
            return result
        last_error = f"[{_key_hint(key)}] {result['error']}"
        if not _is_retryable(result["error"]):
            break

    return {
        "success": False,
        "markdown": "",
        "html": "",
        "error": f"Cloud 抓取失败: {last_error}",
    }
