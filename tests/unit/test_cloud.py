"""Crawl4AI Cloud 兜底路径测试"""

import itertools
import time

import httpx
import pytest

from crawl4ai_mcp import cloud
from crawl4ai_mcp.crawler import Crawler


@pytest.fixture(autouse=True)
def _reset_key_counter(monkeypatch):
    """重置轮询计数器，让 key 轮换顺序在测试里确定"""
    monkeypatch.setattr(cloud, "_key_counter", itertools.count())


@pytest.fixture
def cloud_key(monkeypatch):
    monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_live_test")
    monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "1")
    return "sk_live_test"


def _mock_post(monkeypatch, status=200, payload=None, text=""):
    """替换 httpx.post，返回固定响应"""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})

        def _resp():
            r = httpx.Response(status)
            if payload is not None:
                r._content = __import__("json").dumps(payload).encode()
            else:
                r._content = text.encode()
            return r

        return _resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def _mock_post_by_key(monkeypatch, responses):
    """按 Authorization 里的 key 返回不同响应

    responses: {key: (status, payload)}
    """
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        key = headers["Authorization"].removeprefix("Bearer ")
        calls.append(key)
        status, payload = responses.get(key, (404, None))

        def _resp():
            r = httpx.Response(status)
            r._content = __import__("json").dumps(payload or {}).encode()
            return r

        return _resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


class TestCloudModule:
    def test_disabled_without_key(self, monkeypatch):
        monkeypatch.delenv("CRAWL4AI_API_KEY", raising=False)
        monkeypatch.delenv("CRAWL4AI_CLOUD_KEY", raising=False)
        monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "1")
        assert cloud.cloud_enabled() is False

    def test_disabled_by_flag(self, cloud_key, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "0")
        assert cloud.cloud_enabled() is False

    def test_enabled_with_key(self, cloud_key):
        assert cloud.cloud_enabled() is True

    def test_scrape_success(self, cloud_key, monkeypatch):
        calls = _mock_post(
            monkeypatch,
            payload={
                "ok": True,
                "markdown": "# Title\n\nbody",
                "html": "<html><title>Title</title></html>",
            },
        )
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is True
        assert "# Title" in result["markdown"]
        assert calls[0]["headers"]["Authorization"] == "Bearer sk_live_test"
        assert calls[0]["json"]["url"] == "https://example.com"

    def test_scrape_http_error(self, cloud_key, monkeypatch):
        _mock_post(monkeypatch, status=429, text="rate limited")
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is False
        assert "429" in result["error"]

    def test_scrape_not_ok_payload(self, cloud_key, monkeypatch):
        _mock_post(monkeypatch, payload={"ok": False, "error": "no_credit"})
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is False
        assert "no_credit" in result["error"]

    def test_scrape_empty_markdown(self, cloud_key, monkeypatch):
        _mock_post(monkeypatch, payload={"ok": True, "markdown": "  "})
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is False

    def test_scrape_network_error(self, cloud_key, monkeypatch):
        def boom(*args, **kwargs):
            raise httpx.ConnectError("nope")

        monkeypatch.setattr(httpx, "post", boom)
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is False
        assert "Cloud 请求失败" in result["error"]


