# crawl_mcp

基于 crawl4ai 和 FastMCP 的 MCP 服务器，提供网页爬取和 AI 分析功能。

[![PyPI Version](https://img.shields.io/pypi/v/crawl-mcp)](https://pypi.org/project/crawl-mcp/)
[![GitHub](https://img.shields.io/badge/source-GitHub-black)](https://github.com/gqy20/crawl-mcp)

## 功能

- **crawl_single** - 爬取单个网页，返回 Markdown 格式
- **crawl_site** - 递归爬取整个网站
- **crawl_batch** - 批量爬取多个网页（异步并行）
- **search_text** - 搜索网页内容（通用搜索）
- **search_news** - 搜索新闻内容
- **LLM 集成** - AI 驱动的内容提取和摘要（先快速爬取，后可选处理）
- **自动重试** - 网络错误自动重试（指数退避）

## LLM 处理设计

爬取和 LLM 处理分离，确保快速响应：

1. **快速爬取**（6-10秒）- 始终返回原始 Markdown
2. **可选后处理** - 如提供 `llm_config`，对 Markdown 进行 AI 处理

### 性能对比

| 场景 | 爬取阶段 | 总耗时 |
|------|---------|--------|
| crawl_single（无 LLM） | ~7s | **11s** |
| crawl_single（有 LLM） | ~6s | **40s** |
| crawl_batch 2 页（无 LLM） | ~15s | **15s** |
| crawl_batch（有 LLM） | ~6s/页 | **~20s/页** |

**关键优势**：
- 不使用 LLM 时 11 秒即可获取结果
- 使用 LLM 时爬取阶段仍然快速，用户可以先看到原始内容
- 相比旧设计（LLMExtractionStrategy 需要 123 秒），速度提升 3-10 倍

## 安装

```bash
pip install crawl-mcp
```

## MCP 配置

### Claude Desktop

```json
{
  "mcpServers": {
    "crawl-mcp": {
      "command": "uvx",
      "args": ["crawl-mcp"],
      "env": {
        "OPENAI_API_KEY": "your-api-key"
      }
    }
  }
}
```

### 高级配置（可选）

如需自定义 API 端点或模型：

```json
{
  "mcpServers": {
    "crawl-mcp": {
      "command": "uvx",
      "args": ["crawl-mcp"],
      "env": {
        "OPENAI_API_KEY": "your-api-key",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "LLM_MODEL": "gpt-4o-mini"
      }
    }
  }
}
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | API 密钥 | *必填* |
| `OPENAI_BASE_URL` | API 基础 URL | `https://api.openai.com/v1` |
| `LLM_MODEL` | 模型名称 | `gpt-4o-mini` |

## LLM 配置

所有工具支持可选的 `llm_config` 参数：

```json
{
  "instruction": "提取产品信息",
  "schema": {
    "type": "object",
    "properties": {
      "name": {"type": "string"},
      "price": {"type": "number"}
    }
  }
}
```

- `instruction`: 提取指令
- `schema`: 可选的 JSON Schema

**注意**: `api_key`、`base_url`、`model` 从环境变量读取。

## 搜索功能

### search_text - 通用网页搜索

适用于搜索技术文档、百科、博客、论坛、教程等静态内容。

```json
{
  "name": "search_text",
  "arguments": {
    "query": "Python 快速排序算法",
    "region": "cn-zh",
    "max_results": 5
  }
}
```

**参数说明**：
- `query`: 搜索关键词
- `region`: 区域代码（可选）
  - `wt-wt`: 无区域限制（默认）
  - `us-en`: 美国（英语）
  - `cn-zh`: 中国（中文）
  - `uk-en`: 英国（英语）
  - `jp-jp`: 日本（日语）
- `safesearch`: 安全搜索（可选）
  - `on`: 严格过滤
  - `moderate`: 适度过滤（默认）
  - `off`: 关闭过滤
- `timelimit`: 时间限制（可选）
  - `d`: 最近一天
  - `w`: 最近一周
  - `m`: 最近一月
  - `y`: 最近一年
- `max_results`: 最大结果数（默认：10）

**返回格式**：
```json
{
  "success": true,
  "query": "Python 快速排序算法",
  "count": 5,
  "results": [
    {"title": "...", "href": "https://...", "body": "..."}
  ]
}
```

### search_news - 新闻搜索

适用于搜索突发新闻、时事、财经、体育等时效性内容。

```json
{
  "name": "search_news",
  "arguments": {
    "query": "人工智能最新进展",
    "timelimit": "w",
    "max_results": 10
  }
}
```

**参数说明**：
- 与 `search_text` 相同，但 `timelimit` 仅支持 `d`、`w`、`m`（不支持 `y`）

**返回格式**：
```json
{
  "success": true,
  "query": "人工智能最新进展",
  "count": 3,
  "results": [
    {
      "date": "2024-07-03T16:25:22+00:00",
      "title": "...",
      "body": "...",
      "url": "https://...",
      "image": "https://...",
      "source": "..."
    }
  ]
}
```

## 开发

```bash
uv sync
uv run pytest
uv run python -m crawl4ai_mcp.fastmcp_server --http
```

## 许可证

MIT License
