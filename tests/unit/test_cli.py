"""CLI 测试 + 懒加载验证"""

import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from crawl4ai_mcp.cli import main


def _result(success=True, markdown="# hello", error=None, **extra):
    return {
        "success": success,
        "markdown": markdown,
        "title": "t",
        "error": error,
        **extra,
    }


class TestCrawlCli:
    def test_single_prints_markdown(self, capsys):
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_single.return_value = _result()
            assert main(["https://example.com"]) == 0
            cls.return_value.crawl_single.assert_called_once_with(
                "https://example.com",
                prefer_fast=True,
                css_selector=None,
                excluded_selector=None,
                scan_full_page=False,
            )
        assert capsys.readouterr().out.strip() == "# hello"

    def test_single_failure_exit_1(self, capsys):
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_single.return_value = _result(
                success=False, markdown="", error="boom"
            )
            assert main(["https://example.com"]) == 1
        assert "boom" in capsys.readouterr().err

    def test_failure_prints_actionable_hint(self, capsys):
        """失败时除了原始错误，还给出 error_code 对应的下一步建议"""
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_single.return_value = _result(
                success=False, markdown="", error="boom", error_code="http_404"
            )
            assert main(["https://example.com"]) == 1
        err = capsys.readouterr().err
        assert "boom" in err
        assert "建议" in err
        assert "失效" in err

    def test_quiet_suppresses_progress_logs(self, capsys):
        """--quiet 时浏览器进度日志不刷屏"""
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:

            def noisy(*a, **kw):
                print("[INIT] crawl4ai 启动")
                return _result()

            cls.return_value.crawl_single.side_effect = noisy
            assert main(["--quiet", "https://example.com"]) == 0

        err = capsys.readouterr().err
        assert "[INIT]" not in err

    def test_progress_logs_go_to_stderr_by_default(self, capsys):
        """默认进度日志走 stderr，stdout 只有正文"""
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:

            def noisy(*a, **kw):
                print("[INIT] crawl4ai 启动")
                return _result()

            cls.return_value.crawl_single.side_effect = noisy
            assert main(["https://example.com"]) == 0

        captured = capsys.readouterr()
        assert "[INIT]" in captured.err
        assert "[INIT]" not in captured.out

    def test_browser_flag_skips_fast(self):
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_single.return_value = _result()
            assert main(["--browser", "https://example.com"]) == 0
            cls.return_value.crawl_single.assert_called_once_with(
                "https://example.com",
                prefer_fast=False,
                css_selector=None,
                excluded_selector=None,
                scan_full_page=False,
            )

    def test_single_json_output(self, capsys):
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_single.return_value = _result()
            assert main(["--json", "https://example.com"]) == 0
        assert json.loads(capsys.readouterr().out)["markdown"] == "# hello"

    def test_browser_and_cloud_mutually_exclusive(self):
        with pytest.raises(SystemExit) as exc:
            main(["--browser", "--cloud", "https://example.com"])
        assert exc.value.code == 2

    def test_batch_outputs_json(self, capsys):
        urls = ["https://a.com", "https://b.com"]
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_batch.return_value = [_result(), _result()]
            assert main(urls) == 0
            cls.return_value.crawl_batch.assert_called_once_with(
                urls,
                prefer_fast=True,
                css_selector=None,
                excluded_selector=None,
            )
        assert len(json.loads(capsys.readouterr().out)) == 2

    def test_batch_partial_failure_exit_1(self, capsys):
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_batch.return_value = [
                _result(),
                _result(success=False, markdown="", error="boom"),
            ]
            assert main(["https://a.com", "https://b.com"]) == 1
        assert len(json.loads(capsys.readouterr().out)) == 2

    def test_css_flags_forwarded_single(self):
        """--css/--exclude-css/--full-page 透传到 crawl_single"""
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_single.return_value = _result()
            assert (
                main(
                    [
                        "--css",
                        "article",
                        "--exclude-css",
                        "nav,footer",
                        "--full-page",
                        "https://example.com",
                    ]
                )
                == 0
            )
        cls.return_value.crawl_single.assert_called_once_with(
            "https://example.com",
            prefer_fast=True,
            css_selector="article",
            excluded_selector="nav,footer",
            scan_full_page=True,
        )

    def test_css_flags_forwarded_batch(self):
        """批量模式透传两个选择器参数（scan_full_page 不进批量）"""
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_batch.return_value = [_result(), _result()]
            assert main(["--css", "article", "https://a.com", "https://b.com"]) == 0
        cls.return_value.crawl_batch.assert_called_once_with(
            ["https://a.com", "https://b.com"],
            prefer_fast=True,
            css_selector="article",
            excluded_selector=None,
        )


