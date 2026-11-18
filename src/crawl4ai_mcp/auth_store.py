"""登录态仓库：每站点一个 storage_state 文件，统一放一个目录。

目录默认 ``~/.crawl_mcp/auth/``（``CRAWL_MCP_AUTH_DIR`` 可覆盖），文件为
Playwright storage_state 格式（``{"cookies": [...], "origins": [...]}``）。
爬取时按 URL 的 domain 自动挑匹配的文件注入浏览器（见 crawler._env_browser_config），
不再全局广播所有登录态。

三种来源：
- ``crawl auth import --from chrome|chromium|firefox``：直接从本地已登录浏览器解析
- ``playwright codegen --save-storage=<目录>/<站点>.json``：登录一次导出
- 手写 CRAWL_MCP_COOKIES 环境变量（全局兜底，不经本目录）

Chrome cookie 解密（Linux）：
- v10：无 keyring，固定 key（PBKDF2 "peanuts"/"saltysalt"），直接可解
- v11/v20：key 在 gnome-keyring（secretstorage），keyring 锁定时解不了——
  报错提示解锁后重试，或改用 playwright codegen 导出
"""

import hashlib
import json
import logging
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BROWSERS = ("chrome", "chromium", "firefox")


def auth_dir() -> Path:
    """登录态目录（每次读取，便于测试与运行中调整）"""
    return Path(os.getenv("CRAWL_MCP_AUTH_DIR", "~/.crawl_mcp/auth")).expanduser()


def _registrable(host: str) -> str:
    """host → 注册域（最后两段）。

    ponytail: 最后两段对 co.uk / com.cn 这类二级后缀会切错，
    需要精确时再引 tldextract。
    """
    parts = host.lstrip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def domain_matches(host: str, cookie_domain: str) -> bool:
    """cookie domain（可能带前导点）是否覆盖 host"""
    d = cookie_domain.lstrip(".").lower()
    h = host.lower()
    return h == d or h.endswith(f".{d}")


def load_state(path: Path) -> dict:
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or "cookies" not in state:
        raise ValueError(f"{path} 不是 storage_state 格式（缺 cookies 键）")
    return state


def list_auths() -> list[dict]:
    """扫描目录，返回每个登录态的名称/域名/cookie 数/更新时间"""
    out = []
    d = auth_dir()
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            state = load_state(p)
        except (ValueError, json.JSONDecodeError, OSError) as e:
            out.append({"name": p.stem, "error": str(e)})
            continue
        domains = sorted(
            {
                c.get("domain", "").lstrip(".")
                for c in state.get("cookies", [])
                if c.get("domain")
            }
        )
        out.append(
            {
                "name": p.stem,
                "path": str(p),
                "domains": domains,
                "cookies": len(state.get("cookies", [])),
                "origins": len(state.get("origins", [])),
                "mtime": p.stat().st_mtime,
            }
        )
    return out


def match_auth_files(urls: list[str]) -> list[Path]:
    """找出 cookies domain 覆盖任一 URL host 的登录态文件"""
    hosts = [urlparse(u if "//" in u else f"https://{u}").hostname or "" for u in urls]
    matched = []
    for info in list_auths():
        if "error" in info or not info["domains"]:
            continue
        if any(domain_matches(h, d) for h in hosts if h for d in info["domains"]):
            matched.append(Path(info["path"]))
    return matched


def merged_state_for(urls: list[str]) -> dict | None:
    """合并所有匹配 URL 的登录态为一个 storage_state dict（无匹配返回 None）"""
    files = match_auth_files(urls)
    if not files:
        return None
    cookies: list[dict] = []
    origins: list[dict] = []
    for p in files:
        try:
            state = load_state(p)
        except (ValueError, json.JSONDecodeError, OSError):
            continue
        cookies.extend(state.get("cookies", []))
        origins.extend(state.get("origins", []))
    if not cookies and not origins:
        return None
    # 同名 cookie 后写覆盖先写（更晚的文件优先级高，按文件名排序稳定）
    seen: dict[tuple[str, str], dict] = {}
    for c in cookies:
        seen[(c.get("name", ""), c.get("domain", ""))] = c
    return {"cookies": list(seen.values()), "origins": origins}


# ── 从本地浏览器导入 ────────────────────────────────────────────


def _profile_dirs(browser: str) -> list[Path]:
    home = Path.home()
    if browser == "firefox":
        base = home / ".mozilla/firefox"
        if not base.is_dir():
            return []
        return [
            d / "cookies.sqlite"
            for d in base.iterdir()
            if d.is_dir() and (d / "cookies.sqlite").is_file()
        ]
    conf = (
        home / ".config/google-chrome"
        if browser == "chrome"
        else home / ".config/chromium"
    )
    out = []
    if conf.is_dir():
        for d in sorted(conf.iterdir()):
            db = d / "Cookies"
            if d.is_dir() and db.is_file():
                out.append(db)
    return out


