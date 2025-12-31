"""FastMCP 服务器单元测试"""

import pytest
from unittest.mock import AsyncMock, patch
from crawl4ai_mcp.fastmcp_server import mcp


class TestFastMCPTools:
    """测试 FastMCP 工具注册"""

    def test_mcp_server_has_tools(self):
        """测试 MCP 服务器注册了工具"""
        # Act
        tools = mcp._tools_manager._tools

        # Assert
        tool_names = list(tools.keys())
        assert "crawl_single" in tool_names
        assert "crawl_site" in tool_names
        assert "crawl_batch" in tool_names

    def test_crawl_single_tool_exists(self):
        """测试 crawl_single 工具存在且有正确的 schema"""
        # Act
        tool = mcp._tools_manager._tools.get("crawl_single")

        # Assert
        assert tool is not None
        # 验证函数签名
        import inspect
        sig = inspect.signature(tool.fn)
        assert "url" in sig.parameters
        assert "enhanced" in sig.parameters

    def test_crawl_site_tool_exists(self):
        """测试 crawl_site 工具存在且有正确的 schema"""
        # Act
        tool = mcp._tools_manager._tools.get("crawl_site")

        # Assert
        assert tool is not None
        import inspect
        sig = inspect.signature(tool.fn)
        assert "url" in sig.parameters
        assert "depth" in sig.parameters
        assert "pages" in sig.parameters
        assert "concurrent" in sig.parameters

    def test_crawl_batch_tool_exists(self):
        """测试 crawl_batch 工具存在且有正确的 schema"""
        # Act
        tool = mcp._tools_manager._tools.get("crawl_batch")

        # Assert
        assert tool is not None
        import inspect
        sig = inspect.signature(tool.fn)
        assert "urls" in sig.parameters
        assert "concurrent" in sig.parameters


class TestFastMCPToolFunctions:
    """测试工具函数的实际行为"""

    @pytest.mark.asyncio
    async def test_crawl_single_function_works(self):
        """测试 crawl_single 函数能正确执行"""
        # Arrange
        from crawl4ai_mcp.fastmcp_server import crawl_single
        url = "https://example.com"

        async def mock_crawl(url, enhanced):
            return {"success": True, "markdown": "# Test", "title": "Test", "error": None}

        # Act
        with patch("crawl4ai_mcp.fastmcp_server.Crawler") as MockCrawler:
            mock_instance = MockCrawler.return_value
            mock_instance.crawl_single = mock_crawl
            result = crawl_single(url)

        # Assert
        assert result["success"] is True
        assert result["markdown"] == "# Test"

    @pytest.mark.asyncio
    async def test_crawl_site_function_works(self):
        """测试 crawl_site 函数能正确执行"""
        # Arrange
        from crawl4ai_mcp.fastmcp_server import crawl_site
        url = "https://example.com"

        async def mock_crawl_site(url, depth, pages, concurrent):
            return {
                "successful_pages": 1,
                "total_pages": 1,
                "success_rate": "100%",
                "results": []
            }

        # Act
        with patch("crawl4ai_mcp.fastmcp_server.Crawler") as MockCrawler:
            mock_instance = MockCrawler.return_value
            mock_instance.crawl_site = mock_crawl_site
            result = crawl_site(url)

        # Assert
        assert result["successful_pages"] == 1

    @pytest.mark.asyncio
    async def test_crawl_batch_function_works(self):
        """测试 crawl_batch 函数能正确执行"""
        # Arrange
        from crawl4ai_mcp.fastmcp_server import crawl_batch
        urls = ["https://example.com"]

        async def mock_crawl_batch(urls, concurrent):
            return [{"success": True, "markdown": "# Test", "title": "Test"}]

        # Act
        with patch("crawl4ai_mcp.fastmcp_server.Crawler") as MockCrawler:
            mock_instance = MockCrawler.return_value
            mock_instance.crawl_batch = mock_crawl_batch
            result = crawl_batch(urls)

        # Assert
        assert len(result) == 1
        assert result[0]["success"] is True
