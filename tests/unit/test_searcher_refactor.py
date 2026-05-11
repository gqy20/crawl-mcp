"""Searcher 完整测试 — 合并自 test_searcher.py + test_searcher_refactor.py

覆盖范围：
- _search_wrapper 通用搜索方法（成功/空结果/异常）
- search_text / search_news 委托验证
- extract_url 轻量提取（含格式参数）
- search_books / search_videos 新增搜索类型
- 图片搜索（纯搜索/下载/分析/过滤，全链路）
- 并行下载（顺序保持）
- MCP 工具注册验证
"""

from unittest.mock import patch, MagicMock, AsyncMock
from crawl4ai_mcp.searcher import Searcher
import tempfile


# ============================================================
# 1. _search_wrapper — 核心搜索逻辑
# ============================================================


class TestSearchWrapper:
    """_search_wrapper 统一搜索行为"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_success_returns_standard_format(self, mock_ddgs_class):
        """成功搜索返回标准格式"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.return_value = iter(
            [{"title": "T", "href": "https://t.com", "body": "b"}]
        )

        result = Searcher()._search_wrapper(
            lambda ddgs, **kw: ddgs.text(**kw), "q", max_results=10
        )

        assert result["success"] is True
        assert result["query"] == "q"
        assert result["count"] == 1
        assert len(result["results"]) == 1

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_empty_results_returns_success_with_zero_count(self, mock_ddgs_class):
        """空结果返回成功但 count=0"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.news.return_value = iter([])

        result = Searcher()._search_wrapper(lambda ddgs, **kw: ddgs.news(**kw), "empty")

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_exception_returns_error_format(self, mock_ddgs_class):
        """异常返回错误格式"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.side_effect = ConnectionError("down")

        result = Searcher()._search_wrapper(lambda ddgs, **kw: ddgs.text(**kw), "fail")

        assert result["success"] is False
        assert "error" in result
        assert result["results"] == []
        assert result["query"] == "fail"


class TestSearchDelegation:
    """验证各搜索方法委托给 _search_wrapper"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_text_delegates_to_wrapper(self, mock_ddgs_class):
        """search_text 委托给 _search_wrapper"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.return_value = iter([{"title": "T"}])

        s = Searcher()
        with patch.object(s, "_search_wrapper", wraps=s._search_wrapper) as w:
            s.search_text("python", max_results=5)
            w.assert_called_once()

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_news_delegates_to_wrapper(self, mock_ddgs_class):
        """search_news 委托给 _search_wrapper"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.news.return_value = iter([{"title": "N"}])

        s = Searcher()
        with patch.object(s, "_search_wrapper", wraps=s._search_wrapper) as w:
            s.search_news("tech", max_results=3)
            w.assert_called_once()

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_books_delegates_to_wrapper(self, mock_ddgs_class):
        """search_books 委托给 _search_wrapper"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.books.return_value = iter([])

        s = Searcher()
        with patch.object(s, "_search_wrapper", wraps=s._search_wrapper) as w:
            s.search_books("python")
            w.assert_called_once()

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_videos_delegates_to_wrapper(self, mock_ddgs_class):
        """search_videos 委托给 _search_wrapper"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.videos.return_value = iter([])

        s = Searcher()
        with patch.object(s, "_search_wrapper", wraps=s._search_wrapper) as w:
            s.search_videos("test")
            w.assert_called_once()


# ============================================================
# 2. extract_url — 轻量 URL 提取
# ============================================================


class TestExtractUrl:
    """extract_url 基于 ddgs.extract()"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_returns_markdown_by_default(self, mock_ddgs_class):
        """默认返回 Markdown 格式"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.extract.return_value = {
            "url": "https://example.com",
            "content": "# Hello\n\nWorld",
        }

        result = Searcher().extract_url("https://example.com")

        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert result["content"] == "# Hello\n\nWorld"
        assert result["fmt"] == "text_markdown"

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_handles_error(self, mock_ddgs_class):
        """异常时返回错误格式"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.extract.side_effect = Exception("timeout")

        result = Searcher().extract_url("https://slow.example.com")

        assert result["success"] is False
        assert "error" in result
        assert result["url"] == "https://slow.example.com"

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_passes_fmt_param_to_ddgs(self, mock_ddgs_class):
        """fmt 参数正确传递给 DDGS"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.extract.return_value = {"url": "u", "content": "plain"}

        Searcher().extract_url("https://example.com", fmt="text_plain")

        mock_ddgs.extract.assert_called_once_with(
            "https://example.com", fmt="text_plain"
        )


# ============================================================
# 3. search_books / search_videos — 新增搜索类型
# ============================================================


class TestSearchBooksVideos:
    """books 和 videos 搜索"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_books_returns_results(self, mock_ddgs_class):
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.books.return_value = iter([{"title": "Clean Code", "author": "RCM"}])

        result = Searcher().search_books("clean code", max_results=5)

        assert result["success"] is True
        assert result["count"] == 1
        assert result["results"][0]["title"] == "Clean Code"

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_videos_returns_results(self, mock_ddgs_class):
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.videos.return_value = iter(
            [{"title": "Python Tutorial", "url": "https://yt.com/v"}]
        )

        result = Searcher().search_videos("python tutorial", max_results=5)

        assert result["success"] is True
        assert result["results"][0]["title"] == "Python Tutorial"


