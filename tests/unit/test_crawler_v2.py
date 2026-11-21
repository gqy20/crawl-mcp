"""Crawler v2 升级后测试

覆盖范围：
- 公共工具函数 (_run_async 提取到 utils)
- Crawler 核心爬取（两阶段架构 + LLM 可选插件）
- 浏览器实例复用（重试时复用）
- 批量爬取 + LLM 后处理
- 整站深度爬取（BFSDeepCrawlStrategy + arun）
- 无死代码验证
- Searcher 使用公共 utils
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================
# 1. 公共 _run_async 工具函数
# ============================================================


class TestRunAsyncUtility:
    """测试提取到公共模块的 _run_async"""

    def test_run_async_creates_new_loop_when_none(self):
        """没有事件循环时应创建新的"""
        from crawl4ai_mcp.utils import run_async

        async def dummy():
            return "ok"

        result = run_async(dummy())
        assert result == "ok"

    def test_run_async_handles_existing_loop(self):
        """已有事件循环时应使用 nest_asyncio"""
        from crawl4ai_mcp.utils import run_async

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:

            async def inner():
                return "nested_ok"

            result = run_async(inner())
            assert result == "nested_ok"
        finally:
            loop.close()
            asyncio.set_event_loop(None)


# ============================================================
# 2. crawl_single — 两阶段架构 + LLM 可选插件
# ============================================================


class TestCrawlSingleTwoPhase:
    """测试单页爬取：先爬取，再可选 LLM 后处理（需 API Key）"""

    @pytest.mark.asyncio
    async def test_crawl_single_returns_markdown_without_llm(self):
        """不传 llm_config 时只返回原始 Markdown"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="# Hello\n\nWorld"),
            metadata={"title": "Test"},
        )

        with patch("crawl4ai.AsyncWebCrawler") as mock_cls:
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = mock_result
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single("https://example.com")

        assert result["success"] is True
        assert result["markdown"] == "# Hello\n\nWorld"
        assert result["title"] == "Test"
        assert "llm_summary" not in result
        assert "llm_data" not in result

    @pytest.mark.asyncio
    async def test_crawl_single_with_llm_postprocess(self):
        """API Key 已配置时，传 llm_config 执行两阶段：爬取 + LLM 后处理"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="# Article\n\nLong content..."),
            metadata={"title": "Article"},
        )

        with (
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
            patch("crawl4ai_mcp.crawler._llm_available", return_value=True),
            patch.object(
                crawler,
                "_postprocess_with_llm",
                return_value={"success": True, "summary": "Summary text"},
            ) as mock_llm,
        ):
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = mock_result
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single(
                "https://example.com",
                llm_config={"instruction": "Summarize this"},
            )

        assert result["success"] is True
        assert result["markdown"] == "# Article\n\nLong content..."
        assert result["llm_summary"] == "Summary text"
        mock_llm.assert_called_once_with(
            "# Article\n\nLong content...", "Summarize this", None
        )

    @pytest.mark.asyncio
    async def test_crawl_single_llm_skipped_when_no_api_key(self):
        """API Key 未配置时，传 llm_config 应优雅跳过 LLM 阶段"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="# Hello\n\nWorld"),
            metadata={"title": "Test"},
        )

        with (
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
            patch("crawl4ai_mcp.crawler._llm_available", return_value=False),
            patch.object(crawler, "_postprocess_with_llm") as mock_llm,
        ):
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = mock_result
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single(
                "https://example.com",
                llm_config={"instruction": "Summarize this"},
            )

        # 爬取结果正常返回
        assert result["success"] is True
        assert result["markdown"] == "# Hello\n\nWorld"
        # LLM 被跳过，不调用后处理方法
        mock_llm.assert_not_called()
        # 返回跳过提示
        assert "llm_skipped" in result
        assert "CRAWL_MCP_API_KEY" in result["llm_skipped"]

    @pytest.mark.asyncio
    async def test_crawl_single_llm_error_recorded(self):
        """LLM 失败时记录错误但不影响原始爬取结果"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="Content"),
            metadata={},
        )

        with (
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
            patch("crawl4ai_mcp.crawler._llm_available", return_value=True),
            patch.object(
                crawler,
                "_postprocess_with_llm",
                return_value={"success": False, "error": "LLM failed"},
            ),
        ):
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = mock_result
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single(
                "https://example.com", llm_config={"instruction": "Summarize"}
            )

        assert result["success"] is True
        assert result["llm_error"] == "LLM failed"

    @pytest.mark.asyncio
    async def test_crawl_single_llm_skipped_when_crawl_fails(self):
        """爬取失败时不执行 LLM 后处理"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()

        with (
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
            patch.object(crawler, "_postprocess_with_llm") as mock_llm,
        ):
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.arun.return_value = MagicMock(
                success=False,
                markdown=MagicMock(raw_markdown=""),
                metadata={},
                error_message="Timeout",
            )
            mock_cls.return_value.__aenter__.return_value = mock_crawler_instance

            result = crawler.crawl_single(
                "https://example.com", llm_config={"instruction": "Summarize"}
            )

        assert result["success"] is False
        mock_llm.assert_not_called()


