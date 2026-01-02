# 搜索功能实现方案

## 一、目录结构

```
src/crawl4ai_mcp/
├── __init__.py
├── fastmcp_server.py      # 修改：新增搜索工具
├── crawler.py              # 保持不变
├── llm_config.py           # 保持不变
└── searcher.py             # 新增：搜索模块

tests/
├── unit/
│   ├── test_searcher.py    # 新增：搜索模块测试
│   ├── test_crawler.py     # 保持不变
│   └── test_llm_config.py  # 保持不变
```

## 二、依赖更新

```toml
# pyproject.toml
[project]
dependencies = [
    "beautifulsoup4>=4.13.5",
    "crawl4ai>=0.7.8",
    "fastmcp>=2.14.0",
    "nest-asyncio>=1.6.0",
    "openai>=2.0.0",
    "duckduckgo-search>=8.0.0",  # 新增
]
```

## 三、代码实现

### 3.1 searcher.py（新增）

```python
"""搜索模块 - 基于 duckduckgo-search"""

from typing import List, Dict, Any, Optional
from ddgs import DDGS


class Searcher:
    """搜索类 - 提供网页搜索功能"""

    def __init__(
        self,
        proxy: Optional[str] = None,
        timeout: int = 10,
    ):
        """
        初始化搜索器

        Args:
            proxy: 代理地址，支持 http/https/socks5
            timeout: 请求超时时间（秒）
        """
        self.ddgs = DDGS(proxy=proxy, timeout=timeout)

    def search_text(
        self,
        query: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        文本搜索 - 搜索通用网页内容

        适用于：技术文档、百科、博客、论坛、教程等

        Args:
            query: 搜索关键词
            region: 区域代码
                - wt-wt: 无区域限制（默认）
                - us-en: 美国（英语）
                - uk-en: 英国（英语）
                - cn-zh: 中国（中文）
                - jp-jp: 日本（日语）
            safesearch: 安全搜索级别
                - on: 严格过滤
                - moderate: 适度过滤（默认）
                - off: 关闭过滤
            timelimit: 时间限制
                - d: 最近一天
                - w: 最近一周
                - m: 最近一月
                - y: 最近一年
            max_results: 最大结果数

        Returns:
            {
                "success": True,
                "query": "搜索关键词",
                "count": 结果数量,
                "results": [
                    {
                        "title": "标题",
                        "href": "链接",
                        "body": "摘要"
                    },
                    ...
                ]
            }
        """
        try:
            results = list(self.ddgs.text(
                query=query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=max_results,
            ))
            return {
                "success": True,
                "query": query,
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "results": [],
            }

    def search_news(
        self,
        query: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        新闻搜索 - 搜索新闻内容

        适用于：突发新闻、时事、财经、体育等时效性内容

        Args:
            query: 搜索关键词
            region: 区域代码（同 search_text）
            safesearch: 安全搜索级别（同 search_text）
            timelimit: 时间限制
                - d: 最近一天
                - w: 最近一周
                - m: 最近一月
                - 注意：不支持 y（年）
            max_results: 最大结果数

        Returns:
            {
                "success": True,
                "query": "搜索关键词",
                "count": 结果数量,
                "results": [
                    {
                        "date": "2024-07-03T16:25:22+00:00",
                        "title": "标题",
                        "body": "摘要",
                        "url": "链接",
                        "image": "配图链接",
                        "source": "新闻来源"
                    },
                    ...
                ]
            }
        """
        try:
            results = list(self.ddgs.news(
                keywords=query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=max_results,
            ))
            return {
                "success": True,
                "query": query,
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "results": [],
            }
```

### 3.2 fastmcp_server.py（修改）

