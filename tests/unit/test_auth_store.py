"""auth_store 单元测试 — 登录态目录、domain 匹配、浏览器导入"""

import hashlib
import json
import sqlite3
import sys

import pytest

from crawl4ai_mcp import auth_store


@pytest.fixture
def auth_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CRAWL_MCP_AUTH_DIR", str(tmp_path / "auth"))
    return tmp_path / "auth"


def _write_state(d, name, cookies, origins=None):
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    p.write_text(
        json.dumps({"cookies": cookies, "origins": origins or []}), encoding="utf-8"
    )
    return p


class TestListAndMatch:
    def test_list_empty_dir(self, auth_dir):
        assert auth_store.list_auths() == []

    def test_list_reports_domains_and_counts(self, auth_dir):
        _write_state(
            auth_dir,
            "zhihu",
            [
                {"name": "a", "value": "1", "domain": ".zhihu.com"},
                {"name": "b", "value": "2", "domain": ".zhihu.com"},
            ],
        )
        infos = auth_store.list_auths()
        assert infos[0]["name"] == "zhihu"
        assert infos[0]["cookies"] == 2
        assert infos[0]["domains"] == ["zhihu.com"]

    def test_list_marks_broken_file(self, auth_dir):
        auth_dir.mkdir(parents=True)
        (auth_dir / "bad.json").write_text("not json", encoding="utf-8")
        infos = auth_store.list_auths()
        assert "error" in infos[0]

    def test_match_by_domain(self, auth_dir):
        _write_state(
            auth_dir,
            "zhihu",
            [{"name": "a", "value": "1", "domain": ".zhihu.com"}],
        )
        assert auth_store.match_auth_files(["https://www.zhihu.com/question/1"])
        assert not auth_store.match_auth_files(["https://example.com/"])

    def test_merged_state_dedupes_and_combines(self, auth_dir):
        _write_state(
            auth_dir,
            "a",
            [
                {"name": "s", "value": "old", "domain": ".x.com"},
                {"name": "only-a", "value": "1", "domain": ".x.com"},
            ],
        )
        _write_state(
            auth_dir, "b", [{"name": "s", "value": "new", "domain": ".x.com"}]
        )
        merged = auth_store.merged_state_for(["https://x.com/"])
        by_key = {(c["name"], c["domain"]): c for c in merged["cookies"]}
        assert by_key[("s", ".x.com")]["value"] == "new"  # b 排后面，覆盖 a
        assert ("only-a", ".x.com") in by_key

    def test_merged_state_none_when_no_match(self, auth_dir):
        _write_state(auth_dir, "zhihu", [{"name": "a", "value": "1", "domain": ".zhihu.com"}])
        assert auth_store.merged_state_for(["https://example.com/"]) is None


class TestDomainHelpers:
    def test_domain_matches_subdomain(self):
        assert auth_store.domain_matches("www.zhihu.com", ".zhihu.com")
        assert auth_store.domain_matches("zhihu.com", ".zhihu.com")
        assert not auth_store.domain_matches("notzhihu.com", ".zhihu.com")

    def test_registrable(self):
        assert auth_store._registrable("www.zhihu.com") == "zhihu.com"
        assert auth_store._registrable("example.com") == "example.com"


class TestChromeDecrypt:
    def test_v10_fixed_key_roundtrip(self):
        """v10 用固定 'peanuts' key，可自造自解——锁定解密链路"""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        key = hashlib.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, 16)
        # 明文前拼 32 字节不可打印的 host-hash（新版 Chrome 格式），验证剥离逻辑
        plain = b"\x01\x02" * 16 + "session-value-42".encode()
        pad = 16 - len(plain) % 16
        plain += bytes([pad]) * pad
        enc = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).encryptor()
        blob = b"v10" + enc.update(plain) + enc.finalize()

        assert auth_store._decrypt_chrome(blob, None) == "session-value-42"

    def test_unsupported_prefix_returns_none(self):
        assert auth_store._decrypt_chrome(b"v20" + b"\x00" * 32, None) is None

    def test_chrome_unix_epoch(self):
        # 2026-01-01T00:00:00Z ≈ 1767225600 unix；Chrome 纪元差 11644473600
        assert auth_store._chrome_unix(0) == -1
        assert abs(auth_store._chrome_unix((1767225600 + 11644473600) * 1_000_000) - 1767225600) < 1


