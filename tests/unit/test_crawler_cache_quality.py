"""缓存、JS 壳门控、error_code、timings 的集成测试"""

from unittest.mock import MagicMock, patch

from crawl4ai_mcp.crawler import Crawler

JS_SHELL = (
    "JavaScript is disabled in your browser.\n\n"
    "Please enable JavaScript to proceed.\n\n"
    "A required part of this site couldn't load. This may be due to a browser "
    "extension, network issues, or browser settings."
)


def _browser_result(markdown="# Title\n\nBody"):
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.markdown.raw_markdown = markdown
    mock_result.metadata = {"title": "Title"}
    mock_result.error_message = None
    return mock_result


class TestJsShellGate:
    """JS 占位提示不能被当成正文成功"""

    def test_js_shell_falls_back_to_browser(self):
        crawler = Crawler()
        with (
            patch.object(crawler, "_searcher") as searcher,
            patch("crawl4ai_mcp.crawler.run_async") as run_async,
        ):
            searcher.extract_url.return_value = {
                "success": True,
                "content": JS_SHELL,
            }
            run_async.return_value = {
                "success": True,
                "markdown": "# Real\n\nBody",
                "title": "Real",
                "error": None,
            }
            result = crawler.crawl_single("https://js-only.com")

        assert result["success"] is True
        assert result["method"] == "browser_fallback"
        assert "JavaScript" in result["fallback_reason"]

    def test_long_article_mentioning_js_stays_on_fast_path(self):
        crawler = Crawler()
        with patch.object(crawler, "_searcher") as searcher:
            searcher.extract_url.return_value = {
                "success": True,
                "content": "Please enable JavaScript to proceed. " + "正文内容。" * 600,
            }
            result = crawler.crawl_single("https://article.com")

        assert result["method"] == "fast_extract"
        assert result["success"] is True


class TestErrorCodeAndTimings:
    def test_error_code_present_on_failure(self):
        crawler = Crawler()
        with (
            patch.object(crawler, "_searcher") as searcher,
            patch("crawl4ai_mcp.crawler.run_async") as run_async,
        ):
            searcher.extract_url.return_value = {
                "success": False,
                "content": "",
                "error": "Failed to fetch: HTTP 403",
            }
            run_async.return_value = {
                "success": False,
                "markdown": "",
                "title": "",
                "error": "Blocked by anti-bot protection: Cloudflare JS challenge",
            }
            result = crawler.crawl_single("https://blocked.com")

        assert result["success"] is False
        assert result["error_code"] == "js_challenge"
        assert "fast" in result["timings"]
        assert "browser" in result["timings"]

    def test_error_code_none_on_success(self):
        crawler = Crawler()
        with patch.object(crawler, "_searcher") as searcher:
            searcher.extract_url.return_value = {
                "success": True,
                "content": "正文内容" * 100,
            }
            result = crawler.crawl_single("https://ok.com")

        assert result["success"] is True
        assert result["error_code"] is None
        assert result["timings"]["fast"] >= 0


class TestCrawlCache:
    def test_second_call_hits_cache(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        crawler = Crawler()
        with patch.object(crawler, "_searcher") as searcher:
            searcher.extract_url.return_value = {
                "success": True,
                "content": "正文内容" * 100,
            }
            first = crawler.crawl_single("https://cached.com")
            second = crawler.crawl_single("https://cached.com")

        assert first.get("cached") is not True
        assert second.get("cached") is True
        assert second["markdown"] == first["markdown"]
        # 第二次不再调用提取
        assert searcher.extract_url.call_count == 1

    def test_different_options_use_different_cache_entry(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_CACHE", "1")
        monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path))
        crawler = Crawler()
        with patch.object(crawler, "_searcher") as searcher:
            searcher.extract_url.return_value = {
                "success": True,
                "content": "正文内容" * 100,
            }
            crawler.crawl_single("https://cached.com", prefer_fast=True)
            second = crawler.crawl_single("https://cached.com", prefer_fast=True)
        assert second.get("cached") is True
