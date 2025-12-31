"""MCP 服务器实现"""

from typing import List, Dict, Any
from crawl4ai_mcp.crawler import Crawler


class MCPServer:
    """MCP 服务器，提供爬虫工具"""

    def __init__(self):
        """初始化 MCP 服务器"""
        self._crawler = Crawler()

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        列出所有可用的 MCP 工具

        Returns:
            工具列表
        """
        return [
            {
                "name": "crawl_single",
                "description": "爬取单个网页，返回 Markdown 格式内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要爬取的网页 URL"
                        },
                        "enhanced": {
                            "type": "boolean",
                            "description": "是否使用增强模式（适用于 SPA 网站）",
                            "default": False
                        }
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "crawl_site",
                "description": "爬取整个网站，支持深度和页面数限制",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "起始 URL"
                        },
                        "depth": {
                            "type": "integer",
                            "description": "最大爬取深度",
                            "default": 2
                        },
                        "pages": {
                            "type": "integer",
                            "description": "最大页面数",
                            "default": 10
                        },
                        "concurrent": {
                            "type": "integer",
                            "description": "并发请求数",
                            "default": 3
                        }
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "crawl_batch",
                "description": "批量爬取多个网页",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "URL 列表"
                        },
                        "concurrent": {
                            "type": "integer",
                            "description": "并发请求数",
                            "default": 3
                        }
                    },
                    "required": ["urls"]
                }
            }
        ]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if tool_name == "crawl_single":
            return self._crawl_single(arguments)
        elif tool_name == "crawl_site":
            return self._crawl_site(arguments)
        elif tool_name == "crawl_batch":
            return await self._crawl_batch(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _crawl_single(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """单页爬取"""
        url = arguments["url"]
        enhanced = arguments.get("enhanced", False)
        return self._crawler.crawl_single(url, enhanced)

    def _crawl_site(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """整站爬取"""
        url = arguments["url"]
        depth = arguments.get("depth", 2)
        pages = arguments.get("pages", 10)
        concurrent = arguments.get("concurrent", 3)
        return self._crawler.crawl_site(url, depth, pages, concurrent)

    async def _crawl_batch(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """批量爬取"""
        urls = arguments["urls"]
        concurrent = arguments.get("concurrent", 3)
        results = self._crawler.crawl_batch(urls, concurrent)
        return {"results": results}
