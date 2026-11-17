"""公共工具函数"""

import asyncio


def run_async(coro):
    """运行异步函数的辅助函数，兼容已有事件循环的环境

    使用 nest_asyncio 允许嵌套事件循环，
    解决在 Jupyter、某些测试框架等已有事件循环环境中运行异步代码的问题。
    """
    try:
        asyncio.get_running_loop()
        import nest_asyncio

        nest_asyncio.apply()
        return asyncio.get_event_loop().run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def load_env() -> None:
    """把 .env 载入环境变量（已存在的环境变量优先，不覆盖）

    只在进程入口调用（CLI / MCP 服务器），不影响库用法和测试。
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)
