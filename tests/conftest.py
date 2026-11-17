"""Pytest 配置文件"""

import os
import sys
from pathlib import Path

import pytest

# 添加 src 目录到 Python 路径
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(autouse=True)
def _isolate_cloud_env(monkeypatch):
    """测试不依赖开发者本地的 .env

    `uv run` 会自动把 .env 注入环境，若本地配了 CRAWL4AI_API_KEY，
    Cloud 兜底会在测试里意外生效，导致降级链路断言不稳定。
    """
    monkeypatch.delenv("CRAWL4AI_API_KEY", raising=False)
    monkeypatch.delenv("CRAWL4AI_CLOUD_KEY", raising=False)
    monkeypatch.setenv("CRAWL4AI_CLOUD_FALLBACK", "0")
    os.environ.pop("CRAWL4AI_API_KEY", None)
    os.environ.pop("CRAWL4AI_CLOUD_KEY", None)


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch, tmp_path):
    """测试走独立缓存目录，避免读到开发者本地的缓存条目"""
    monkeypatch.setenv("CRAWL_MCP_CACHE", "0")
    monkeypatch.setenv("CRAWL_MCP_CACHE_DIR", str(tmp_path / "cache"))