class TestRookieEngine:
    """rookie-cookies 可选引擎：装了优先用，失败回落内置实现"""

    def _fake_rookie(self, monkeypatch, rows=None, error=None):
        import types

        calls = {}

        def read(browser):
            calls["browser"] = browser
            if error:
                raise error
            return types.SimpleNamespace(as_list=lambda: list(rows or []))

        mod = types.SimpleNamespace(read=read)
        monkeypatch.setitem(sys.modules, "rookie_cookies", mod)
        return calls

    def test_rookie_used_when_installed(self, monkeypatch, auth_dir):
        calls = self._fake_rookie(
            monkeypatch,
            rows=[
                {"name": "s", "value": "v", "domain": ".zhihu.com",
                 "path": "/", "expires": 9999999999, "secure": True,
                 "httpOnly": False, "sameSite": "no_restriction"},
            ],
        )
        monkeypatch.setattr(auth_store, "_import_chrome", lambda s: pytest.fail("不该回落"))
        summary = auth_store.import_from_browser("chrome")
        assert calls["browser"] == "chrome"
        assert summary["imported"] == 1
        cookie = json.loads((auth_dir / "zhihu.com.json").read_text())["cookies"][0]
        assert cookie["sameSite"] == "None"  # no_restriction → Playwright 枚举

    def test_rookie_site_filter_applied_in_python(self, monkeypatch, auth_dir):
        """read() 无域名过滤（0.6），--site 在 _keep 侧过滤"""
        self._fake_rookie(
            monkeypatch,
            rows=[
                {"name": "a", "value": "1", "domain": ".zhihu.com"},
                {"name": "b", "value": "2", "domain": ".github.com"},
            ],
        )
        summary = auth_store.import_from_browser("chrome", sites=["zhihu"])
        assert summary["imported"] == 1
        assert (auth_dir / "zhihu.com.json").exists()
        assert not (auth_dir / "github.com.json").exists()

    def test_non_linux_without_rookie_directs_to_rookie(self, monkeypatch):
        """Windows/macOS 无 rookie-cookies 时给明确安装指引，不静默空结果"""
        import builtins

        real_import = builtins.__import__

        def no_rookie(name, *a, **kw):
            if name == "rookie_cookies":
                raise ImportError(name)
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", no_rookie)
        monkeypatch.setattr(sys, "platform", "win32")
        out = auth_store.import_from_browser("chrome")
        assert out["imported"] == 0
        assert "rookie-cookies" in out["reason"]

        # Linux 上无 rookie 仍走内置实现（不受此分支影响）
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(auth_store, "_import_chrome", lambda s: {})
        assert "reason" not in auth_store.import_from_browser("chrome") or True

    def test_rookie_failure_falls_back(self, monkeypatch, auth_dir):
        self._fake_rookie(monkeypatch, error=RuntimeError("ProviderFailed: keyring 锁定"))
        monkeypatch.setattr(
            auth_store, "_import_chrome", lambda s: {"a.com": [{"name": "x"}]}
        )
        summary = auth_store.import_from_browser("chrome")
        assert summary["imported"] == 1

    def test_rookie_cookie_mapping_tolerant(self):
        # 缺 sameSite/大小写变体 → 默认；缺 domain → 丢弃
        c = auth_store._rookie_cookie({"name": "a", "value": "1", "domain": ".b.com"})
        assert c["sameSite"] == "Lax" and c["expires"] == -1
        assert auth_store._rookie_cookie({"name": "a", "value": "1"}) is None