# ============================================================
# 3. 浏览器实例复用（重试优化）
# ============================================================


class TestBrowserReuse:
    """测试重试机制中浏览器实例的复用"""

    @pytest.mark.asyncio
    async def test_retry_reuses_browser_instance(self):
        """网络错误重试时应复用同一个 AsyncWebCrawler 实例"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        call_count = [0]

        def make_failing_then_success():
            async def _inner(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise Exception("ERR_NETWORK_CHANGED")
                return MagicMock(
                    success=True,
                    markdown=MagicMock(raw_markdown="Retry OK"),
                    metadata={"title": "OK"},
                )

            return _inner

        failing_then_success = make_failing_then_success()

        with patch("crawl4ai.AsyncWebCrawler") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.arun = failing_then_success
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            result = await crawler._crawl("https://example.com")

        assert result["success"] is True
        assert mock_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_non_network_error_does_not_retry(self):
        """非网络错误不应重试，直接抛出异常"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()

        with patch("crawl4ai.AsyncWebCrawler") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.arun.side_effect = ValueError("Bad URL")
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__.return_value = False  # 不抑制异常
            mock_cls.return_value = mock_cm

            with pytest.raises(ValueError, match="Bad URL"):
                await crawler._crawl("https://bad.url")


class TestCreateConfigSelectors:
    """css_selector / excluded_selector / scan_full_page 注入浏览器配置"""

    def test_selector_injected_into_normal_config(self):
        from crawl4ai_mcp.crawler import Crawler

        config = Crawler()._create_config(
            css_selector="article", excluded_selector="nav,footer"
        )
        assert config.css_selector == "article"
        assert config.excluded_selector == "nav,footer"

    def test_selector_injected_into_enhanced_config(self):
        from crawl4ai_mcp.crawler import Crawler

        config = Crawler()._create_config(enhanced=True, css_selector="article")
        assert config.css_selector == "article"
        assert config.magic is True

    def test_defaults_keep_config_clean(self):
        from crawl4ai_mcp.crawler import Crawler

        config = Crawler()._create_config()
        # crawl4ai 默认 excluded_selector 为空串、css_selector 为 None
        assert not config.css_selector
        assert not config.excluded_selector
        assert config.scan_full_page is False

    def test_scan_full_page_enables_scroll(self):
        from crawl4ai_mcp.crawler import Crawler

        config = Crawler()._create_config(scan_full_page=True)
        assert config.scan_full_page is True
        assert config.scroll_delay == 0.5


class TestEnvBrowserConfig:
    """CRAWL_MCP_COOKIES 环境变量解析（登录态只从环境读，不走工具参数）"""

    def test_unset_returns_none(self, monkeypatch):
        from crawl4ai_mcp.crawler import _env_browser_config

        monkeypatch.delenv("CRAWL_MCP_COOKIES", raising=False)
        assert _env_browser_config() is None

    def test_invalid_json_ignored(self, monkeypatch):
        from crawl4ai_mcp.crawler import _env_browser_config

        monkeypatch.setenv("CRAWL_MCP_COOKIES", "{broken")
        assert _env_browser_config() is None

    def test_non_list_or_missing_fields_ignored(self, monkeypatch):
        from crawl4ai_mcp.crawler import _env_browser_config

        monkeypatch.setenv("CRAWL_MCP_COOKIES", '{"name": "x"}')
        assert _env_browser_config() is None
        monkeypatch.setenv("CRAWL_MCP_COOKIES", '[{"name": "x"}]')  # 缺 value
        assert _env_browser_config() is None

    def test_valid_cookies_return_browser_config(self, monkeypatch):
        from crawl4ai_mcp.crawler import _env_browser_config

        monkeypatch.setenv(
            "CRAWL_MCP_COOKIES",
            '[{"name": "session", "value": "abc", "domain": ".example.com"}]',
        )
        cfg = _env_browser_config()
        assert cfg is not None
        assert cfg.cookies == [
            {"name": "session", "value": "abc", "domain": ".example.com"}
        ]

    def test_storage_state_file_passed_through(self, monkeypatch, tmp_path):
        from crawl4ai_mcp.crawler import _env_browser_config

        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("CRAWL_MCP_STORAGE_STATE", str(state))
        cfg = _env_browser_config()
        assert cfg is not None
        assert cfg.storage_state == str(state)

    def test_storage_state_missing_file_ignored(self, monkeypatch):
        from crawl4ai_mcp.crawler import _env_browser_config

        monkeypatch.setenv("CRAWL_MCP_STORAGE_STATE", "/nonexistent/state.json")
        assert _env_browser_config() is None

    def test_cookies_and_storage_state_combine(self, monkeypatch, tmp_path):
        from crawl4ai_mcp.crawler import _env_browser_config

        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("CRAWL_MCP_STORAGE_STATE", str(state))
        monkeypatch.setenv(
            "CRAWL_MCP_COOKIES",
            '[{"name": "session", "value": "abc", "domain": ".example.com"}]',
        )
        cfg = _env_browser_config()
        assert cfg is not None
        assert cfg.cookies and cfg.storage_state


