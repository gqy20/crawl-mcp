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
    """数据集格式统一：(渠道, URL, 预期)"""
    assert len(case) == 3
    group, url, expect = case
    assert group and url.startswith("https://")
    assert expect is None or expect[0] == "error"