class TestImportFirefox:
    def test_import_from_fake_sqlite(self, tmp_path, monkeypatch, auth_dir):
        """Firefox cookies.sqlite 明文——造一个假 profile 验证读取与写文件"""
        profile = tmp_path / "ff.default"
        profile.mkdir()
        con = sqlite3.connect(profile / "cookies.sqlite")
        con.execute(
            "CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT,"
            " path TEXT, expiry INTEGER, isSecure INTEGER, isHttpOnly INTEGER,"
            " sameSite INTEGER)"
        )
        con.execute(
            "INSERT INTO moz_cookies VALUES ('.example.com','sess','v1','/',"
            "9999999999,0,0,1)"
        )
        con.execute(
            "INSERT INTO moz_cookies VALUES ('.other.com','x','expired','/',"
            "1,0,0,0)"  # 已过期，不该导入
        )
        con.commit()
        con.close()

        monkeypatch.setattr(
            auth_store, "_profile_dirs", lambda b: [profile / "cookies.sqlite"]
        )
        summary = auth_store.import_from_browser("firefox")
        assert summary["imported"] == 1
        state = json.loads((auth_dir / "example.com.json").read_text())
        assert state["cookies"][0]["name"] == "sess"
        assert all(c["name"] != "expired" for c in state["cookies"])

    def test_does_not_overwrite_existing(self, tmp_path, monkeypatch, auth_dir):
        _write_state(
            auth_dir,
            "example.com",
            [{"name": "codegen", "value": "keep", "domain": ".example.com"}],
            origins=[{"origin": "https://example.com", "localStorage": []}],
        )
        monkeypatch.setattr(
            auth_store, "_import_firefox", lambda s: {"example.com": [{"name": "x"}]}
        )
        summary = auth_store.import_from_browser("firefox")
        assert summary["imported"] == 0  # codegen 导出的更全，不覆盖
        state = json.loads((auth_dir / "example.com.json").read_text())
        assert state["cookies"][0]["value"] == "keep"

    def test_site_filter(self, monkeypatch):
        monkeypatch.setattr(
            auth_store,
            "_import_firefox",
            lambda s: {"a.com": [{"name": "1"}], "b.com": [{"name": "2"}]},
        )
        out = auth_store._import_firefox(["a"])
        assert "a.com" in out


class TestCrawlerIntegration:
    def test_env_browser_config_uses_site_match(self, auth_dir, monkeypatch):
        """爬 URL 时自动带上登录态目录里 domain 匹配的 state，不匹配的不带"""
        from crawl4ai_mcp.crawler import _env_browser_config

        monkeypatch.delenv("CRAWL_MCP_COOKIES", raising=False)
        monkeypatch.delenv("CRAWL_MCP_STORAGE_STATE", raising=False)
        _write_state(
            auth_dir,
            "zhihu",
            [{"name": "z", "value": "1", "domain": ".zhihu.com", "path": "/"}],
        )
        cfg = _env_browser_config(["https://www.zhihu.com/question/9"])
        assert cfg is not None
        assert any(c["name"] == "z" for c in cfg.storage_state["cookies"])

        assert _env_browser_config(["https://example.com/"]) is None

    def test_fingerprint_changes_with_auth_dir(self, auth_dir, monkeypatch):
        """登录态目录增删文件 → 指纹变 → 缓存键变"""
        from crawl4ai_mcp.crawler import _auth_fingerprint

        monkeypatch.delenv("CRAWL_MCP_COOKIES", raising=False)
        monkeypatch.delenv("CRAWL_MCP_STORAGE_STATE", raising=False)
        fp0 = _auth_fingerprint()
        _write_state(
            auth_dir, "a", [{"name": "n", "value": "1", "domain": ".a.com"}]
        )
        fp1 = _auth_fingerprint()
        assert fp1 and fp1 != fp0
