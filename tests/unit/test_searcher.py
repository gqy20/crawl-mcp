"""Searcher 类单元测试"""

from unittest.mock import patch, MagicMock
from crawl4ai_mcp.searcher import Searcher


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
