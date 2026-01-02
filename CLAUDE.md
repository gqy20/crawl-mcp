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

# 运行 MCP 服务器（开发调试）
uv run python -m crawl4ai_mcp.fastmcp_server --http
```

## 项目架构

### 核心设计：爬取与 LLM 处理分离

本项目采用**两阶段设计**，将网页爬取和 LLM 处理完全分离，确保不使用 LLM 时也能快速响应：

1. **阶段 1：快速爬取**（~6-10 秒）- 始终执行，返回原始 Markdown
2. **阶段 2：可选后处理**（~30 秒）- 仅当提供 `llm_config` 时执行

这种设计相比 crawl4ai 原生的 `LLMExtractionStrategy`（需要 123 秒），速度提升 3-10 倍。

### 模块结构

- **`src/crawl4ai_mcp/crawler.py`** - 核心爬虫逻辑
  - `Crawler` 类：统一的爬虫接口
  - `_run_async()`：使用 `nest_asyncio` 实现嵌套事件循环兼容
  - `_crawl()`：内部异步爬取方法，包含重试机制（指数退避）
  - `crawl_single()`: 单页爬取
  - `crawl_batch()`: 批量爬取，使用 `arun_many` 实现真正的异步并行
  - `crawl_site()`: 整站爬取（待完善）
  - `postprocess_markdown()` / `_call_llm()`: LLM 后处理逻辑

- **`src/crawl4ai_mcp/llm_config.py`** - LLM 配置管理
  - `LLMConfig` 数据类：存储 API 密钥、模型、指令等
  - `get_default_llm_config()`: 从环境变量读取配置
  - `get_llm_config()`: 合并环境变量和用户配置
  - **重要**：认证配置（`api_key`、`base_url`、`model`）必须从环境变量读取，不允许用户传入

- **`src/crawl4ai_mcp/fastmcp_server.py`** - MCP 服务器入口
  - 使用 FastMCP 框架注册三个工具：`crawl_single`、`crawl_site`、`crawl_batch`
  - 单例 `_crawler` 实例
  - 支持 STDIO 和 HTTP 两种传输方式

### LLM 配置格式

`llm_config` 参数支持三种格式：
1. **字典**：`{"instruction": "提取产品信息", "schema": {...}}`
2. **JSON 字符串**：`'{"instruction": "总结"}'`
3. **纯文本**：`"总结页面内容"`（自动作为 `instruction`）

### 关键实现细节

- **重试机制**：只对网络错误（`ERR_NETWORK_CHANGED`、`ERR_CONNECTION_RESET` 等）重试，最多 3 次，使用指数退避（1s、2s、4s）
- **并发控制**：`crawl_batch` 使用 `SemaphoreDispatcher` 控制并发数
- **响应格式**：爬取结果始终包含 `success`、`markdown`、`title`、`error`；LLM 结果包含 `llm_summary`/`llm_data`/`llm_content` 或 `llm_error`

### 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `OPENAI_API_KEY` | API 密钥 | 是 |
| `OPENAI_BASE_URL` | API 基础 URL | 否（默认 `https://api.openai.com/v1`） |
| `LLM_MODEL` | 模型名称 | 否（默认 `gpt-4o-mini`） |

## 发布流程

1. 更新 `pyproject.toml` 中的版本号
2. 创建 git tag：`git tag v0.1.1 && git push --tags`
3. GitHub Actions 会自动：
   - 运行完整测试套件
   - 检查代码格式
   - 验证版本号匹配
   - 构建分发包
   - 发布到 PyPI

或手动触发：GitHub → Actions → Publish to PyPI → Run workflow