class TestMultiKeyRotation:
    """多 key：逗号分隔、轮询分配、402/429 自动换 key"""

    def test_keys_parsed_from_comma(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a, sk_b ,sk_c")
        assert cloud.get_cloud_keys() == ["sk_a", "sk_b", "sk_c"]

    def test_single_key(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a")
        assert cloud.get_cloud_keys() == ["sk_a"]

    def test_round_robin_across_keys(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a,sk_b")
        monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "1")
        calls = _mock_post_by_key(
            monkeypatch,
            {
                "sk_a": (200, {"ok": True, "markdown": "A"}),
                "sk_b": (200, {"ok": True, "markdown": "B"}),
            },
        )
        for _ in range(4):
            cloud.cloud_scrape("https://example.com")
        # 4 次调用在两个 key 间均摊
        assert calls.count("sk_a") == 2
        assert calls.count("sk_b") == 2

    def test_switch_key_on_402_no_credit(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a,sk_b")
        monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "1")
        calls = _mock_post_by_key(
            monkeypatch,
            {
                "sk_a": (402, {"error": "no_credit"}),
                "sk_b": (200, {"ok": True, "markdown": "B"}),
            },
        )
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is True
        assert calls == ["sk_a", "sk_b"]

    def test_switch_key_on_429_rate_limited(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a,sk_b")
        monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "1")
        calls = _mock_post_by_key(
            monkeypatch,
            {
                "sk_a": (429, {"error": "rate"}),
                "sk_b": (200, {"ok": True, "markdown": "B"}),
            },
        )
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is True
        assert calls == ["sk_a", "sk_b"]

    def test_no_switch_on_other_error(self, monkeypatch):
        """404（URL 问题）换 key 也没用，不重试"""
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a,sk_b")
        monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "1")
        calls = _mock_post_by_key(monkeypatch, {})
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is False
        assert calls == ["sk_a"]

    def test_all_keys_exhausted(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a,sk_b")
        monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "1")
        calls = _mock_post_by_key(
            monkeypatch,
            {
                "sk_a": (402, {"error": "no_credit"}),
                "sk_b": (402, {"error": "no_credit"}),
            },
        )
        result = cloud.cloud_scrape("https://example.com")
        assert result["success"] is False
        assert len(calls) == 2
        assert "402" in result["error"]


class TestCloudBudget:
    """兜底路径的整段预算：超时就把位置让给浏览器，不要干等"""

    def test_budget_caps_attempt_timeout(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a")
        seen = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            seen["timeout"] = timeout
            raise RuntimeError("boom")

        monkeypatch.setattr("httpx.post", fake_post)
        cloud.cloud_scrape("https://example.com", timeout=30.0, budget=5.0)
        assert seen["timeout"] <= 5.0

    def test_budget_stops_before_second_key(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a,sk_b")
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append(headers["Authorization"])
            time.sleep(0.2)
            raise RuntimeError("boom")

        monkeypatch.setattr("httpx.post", fake_post)
        result = cloud.cloud_scrape("https://example.com", timeout=30.0, budget=0.05)
        assert result["success"] is False
        # 预算耗尽后不再尝试第二个 key
        assert len(calls) <= 1

    def test_no_budget_keeps_full_timeout(self, monkeypatch):
        monkeypatch.setenv("CRAWL4AI_API_KEY", "sk_a")
        seen = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            seen["timeout"] = timeout
            raise RuntimeError("boom")

        monkeypatch.setattr("httpx.post", fake_post)
        cloud.cloud_scrape("https://example.com", timeout=30.0)
        assert seen["timeout"] == 30.0


class TestCloudFallbackInCrawler:
    def test_cloud_used_when_fast_extract_fails(self, cloud_key, monkeypatch):
        """快速提取失败 → Cloud 兜底成功，不再走浏览器"""
        crawler = Crawler()
        monkeypatch.setattr(
            crawler._searcher,
            "extract_url",
            lambda url: {"success": False, "content": "", "error": "boom"},
        )
        monkeypatch.setattr(
            crawler,
            "_cloud_fallback",
            lambda url: {
                "success": True,
                "markdown": "# Cloud\n\ncontent",
                "html": "<title>Cloud</title>",
                "error": None,
            },
        )
        monkeypatch.setattr(
            crawler,
            "_crawl",
            lambda *a, **k: pytest.fail("不应走浏览器路径"),
        )

        result = crawler.crawl_single("https://example.com")
        assert result["success"] is True
        assert result["method"] == "cloud_fallback"
        assert result["title"] == "Cloud"
        assert "快速提取失败" in result["fallback_reason"]

    def test_cloud_failure_falls_through_to_browser(self, cloud_key, monkeypatch):
        """Cloud 失败 → 继续走浏览器，错误原因带入 fallback_reason"""
        crawler = Crawler()
        monkeypatch.setattr(
            crawler._searcher,
            "extract_url",
            lambda url: {"success": False, "content": "", "error": "boom"},
        )
        monkeypatch.setattr(
            crawler,
            "_cloud_fallback",
            lambda url: {
                "success": False,
                "markdown": "",
                "html": "",
                "error": "Cloud 返回 HTTP 402",
            },
        )

        async def fake_crawl(url, enhanced):
            return {
                "success": True,
                "markdown": "# Browser",
                "title": "B",
                "error": None,
            }

        monkeypatch.setattr(crawler, "_crawl", fake_crawl)

        result = crawler.crawl_single("https://example.com")
        assert result["success"] is True
        assert result["method"] == "browser_fallback"
        assert "Cloud 兜底失败" in result["fallback_reason"]

    def test_no_cloud_call_when_disabled(self, monkeypatch):
        """未启用 Cloud 时完全不发起 Cloud 调用"""
        monkeypatch.delenv("CRAWL4AI_API_KEY", raising=False)
        monkeypatch.delenv("CRAWL4AI_CLOUD_KEY", raising=False)
        crawler = Crawler()

        def fail(*args, **kwargs):
            pytest.fail("不应发起 Cloud 请求")

        monkeypatch.setattr(cloud, "cloud_scrape", fail)
        assert crawler._cloud_fallback("https://example.com") is None

    def test_batch_cloud_fallback(self, cloud_key, monkeypatch):
        """批量：快提取失败的项走 Cloud 兜底，method 标记 cloud_fallback"""
        crawler = Crawler()

        def fake_extract(url):
            if "bad" in url:
                return {"success": False, "content": "", "error": "boom"}
            return {"success": True, "content": "x" * 300, "error": None}

        monkeypatch.setattr(crawler._searcher, "extract_url", fake_extract)

        async def fake_parallel_cloud(urls):
            return [
                {
                    "success": True,
                    "markdown": "# C",
                    "html": "<title>C</title>",
                    "error": None,
                }
                for _ in urls
            ]

        monkeypatch.setattr(crawler, "_parallel_cloud_scrape", fake_parallel_cloud)
        monkeypatch.setattr(
            crawler,
            "_browser_crawl_subset",
            lambda *a, **k: pytest.fail("不应走浏览器路径"),
        )

        results = crawler.crawl_batch(["https://ok.com", "https://bad.com"])
        assert results[0]["method"] == "fast_extract"
        assert results[1]["method"] == "cloud_fallback"
        assert results[1]["success"] is True
