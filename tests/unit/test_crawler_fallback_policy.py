"""降级策略测试：终止错误跳过降级、本机网络错误跳过浏览器、负缓存、域名记忆"""

from unittest.mock import AsyncMock, patch

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
    def test_repeated_dns_failure_skips_chain(self):
        """同域名连续 2 次域名级故障（DNS）后，直接给结论"""
        crawler = Crawler()
        failure = {
            "success": False,
            "content": "",
            "error": "Could not resolve host: bad.invalid",
        }
        with (
            patch.object(
                crawler._searcher, "extract_url", return_value=failure
            ) as extract,
            patch.object(crawler, "_cloud_fallback", return_value=None),
            patch.object(crawler, "_crawl"),
        ):
            crawler.crawl_single("https://bad.invalid/a")
            crawler.crawl_single("https://bad.invalid/b")
            third = crawler.crawl_single("https://bad.invalid/c")

        assert third["method"] == "domain_memo"
        assert third["error_code"] == "dns_error"
        assert third["hint"]
        assert extract.call_count == 2  # 第三次没再请求

    def test_other_domain_not_affected(self):
        crawler = Crawler()
        failure = {
            "success": False,
            "content": "",
            "error": "Could not resolve host: bad.invalid",
        }
        with (
            patch.object(
                crawler._searcher, "extract_url", return_value=failure
            ) as extract,
            patch.object(crawler, "_cloud_fallback", return_value=None),
            patch.object(crawler, "_crawl"),
        ):
            crawler.crawl_single("https://bad.invalid/a")
            crawler.crawl_single("https://bad.invalid/b")
            other = crawler.crawl_single("https://good.example.com/c")

        assert other.get("method") != "domain_memo"
        assert extract.call_count == 3

    @pytest.mark.parametrize(
        "error", ["Failed to fetch: HTTP 404", "Near-empty content (66 bytes)"]
    )
    def test_path_level_failure_does_not_pollute_domain(self, error):
        """404/empty_content 是路径级问题：同站两条路径失败，
        不能连累第三条路径（cas.cn/tzgg 空模板误伤 cas.cn 首页的回归）"""
        crawler = Crawler()
        failure = {"success": False, "content": "", "error": error}
        browser_failure = {
            "success": False,
            "markdown": "",
            "title": "",
            "error": error,
        }
        with (
            patch.object(
                crawler._searcher, "extract_url", return_value=failure
            ) as extract,
            patch.object(crawler, "_cloud_fallback", return_value=None),
            patch.object(crawler, "_crawl", return_value=browser_failure),
        ):
            crawler.crawl_single("https://cas.cn/tzgg/a")
            crawler.crawl_single("https://cas.cn/tzgg/b")
            third = crawler.crawl_single("https://cas.cn/")

        assert third.get("method") != "domain_memo"
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


# ── 批量路径的同类问题 ────────────────────────────────────────


class TestBatchFallbackPolicy:
    def test_dns_error_keeps_original_error_and_skips_browser(self):
        """批量 skip_browser 分支要保留快速提取的原始错误，
        否则收尾归类只能得到 unknown"""
        crawler = Crawler()
        failure = {
            "success": False,
            "content": "",
            "error": "Could not resolve host: bad.invalid",
        }
        with (
            patch.object(
                crawler,
                "_parallel_fast_extract",
                new=AsyncMock(return_value=[failure]),
            ),
            patch.object(
                crawler, "_parallel_cloud_scrape", new=AsyncMock(return_value=[None])
            ),
            patch.object(crawler, "_browser_crawl_subset", new=AsyncMock()) as browser,
        ):
            results = crawler.crawl_batch(["https://bad.invalid/a"])

        r = results[0]
        assert r["success"] is False
        assert r["error_code"] == "dns_error"
        assert "Could not resolve" in r["error"]
        browser.assert_not_called()

    def test_cached_hit_not_reprocessed_by_llm(self, monkeypatch):
        """缓存命中已带 LLM 字段（缓存键含 llm 配置），不能重复调 LLM"""
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "test_key")
        crawler = Crawler()
        ok = {"success": True, "content": "x" * 500}
        llm = {"instruction": "总结"}
        with (
            patch.object(
                crawler, "_parallel_fast_extract", new=AsyncMock(return_value=[ok])
            ),
            patch.object(
                crawler,
                "_postprocess_batch_with_llm",
                new=AsyncMock(return_value=[{"summary": "s"}]),
            ) as llm_mock,
        ):
            first = crawler.crawl_batch(["https://x.com/a"], llm_config=llm)
            second = crawler.crawl_batch(["https://x.com/a"], llm_config=llm)

        assert first[0]["llm_summary"] == "s"
        assert second[0]["cached"] is True
        assert second[0]["llm_summary"] == "s"
        assert llm_mock.call_count == 1


# ── 浏览器重试预算 ────────────────────────────────────────────


class TestBrowserRetryBudget:
    def test_retry_stops_when_budget_exhausted(self, monkeypatch):
        """网络错误重试不能无限退避：预算用尽直接抛出，不再重试"""
        import crawl4ai_mcp.crawler as mod
        from crawl4ai_mcp.utils import run_async

        monkeypatch.setattr(mod, "BROWSER_RETRY_BUDGET", 0)
        crawler = Crawler()
        fake = AsyncMock()
        fake.__aenter__.return_value = fake  # async with 拿到的就是它自己
        fake.arun.side_effect = Exception("net::ERR_TIMED_OUT")
        with patch("crawl4ai.AsyncWebCrawler", return_value=fake):
            with pytest.raises(Exception, match="ERR_TIMED_OUT"):
                run_async(crawler._crawl("https://x.com"))

        assert fake.arun.call_count == 1  # 没有预算就不重试
