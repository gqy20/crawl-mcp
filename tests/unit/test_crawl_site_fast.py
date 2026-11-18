"""crawl_site 快速 BFS 路径 + crawl_cloud 统一收尾"""

from unittest.mock import AsyncMock, patch

import pytest

from crawl4ai_mcp.crawler import Crawler


@pytest.fixture(autouse=True)
def _cache_on(monkeypatch, tmp_path):
    monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
    monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path / "cache"))


def _entry(markdown="[next](/a)", method="fast_extract"):
    return {
        "success": True,
        "markdown": markdown,
        "title": "entry",
        "error": None,
        "method": method,
    }


def _page(markdown=""):
    return {"success": True, "markdown": markdown, "title": "p", "error": None}


# ── 站内链接提取 ──────────────────────────────────────────────


class TestSiteLinks:
    def test_same_site_only_and_relative_resolved(self):
        md = (
            "[a](/x) [b](https://site.com/y) [c](https://other.com/z) [d](mailto:a@b.c)"
        )
        links = Crawler()._site_links(md, "https://site.com/entry")
        assert links == ["https://site.com/x", "https://site.com/y"]

    def test_dedupes_and_strips_fragment(self):
        md = "[a](/x#top) [b](/x) [c](/x?q=1)"
        links = Crawler()._site_links(md, "https://site.com/")
        assert links == ["https://site.com/x", "https://site.com/x?q=1"]

    def test_skips_images_and_assets(self):
        md = "![img](/i.png) [logo](/l.svg) [page](/p)"
        assert Crawler()._site_links(md, "https://site.com/") == ["https://site.com/p"]


# ── 快速 BFS ──────────────────────────────────────────────────


class TestCrawlSiteFast:
    def test_static_site_uses_fast_bfs_not_browser(self):
        crawler = Crawler()
        with (
            patch.object(crawler, "crawl_single", return_value=_entry()),
            patch.object(
                crawler, "_crawl_batch", new=AsyncMock(return_value=[_page()])
            ) as batch,
            patch.object(crawler, "_crawl_site_browser", new=AsyncMock()) as bfs,
        ):
            result = crawler.crawl_site("https://site.com/", depth=1, pages=10)

        bfs.assert_not_called()
        batch.assert_awaited_once_with(["https://site.com/a"], concurrent=3)
        assert result["total_pages"] == 2
        assert result["successful_pages"] == 2
        assert result["success_rate"] == "100.0%"

    def test_pages_cap_limits_frontier(self):
        crawler = Crawler()
        entry = _entry("[a](/a) [b](/b) [c](/c)")
        with (
            patch.object(crawler, "crawl_single", return_value=entry),
            patch.object(
                crawler, "_crawl_batch", new=AsyncMock(return_value=[_page()])
            ) as batch,
            patch.object(crawler, "_crawl_site_browser", new=AsyncMock()),
        ):
            result = crawler.crawl_site("https://site.com/", depth=2, pages=2)

        batch.assert_awaited_once_with(["https://site.com/a"], concurrent=3)
        assert result["total_pages"] == 2

    def test_depth_walks_layers(self):
        crawler = Crawler()
        with (
            patch.object(crawler, "crawl_single", return_value=_entry()),
            patch.object(
                crawler,
                "_crawl_batch",
                new=AsyncMock(side_effect=[[_page("[next2](/b)")], [_page()]]),
            ) as batch,
            patch.object(crawler, "_crawl_site_browser", new=AsyncMock()),
        ):
            result = crawler.crawl_site("https://site.com/", depth=2, pages=10)

        assert [c.args[0] for c in batch.await_args_list] == [
            ["https://site.com/a"],
            ["https://site.com/b"],
        ]
        assert result["total_pages"] == 3

    def test_spa_entry_falls_back_to_browser_bfs(self):
        crawler = Crawler()
        with (
            patch.object(
                crawler, "crawl_single", return_value=_entry(method="browser_fallback")
            ),
            patch.object(crawler, "_crawl_batch", new=AsyncMock()) as batch,
            patch.object(
                crawler, "_crawl_site_browser", new=AsyncMock(return_value=[_page()])
            ) as bfs,
        ):
            result = crawler.crawl_site("https://spa.com/", depth=2, pages=10)

        batch.assert_not_called()
        bfs.assert_awaited_once_with("https://spa.com/", 2, 10, 3)
        assert result["total_pages"] == 1

    def test_failed_entry_falls_back_to_browser_bfs(self):
        crawler = Crawler()
        failed = {"success": False, "markdown": "", "title": "", "error": "HTTP 403"}
        with (
            patch.object(crawler, "crawl_single", return_value=failed),
            patch.object(
                crawler, "_crawl_site_browser", new=AsyncMock(return_value=[])
            ) as bfs,
        ):
            result = crawler.crawl_site("https://x.com/")

        bfs.assert_awaited_once()
        assert result["total_pages"] == 0
        assert result["success_rate"] == "0%"


# ── crawl_cloud 统一收尾 ──────────────────────────────────────


class TestCrawlCloudFinalize:
    def test_failure_gets_error_code_hint_timings(self):
        crawler = Crawler()
        failure = {
            "success": False,
            "markdown": "",
            "html": "",
            "error": "Cloud 返回 HTTP 404: gone",
        }
        with patch("crawl4ai_mcp.crawler.cloud_scrape", return_value=failure):
            r = crawler.crawl_cloud("https://x.com/gone")

        assert r["error_code"] == "http_404"
        assert r["hint"]
        assert "cloud" in r["timings"]

    def test_success_is_cached(self):
        crawler = Crawler()
        ok = {"success": True, "markdown": "# ok", "html": "<h1>ok</h1>", "error": None}
        with patch("crawl4ai_mcp.crawler.cloud_scrape", return_value=ok) as scrape:
            crawler.crawl_cloud("https://x.com/a")
            second = crawler.crawl_cloud("https://x.com/a")

        assert second["cached"] is True
        assert scrape.call_count == 1
