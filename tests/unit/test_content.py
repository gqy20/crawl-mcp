"""正文质量判定、清洗与错误分类的单元测试"""

from crawl4ai_mcp.content import (
    classify_error,
    clean_markdown,
    looks_like_js_shell,
    suggest_action,
)


class TestJsShell:
    def test_detects_disabled_js_placeholder(self):
        text = (
            "JavaScript is disabled in your browser.\n\n"
            "Please enable JavaScript to proceed.\n\n"
            "A required part of this site couldn't load."
        )
        assert looks_like_js_shell(text) is True

    def test_normal_article_not_flagged(self):
        text = "This article explains how to enable JavaScript in the browser settings."
        assert looks_like_js_shell(text) is False

    def test_long_content_mentioning_js_not_flagged(self):
        text = "Please enable JavaScript to proceed. " + "正文内容。" * 300
        assert looks_like_js_shell(text) is False

    def test_medium_article_with_js_mention_not_flagged(self):
        text = "正文内容。" * 100 + " please enable javascript"
        assert looks_like_js_shell(text) is False

    def test_empty_text(self):
        assert looks_like_js_shell("") is False


class TestCleanMarkdown:
    def test_removes_link_definitions(self):
        text = "正文内容\n\n[1]: https://example.com/a\n[2]: https://example.com/b\n"
        cleaned = clean_markdown(text)
        assert "example.com" not in cleaned
        assert "正文内容" in cleaned

    def test_removes_short_navigation_links(self):
        text = "[首页][1]\n\n正文段落内容在这里。\n\n[登录][2]\n"
        cleaned = clean_markdown(text)
        assert "[首页][1]" not in cleaned
        assert "正文段落内容在这里。" in cleaned

    def test_keeps_long_link_lines(self):
        text = "[这是一条很长的参考文献链接内容超过十二个字][1]\n"
        assert clean_markdown(text).strip() == text.strip()

    def test_removes_boilerplate_lines(self):
        text = "Advertisement\n\n正文。\n\nSkip to main content\n"
        cleaned = clean_markdown(text)
        assert "Advertisement" not in cleaned
        assert "正文。" in cleaned

    def test_collapses_blank_lines(self):
        text = "A\n\n\n\n\nB\n"
        assert clean_markdown(text) == "A\n\nB"

    def test_keeps_list_and_table_structure(self):
        text = "| 列1 | 列2 |\n|---|---|\n* 项目一\n* 项目二\n"
        cleaned = clean_markdown(text)
        assert "| 列1 | 列2 |" in cleaned
        assert "* 项目一" in cleaned

    def test_empty_input(self):
        assert clean_markdown("") == ""


class TestClassifyError:
    def test_http_403(self):
        assert classify_error("Failed to fetch: HTTP 403") == "http_403"

    def test_http_404(self):
        assert classify_error("HTTP 404 Not Found") == "http_404"

    def test_rate_limited(self):
        assert classify_error("Cloud 返回 HTTP 429") == "rate_limited"

    def test_tls_error(self):
        assert classify_error("invalid peer certificate: UnknownIssuer") == "tls_error"

    def test_cloudflare_challenge(self):
        err = "Blocked by anti-bot protection: Cloudflare JS challenge"
        assert classify_error(err) == "js_challenge"

    def test_empty_content_wins_over_antibot(self):
        err = "Blocked by anti-bot protection: Near-empty content (66 bytes) with HTTP 200"
        assert classify_error(err) == "empty_content"

    def test_js_shell_beats_empty_content(self):
        """JS 壳页（script_heavy_shell）要归到 js_challenge，不是 empty_content——
        前者换浏览器/换路径有用，后者重试没用"""
        err = (
            "Blocked by anti-bot protection: Structural: minimal_text, "
            "no_content_elements, script_heavy_shell (657 bytes, 0 chars visible)"
        )
        assert classify_error(err) == "js_challenge"

    def test_plain_antibot(self):
        assert classify_error("Blocked by anti-bot protection") == "antibot"

    def test_timeout(self):
        assert classify_error("Operation timed out") == "timeout"

    def test_no_results(self):
        assert classify_error("No results found.") == "no_results"

    def test_unknown(self):
        assert classify_error("something odd happened") == "unknown"

    def test_none_gives_none(self):
        assert classify_error(None) is None
        assert classify_error("") is None


class TestSuggestAction:
    def test_known_code_has_advice(self):
        assert suggest_action("http_404")

    def test_unknown_code_has_no_advice(self):
        assert suggest_action(None) == ""
        assert suggest_action("unknown") == ""
        assert suggest_action("") == ""
