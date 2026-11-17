"""磁盘缓存：按 URL 缓存爬取结果，避免重复请求

实测 Claude 历史会话里 51% 的外部抓取是重复 URL（同一个政策原文被反复抓 14 次），
缓存能直接省掉这些请求，Cloud 计费场景下等于直接省钱。

三类条目共用一套落盘机制，靠 namespace 区分：
  - 正缓存（"crawl"）    成功结果，TTL 由 CRAWL_MCP_CACHE_TTL 控制
  - 负缓存（"negative"） 失败结果，短 TTL：确定性失败重试也没用，不必每次重走降级链路
  - 域名记忆（"domain"） 域名级的失败结论，连续失败就记住，别再为同一个域名耗时间

环境变量:
    CRAWL_MCP_CACHE:      设为 0 关闭缓存
    CRAWL_MCP_CACHE_DIR:  缓存目录（默认 ~/.cache/crawl_mcp）
    CRAWL_MCP_CACHE_TTL:  正缓存有效期秒数（默认 3600）
    CRAWL_MCP_NEG_TTL:    负缓存有效期秒数（默认 300）
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_TTL = 3600  # 秒
NEGATIVE_TTL = 300  # 失败结果的缓存时间：短一点，站点恢复后能及时反映

#: namespace → 默认 TTL
_TTLS = {
    "crawl": DEFAULT_TTL,
    "negative": NEGATIVE_TTL,
    "domain": NEGATIVE_TTL,
}


def _cache_dir() -> Path:
    return Path(
        os.getenv("CRAWL_MCP_CACHE_DIR") or Path.home() / ".cache" / "crawl_mcp"
    )


def enabled() -> bool:
    """缓存是否启用"""
    return os.getenv("CRAWL_MCP_CACHE", "1") != "0"


def _ttl(namespace: str) -> int:
    """namespace 的默认 TTL

    env 优先：CRAWL_MCP_NEG_TTL 管负缓存/域名记忆，CRAWL_MCP_CACHE_TTL 管其余。
    """
    env_name = (
        "CRAWL_MCP_NEG_TTL"
        if namespace in ("negative", "domain")
        else ("CRAWL_MCP_CACHE_TTL")
    )
    raw = os.getenv(env_name)
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            pass
    return _TTLS.get(namespace, DEFAULT_TTL)


def _key(namespace: str, url: str, opts: dict[str, Any] | None = None) -> str:
    payload = json.dumps(opts or {}, sort_keys=True, ensure_ascii=False, default=str)
    raw = f"{namespace}|{url}|{payload}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _path(namespace: str, url: str, opts: dict[str, Any] | None = None) -> Path:
    key = _key(namespace, url, opts)
    return _cache_dir() / key[:2] / f"{key}.json"


def lookup(
    namespace: str, url: str, opts: dict[str, Any] | None = None
) -> tuple[dict[str, Any], float] | None:
    """读取条目，返回 (结果, 落盘时间戳)；不存在或过期返回 None"""
    if not enabled():
        return None
    path = _path(namespace, url, opts)
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = float(data.get("ts") or path.stat().st_mtime)
        # 老条目没有 exp 字段，按 mtime + namespace 默认 TTL 兜底
        exp = data.get("exp")
        expired = time.time() > (float(exp) if exp else ts + _ttl(namespace))
        if expired:
            path.unlink(missing_ok=True)
            return None
        return data.get("result"), ts
    except Exception:
        return None


def get(
    namespace: str, url: str, opts: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """读取缓存条目；不存在或过期返回 None"""
    found = lookup(namespace, url, opts)
    return found[0] if found else None


def put(
    namespace: str,
    url: str,
    result: dict[str, Any],
    opts: dict[str, Any] | None = None,
    ttl: int | None = None,
) -> None:
    """写入缓存条目；失败不影响主流程"""
    if not enabled():
        return
    try:
        path = _path(namespace, url, opts)
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        path.write_text(
            json.dumps(
                {
                    "ts": now,
                    "exp": now + (ttl if ttl is not None else _ttl(namespace)),
                    "result": result,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def clear() -> int:
    """清空缓存，返回删除的文件数"""
    removed = 0
    root = _cache_dir()
    if root.exists():
        for f in root.rglob("*.json"):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed
