"""Searcher 类单元测试"""

from unittest.mock import patch, MagicMock
from crawl4ai_mcp.searcher import Searcher


class TestSearcherText:
    """测试文本搜索功能"""

    def test_search_text_success(self):
        """测试成功搜索 - 返回正确格式的结果"""
        # Arrange
        searcher = Searcher()
        query = "Python programming"

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

        # Act
        with patch.object(searcher.ddgs, "text", return_value=iter(mock_results)):
            result = searcher.search_text(query, max_results=10)

        # Assert
        assert result["success"] is True
        assert result["query"] == query
        assert result["count"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Python Official Website"
        assert result["results"][0]["href"] == "https://www.python.org"
        assert result["results"][1]["body"] == "Python 3 tutorial"

    def test_search_text_with_timelimit(self):
        """测试带时间限制的搜索 - 正确传递参数"""
        # Arrange
        searcher = Searcher()

        # Act
        with patch.object(searcher.ddgs, "text", return_value=iter([])) as mock_text:
            searcher.search_text("news", timelimit="d", max_results=5)

        # Assert
        mock_text.assert_called_once()
        call_kwargs = mock_text.call_args.kwargs
        assert call_kwargs["timelimit"] == "d"
        assert call_kwargs["max_results"] == 5
        assert call_kwargs["keywords"] == "news"

    def test_search_text_empty_results(self):
        """测试无搜索结果 - 返回空列表但成功"""
        # Arrange
        searcher = Searcher()

        # Act
        with patch.object(searcher.ddgs, "text", return_value=iter([])):
            result = searcher.search_text("nonexistent_term_xyz123")

        # Assert
        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []

    def test_search_text_network_error(self):
        """测试网络错误 - 返回错误信息"""
        # Arrange
        searcher = Searcher()

        # Act
        with patch.object(
            searcher.ddgs, "text", side_effect=Exception("Network error")
        ):
            result = searcher.search_text("test")

        # Assert
        assert result["success"] is False
        assert "error" in result
        assert result["results"] == []
        assert result["query"] == "test"

    def test_search_text_default_parameters(self):
        """测试默认参数 - 使用正确的默认值"""
        # Arrange
        searcher = Searcher()

        # Act
        with patch.object(searcher.ddgs, "text", return_value=iter([])) as mock_text:
            searcher.search_text("test")

        # Assert
        call_kwargs = mock_text.call_args.kwargs
        assert call_kwargs["region"] == "wt-wt"
        assert call_kwargs["safesearch"] == "moderate"
        assert call_kwargs["timelimit"] is None
        assert call_kwargs["max_results"] == 10


class TestSearcherNews:
    """测试新闻搜索功能"""

    def test_search_news_success(self):
        """测试成功搜索新闻 - 返回包含日期和来源的结果"""
        # Arrange
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

        # Act
        with patch.object(searcher.ddgs, "news", return_value=iter(mock_results)):
            result = searcher.search_news(query, max_results=10)

        # Assert
        assert result["success"] is True
        assert result["count"] == 1
        assert "date" in result["results"][0]
        assert "source" in result["results"][0]
        assert result["results"][0]["source"] == "TechNews"
        assert result["results"][0]["url"] == "https://example.com/news1"

    def test_search_news_error_handling(self):
        """测试新闻搜索错误处理 - 返回错误信息"""
        # Arrange
        searcher = Searcher()

        # Act
        with patch.object(searcher.ddgs, "news", side_effect=Exception("API error")):
            result = searcher.search_news("test")

        # Assert
        assert result["success"] is False
        assert result["results"] == []
        assert "error" in result

    def test_search_news_empty_results(self):
        """测试无新闻结果 - 返回空列表但成功"""
        # Arrange
        searcher = Searcher()

        # Act
        with patch.object(searcher.ddgs, "news", return_value=iter([])):
            result = searcher.search_news("ancient_history")

        # Assert
        assert result["success"] is True
        assert result["count"] == 0

    def test_search_news_with_region(self):
        """测试带区域参数的新闻搜索"""
        # Arrange
        searcher = Searcher()

        # Act
        with patch.object(searcher.ddgs, "news", return_value=iter([])) as mock_news:
            searcher.search_news("test", region="cn-zh")

        # Assert
        call_kwargs = mock_news.call_args.kwargs
        assert call_kwargs["region"] == "cn-zh"


class TestSearcherInit:
    """测试 Searcher 初始化"""

    def test_init_default_parameters(self):
        """测试默认初始化参数"""
        # Act
        searcher = Searcher()

        # Assert
        assert searcher.ddgs is not None

    @patch("crawl4ai_mcp.searcher.DDGS")
    def test_init_with_proxy(self, mock_ddgs_class):
        """测试带代理的初始化"""
        # Arrange
        mock_instance = MagicMock()
        mock_ddgs_class.return_value = mock_instance

        # Act
        Searcher(proxy="http://proxy.example.com:8080", timeout=20)

        # Assert
        mock_ddgs_class.assert_called_once_with(
            proxy="http://proxy.example.com:8080", timeout=20
        )