class TestAuthFingerprint:
    """登录态指纹进缓存键：登录态变了，旧正/负缓存不再命中"""

    def test_no_auth_env_gives_empty(self, monkeypatch):
        from crawl4ai_mcp.crawler import _auth_fingerprint

        monkeypatch.delenv("CRAWL_MCP_COOKIES", raising=False)
        monkeypatch.delenv("CRAWL_MCP_STORAGE_STATE", raising=False)
        assert _auth_fingerprint() == ""

    def test_cookie_changes_fingerprint(self, monkeypatch):
        from crawl4ai_mcp.crawler import _auth_fingerprint

        monkeypatch.setenv("CRAWL_MCP_COOKIES", '[{"name": "a", "value": "1"}]')
        fp1 = _auth_fingerprint()
        monkeypatch.setenv("CRAWL_MCP_COOKIES", '[{"name": "a", "value": "2"}]')
        fp2 = _auth_fingerprint()
        assert fp1 and fp2 and fp1 != fp2

    def test_fingerprint_stable_and_no_secret_leak(self, monkeypatch):
        from crawl4ai_mcp.crawler import _auth_fingerprint

        monkeypatch.setenv("CRAWL_MCP_COOKIES", '[{"name": "a", "value": "secret"}]')
        fp1 = _auth_fingerprint()
        monkeypatch.setenv("CRAWL_MCP_COOKIES", '[{"name": "a", "value": "secret"}]')
        assert _auth_fingerprint() == fp1
        assert "secret" not in fp1

    def test_crawl_single_cache_opts_carry_auth(self, monkeypatch):
        """cache.lookup 收到的 opts 必须带 auth 指纹"""
        from unittest.mock import patch

        from crawl4ai_mcp.crawler import Crawler

        monkeypatch.setenv("CRAWL_MCP_COOKIES", '[{"name": "a", "value": "1"}]')
        opts_seen = []
        with patch("crawl4ai_mcp.crawler.cache") as mock_cache:
            mock_cache.lookup.return_value = None
            mock_cache.get.return_value = None
            with (
                patch.object(
                    Crawler,
                    "_extract",
                    # _extract 的真实形状是 content 键（决策函数读它判字数）；
                    # 此前误写成 markdown，content 为空被判定降级浏览器，
                    # CI 无 Chromium 直接崩，本地则偷偷起真浏览器爬 example.com
                    return_value={"success": True, "content": "x" * 300, "title": "t"},
                ),
                # 护栏：快速路径足够成功就不该碰浏览器，碰了立即报错
                patch.object(
                    Crawler, "_crawl", side_effect=AssertionError("不该走浏览器路径")
                ),
            ):
                Crawler().crawl_single("https://example.com")
            for call in mock_cache.lookup.call_args_list:
                opts_seen.append(call.args[2])
        assert opts_seen and all(o.get("auth") for o in opts_seen)


class TestBrowserLoginWallPostcheck:
    """浏览器成功结果终检：登录墙壳降为失败（登录态过期/无效）"""

    def test_shell_demoted_to_failure(self):
        from crawl4ai_mcp.crawler import Crawler

        shell = "Welcome\nPlease log in to continue\nSign up now\nGet started"
        result = Crawler._postcheck_browser(
            {"success": True, "markdown": shell, "title": "T", "error": None}
        )
        assert result["success"] is False
        assert result["markdown"] == ""
        assert "登录" in result["error"]

    def test_real_content_untouched(self):
        from crawl4ai_mcp.crawler import Crawler

        body = "Article body. " * 100  # 长正文不受影响
        result = Crawler._postcheck_browser(
            {"success": True, "markdown": body, "title": "T", "error": None}
        )
        assert result["success"] is True

    def test_format_crawl4ai_result_applies_postcheck(self):
        from unittest.mock import MagicMock

        from crawl4ai_mcp.crawler import Crawler

        raw = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="Log in\nSign up\nGet started"),
            metadata={"title": "T"},
        )
        out = Crawler._format_crawl4ai_result(raw)
        assert out["success"] is False


