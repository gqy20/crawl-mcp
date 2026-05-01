"""Searcher 重构测试 — TDD 红阶段

覆盖范围：
- _search_wrapper 通用搜索方法（消除 search_text/search_news 重复）
- _download_images 并行下载
"""

from unittest.mock import patch, MagicMock
from crawl4ai_mcp.searcher import Searcher


# ============================================================
# 1. _search_wrapper — 消除 search_text/search_news 重复
# ============================================================


class TestSearchWrapperExists:
    """验证 _search_wrapper 方法存在且行为正确"""

    def test_search_wrapper_method_exists(self):
        """_search_wrapper 应该作为公共方法存在"""
        searcher = Searcher()
        assert hasattr(searcher, "_search_wrapper")

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_wrapper_returns_success_format(self, mock_ddgs_class):
        """_search_wrapper 成功时应返回标准格式"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.return_value = iter(
            [{"title": "Test", "href": "https://t.com", "body": "content"}]
        )

        searcher = Searcher()
        result = searcher._search_wrapper(
            lambda ddgs, **kw: ddgs.text(**kw),
            "test query",
            max_results=10,
        )

        assert result["success"] is True
        assert result["query"] == "test query"
        assert result["count"] == 1
        assert len(result["results"]) == 1

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_wrapper_handles_empty_results(self, mock_ddgs_class):
        """_search_wrapper 空结果应返回成功但 count=0"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.news.return_value = iter([])

        searcher = Searcher()
        result = searcher._search_wrapper(lambda ddgs, **kw: ddgs.news(**kw), "empty")

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_wrapper_handles_exception(self, mock_ddgs_class):
        """_search_wrapper 异常应返回错误格式"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.side_effect = ConnectionError("network down")

        searcher = Searcher()
        result = searcher._search_wrapper(lambda ddgs, **kw: ddgs.text(**kw), "fail")

        assert result["success"] is False
        assert "error" in result
        assert result["results"] == []
        assert result["query"] == "fail"


class TestSearchTextUsesWrapper:
    """验证 search_text 委托给 _search_wrapper"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_text_delegates_to_wrapper(self, mock_ddgs_class):
        """search_text 应通过 _search_wrapper 实现逻辑"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.return_value = iter([{"title": "T", "href": "h", "body": "b"}])

        searcher = Searcher()

        with patch.object(
            searcher,
            "_search_wrapper",
            wraps=searcher._search_wrapper,
        ) as mock_wrapper:
            searcher.search_text("python", max_results=5)

            mock_wrapper.assert_called_once()
            call_args = mock_wrapper.call_args
            # 第一个位置参数是 search_fn
            assert callable(call_args[0][0])
            # 第二个是 query
            assert call_args[0][1] == "python"


class TestSearchNewsUsesWrapper:
    """验证 search_news 委托给 _search_wrapper"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_news_delegates_to_wrapper(self, mock_ddgs_class):
        """search_news 应通过 _search_wrapper 实现逻辑"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.news.return_value = iter(
            [{"date": "2024", "title": "N", "body": "b", "url": "u"}]
        )

        searcher = Searcher()

        with patch.object(
            searcher,
            "_search_wrapper",
            wraps=searcher._search_wrapper,
        ) as mock_wrapper:
            searcher.search_news("tech", max_results=3)

            mock_wrapper.assert_called_once()


# ============================================================
# 2. _download_images 并行下载
# ============================================================


class TestDownloadImagesParallel:
    """验证图片下载支持并行"""

    @patch("crawl4ai_mcp.searcher.requests.get")
    def test_download_multiple_images_concurrently(self, mock_get):
        """多张图片应并行下载而非串行"""
        import concurrent.futures

        original_submit = concurrent.futures.ThreadPoolExecutor.submit
        submit_calls = []

        def tracking_submit(self_, fn, *args, **kwargs):
            submit_calls.append((fn, args, kwargs))
            return original_submit(self_, fn, *args, **kwargs)

        with patch.object(
            concurrent.futures.ThreadPoolExecutor, "submit", tracking_submit
        ):
            mock_response = MagicMock()
            mock_response.iter_content = MagicMock(return_value=[b"data"])
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            images = [{"image": f"https://example.com/img{i}.jpg"} for i in range(3)]

            searcher = Searcher()
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                searcher._download_images(images, tmpdir)

        # 验证使用了 ThreadPoolExecutor（即并行下载）
        assert len(submit_calls) == 3

    @patch("crawl4ai_mcp.searcher.requests.get")
    def test_download_preserves_result_order(self, mock_get):
        """并行下载后结果顺序应与输入一致"""
        mock_response = MagicMock()
        mock_response.iter_content = MagicMock(return_value=[b"data"])
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        images = [
            {"image": "https://a.com/1.jpg"},
            {"image": "https://b.com/2.jpg"},
            {"image": "https://c.com/3.jpg"},
        ]

        searcher = Searcher()
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            result = searcher._download_images(images, tmpdir)

        urls = [r["url"] for r in result["results"]]
        assert urls == [
            "https://a.com/1.jpg",
            "https://b.com/2.jpg",
            "https://c.com/3.jpg",
        ]


# ============================================================
# 3. extract_url — 基于 ddgs.extract() 的轻量 URL 提取
# ============================================================


class TestExtractUrlExists:
    """验证 extract_url 方法存在且行为正确"""

    def test_extract_url_method_exists(self):
        """extract_url 应该作为公共方法存在"""
        searcher = Searcher()
        assert hasattr(searcher, "extract_url")

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_extract_url_returns_markdown(self, mock_ddgs_class):
        """extract_url 默认应返回 Markdown 格式内容"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.extract.return_value = {
            "url": "https://example.com",
            "content": "# Hello\n\nWorld content",
        }

        searcher = Searcher()
        result = searcher.extract_url("https://example.com")

        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert result["content"] == "# Hello\n\nWorld content"
        assert "markdown" in result or "content" in result

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_extract_url_handles_error(self, mock_ddgs_class):
        """extract_url 异常时应返回错误格式"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.extract.side_effect = Exception("Connection timeout")

        searcher = Searcher()
        result = searcher.extract_url("https://timeout.example.com")

        assert result["success"] is False
        assert "error" in result
        assert result["url"] == "https://timeout.example.com"

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_extract_url_passes_fmt_param(self, mock_ddgs_class):
        """extract_url 应支持 fmt 参数传递"""
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.extract.return_value = {
            "url": "https://example.com",
            "content": "plain text",
        }

        searcher = Searcher()
        searcher.extract_url("https://example.com", fmt="text_plain")

        mock_ddgs.extract.assert_called_once_with(
            "https://example.com", fmt="text_plain"
        )


class TestExtractUrlMCPToolRegistered:
    """验证 extract_url 已注册为 MCP 工具"""

    def test_extract_url_tool_registered(self):
        """fastmcp_server 应注册 extract_url 工具"""
        import asyncio
        from crawl4ai_mcp.fastmcp_server import mcp

        tools = asyncio.run(mcp.list_tools())
        tool_names = [t.name for t in tools]
        assert "extract_url" in tool_names


# ============================================================
# 4. search_books / search_videos — 新增搜索类型
# ============================================================


class TestSearchBooksExists:
    """验证 search_books 方法存在且行为正确"""

    def test_search_books_method_exists(self):
        searcher = Searcher()
        assert hasattr(searcher, "search_books")

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_books_returns_results(self, mock_ddgs_class):
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.books.return_value = iter(
            [
                {
                    "title": "Clean Code",
                    "author": "Robert C. Martin",
                    "url": "https://example.com/clean-code",
                }
            ]
        )

        result = Searcher().search_books("clean code", max_results=5)

        assert result["success"] is True
        assert result["query"] == "clean code"
        assert result["count"] == 1
        assert result["results"][0]["title"] == "Clean Code"

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_books_delegates_to_wrapper(self, mock_ddgs_class):
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.books.return_value = iter([])

        searcher = Searcher()
        with patch.object(
            searcher, "_search_wrapper", wraps=searcher._search_wrapper
        ) as mock_wrapper:
            searcher.search_books("python")

            mock_wrapper.assert_called_once()


class TestSearchVideosExists:
    """验证 search_videos 方法存在且行为正确"""

    def test_search_videos_method_exists(self):
        searcher = Searcher()
        assert hasattr(searcher, "search_videos")

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_videos_returns_results(self, mock_ddgs_class):
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.videos.return_value = iter(
            [
                {
                    "title": "Python Tutorial",
                    "url": "https://youtube.com/watch?v=abc",
                    "duration": "10:30",
                }
            ]
        )

        result = Searcher().search_videos("python tutorial", max_results=5)

        assert result["success"] is True
        assert result["query"] == "python tutorial"
        assert result["count"] == 1

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_videos_delegates_to_wrapper(self, mock_ddgs_class):
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.videos.return_value = iter([])

        searcher = Searcher()
        with patch.object(
            searcher, "_search_wrapper", wraps=searcher._search_wrapper
        ) as mock_wrapper:
            searcher.search_videos("test")

            mock_wrapper.assert_called_once()


class TestSearchBooksVideosMCPRegistered:
    """验证新搜索工具已注册为 MCP 工具"""

    def test_search_books_tool_registered(self):
        import asyncio
        from crawl4ai_mcp.fastmcp_server import mcp

        tools = asyncio.run(mcp.list_tools())
        tool_names = [t.name for t in tools]
        assert "search_books" in tool_names

    def test_search_videos_tool_registered(self):
        import asyncio
        from crawl4ai_mcp.fastmcp_server import mcp

        tools = asyncio.run(mcp.list_tools())
        tool_names = [t.name for t in tools]
        assert "search_videos" in tool_names