def _copy_db(src: Path) -> Path:
    """SQLite 被浏览器锁着，复制一份再读"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.write(src.read_bytes())
    tmp.close()
    return Path(tmp.name)


def _import_firefox(sites: list[str] | None) -> dict[str, list[dict]]:
    """Firefox cookies.sqlite 是明文，直接读。返回 {注册域: [cookie, ...]}"""
    by_site: dict[str, list[dict]] = {}
    for db in _profile_dirs("firefox"):
        try:
            con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
            rows = con.execute(
                "SELECT host, name, value, path, expiry, isSecure, isHttpOnly,"
                " sameSite FROM moz_cookies"
            ).fetchall()
            con.close()
        except sqlite3.Error as e:
            logger.warning("读取 %s 失败: %s", db, e)
            continue
        _rows_to_cookies(by_site, rows, sites, _ff_cookie)
    return by_site


def _ff_cookie(r) -> dict:
    host, name, value, path, expiry, secure, httponly, samesite = r
    return {
        "name": name,
        "value": value,
        "domain": host,
        "path": path or "/",
        "expires": expiry or -1,
        "secure": bool(secure),
        "httpOnly": bool(httponly),
        "sameSite": {0: "None", 1: "Lax", 2: "Strict"}.get(samesite, "Lax"),
    }


def _import_chrome(sites: list[str] | None) -> dict[str, list[dict]]:
    """Chrome/Chromium：value 列明文直取，encrypted_value 解 v10/v11。"""
    _KEYRING_FAILED = object()
    key_v11 = None  # 未尝试取 keyring；失败后置 _KEYRING_FAILED，只试一次
    by_site: dict[str, list[dict]] = {}
    for db in _profile_dirs(_chrome_family()):
        local = _copy_db(db)
        try:
            con = sqlite3.connect(str(local))
            rows = con.execute(
                "SELECT host_key, name, value, encrypted_value, path,"
                " expires_utc, is_secure, is_httponly, samesite FROM cookies"
            ).fetchall()
            con.close()
        except sqlite3.Error as e:
            logger.warning("读取 %s 失败: %s", db, e)
            local.unlink(missing_ok=True)
            continue
        local.unlink(missing_ok=True)
        for r in rows:
            host, name, value, enc, path, expires_utc, secure, httponly, samesite = r
            if enc:
                if key_v11 is None:
                    key_v11 = _chrome_keyring_password() or _KEYRING_FAILED
                value = _decrypt_chrome(
                    enc,
                    None if key_v11 is _KEYRING_FAILED else key_v11,
                )
                if value is None:
                    continue  # 解不了（如 v11 且 keyring 锁定），跳过该条
            if not value:
                continue
            cookie = {
                "name": name,
                "value": value,
                "domain": host,
                "path": path or "/",
                "expires": _chrome_unix(expires_utc),
                "secure": bool(secure),
                "httpOnly": bool(httponly),
                "sameSite": _chrome_samesite(samesite),
            }
            _keep(by_site, cookie, sites)
    return by_site


def _chrome_family() -> str:
    return "chrome"


def _rows_to_cookies(by_site, rows, sites, to_cookie):
    for r in rows:
        _keep(by_site, to_cookie(r), sites)


def _keep(by_site: dict, cookie: dict, sites: list[str] | None) -> None:
    domain = cookie.get("domain", "")
    site = _registrable(domain)
    if not site or (sites and not any(s in site or site in s for s in sites)):
        return
    if cookie.get("expires", -1) != -1 and cookie["expires"] < _now():
        return  # 过期 cookie 不导
    by_site.setdefault(site, []).append(cookie)


def _now() -> float:
    import time

    return time.time()


def _chrome_unix(expires_utc) -> float:
    """Chrome 1601 纪元微秒 → unix 秒；0 表示会话 cookie"""
    if not expires_utc:
        return -1
    return expires_utc / 1_000_000 - 11_644_473_600


def _chrome_samesite(raw) -> str:
    if isinstance(raw, str):  # 新版存文本
        return {
            "no_restriction": "None",
            "lax": "Lax",
            "strict": "Strict",
        }.get(raw.lower(), "Lax")
    return {1: "None", 2: "Lax", 3: "Strict"}.get(raw, "Lax")


def _chrome_keyring_password() -> bytes | None:
    """从 gnome-keyring 取 Chrome Safe Storage 密码（v11 用）。锁住/缺失返回 None。"""
    try:
        import secretstorage
    except ImportError:
        logger.warning(
            "secretstorage 未安装，v11 cookie 解不了（pip install secretstorage）"
        )
        return None
    try:
        bus = secretstorage.dbus_init()
        col = secretstorage.get_default_collection(bus)
        if col.is_locked():
            logger.warning(
                "keyring 锁定，v11 cookie 解不了；解锁后重试或用 playwright codegen 导出"
            )
            return None
        for item in col.get_all_items():
            if item.get_label() == "Chrome Safe Storage":
                return item.get_secret()
    except Exception as e:  # D-Bus 不可用等
        logger.warning("读取 keyring 失败: %s", e)
    return None


def _decrypt_chrome(blob: bytes, keyring_password: bytes | None) -> str | None:
    """解 Chrome encrypted_value。v10 固定 key，v11 用 keyring 密码派生。"""
    prefix = bytes(blob[:3])
    try:
        if prefix == b"v10":
            key = hashlib.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, 16)
        elif prefix == b"v11":
            if not keyring_password:
                return None
            key = hashlib.pbkdf2_hmac("sha1", keyring_password, b"saltysalt", 1, 16)
        else:  # v20 等更新格式
            logger.warning(
                "暂不支持的 cookie 加密版本 %r（用 playwright codegen 导出）", prefix
            )
            return None
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
        plain = dec.update(blob[3:]) + dec.finalize()
        plain = plain[: -plain[-1]]  # 去 PKCS7 填充
        # 新版 Chrome 在值前拼了 32 字节 SHA256(host)，启发式剥掉
        if len(plain) > 32 and any(b > 0x7F or b < 0x20 for b in plain[:32]):
            plain = plain[32:]
        return plain.decode("utf-8", "replace")
    except Exception as e:
        logger.warning("解密 cookie 失败: %s", e)
        return None


def import_from_browser(browser: str, sites: list[str] | None = None) -> dict:
    """从本地浏览器导入 cookie 到登录态目录，返回摘要。

    browser: chrome / chromium / firefox
    sites:   只导这些站点（子串匹配注册域），None = 全部

    装了 rookie-cookies（pip install rookie-cookies，Rust 核心）时优先用它——
    覆盖 KWallet、Windows v20 ABE、Edge/Brave 等更多浏览器；未安装或读取失败
    回落到本模块内置实现（sqlite + v10/v11 解密）。
    """
    if browser not in BROWSERS:
        raise ValueError(f"不支持的浏览器 {browser!r}，可选: {', '.join(BROWSERS)}")
    by_site = _try_rookie(browser, sites)
    if by_site is None:
        if sys.platform not in ("linux", "linux2"):
            # 内置解析只写了 Linux 的 profile 路径和加密格式
            # （v10 peanuts / v11 keyring）；Windows 的 DPAPI/App-Bound v20、
            # macOS 的 Keychain 都在 rookie-cookies 里
            return {
                "imported": 0,
                "files": [],
                "reason": (
                    f"此平台（{sys.platform}）需要 rookie-cookies 引擎："
                    "pip install rookie-cookies"
                ),
            }
        by_site = (
            _import_firefox(sites) if browser == "firefox" else _import_chrome(sites)
        )
    if not by_site:
        return {"imported": 0, "files": [], "reason": "没有读到任何可用 cookie"}

    d = auth_dir()
    d.mkdir(parents=True, exist_ok=True)
    written = []
    for site, cookies in sorted(by_site.items()):
        # 已有同名文件（如 codegen 导出的完整登录态）不覆盖——那个含 localStorage，更全
        path = d / f"{site}.json"
        if path.exists():
            logger.info("%s 已存在，跳过（不覆盖既有登录态）", path.name)
            continue
        path.write_text(
            json.dumps(
                {"cookies": cookies, "origins": []}, ensure_ascii=False, indent=1
            ),
            encoding="utf-8",
        )
        written.append({"site": site, "cookies": len(cookies), "path": str(path)})
    return {"imported": len(written), "files": written}


def _try_rookie(browser: str, sites: list[str] | None) -> dict[str, list[dict]] | None:
    """rookie-cookies 引擎：装了就用（多浏览器/多密钥后端），失败返回 None 回落内置。"""
    try:
        import rookie_cookies as rc
    except ImportError:
        return None
    try:
        # 0.6 的 read() 无域名过滤（extract 尚未随 wheel 发布），--site 在 _keep 侧过滤；
        # keyring 锁定时 Rust 侧逐条重试密钥后端会慢，但该场景最终异常回落内置实现
        rows = rc.read(browser=browser).as_list()
    except Exception as e:
        # 典型：Linux Chrome v11 且 login keyring 锁定（Secret Service 搜不到条目）
        logger.warning("rookie-cookies 读取失败，回落内置实现: %s", str(e)[:300])
        return None
    by_site: dict[str, list[dict]] = {}
    for c in rows:
        cookie = _rookie_cookie(c)
        if cookie:
            _keep(by_site, cookie, sites)
    return by_site


_SAMESITE_MAP = {
    "strict": "Strict",
    "lax": "Lax",
    "none": "None",
    "no_restriction": "None",
    "unspecified": "Lax",
}


def _rookie_cookie(c: dict) -> dict | None:
    """rookie 输出（playwright 风格 dict）→ storage_state cookie，字段宽松映射"""
    if not c.get("name") or "value" not in c or not c.get("domain"):
        return None
    raw_ss = str(c.get("sameSite") or "").lower()
    return {
        "name": c["name"],
        "value": c["value"],
        "domain": c["domain"],
        "path": c.get("path") or "/",
        "expires": c.get("expires", -1),
        "secure": bool(c.get("secure")),
        "httpOnly": bool(c.get("httpOnly")),
        "sameSite": _SAMESITE_MAP.get(raw_ss, "Lax"),
    }
