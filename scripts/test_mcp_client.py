"""测试 MCP HTTP 客户端"""

import asyncio
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp import Client


async def main():
    # 连接 HTTP 服务器
    transport = StreamableHttpTransport(url="http://127.0.0.1:8001/mcp")
    async with Client(transport) as client:
        # 列出工具
        tools = await client.list_tools()
        print("=== 可用工具 ===")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")
            if tool.inputSchema:
                print(f"    参数: {list(tool.inputSchema.get('properties', {}).keys())}")

        print("\n✅ MCP 服务器连接成功！")


if __name__ == "__main__":
    asyncio.run(main())