# ============================================================
# 4. search_images — 全链路（搜索/下载/分析/过滤）
# ============================================================


class TestSearchImages:
    """图片搜索完整场景"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_only_returns_no_download_or_analysis(self, mock_ddgs_class):
        """仅搜索时不包含 download_results 和 analysis_results"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter(
            [
                {
                    "title": "Sunset",
                    "image": "https://img.com/sunset.jpg",
                    "thumbnail": "https://img.com/s_t.jpg",
                    "height": 1080,
                    "width": 1920,
                    "source": "Bing",
                }
            ]
        )

        result = Searcher().search_images("sunset", max_results=10)

        assert result["success"] is True
        assert result["search_results"]["count"] == 1
        assert "download_results" not in result
        assert "analysis_results" not in result

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_empty_results_handled_gracefully(self, mock_ddgs_class):
        """空结果正常返回"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter([])

        result = Searcher().search_images("xyz_nonexistent")

        assert result["success"] is True
        assert result["search_results"]["count"] == 0

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_network_error_returns_error(self, mock_ddgs_class):
        """网络错误返回错误信息"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.side_effect = Exception("Network error")

        result = Searcher().search_images("test")

        assert result["success"] is False
        assert "error" in result

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_filter_params_passed_to_ddgs(self, mock_ddgs_class):
        """过滤参数正确传递"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter([{"title": "R"}])

        Searcher().search_images(
            "flower", size="Large", color="Red", type_image="photo", layout="Square"
        )

        kw = mock_ddgs.images.call_args[1]
        assert kw["size"] == "Large"
        assert kw["color"] == "Red"
        assert kw["type_image"] == "photo"
        assert kw["layout"] == "Square"

    @patch("crawl4ai_mcp.searcher.DDGS")
    @patch("crawl4ai_mcp.searcher.requests.get")
    def test_download_writes_files_to_output_dir(self, mock_get, mock_ddgs_class):
        """下载模式写入文件到指定目录"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter(
            [{"title": "Img", "image": "https://a.com/img.jpg"}]
        )

        mock_response = MagicMock()
        mock_response.iter_content = MagicMock(return_value=[b"data"])
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            result = Searcher().search_images(
                "test", max_results=10, download=True, output_dir=tmpdir
            )

        assert result["download_results"]["total"] == 1
        assert result["download_results"]["downloaded"] == 1
        assert result["download_results"]["results"][0]["success"] is True

    @patch("crawl4ai_mcp.searcher.DDGS")
    @patch("crawl4ai_mcp.searcher.requests.get")
    @patch("crawl4ai_mcp.searcher.AsyncOpenAI")
    def test_analyze_without_download_uses_url(
        self, mock_openai, mock_get, mock_ddgs_class
    ):
        """不下载时分析使用原始 URL"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter(
            [{"title": "Img", "image": "https://a.com/img.jpg"}]
        )

        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="beautiful landscape"))]
        )

        import os

        os.environ["OPENAI_API_KEY"] = "test_key"
        result = Searcher().search_images(
            "landscape", max_results=10, analyze=True, analysis_prompt="describe it"
        )

        assert "analysis_results" in result
        assert result["analysis_results"]["results"][0]["type"] == "url"
        assert "download_results" not in result


# ============================================================
# 5. 并行下载 — 顺序保证
# ============================================================


class TestDownloadImagesParallel:
    """并行下载行为验证"""

    @patch("crawl4ai_mcp.searcher.requests.get")
    def test_preserves_input_order(self, mock_get):
        """并行下载后结果顺序与输入一致"""
        mock_response = MagicMock()
        mock_response.iter_content = MagicMock(return_value=[b"data"])
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        images = [
            {"image": "https://a.com/1.jpg"},
            {"image": "https://b.com/2.jpg"},
            {"image": "https://c.com/3.jpg"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = Searcher()._download_images(images, tmpdir)

        urls = [r["url"] for r in result["results"]]
        assert urls == [
            "https://a.com/1.jpg",
            "https://b.com/2.jpg",
            "https://c.com/3.jpg",
        ]


# ============================================================
# 6. MCP 工具注册验证
# ============================================================


class TestMCPToolRegistration:
    """所有搜索工具已注册为 MCP 工具"""

    def _tool_names(self):
        import asyncio
        from crawl4ai_mcp.fastmcp_server import mcp

        return [t.name for t in asyncio.run(mcp.list_tools())]

    def test_extract_url_registered(self):
        assert "extract_url" in self._tool_names()

    def test_search_text_registered(self):
        assert "search_text" in self._tool_names()

    def test_search_news_registered(self):
        assert "search_news" in self._tool_names()

    def test_search_books_registered(self):
        assert "search_books" in self._tool_names()

    def test_search_videos_registered(self):
        assert "search_videos" in self._tool_names()

    def test_search_images_registered(self):
        assert "search_images" in self._tool_names()