```python
"""FastMCP 服务器实现"""

from typing import List, Dict, Any, Optional, Union
from fastmcp import FastMCP
from crawl4ai_mcp.crawler import Crawler
from crawl4ai_mcp.searcher import Searcher  # 新增

# 读取包版本
try:
    from importlib.metadata import version as get_version
    __version__ = get_version("crawl_mcp")
except Exception:
    __version__ = "0.2.0"  # 版本号升级

# 创建 FastMCP 实例
mcp = FastMCP(name="crawl-mcp", version=__version__)

# 创建爬虫实例（单例）
_crawler = Crawler()

# 创建搜索器实例（单例，新增）
_searcher = Searcher()


# ========== 现有工具保持不变 ==========

@mcp.tool
def crawl_single(
    url: str,
    enhanced: bool = False,
    llm_config: Optional[Union[Dict[str, Any], str]] = None,
) -> Dict[str, Any]:
    """爬取单个网页，返回 Markdown 格式内容"""
    return _crawler.crawl_single(url, enhanced, llm_config)


@mcp.tool
def crawl_site(
    url: str,
    depth: int = 2,
    pages: int = 10,
    concurrent: int = 3,
    llm_config: Optional[Union[Dict[str, Any], str]] = None,
) -> Dict[str, Any]:
    """递归爬取整个网站"""
    return _crawler.crawl_site(url, depth, pages, concurrent)


@mcp.tool
def crawl_batch(
    urls: List[str],
    concurrent: int = 3,
    llm_config: Optional[Union[Dict[str, Any], str]] = None,
) -> List[Dict[str, Any]]:
    """批量爬取多个网页（异步并行）"""
    return _crawler.crawl_batch(urls, concurrent, llm_config)


# ========== 新增搜索工具 ==========

@mcp.tool
def search_text(
    query: str,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    搜索网页内容（通用搜索）

    适用于搜索技术文档、百科、博客、论坛、教程等静态内容。

    Args:
        query: 搜索关键词
        region: 区域代码
            - wt-wt: 无区域限制（默认）
            - us-en: 美国（英语）
            - cn-zh: 中国（中文）
            - uk-en: 英国（英语）
            - jp-jp: 日本（日语）
        safesearch: 安全搜索 (on/moderate/off)
        timelimit: 时间限制 (d=天, w=周, m=月, y=年)
        max_results: 最大结果数（默认：10）

    Returns:
        包含搜索结果的字典，格式：
        {
            "success": True,
            "query": "搜索关键词",
            "count": 5,
            "results": [
                {"title": "...", "href": "...", "body": "..."},
                ...
            ]
        }
    """
    return _searcher.search_text(query, region, safesearch, timelimit, max_results)


@mcp.tool
def search_news(
    query: str,
    region: str = "wt-wt",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    搜索新闻内容

    适用于搜索突发新闻、时事、财经、体育等时效性内容。

    Args:
        query: 搜索关键词
        region: 区域代码（同 search_text）
        safesearch: 安全搜索 (on/moderate/off)
        timelimit: 时间限制 (d=天, w=周, m=月)
        max_results: 最大结果数（默认：10）

    Returns:
        包含新闻搜索结果的字典，格式：
        {
            "success": True,
            "query": "搜索关键词",
            "count": 3,
            "results": [
                {
                    "date": "2024-07-03T16:25:22+00:00",
                    "title": "...",
                    "body": "...",
                    "url": "...",
                    "image": "...",
                    "source": "..."
                },
                ...
            ]
        }
    """
    return _searcher.search_news(query, region, safesearch, timelimit, max_results)


def main():
    """CLI 入口点"""
    import sys
    if "--http" in sys.argv:
        mcp.run(transport="http", host="0.0.0.0", port=8001)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
```

### 3.3 __init__.py（更新）

```python
"""crawl4ai_mcp - 基于 crawl4ai 和 FastMCP 的 MCP 服务器"""

__version__ = "0.2.0"

from crawl4ai_mcp.searcher import Searcher
from crawl4ai_mcp.crawler import Crawler

__all__ = ["__version__", "Searcher", "Crawler"]
```

## 四、测试用例

### tests/unit/test_searcher.py（新增）

