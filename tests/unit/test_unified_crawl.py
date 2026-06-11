"""统一爬取工具测试 — 自动降级（快速提取 → 浏览器渲染）

覆盖：
  1. 快速路径成功（extract_url 返回足够内容）
  2. 失败降级（extract_url 抛异常）
  3. 短内容降级（content < min_content_length）
  4. method / fallback_reason 字段
  5. prefer_fast=False 跳过快速路径
  6. SPA 自动检测 → enhanced=True
  7. LLM 后处理在两条路径都正常工作
  8. 批量模式：全快 / 混合 / 全慢
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from crawl4ai_mcp.crawler import Crawler


# ============================================================
# 1. SPA 检测
# ============================================================


class TestSPADetection:
    """SPA 启发式检测"""

    def test_detects_nextjs_app(self):
        """__NEXT_DATA__ 被识别为 SPA"""
        assert Crawler._looks_like_spa('<script id="__NEXT_DATA__">{}') is True

    def test_detects_vue_app(self):
        """<div id="app"> 被识别为 SPA"""
        assert Crawler._looks_like_spa('<div id="app"></div>') is True

    def test_detects_react_root(self):
        """<div id="root"> 被识别为 SPA"""
        assert Crawler._looks_like_spa('<div id="root"></div>') is True

    def test_long_content_not_flagged_as_spa(self):
        """长内容（>1000 chars）不被误判为 SPA"""
        long_text = "real content " * 300  # ~1500 chars
        assert Crawler._looks_like_spa(long_text) is False

    def test_empty_content_not_spa(self):
        """空字符串不报 SPA"""
        assert Crawler._looks_like_spa("") is False

    def test_nuxt_detected(self):
        """nuxt-app 被识别为 SPA"""
        assert Crawler._looks_like_spa("<div class='nuxt-app'>") is True


# ============================================================
# 2. 标题提取
# ============================================================


class TestTitleExtraction:
    """从 HTML 内容提取 <title>"""

    def test_extracts_title_tag(self):
        """正常 <title> 提取"""
        result = Crawler._extract_title_from_html(
            "<html><head><title>Hello World</title></head><body>x</body></html>"
        )
        assert result == "Hello World"

    def test_handles_missing_title(self):
        """无 title 标签返回空字符串"""
        result = Crawler._extract_title_from_html("<p>No title here</p>")
        assert result == ""

    def test_handles_title_with_attributes(self):
        """带属性的 title 标签也能提取"""
        result = Crawler._extract_title_from_html('<title lang="en">My Page</title>')
        assert result == "My Page"

    def test_handles_multiline_title(self):
        """多行 title 提取"""
        result = Crawler._extract_title_from_html("<title>\n  Multi\n  Line\n</title>")
        assert result == "Multi\n  Line"


# ============================================================
# 3. 快速结果格式标准化
# ============================================================


class TestNormalizeFastResult:
    """extract_url 输出 → 标准 crawl_single 格式"""

    def test_success_normalized(self):
        """成功的 extract 结果被正确映射"""
        crawler = Crawler()
        extract_result = {
            "success": True,
            "url": "https://example.com",
            "content": "# Hello\n\nWorld",
            "fmt": "text_markdown",
        }
        result = crawler._normalize_fast_result(extract_result)

        assert result["success"] is True
        assert result["markdown"] == "# Hello\n\nWorld"
        assert result["title"] == ""  # 无 title tag
        assert result["method"] == "fast_extract"
        assert "error" not in result or result.get("error") is None

    def test_failure_normalized(self):
        """失败的 extract 结果保留 error 信息"""
        crawler = Crawler()
        extract_result = {
            "success": False,
            "url": "https://example.com",
            "error": "Timeout",
        }
        result = crawler._normalize_fast_result(extract_result)

        assert result["success"] is False
        assert result["error"] == "Timeout"
        assert result["method"] == "fast_extract"

    def test_title_extracted_from_content(self):
        """从 content 中自动提取 title"""
        crawler = Crawler()
        html = "<title>Test Page</title><p>Content here</p>"
        result = crawler._normalize_fast_result({"success": True, "content": html})
        assert result["title"] == "Test Page"


# ============================================================
# 4. 统一 crawl_single — 自动降级核心逻辑
# ============================================================


class TestUnifiedCrawlSingleFallback:
    """crawl_single 的自动降级行为验证"""

    @pytest.mark.asyncio
    async def test_fast_path_returns_markdown_format(self):
        """快速路径成功时返回 markdown 格式（非 content）"""
        crawler = Crawler()

        fast_mock = {
            "success": True,
            "content": "# Article\n\nFull content here" * 20,  # >200 chars
        }

        with patch.object(crawler._searcher, "extract_url", return_value=fast_mock):
            result = crawler.crawl_single("https://blog.example.com")

        assert result["success"] is True
        assert "markdown" in result
        assert result["markdown"] == fast_mock["content"]
        assert result["method"] == "fast_extract"

    @pytest.mark.asyncio
    async def test_fast_path_includes_method_field(self):
        """快速路径标记 method='fast_extract'"""
        crawler = Crawler()

        with patch.object(
            crawler._searcher,
            "extract_url",
            return_value={"success": True, "content": "x" * 300},
        ):
            result = crawler.crawl_single("https://example.com")

        assert result.get("method") == "fast_extract"

    @pytest.mark.asyncio
    async def test_fallback_on_extract_error(self):
        """extract_url 失败时降级到浏览器"""
        crawler = Crawler()

        browser_mock = {
            "success": True,
            "markdown": "# Browser Result\n\nRendered content",
            "title": "Browser Title",
        }

        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={"success": False, "error": "Connection timeout"},
            ),
            patch.object(crawler, "_crawl", return_value=browser_mock) as mock_crawl,
        ):
            result = crawler.crawl_single("https://spa.example.com")

        assert result["success"] is True
        assert result["method"] == "browser_fallback"
        assert "fallback_reason" in result
        assert (
            "failed" in result["fallback_reason"].lower()
            or "timeout" in result["fallback_reason"].lower()
        )
        mock_crawl.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_short_content(self):
        """extract_url 成功但内容过短时降级到浏览器"""
        crawler = Crawler()

        browser_mock = {
            "success": True,
            "markdown": "# Full Content\n\n" + "Real content " * 50,
            "title": "Real Title",
        }

        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={"success": True, "content": "Too short"},  # < 200 chars
            ),
            patch.object(crawler, "_crawl", return_value=browser_mock) as mock_crawl,
        ):
            result = crawler.crawl_single("https://spa.example.com")

        assert result["method"] == "browser_fallback"
        assert (
            "insufficient" in result["fallback_reason"].lower()
            or "short" in result["fallback_reason"].lower()
        )
        mock_crawl.assert_called_once()

    @pytest.mark.asyncio
    async def test_prefer_fast_false_skips_extract(self):
        """prefer_fast=False 时跳过快速路径，直接用浏览器"""
        crawler = Crawler()

        browser_mock = {
            "success": True,
            "markdown": "# Direct Browser\n\nContent",
            "title": "Title",
        }

        with (
            patch.object(crawler._searcher, "extract_url") as mock_extract,
            patch.object(crawler, "_crawl", return_value=browser_mock),
        ):
            result = crawler.crawl_single("https://example.com", prefer_fast=False)

        mock_extract.assert_not_called()
        assert result["success"] is True
        assert result["markdown"] == "# Direct Browser\n\nContent"

    @pytest.mark.asyncio
    async def test_enhanced_auto_detected_for_spa(self):
        """快速提取返回 SPA 骨架时，浏览器降级自动使用 enhanced=True"""
        crawler = Crawler()

        spa_skeleton = '<html><body><div id="app"></div><script src="/app.js"></script></body></html>'
        browser_mock = {
            "success": True,
            "markdown": "# Rendered SPA\n\nActual content",
            "title": "SPA App",
        }

        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={"success": True, "content": spa_skeleton},
            ),
            patch.object(crawler, "_crawl", return_value=browser_mock) as mock_crawl,
        ):
            crawler.crawl_single("https://spa.app")

        # _crawl 应该以 enhanced=True 调用（位置参数）
        call_args = mock_crawl.call_args
        assert len(call_args[0]) >= 2 and call_args[0][1] is True

    @pytest.mark.asyncio
    async def test_explicit_enhanced_respected(self):
        """用户显式设置 enhanced=True 时不会被覆盖"""
        crawler = Crawler()

        short_content = "Just a bit"
        browser_mock = {
            "success": True,
            "markdown": "# Enhanced Result",
            "title": "Title",
        }

        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={"success": True, "content": short_content},
            ),
            patch.object(crawler, "_crawl", return_value=browser_mock) as mock_crawl,
        ):
            crawler.crawl_single("https://example.com", enhanced=True)

        # 用户显式 enhanced=True 应保留
        call_args = mock_crawl.call_args
        assert len(call_args[0]) >= 2 and call_args[0][1] is True

    @pytest.mark.asyncio
    async def test_min_content_length_zero_accepts_anything(self):
        """min_content_length=0 时即使空内容也接受快速路径结果"""
        crawler = Crawler()

        with (
            patch.object(
                crawler._searcher,
                "extract_url",
                return_value={"success": True, "content": ""},
            ),
            patch.object(crawler, "_crawl") as mock_crawl,
        ):
            result = crawler.crawl_single("https://example.com", min_content_length=0)

        mock_crawl.assert_not_called()
        assert result["method"] == "fast_extract"

    @pytest.mark.asyncio
    async def test_llm_postprocess_on_fast_path(self):
        """LLM 后处理在快速路径上正常工作"""
        crawler = Crawler()

        fast_mock = {
            "success": True,
            "content": "# Article\n\nLong enough content " * 30,
        }

        llm_mock = {"success": True, "summary": "Article summary"}

        with (
            patch.object(crawler._searcher, "extract_url", return_value=fast_mock),
            patch("crawl4ai_mcp.crawler._llm_available", return_value=True),
            patch.object(crawler, "_postprocess_with_llm", return_value=llm_mock),
        ):
            result = crawler.crawl_single("https://example.com", llm_config="总结内容")

        assert result["llm_summary"] == "Article summary"
        assert result["method"] == "fast_extract"

    @pytest.mark.asyncio
    async def test_llm_skipped_on_fast_path(self):
        """LLM skip 行为在快速路径上保持一致"""
        crawler = Crawler()

        fast_mock = {
            "success": True,
            "content": "# Article\n\nLong enough content " * 30,
        }

        with (
            patch.object(crawler._searcher, "extract_url", return_value=fast_mock),
            patch("crawl4ai_mcp.crawler._llm_available", return_value=False),
        ):
            result = crawler.crawl_single("https://example.com", llm_config="总结")

        assert "llm_skipped" in result
        assert result["method"] == "fast_extract"


# ============================================================
# 5. 批量模式统一测试
# ============================================================


class TestUnifiedCrawlBatch:
    """crawl_batch 的统一降级行为"""

    @pytest.mark.asyncio
    async def test_batch_all_fast_success(self):
        """所有 URL 都能快速提取成功时不调用浏览器"""
        crawler = Crawler()

        urls = ["https://a.com", "https://b.com", "https://c.com"]
        fast_results = [
            {"success": True, "content": f"Content {i} " * 30}  # >200 chars
            for i, _ in enumerate(urls)
        ]

        with patch.object(crawler._searcher, "extract_url", side_effect=fast_results):
            results = crawler.crawl_batch(urls)

        assert len(results) == 3
        assert all(r["method"] == "fast_extract" for r in results)
        assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_batch_partial_fallback(self):
        """部分 URL 快速失败，部分成功 → 混合结果"""
        crawler = Crawler()

        urls = ["https://static.com", "https://spa.com"]
        fast_results = [
            {"success": True, "content": "Static page content " * 30},  # OK
            {"success": False, "error": "Timeout"},  # fail → fallback
        ]

        with (
            patch.object(crawler._searcher, "extract_url", side_effect=fast_results),
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
        ):
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            arun_many_result = [MagicMock(success=True)]
            arun_many_result[0].markdown.raw_markdown = "# Rendered SPA\n\nContent"
            arun_many_result[0].metadata = {"title": "SPA App"}
            arun_many_result[0].error_message = None
            mock_instance.arun_many.return_value = arun_many_result
            mock_cls.return_value = mock_instance

            results = crawler.crawl_batch(urls)

        assert results[0]["method"] == "fast_extract"
        assert results[1]["method"] == "browser_fallback"

    @pytest.mark.asyncio
    async def test_batch_empty_urls(self):
        """空 URL 列表返回空列表"""
        crawler = Crawler()
        results = crawler.crawl_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_prefer_fast_false_all_browser(self):
        """prefer_fast=False 时所有 URL 都走浏览器"""
        crawler = Crawler()

        urls = ["https://a.com"]

        with (
            patch.object(crawler._searcher, "extract_url") as mock_extract,
            patch("crawl4ai_mcp.crawler.AsyncWebCrawler") as mock_cls,
        ):
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            arun_result = [MagicMock(success=True)]
            arun_result[0].markdown.raw_markdown = "# Content"
            arun_result[0].metadata = {"title": "T"}
            arun_result[0].error_message = None
            mock_instance.arun_many.return_value = arun_result
            mock_cls.return_value = mock_instance

            crawler.crawl_batch(urls, prefer_fast=False)

        mock_extract.assert_not_called()