# ============================================================
# 4. crawl_batch — 并行爬取 + LLM 后处理
# ============================================================


class TestCrawlBatchV2:
    """测试批量爬取升级版"""

    @pytest.mark.asyncio
    async def test_batch_crawls_all_urls_in_parallel(self):
        """批量爬取应并行处理所有 URL"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        urls = ["https://a.com", "https://b.com", "https://c.com"]

        mock_results = [
            MagicMock(
                success=True,
                markdown=MagicMock(raw_markdown=f"Content {i}"),
                metadata={"title": f"Page {i}"},
            )
            for i in range(3)
        ]

        with patch("crawl4ai.AsyncWebCrawler") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.arun_many.return_value = mock_results
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            results = await crawler._crawl_batch(urls, concurrent=3)

        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert results[0]["markdown"] == "Content 0"
        mock_instance.arun_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_empty_urls_returns_empty(self):
        """空 URL 列表返回空结果"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        results = await crawler._crawl_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_with_llm_postprocess(self):
        """API Key 已配置时，带 LLM 配置的批量爬取应对成功结果做并行 LLM 后处理"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        urls = ["https://a.com", "https://b.com"]

        mock_results = [
            MagicMock(
                success=True,
                markdown=MagicMock(raw_markdown=f"Data {i}"),
                metadata={"title": f"P{i}"},
            )
            for i in range(2)
        ]

        with (
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
            patch("crawl4ai_mcp.crawler._llm_available", return_value=True),
            patch.object(
                crawler,
                "_postprocess_batch_with_llm",
                return_value=[
                    {"summary": "S0", "__index__": 0},
                    {"summary": "S1", "__index__": 1},
                ],
            ) as mock_llm,
        ):
            mock_instance = AsyncMock()
            mock_instance.arun_many.return_value = mock_results
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            results = await crawler._crawl_batch(
                urls,
                concurrent=2,
                llm_config={"instruction": "Summarize"},
                llm_concurrent=2,
            )

        assert len(results) == 2
        assert results[0]["llm_summary"] == "S0"
        assert results[1]["llm_summary"] == "S1"
        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_llm_skipped_when_no_api_key(self):
        """API Key 未配置时，批量爬取应优雅跳过 LLM 阶段"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        urls = ["https://a.com", "https://b.com"]

        mock_results = [
            MagicMock(
                success=True,
                markdown=MagicMock(raw_markdown=f"Data {i}"),
                metadata={"title": f"P{i}"},
            )
            for i in range(2)
        ]

        with (
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
            patch("crawl4ai_mcp.crawler._llm_available", return_value=False),
            patch.object(crawler, "_postprocess_batch_with_llm") as mock_llm,
        ):
            mock_instance = AsyncMock()
            mock_instance.arun_many.return_value = mock_results
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            results = await crawler._crawl_batch(
                urls,
                concurrent=2,
                llm_config={"instruction": "Summarize"},
                llm_concurrent=2,
            )

        # 爬取结果正常
        assert len(results) == 2
        assert all(r["success"] for r in results)
        # LLM 被跳过
        mock_llm.assert_not_called()
        # 每个结果都有 skip 提示
        assert all("llm_skipped" in r for r in results)


# ============================================================
# 5. crawl_site — 深度爬取（BFSDeepCrawlStrategy + arun）
# ============================================================