```python
"""Searcher 类单元测试"""

import pytest
from unittest.mock import patch, MagicMock
from crawl4ai_mcp.searcher import Searcher


class TestSearcherText:
    """测试文本搜索功能"""

    def test_search_text_success(self):
        """测试成功搜索"""
        searcher = Searcher()
        query = "Python programming"

        # Mock DDGS 返回结果
        mock_results = [
            {
                "title": "Python Official Website",
                "href": "https://www.python.org",
                "body": "Welcome to Python.org",
            },
            {
                "title": "Python Tutorial",
                "href": "https://docs.python.org/tutorial",
                "body": "Python 3 tutorial",
            },
        ]

        with patch.object(searcher.ddgs, 'text', return_value=mock_results):
            result = searcher.search_text(query, max_results=10)

        # Assert
        assert result["success"] is True
        assert result["query"] == query
        assert result["count"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Python Official Website"

    def test_search_text_with_timelimit(self):
        """测试带时间限制的搜索"""
        searcher = Searcher()

        with patch.object(searcher.ddgs, 'text', return_value=[]) as mock_text:
            searcher.search_text("news", timelimit="d", max_results=5)

        # 验证参数传递
        mock_text.assert_called_once()
        call_kwargs = mock_text.call_args.kwargs
        assert call_kwargs["timelimit"] == "d"
        assert call_kwargs["max_results"] == 5

    def test_search_text_error_handling(self):
        """测试错误处理"""
        searcher = Searcher()

        with patch.object(searcher.ddgs, 'text', side_effect=Exception("Network error")):
            result = searcher.search_text("test")

        assert result["success"] is False
        assert "error" in result
        assert result["results"] == []


class TestSearcherNews:
    """测试新闻搜索功能"""

    def test_search_news_success(self):
        """测试成功搜索新闻"""
        searcher = Searcher()
        query = "technology news"

        mock_results = [
            {
                "date": "2024-07-03T16:25:22+00:00",
                "title": "Tech Giant Launches AI",
                "body": "Breaking news about AI...",
                "url": "https://example.com/news1",
                "image": "https://example.com/image1.jpg",
                "source": "TechNews",
            }
        ]

        with patch.object(searcher.ddgs, 'news', return_value=mock_results):
            result = searcher.search_news(query, max_results=10)

        assert result["success"] is True
        assert result["count"] == 1
        assert "date" in result["results"][0]
        assert "source" in result["results"][0]

    def test_search_news_error_handling(self):
        """测试新闻搜索错误处理"""
        searcher = Searcher()

        with patch.object(searcher.ddgs, 'news', side_effect=Exception("API error")):
            result = searcher.search_news("test")

        assert result["success"] is False
        assert result["results"] == []


class TestSearcherIntegration:
    """集成测试"""

    @pytest.mark.skipif(True, reason="需要网络连接，默认跳过")
    def test_search_text_real(self):
        """真实搜索测试（默认跳过）"""
        searcher = Searcher()
        result = searcher.search_text("Python", max_results=3)
        assert result["success"] is True
        assert result["count"] > 0
```

## 五、README 更新

### 新增功能说明

```markdown
## 功能

- **crawl_single** - 爬取单个网页，返回 Markdown 格式
- **crawl_site** - 递归爬取整个网站
- **crawl_batch** - 批量爬取多个网页（异步并行）
- **search_text** - 搜索网页内容（通用搜索）
- **search_news** - 搜索新闻内容
- **LLM 集成** - AI 驱动的内容提取和摘要
```

### 新增使用示例

```markdown
### 搜索功能示例

#### 文本搜索
```json
{
  "name": "search_text",
  "arguments": {
    "query": "Python 快速排序算法",
    "region": "cn-zh",
    "max_results": 5
  }
}
```

#### 新闻搜索
```json
{
  "name": "search_news",
  "arguments": {
    "query": "人工智能最新进展",
    "timelimit": "w",
    "max_results": 10
  }
}
```
```

## 六、版本变更

### CHANGELOG.md（新增）

```markdown
# Changelog

## [0.2.0] - 2025-01-02

### Added
- 新增 `search_text` 工具：通用网页搜索
- 新增 `search_news` 工具：新闻内容搜索
- 新增 `Searcher` 类：基于 duckduckgo-search 的搜索模块
- 依赖新增 `duckduckgo-search>=8.0.0`

### Changed
- 版本号升级至 0.2.0

## [0.1.1] - 2024-12-XX
- 初始版本
```

## 七、实现检查清单

- [ ] 更新 `pyproject.toml` 依赖
- [ ] 创建 `src/crawl4ai_mcp/searcher.py`
- [ ] 修改 `src/crawl4ai_mcp/fastmcp_server.py`
- [ ] 更新 `src/crawl4ai_mcp/__init__.py`
- [ ] 创建 `tests/unit/test_searcher.py`
- [ ] 更新 `README.md`
- [ ] 创建 `CHANGELOG.md`
- [ ] 运行测试：`uv run pytest tests/unit/test_searcher.py`
- [ ] 运行 lint：`uv run ruff check . && uv run ruff format .`
- [ ] 手动测试 MCP 工具
- [ ] 更新版本号至 0.2.0
- [ ] 提交代码
```
