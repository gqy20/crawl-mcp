"""MCP 服务器单元测试"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from crawl4ai_mcp.mcp_server import MCPServer


class TestMCPServerSingle:
    """测试单页爬取 MCP 工具"""

    def test_crawl_single_tool_exists(self):
        """测试 single 工具存在"""
        # Arrange
        server = MCPServer()

        # Act
        tools = server.list_tools()

        # Assert
        tool_names = [tool["name"] for tool in tools]
        assert "crawl_single" in tool_names

    def test_crawl_single_tool_schema(self):
        """测试 single 工具 schema 正确"""
        # Arrange
        server = MCPServer()

        # Act
        tools = server.list_tools()
        single_tool = next(t for t in tools if t["name"] == "crawl_single")

        # Assert
        assert "url" in single_tool["inputSchema"]["properties"]
        assert "enhanced" in single_tool["inputSchema"]["properties"]

    @pytest.mark.asyncio
    async def test_crawl_single_call(self):
        """测试调用 single 工具"""
        # Arrange
        server = MCPServer()
        url = "https://example.com"

        # Act
        result = await server.call_tool("crawl_single", {"url": url})

        # Assert
        assert result["success"] is True


class TestMCPServerSite:
    """测试整站爬取 MCP 工具"""

    def test_crawl_site_tool_exists(self):
        """测试 site 工具存在"""
        # Arrange
        server = MCPServer()

        # Act
        tools = server.list_tools()

        # Assert
        tool_names = [tool["name"] for tool in tools]
        assert "crawl_site" in tool_names

    def test_crawl_site_tool_schema(self):
        """测试 site 工具 schema 正确"""
        # Arrange
        server = MCPServer()

        # Act
        tools = server.list_tools()
        site_tool = next(t for t in tools if t["name"] == "crawl_site")

        # Assert
        assert "url" in site_tool["inputSchema"]["properties"]
        assert "depth" in site_tool["inputSchema"]["properties"]
        assert "pages" in site_tool["inputSchema"]["properties"]
        assert "concurrent" in site_tool["inputSchema"]["properties"]


class TestMCPServerBatch:
    """测试批量爬取 MCP 工具"""

    def test_crawl_batch_tool_exists(self):
        """测试 batch 工具存在"""
        # Arrange
        server = MCPServer()

        # Act
        tools = server.list_tools()

        # Assert
        tool_names = [tool["name"] for tool in tools]
        assert "crawl_batch" in tool_names

    def test_crawl_batch_tool_schema(self):
        """测试 batch 工具 schema 正确"""
        # Arrange
        server = MCPServer()

        # Act
        tools = server.list_tools()
        batch_tool = next(t for t in tools if t["name"] == "crawl_batch")

        # Assert
        assert "urls" in batch_tool["inputSchema"]["properties"]
        assert "concurrent" in batch_tool["inputSchema"]["properties"]