class TestAuthCli:
    def test_list_empty_dir_hints_import(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("CRAWL_MCP_AUTH_DIR", str(tmp_path / "auth"))
        assert main(["auth", "list"]) == 0
        assert "为空" in capsys.readouterr().out

    def test_list_shows_entries(self, capsys, monkeypatch, tmp_path):
        d = tmp_path / "auth"
        d.mkdir()
        (d / "example.json").write_text(
            json.dumps(
                {
                    "cookies": [{"name": "a", "value": "1", "domain": ".example.com"}],
                    "origins": [],
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("CRAWL_MCP_AUTH_DIR", str(d))
        assert main(["auth", "list"]) == 0
        out = capsys.readouterr().out
        assert "example" in out and "example.com" in out

    def test_check_missing_file_exits_1(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("CRAWL_MCP_AUTH_DIR", str(tmp_path / "auth"))
        assert main(["auth", "check", "nope", "--url", "https://x.com"]) == 1
        assert "没有这个登录态" in capsys.readouterr().err

    def test_check_reports_valid(self, monkeypatch, tmp_path, capsys):
        d = tmp_path / "auth"
        d.mkdir()
        (d / "example.json").write_text(
            '{"cookies": [], "origins": []}', encoding="utf-8"
        )
        monkeypatch.setenv("CRAWL_MCP_AUTH_DIR", str(d))
        with (
            patch("crawl4ai_mcp.crawler.Crawler") as cls,
            patch("crawl4ai_mcp.cache.clear"),
        ):
            cls.return_value.crawl_single.return_value = _result(markdown="x" * 500)
            assert main(["auth", "check", "example", "--url", "https://x.com/me"]) == 0
        assert "有效" in capsys.readouterr().out

    def test_check_reports_login_wall(self, monkeypatch, tmp_path, capsys):
        d = tmp_path / "auth"
        d.mkdir()
        (d / "example.json").write_text(
            '{"cookies": [], "origins": []}', encoding="utf-8"
        )
        monkeypatch.setenv("CRAWL_MCP_AUTH_DIR", str(d))
        with (
            patch("crawl4ai_mcp.crawler.Crawler") as cls,
            patch("crawl4ai_mcp.cache.clear"),
        ):
            cls.return_value.crawl_single.return_value = _result(
                success=False, markdown="", error="x", error_code="login_wall"
            )
            assert main(["auth", "check", "example", "--url", "https://x.com/me"]) == 1
        assert "失效" in capsys.readouterr().out


class TestSearchCli:
    def test_search_text_output(self, capsys):
        with patch("crawl4ai_mcp.searcher.Searcher") as cls:
            cls.return_value.search_text.return_value = {
                "success": True,
                "results": [{"title": "T", "href": "https://x.com", "body": "B"}],
            }
            assert main(["search", "q", "-n", "5"]) == 0
            cls.return_value.search_text.assert_called_once_with(
                "q", max_results=5, page=1, backend=None
            )
        out = capsys.readouterr().out
        assert "https://x.com" in out and "T" in out

    def test_search_failure_exit_1(self, capsys):
        with patch("crawl4ai_mcp.searcher.Searcher") as cls:
            cls.return_value.search_text.return_value = {
                "success": False,
                "error": "boom",
                "results": [],
            }
            assert main(["search", "q"]) == 1
        assert "boom" in capsys.readouterr().err

    def test_search_variants_dispatch(self):
        for flag, method in [
            ("--news", "search_news"),
            ("--books", "search_books"),
            ("--videos", "search_videos"),
        ]:
            with patch("crawl4ai_mcp.searcher.Searcher") as cls:
                getattr(cls.return_value, method).return_value = {
                    "success": True,
                    "results": [{"title": "T", "url": "https://x.com", "content": "B"}],
                }
                assert main(["search", flag, "q", "-n", "3"]) == 0
                getattr(cls.return_value, method).assert_called_once_with(
                    "q", max_results=3, page=1, backend=None
                )

    def test_search_news_uses_url_content_fields(self, capsys):
        with patch("crawl4ai_mcp.searcher.Searcher") as cls:
            cls.return_value.search_news.return_value = {
                "success": True,
                "results": [{"title": "T", "url": "https://x.com", "content": "B"}],
            }
            assert main(["search", "--news", "q"]) == 0
        out = capsys.readouterr().out
        assert "https://x.com" in out and "B" in out

    def test_search_flags_mutually_exclusive(self):
        with pytest.raises(SystemExit) as exc:
            main(["search", "--news", "--books", "q"])
        assert exc.value.code == 2


class TestSiteCli:
    def test_site_outputs_json(self, capsys):
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_site.return_value = {
                "successful_pages": 2,
                "total_pages": 2,
                "success_rate": "100.0%",
                "results": [_result(), _result()],
            }
            assert main(["site", "https://x.com", "--depth", "1", "--pages", "2"]) == 0
            cls.return_value.crawl_site.assert_called_once_with(
                "https://x.com", depth=1, pages=2, concurrent=3
            )
        assert json.loads(capsys.readouterr().out)["total_pages"] == 2

    def test_site_partial_failure_exit_1(self, capsys):
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_site.return_value = {
                "successful_pages": 1,
                "total_pages": 2,
                "success_rate": "50.0%",
                "results": [_result(), _result(success=False)],
            }
            assert main(["site", "https://x.com"]) == 1
        assert json.loads(capsys.readouterr().out)["successful_pages"] == 1

    def test_site_concurrent_flag(self, capsys):
        with patch("crawl4ai_mcp.crawler.Crawler") as cls:
            cls.return_value.crawl_site.return_value = {
                "successful_pages": 2,
                "total_pages": 2,
                "success_rate": "100.0%",
                "results": [],
            }
            assert main(["site", "https://x.com", "--concurrent", "5"]) == 0
            cls.return_value.crawl_site.assert_called_once_with(
                "https://x.com", depth=2, pages=10, concurrent=5
            )


class TestImagesCli:
    def _search_result(self, download_results=None):
        result = {
            "success": True,
            "query": "cat",
            "search_results": {
                "count": 1,
                "results": [{"title": "T", "image": "https://x.com/a.jpg"}],
            },
        }
        if download_results is not None:
            result["download_results"] = download_results
        return result

    def test_images_prints_urls(self, capsys):
        with patch("crawl4ai_mcp.searcher.Searcher") as cls:
            cls.return_value.search_images.return_value = self._search_result()
            assert main(["images", "cat", "-n", "3"]) == 0
            cls.return_value.search_images.assert_called_once_with(
                "cat",
                max_results=3,
                page=1,
                backend=None,
                license_image=None,
                download=False,
                output_dir="./downloads/images",
            )
        assert capsys.readouterr().out.strip() == "https://x.com/a.jpg"

    def test_images_download_prints_paths(self, capsys):
        dr = {
            "total": 1,
            "downloaded": 1,
            "failed": 0,
            "results": [{"success": True, "filepath": "/tmp/a.jpg", "size": 2500000}],
        }
        with patch("crawl4ai_mcp.searcher.Searcher") as cls:
            cls.return_value.search_images.return_value = self._search_result(dr)
            assert main(["images", "cat", "--download", "--output-dir", "/tmp"]) == 0
            cls.return_value.search_images.assert_called_once_with(
                "cat",
                max_results=10,
                page=1,
                backend=None,
                license_image=None,
                download=True,
                output_dir="/tmp",
            )
        assert capsys.readouterr().out.strip() == "/tmp/a.jpg (2.4MB)"

    def test_images_partial_download_failure_exit_1(self, capsys):
        dr = {
            "total": 1,
            "downloaded": 0,
            "failed": 1,
            "results": [
                {"success": False, "url": "https://x.com/a.jpg", "error": "403"}
            ],
        }
        with patch("crawl4ai_mcp.searcher.Searcher") as cls:
            cls.return_value.search_images.return_value = self._search_result(dr)
            assert main(["images", "cat", "--download"]) == 1
        assert "403" in capsys.readouterr().err

    def test_images_json_output(self, capsys):
        with patch("crawl4ai_mcp.searcher.Searcher") as cls:
            cls.return_value.search_images.return_value = self._search_result()
            assert main(["images", "cat", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["query"] == "cat"

    def test_images_search_failure_exit_1(self, capsys):
        with patch("crawl4ai_mcp.searcher.Searcher") as cls:
            cls.return_value.search_images.return_value = {
                "success": False,
                "error": "boom",
            }
            assert main(["images", "cat"]) == 1
        assert "boom" in capsys.readouterr().err


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("crawl ")


def test_lazy_import_avoids_heavy_deps():
    """快速路径导入链不得连带 crawl4ai / fastmcp / openai（子进程验证）"""
    code = (
        "import sys; "
        "from crawl4ai_mcp.crawler import Crawler; "
        "heavy = {'crawl4ai', 'fastmcp', 'openai'} & set(sys.modules); "
        "assert not heavy, f'heavy deps loaded: {heavy}'"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