class TestCrawlSiteV2:
    """浏览器 BFS 深爬路径 — BFSDeepCrawlStrategy + arun()

    入口页快速提取失败时 crawl_site 退回这条路径；
    快速 BFS 路径的测试见 test_crawl_site_fast.py
    """

    _FAILED_ENTRY = {"success": False, "markdown": "", "title": "", "error": "HTTP 403"}

    @pytest.mark.asyncio
    async def test_crawl_site_uses_deep_crawl_strategy(self):
        """整站爬取应通过 config.deep_crawl_strategy 使用 BFSDeepCrawlStrategy"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="# Home\nContent"),
            metadata={"title": "Home Page"},
        )

        with (
            patch.object(crawler, "crawl_single", return_value=self._FAILED_ENTRY),
            patch("crawl4ai.BFSDeepCrawlStrategy") as mock_strategy_cls,
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
        ):
            mock_strategy_cls.return_value = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.arun.return_value = mock_result
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            result = await crawler._crawl_site(
                "https://example.com", depth=2, pages=10, concurrent=3
            )

        mock_strategy_cls.assert_called_once()
        call_kwargs = (
            mock_strategy_cls.call_args[1] if mock_strategy_cls.call_args else {}
        )
        assert call_kwargs.get("max_depth") == 2
        assert call_kwargs.get("max_pages") == 10
        assert result["successful_pages"] == 1
        assert result["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_crawl_site_respects_page_limit(self):
        """整站爬取应通过 max_pages 限制页面数"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="Page content"),
            metadata={"title": "Page"},
        )

        with (
            patch.object(crawler, "crawl_single", return_value=self._FAILED_ENTRY),
            patch("crawl4ai.BFSDeepCrawlStrategy") as mock_strategy_cls,
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
        ):
            mock_strategy_cls.return_value = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.arun.return_value = mock_result
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            result = await crawler._crawl_site(
                "https://example.com", depth=3, pages=5, concurrent=2
            )

        call_kwargs = (
            mock_strategy_cls.call_args[1] if mock_strategy_cls.call_args else {}
        )
        assert call_kwargs.get("max_pages") == 5
        assert result["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_crawl_site_uses_concurrent_dispatcher(self):
        """整站爬取应把 concurrent 传给 SemaphoreDispatcher"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=True,
            markdown=MagicMock(raw_markdown="Page content"),
            metadata={"title": "Page"},
        )

        with (
            patch.object(crawler, "crawl_single", return_value=self._FAILED_ENTRY),
            patch("crawl4ai.SemaphoreDispatcher") as mock_dispatcher_cls,
            patch("crawl4ai.BFSDeepCrawlStrategy"),
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
        ):
            dispatcher = MagicMock()
            mock_dispatcher_cls.return_value = dispatcher
            mock_instance = AsyncMock()
            mock_instance.arun.return_value = mock_result
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            await crawler._crawl_site(
                "https://example.com", depth=2, pages=10, concurrent=4
            )

        mock_dispatcher_cls.assert_called_once_with(semaphore_count=4)
        assert mock_instance.arun.call_args[1]["dispatcher"] is dispatcher

    @pytest.mark.asyncio
    async def test_crawl_site_handles_failure(self):
        """爬取失败时应返回错误信息"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        mock_result = MagicMock(
            success=False,
            markdown=MagicMock(raw_markdown=""),
            error_message="Timeout",
            metadata={},
        )

        with (
            patch.object(crawler, "crawl_single", return_value=self._FAILED_ENTRY),
            patch("crawl4ai.BFSDeepCrawlStrategy") as mock_strategy_cls,
            patch("crawl4ai.AsyncWebCrawler") as mock_cls,
        ):
            mock_strategy_cls.return_value = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.arun.return_value = mock_result
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_instance
            mock_cm.__aexit__ = AsyncMock()
            mock_cls.return_value = mock_cm

            result = await crawler._crawl_site("https://example.com")

        assert result["successful_pages"] == 0
        assert result["total_pages"] == 1
        assert result["success_rate"] == "0.0%"


# ============================================================
# 6. 无死代码验证
# ============================================================


class TestNoDeadCode:
    """验证旧版死代码已被清理"""

    def test_no_add_llm_strategy_method(self):
        """_add_llm_strategy 方法不应存在"""
        from crawl4ai_mcp.crawler import Crawler

        crawler = Crawler()
        assert not hasattr(crawler, "_add_llm_strategy")

    def test_no_direct_llm_extraction_imports(self):
        """crawler.py 不应使用旧的 Crawl4AILLMConfig 别名"""
        import crawl4ai_mcp.crawler as crawler_module

        source = crawler_module.__file__
        if source:
            with open(source) as f:
                code = f.read()
            # 允许使用原生 LLMExtractionStrategy（复用设计）
            assert "from crawl4ai import LLMConfig as Crawl4AILLMConfig" not in code


# ============================================================
# 7. Searcher 使用公共 utils
# ============================================================


class TestSearcherUsesSharedUtils:
    """验证 Searcher 使用公共 _run_async 而非自实现"""

    def test_searcher_has_no_duplicate_run_async(self):
        """searcher.py 不应有自己的 _run_async 定义"""
        import crawl4ai_mcp.searcher as searcher_module

        source = searcher_module.__file__
        if source:
            with open(source) as f:
                code = f.read()
            assert "_run_async" not in code or "def _run_async" not in code
