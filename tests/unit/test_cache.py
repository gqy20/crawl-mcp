"""磁盘缓存的单元测试"""

from crawl4ai_mcp import cache


class TestCache:
    def test_put_and_get(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        cache.put("fast", "https://a.com", {"success": True, "content": "x"})
        assert cache.get("fast", "https://a.com") == {
            "success": True,
            "content": "x",
        }

    def test_missing_key_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        assert cache.get("fast", "https://nope.com") is None

    def test_namespace_isolated(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        cache.put("fast", "https://a.com", {"v": 1})
        assert cache.get("crawl", "https://a.com") is None

    def test_opts_differ_key(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        cache.put("crawl", "https://a.com", {"v": 1}, {"prefer_fast": True})
        cache.put("crawl", "https://a.com", {"v": 2}, {"prefer_fast": False})
        assert cache.get("crawl", "https://a.com", {"prefer_fast": True}) == {"v": 1}
        assert cache.get("crawl", "https://a.com", {"prefer_fast": False}) == {"v": 2}

    def test_expired_entry_dropped(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CRAWL_MCP_CACHE_TTL", "0")
        cache.put("fast", "https://a.com", {"v": 1})
        assert cache.get("fast", "https://a.com") is None

    def test_disabled_cache(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CRAWL_MCP_CACHE", "0")
        cache.put("fast", "https://a.com", {"v": 1})
        assert cache.get("fast", "https://a.com") is None

    def test_clear_removes_entries(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        cache.put("fast", "https://a.com", {"v": 1})
        cache.put("fast", "https://b.com", {"v": 2})
        assert cache.clear() == 2
        assert cache.get("fast", "https://a.com") is None
