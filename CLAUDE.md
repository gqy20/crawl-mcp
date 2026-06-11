# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 开发命令

```bash
# 安装依赖
uv sync

# 运行测试（所有测试）
uv run pytest

# 运行特定测试文件
uv run pytest tests/unit/test_crawler.py

# 运行特定测试类/函数
uv run pytest tests/unit/test_crawler.py::TestCrawlerSingle::test_crawl_single_success

# 带覆盖率报告的测试
uv run pytest -v --cov=src/crawl4ai_mcp --cov-report=term-missing

# 代码检查和格式化
uv run ruff check .
uv run ruff format .

# 运行 MCP 服务器（开发调试，HTTP 模式）
uv run python -m crawl4ai_mcp.fastmcp_server --http

# 运行 MCP 服务器（生产模式，STDIO）
uv run crawl-mcp
```

## 项目架构

### 核心设计：自动降级爬取 + 可选 LLM 插件

本项目定位为**专业网页爬取工具**，内置「快速提取 → 浏览器渲染」自动降级策略：

1. **阶段 0：快速提取**（~0.3-0.6s）— 基于 `ddgs.extract()`，适用于静态页面
2. **阶段 1：浏览器降级**（~15-23s）— 快速提取失败或内容不足时自动切换到 Playwright
3. **阶段 2：可选 LLM 插件** — 仅当提供 `llm_config` **且**配置了 `CRAWL_MCP_API_KEY` 时执行

> **设计原则**：不配置 API Key 时，工具完全作为纯爬取工具使用，零依赖外部 LLM 服务。
> 用户拿到 Markdown 后可自行调用任何 LLM 处理。静态页享受 0.5s 速度，SPA 自动降级到浏览器。

### 模块职责

| 模块 | 职责 | 关键类/函数 |
|------|------|-------------|
| `crawler.py` | 网页爬取核心（自动降级：快速提取→浏览器） | `Crawler.crawl_single()`, `Crawler.crawl_batch()` |
| `searcher.py` | 搜索 + 快速提取（ddgs.extract） | `Searcher.search_text()`, `Searcher.extract_url()` |
| `llm_config.py` | LLM 配置管理 | `get_default_llm_config()`, `LLMConfig` |
| `fastmcp_server.py` | MCP 服务器入口，注册所有工具 | `@mcp.tool` 装饰器 |

### 异步处理模式

**关键设计决策**：使用 `nest_asyncio` 实现嵌套事件循环兼容

- `_run_async()` 辅助函数（在 `utils.py` 中统一提供）封装了异步调用
- 允许在已有事件循环的环境（如 Jupyter、某些测试框架）中运行
- 底层爬取使用 `AsyncWebCrawler.arun()` 和 `arun_many()`
- 快速提取路径（`ddgs.extract`）通过 `ThreadPoolExecutor` 并行化

### 并发控制

- **快速提取并发**：`crawl_batch` Phase 1 使用 `ThreadPoolExecutor` 并行 `extract_url`
- **浏览器爬取并发**：Phase 2 使用 `SemaphoreDispatcher`（`concurrent` 参数）
- **LLM 并发**：批量 LLM 处理使用 `concurrent.futures.ThreadPoolExecutor`（`llm_concurrent` 参数）
- **图片分析并发**：`search_images` 使用 `asyncio.Semaphore`（`analyze_concurrent` 参数）

### LLM 配置格式（实验性功能）

`llm_config` 参数支持三种格式：
1. **字典**：`{"instruction": "提取产品信息", "schema": {...}}`
2. **JSON 字符串**：`'{"instruction": "总结"}'`
3. **纯文本**：`"总结页面内容"`（自动作为 `instruction`）

**重要安全约束**：认证配置必须从环境变量读取，不允许用户传入。未配置 `CRAWL_MCP_API_KEY` 时传 `llm_config` 会优雅跳过并返回 `llm_skipped` 提示。

### 重试机制

只对特定网络错误重试，最多 3 次，使用指数退避（1s、2s、4s）：

- `ERR_NETWORK_CHANGED`
- `ERR_CONNECTION_RESET`
- `ERR_INTERNET_DISCONNECTED`
- `ERR_TIMED_OUT`

### MCP 工具列表

| 工具 | 功能 | 关键参数 |
|------|------|----------|
| `crawl_single` | 单页爬取（**自动降级**：快速提取→浏览器） | `url`, `enhanced`, `llm_config`(实验性), `prefer_fast`, `min_content_length` |
| `crawl_batch` | 批量爬取（**自动降级**，三阶段并行） | `urls`, `concurrent`, `llm_config`(实验性), `llm_concurrent`, `prefer_fast` |
| `crawl_site` | 整站爬取（纯浏览器模式） | `url`, `depth`, `pages`, `concurrent` |
| `search_text` | 通用网页搜索 | `query`, `region`, `max_results` |
| `search_news` | 新闻搜索 | `query`, `timelimit`, `max_results` |
| `search_images` | 图片搜索+下载+分析 | `query`, `download`, `analyze`, `analyze_concurrent` |

### 环境变量

| 变量 | 说明 | 必需 | 默认值 |
|------|------|------|--------|
| `CRAWL_MCP_API_KEY` | API 密钥（LLM/图片分析必需） | 否* | - |
| `CRAWL_MCP_BASE_URL` | API 基础 URL | 否 | `https://api.openai.com/v1` |
| `CRAWL_MCP_TEXT_MODEL` | 文本模型名称 | 否 | `glm-4.7` |
| `CRAWL_MCP_VISION_MODEL` | 图片分析模型名称 | 否 | `glm-4.6v` |

> *不配置时所有爬取/搜索功能正常工作，仅 LLM 后处理和图片分析不可用。

### 响应格式约定

**爬取结果**（`crawl_single` / `crawl_batch`）：
```python
{
    "success": bool,
    "markdown": str,
    "title": str,
    "error": str | None,
    "method": "fast_extract" | "browser_fallback",  # 使用的提取方法
    "fallback_reason": str | None,                   # 降级原因（仅 browser_fallback 时）
    # 可选 LLM 结果（仅当 llm_config + CRAWL_MCP_API_KEY 时出现）
    "llm_summary": str,       # 纯文本摘要
    "llm_data": dict,         # 结构化提取
    "llm_error": str,         # LLM 处理错误
    # LLM 跳过提示（传了 llm_config 但未配置 API Key）
    "llm_skipped": str,       # 跳过原因说明
}
```


**搜索结果**：
```python
# search_text / search_news
{
    "success": bool,
    "query": str,
    "count": int,
    "results": list,
    "error": str | None
}

# search_images
{
    "success": bool,
    "query": str,
    "search_results": {"count": int, "results": list},
    "download_results": {...},   # 仅当 download=True
    "analysis_results": {...}    # 仅当 analyze=True
}
```

## 发布流程

1. 更新 `pyproject.toml` 中的版本号
2. 创建 git tag：`git tag v0.2.0 && git push --tags`
3. GitHub Actions 会自动：
   - 运行完整测试套件
   - 检查代码格式
   - 验证版本号匹配
   - 构建分发包
   - 发布到 PyPI

或手动触发：GitHub → Actions → Publish to PyPI → Run workflow
