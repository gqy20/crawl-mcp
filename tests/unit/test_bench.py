"""bench.py 的判定逻辑测试（不需要联网）"""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "bench", Path(__file__).resolve().parents[2] / "scripts" / "bench.py"
)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def _row(**kw):
    base = {
        "ok": False,
        "chars": 0,
        "error_code": None,
        "expect": None,
        "expect_texts": (),
        "missing_texts": [],
    }
    base.update(kw)
    return base


class TestJudge:
    def test_success_meets_expectation(self):
        verdict, detail = bench._judge(_row(ok=True, chars=1000))
        assert verdict == "✓"
        assert detail == ""

    def test_too_short_content_fails_expectation(self):
        verdict, detail = bench._judge(_row(ok=True, chars=10))
        assert verdict == "✗"
        assert "正文过短" in detail

    def test_failed_crawl_fails_expectation(self):
        verdict, detail = bench._judge(_row(error_code="http_403"))
        assert verdict == "✗"
        assert "http_403" in detail

    def test_expected_error_meets_expectation(self):
        row = _row(error_code="empty_content", expect=("error", "empty_content"))
        verdict, detail = bench._judge(row)
        assert verdict == "✓"
        assert detail == ""

    def test_expected_error_but_different_code_is_regression(self):
        row = _row(error_code="http_404", expect=("error", "empty_content"))
        verdict, detail = bench._judge(row)
        assert verdict == "✗"
        assert "empty_content" in detail and "http_404" in detail

    def test_expected_error_but_succeeded_is_regression(self):
        row = _row(ok=True, chars=500, expect=("error", "empty_content"))
        verdict, detail = bench._judge(row)
        assert verdict == "✗"
        assert "实际成功" in detail


class TestJudgeExpectText:
    def test_text_present_passes(self):
        row = _row(ok=True, chars=500, expect_texts=("AirPods",), missing_texts=[])
        assert bench._judge(row) == ("✓", "")

    def test_text_missing_fails(self):
        row = _row(
            ok=True, chars=500, expect_texts=("AirPods",), missing_texts=["AirPods"]
        )
        verdict, detail = bench._judge(row)
        assert verdict == "✗"
        assert "缺关键内容" in detail and "AirPods" in detail

    def test_text_irrelevant_when_expect_error(self):
        """预期失败的用例不看关键内容"""
        row = _row(
            error_code="http_404",
            expect=("error", "http_404"),
            expect_texts=("x",),
            missing_texts=["x"],
        )
        assert bench._judge(row) == ("✓", "")


class TestFormatTimings:
    def test_missing_stages_show_dash(self):
        assert bench._fmt_timings({"fast": 0.2}) == "f0.2 c- b-"

    def test_all_stages(self):
        text = bench._fmt_timings({"fast": 0.3, "cloud": 2.8, "browser": 26.4})
        assert text == "f0.3 c2.8 b26.4"

    def test_none_timings(self):
        assert bench._fmt_timings(None) == "f- c- b-"


@pytest.mark.parametrize("case", bench.QUICK_CASES + bench.FULL_CASES)
def test_every_case_has_group_url_and_expect(case):
    """数据集格式统一：(渠道, URL, 预期, 关键内容)"""
    assert len(case) == 4
    group, url, expect, texts = case
    assert group and url.startswith("https://")
    assert expect is None or expect[0] == "error"
    # 关键内容只允许配在预期成功的用例上
    assert not texts or expect is None


def test_site_cases_format():
    """站内用例格式：(渠道, URL, 深度, 页数)，深度/页数有下限"""
    assert bench.SITES, "bench.yml 应至少有一个 sites 用例"
    for group, url, depth, pages in bench.SITES:
        assert group and url.startswith("https://")
        assert depth >= 1 and pages >= bench.SITE_MIN_OK


def test_render_includes_site_section():
    run = {
        "ts": "t",
        "mode": "quick",
        "env": {"python": "3", "crawl4ai": "0", "fastmcp": "0", "ddgs": "0"},
        "cloud": "未启用",
        "crawls": [],
        "searches": [],
        "sites": [
            {
                "group": "工具文档-x",
                "depth": 1,
                "ok_pages": 5,
                "pages": 5,
                "sec": 2.1,
                "verdict": "✓",
                "detail": "",
            }
        ],
        "summary": bench._summary([], []),
    }
    out = bench.render(run, [])
    assert "站内爬取" in out
    assert "5/5" in out and "2.1s" in out
