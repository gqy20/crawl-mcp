"""降级策略测试：终止错误跳过降级、本机网络错误跳过浏览器、负缓存、域名记忆"""

from unittest.mock import patch

import pytest

from crawl4ai_mcp.crawler import Crawler


@pytest.fixture(autouse=True)
def _cache_on(monkeypatch, tmp_path):
    """conftest 里默认关掉了缓存，这里单独打开（测的就是缓存行为）"""
    monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
    monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path / "cache"))


# ── 终止错误：404 不值得再降级 ──────────────────────────────────


class TestTerminalErrorSkipsFallback:
    def test_404_skips_cloud_and_browser(self):
        """快速提取拿到 HTTP 404 → 不再走 Cloud 和浏览器"""
        crawler = Crawler()
        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={
                    "success": False,
                    "content": "",
                    "error": "Failed to fetch https://x.com: HTTP 404",
                },
            ),
            patch.object(crawler, "_cloud_fallback") as cloud,
            patch.object(crawler, "_crawl") as browser,
        ):
            result = crawler.crawl_single("https://x.com/gone")

        assert result["success"] is False
        assert result["error_code"] == "http_404"
        assert "跳过降级" in result["fallback_reason"]
        cloud.assert_not_called()
        browser.assert_not_called()

    def test_404_returns_actionable_hint(self):
        crawler = Crawler()
        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={"success": False, "content": "", "error": "HTTP 404"},
            ),
            patch.object(crawler, "_crawl"),
        ):
            result = crawler.crawl_single("https://x.com/gone")
        assert result["hint"]

    def test_403_still_falls_back(self):
        """403 只是被拒，不是死路：仍要降级"""
        crawler = Crawler()
        browser_result = {
            "success": True,
            "markdown": "# ok",
            "title": "t",
            "error": None,
        }
        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={
                    "success": False,
                    "content": "",
                    "error": "Failed to fetch: HTTP 403",
                },
            ),
            patch.object(crawler, "_cloud_fallback", return_value=None),
            patch.object(crawler, "_crawl", return_value=browser_result) as browser,
        ):
            result = crawler.crawl_single("https://x.com/forbidden")

        assert result["success"] is True
        assert result["method"] == "browser_fallback"
        browser.assert_called_once()


# ── 本机网络问题：Cloud 值得试，浏览器不值得 ────────────────────


class TestLocalNetworkErrorSkipsBrowser:
    def test_dns_error_skips_browser_but_tries_cloud(self):
        crawler = Crawler()
        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={
                    "success": False,
                    "content": "",
                    "error": "Could not resolve host: example.invalid",
                },
            ),
            patch.object(crawler, "_cloud_fallback", return_value=None) as cloud,
            patch.object(crawler, "_crawl") as browser,
        ):
            result = crawler.crawl_single("https://example.invalid/x")

        assert result["success"] is False
        assert result["error_code"] == "dns_error"
        cloud.assert_called_once()
        browser.assert_not_called()
        assert "跳过浏览器" in result["fallback_reason"]

    def test_timeout_still_tries_browser(self):
        """超时可能是站点慢（SPA），浏览器还有机会"""
        crawler = Crawler()
        browser_result = {
            "success": True,
            "markdown": "# ok",
            "title": "t",
            "error": None,
        }
        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={
                    "success": False,
                    "content": "",
                    "error": "Request timed out",
                },
            ),
            patch.object(crawler, "_cloud_fallback", return_value=None),
            patch.object(crawler, "_crawl", return_value=browser_result) as browser,
        ):
            result = crawler.crawl_single("https://slow.example.com")

        assert result["success"] is True
        browser.assert_called_once()


# ── 负缓存 ────────────────────────────────────────────────────


class TestNegativeCache:
    def test_failure_is_cached_and_replayed(self):
        """确定性失败第二次直接命中负缓存，不再发请求"""
        crawler = Crawler()
        failure = {
            "success": False,
            "content": "",
            "error": "Failed to fetch https://x.com: HTTP 404",
        }
        with (
            patch.object(
                crawler._searcher, "extract_url", return_value=failure
            ) as extract,
            patch.object(crawler, "_crawl"),
        ):
            first = crawler.crawl_single("https://x.com/gone")
            second = crawler.crawl_single("https://x.com/gone")

        assert first["error_code"] == "http_404"
        assert second["cached"] is True
        assert second["error_code"] == "http_404"
        assert extract.call_count == 1  # 第二次没再请求

    def test_transient_failure_is_not_cached(self):
        """超时这类波动性失败不进负缓存"""
        crawler = Crawler()
        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={"success": False, "content": "", "error": "timed out"},
            ) as extract,
            patch.object(crawler, "_cloud_fallback", return_value=None),
            patch.object(
                crawler,
                "_crawl",
                return_value={
                    "success": False,
                    "markdown": "",
                    "title": "",
                    "error": "timed out",
                },
            ),
        ):
            crawler.crawl_single("https://slow.example.com")
            crawler.crawl_single("https://slow.example.com")

        assert extract.call_count == 2


# ── 域名记忆 ──────────────────────────────────────────────────


class TestDomainMemory:
    def test_repeated_failure_skips_chain(self):
        """同域名连续 2 次确定性失败后，直接给结论"""
        crawler = Crawler()
        failure = {
            "success": False,
            "content": "",
            "error": "Failed to fetch: HTTP 404",
        }
        with (
            patch.object(
                crawler._searcher, "extract_url", return_value=failure
            ) as extract,
            patch.object(crawler, "_crawl"),
        ):
            crawler.crawl_single("https://bad.example.com/a")
            crawler.crawl_single("https://bad.example.com/b")
            third = crawler.crawl_single("https://bad.example.com/c")

        assert third["method"] == "domain_memo"
        assert third["error_code"] == "http_404"
        assert third["hint"]
        assert extract.call_count == 2  # 第三次没再请求

    def test_other_domain_not_affected(self):
        crawler = Crawler()
        failure = {
            "success": False,
            "content": "",
            "error": "Failed to fetch: HTTP 404",
        }
        with (
            patch.object(
                crawler._searcher, "extract_url", return_value=failure
            ) as extract,
            patch.object(crawler, "_crawl"),
        ):
            crawler.crawl_single("https://bad.example.com/a")
            crawler.crawl_single("https://bad.example.com/b")
            other = crawler.crawl_single("https://good.example.com/c")

        assert other.get("method") != "domain_memo"
        assert extract.call_count == 3

    def test_success_clears_domain_memo_intent(self):
        """成功过的域名不该被失败记忆连累"""
        crawler = Crawler()
        with patch.object(
            crawler._searcher,
            "extract_url",
            return_value={"success": True, "content": "x" * 500},
        ):
            result = crawler.crawl_single("https://ok.example.com/a")
        assert result["success"] is True
        assert result.get("method") != "domain_memo"


# ── 缓存命中的元信息 ──────────────────────────────────────────


class TestCacheMeta:
    def test_cached_hit_reports_age(self):
        crawler = Crawler()
        with patch.object(
            crawler._searcher,
            "extract_url",
            return_value={"success": True, "content": "x" * 500},
        ):
            crawler.crawl_single("https://x.com/a")
            hit = crawler.crawl_single("https://x.com/a")

        assert hit["cached"] is True
        assert hit["cached_age"] >= 0
        assert "timings" not in hit
