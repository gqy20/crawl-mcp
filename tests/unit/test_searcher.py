"""Searcher 类单元测试"""

from unittest.mock import patch, MagicMock
from crawl4ai_mcp.searcher import Searcher
import tempfile


class TestSearcherText:
    """测试文本搜索功能"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_text_success(self, mock_ddgs_class):
        """测试成功搜索 - 返回正确格式的结果"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.return_value = iter(
            [
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
        )
        searcher = Searcher()
        query = "Python programming"

        # Act
        result = searcher.search_text(query, max_results=10)

        # Assert
        assert result["success"] is True
        assert result["query"] == query
        assert result["count"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Python Official Website"
        assert result["results"][0]["href"] == "https://www.python.org"
        assert result["results"][1]["body"] == "Python 3 tutorial"

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_text_empty_results(self, mock_ddgs_class):
        """测试无搜索结果 - 返回空列表但成功"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.return_value = iter([])
        searcher = Searcher()

        # Act
        result = searcher.search_text("nonexistent_term_xyz123")

        # Assert
        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_text_network_error(self, mock_ddgs_class):
        """测试网络错误 - 返回错误信息"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.text.side_effect = Exception("Network error")
        searcher = Searcher()

        # Act
        result = searcher.search_text("test")

        # Assert
        assert result["success"] is False
        assert "error" in result
        assert result["results"] == []
        assert result["query"] == "test"


class TestSearcherNews:
    """测试新闻搜索功能"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_news_success(self, mock_ddgs_class):
        """测试成功搜索新闻 - 返回包含日期和来源的结果"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.news.return_value = iter(
            [
                {
                    "date": "2024-07-03T16:25:22+00:00",
                    "title": "Tech Giant Launches AI",
                    "body": "Breaking news about AI...",
                    "url": "https://example.com/news1",
                    "image": "https://example.com/image1.jpg",
                    "source": "TechNews",
                }
            ]
        )
        searcher = Searcher()
        query = "technology news"

        # Act
        result = searcher.search_news(query, max_results=10)

        # Assert
        assert result["success"] is True
        assert result["count"] == 1
        assert "date" in result["results"][0]
        assert "source" in result["results"][0]
        assert result["results"][0]["source"] == "TechNews"
        assert result["results"][0]["url"] == "https://example.com/news1"

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_news_error_handling(self, mock_ddgs_class):
        """测试新闻搜索错误处理 - 返回错误信息"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.news.side_effect = Exception("API error")
        searcher = Searcher()

        # Act
        result = searcher.search_news("test")

        # Assert
        assert result["success"] is False
        assert result["results"] == []
        assert "error" in result

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_news_empty_results(self, mock_ddgs_class):
        """测试无新闻结果 - 返回空列表但成功"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.news.return_value = iter([])
        searcher = Searcher()

        # Act
        result = searcher.search_news("ancient_history")

        # Assert
        assert result["success"] is True
        assert result["count"] == 0


class TestSearcherInit:
    """测试 Searcher 初始化"""

    def test_init_default_parameters(self):
        """测试默认初始化参数"""
        # Act
        searcher = Searcher()

        # Assert
        assert searcher is not None


class TestSearcherImages:
    """测试图片搜索功能"""

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_images_only_search(self, mock_ddgs_class):
        """测试仅搜索图片（不下载不分析）"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter(
            [
                {
                    "title": "Beautiful sunset",
                    "image": "https://example.com/sunset.jpg",
                    "thumbnail": "https://example.com/sunset_thumb.jpg",
                    "url": "https://example.com/page",
                    "height": 1080,
                    "width": 1920,
                    "source": "Bing",
                },
                {
                    "title": "Mountain landscape",
                    "image": "https://example.com/mountain.jpg",
                    "thumbnail": "https://example.com/mountain_thumb.jpg",
                    "url": "https://example.com/page2",
                    "height": 1200,
                    "width": 1600,
                    "source": "Google",
                },
            ]
        )
        searcher = Searcher()
        query = "beautiful landscape"

        # Act
        result = searcher.search_images(query, max_results=10)

        # Assert
        assert result["success"] is True
        assert result["query"] == query
        assert "search_results" in result
        assert result["search_results"]["count"] == 2
        assert len(result["search_results"]["results"]) == 2
        # 不应该有 download_results 或 analysis_results
        assert "download_results" not in result
        assert "analysis_results" not in result

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_images_empty_results(self, mock_ddgs_class):
        """测试无图片搜索结果"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter([])
        searcher = Searcher()

        # Act
        result = searcher.search_images("xyz_nonexistent_term")

        # Assert
        assert result["success"] is True
        assert result["search_results"]["count"] == 0
        assert result["search_results"]["results"] == []

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_images_error(self, mock_ddgs_class):
        """测试搜索失败"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.side_effect = Exception("Network error")
        searcher = Searcher()

        # Act
        result = searcher.search_images("test")

        # Assert
        assert result["success"] is False
        assert "error" in result

    @patch("crawl4ai_mcp.searcher.DDGS")
    @patch("crawl4ai_mcp.searcher.requests.get")
    def test_search_images_with_download(self, mock_get, mock_ddgs_class):
        """测试搜索并下载图片"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter(
            [
                {
                    "title": "Test image",
                    "image": "https://example.com/test.jpg",
                    "thumbnail": "https://example.com/test_thumb.jpg",
                    "url": "https://example.com/page",
                    "height": 500,
                    "width": 500,
                    "source": "Test",
                },
            ]
        )

        # Mock HTTP 响应
        mock_response = MagicMock()
        mock_response.iter_content = MagicMock(return_value=[b"fake_image_data"])
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        searcher = Searcher()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Act
            result = searcher.search_images(
                "test", max_results=10, download=True, output_dir=tmpdir
            )

            # Assert
            assert result["success"] is True
            assert "download_results" in result
            assert result["download_results"]["total"] == 1
            assert result["download_results"]["downloaded"] == 1
            assert result["download_results"]["failed"] == 0
            assert len(result["download_results"]["results"]) == 1
            assert result["download_results"]["results"][0]["success"] is True
            assert "filepath" in result["download_results"]["results"][0]

    @patch("crawl4ai_mcp.searcher.DDGS")
    @patch("crawl4ai_mcp.searcher.requests.get")
    @patch("crawl4ai_mcp.searcher.OpenAI")
    def test_search_images_with_download_and_analyze(
        self, mock_openai_class, mock_get, mock_ddgs_class
    ):
        """测试搜索、下载并分析图片"""
        # Arrange - DDGS mock
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter(
            [
                {
                    "title": "Test image",
                    "image": "https://example.com/test.jpg",
                    "thumbnail": "https://example.com/test_thumb.jpg",
                    "url": "https://example.com/page",
                    "height": 500,
                    "width": 500,
                    "source": "Test",
                },
            ]
        )

        # Mock HTTP 响应
        mock_response = MagicMock()
        mock_response.iter_content = MagicMock(return_value=[b"fake_image_data"])
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Mock OpenAI 客户端
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="这是一张测试图片"))
        ]
        mock_client.chat.completions.create.return_value = mock_completion

        # 设置环境变量
        import os

        os.environ["OPENAI_API_KEY"] = "test_key"

        searcher = Searcher()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Act
            result = searcher.search_images(
                "test",
                max_results=10,
                download=True,
                output_dir=tmpdir,
                analyze=True,
                analysis_prompt="描述这张图片",
            )

            # Assert
            assert result["success"] is True
            assert "download_results" in result
            assert "analysis_results" in result
            assert result["analysis_results"]["count"] == 1
            assert len(result["analysis_results"]["results"]) == 1
            assert "analysis" in result["analysis_results"]["results"][0]

    @patch("crawl4ai_mcp.searcher.DDGS")
    @patch("crawl4ai_mcp.searcher.OpenAI")
    def test_search_images_analyze_without_download(
        self, mock_openai_class, mock_ddgs_class
    ):
        """测试仅分析图片（不下载）- 使用 URL"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter(
            [
                {
                    "title": "Test image",
                    "image": "https://example.com/test.jpg",
                    "thumbnail": "https://example.com/test_thumb.jpg",
                    "url": "https://example.com/page",
                    "height": 500,
                    "width": 500,
                    "source": "Test",
                },
            ]
        )

        # Mock OpenAI 客户端
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="这是一张美丽的风景图片"))
        ]
        mock_client.chat.completions.create.return_value = mock_completion

        import os

        os.environ["OPENAI_API_KEY"] = "test_key"

        searcher = Searcher()

        # Act
        result = searcher.search_images(
            "landscape", max_results=10, analyze=True, analysis_prompt="描述这张图片"
        )

        # Assert
        assert result["success"] is True
        assert "download_results" not in result
        assert "analysis_results" in result
        assert result["analysis_results"]["count"] == 1
        assert result["analysis_results"]["results"][0]["type"] == "url"

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_search_images_with_filters(self, mock_ddgs_class):
        """测试带过滤条件的图片搜索"""
        # Arrange
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        mock_ddgs.images.return_value = iter([{"title": "Red photo", "image": "url"}])

        searcher = Searcher()

        # Act
        searcher.search_images(
            "flower",
            size="Large",
            color="Red",
            type_image="photo",
            layout="Square",
        )

        # Assert - 验证参数传递正确
        mock_ddgs.images.assert_called_once()
        call_kwargs = mock_ddgs.images.call_args[1]
        assert call_kwargs["size"] == "Large"
        assert call_kwargs["color"] == "Red"
        assert call_kwargs["type_image"] == "photo"
        assert call_kwargs["layout"] == "Square"
