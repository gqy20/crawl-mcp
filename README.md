# crawl_mcp

基于 crawl4ai 和 FastMCP 的 MCP 服务器，提供网页爬取和搜索功能。

[![PyPI Version](https://img.shields.io/pypi/v/crawl-mcp)](https://pypi.org/project/crawl-mcp/)
[![GitHub](https://img.shields.io/badge/source-GitHub-black)](https://github.com/gqy20/crawl-mcp)

## 功能

### 爬取工具
- **crawl_single** - 爬取单个网页，返回 Markdown 格式（浏览器渲染，适合 SPA）
- **extract_url** - 轻量级 URL 提取（无需浏览器，速度快 5-10 倍）
- **crawl_site** - 递归爬取整个网站
- **crawl_batch** - 批量爬取多个网页（异步并行）

### 搜索工具
- **search_text** - 通用网页搜索
- **search_news** - 新闻内容搜索
- **search_images** - 图片搜索（支持下载和 AI 分析）
- **search_books** - 图书/电子书搜索
- **search_videos** - 视频搜索（含时长、播放量等）

### 可选 AI 能力
- **LLM 后处理**（实验性）- 对已爬取的 Markdown 进行 AI 摘要/结构化提取
- **图片分析** - 使用视觉模型分析图片内容

> **核心定位**：专业爬取工具。不配置 API Key 即可使用全部爬取和搜索功能。

## 性能

| 场景 | 耗时 | 说明 |
|------|------|------|
| extract_url（静态页面） | **~1.5s** | ddgs extract，无需浏览器 |
| crawl_single（纯爬取） | ~7-12s | 浏览器渲染 |
| crawl_batch 2 页（纯爬取） | ~12-15s | 并行爬取 |
| search_text / news / books / videos | **~1.5-2s** | ddgs 搜索 |

**关键优势**：
- 静态页面用 `extract_url`，1.5 秒出结果
- SPA/JS 重度页面用 `crawl_single`，浏览器渲染保证完整
- 搜索类工具全部基于 ddgs，秒级响应
- 无需配置任何 API Key 即可使用核心功能

## 安装

```bash
pip install crawl-mcp
```

## MCP 配置

### 基础配置（纯爬取，无需 API Key）

```json
{
  "mcpServers": {
    "crawl-mcp": {
      "command": "uvx",
      "args": ["crawl-mcp"]
    }
  }
}
```

### 完整配置（含 LLM / 图片分析）

```json
{
  "mcpServers": {
    "crawl-mcp": {
      "command": "uvx",
      "args": ["crawl-mcp"],
      "env": {
        "CRAWL_MCP_API_KEY": "your-api-key",
        "CRAWL_MCP_BASE_URL": "https://api.openai.com/v1",
        "CRAWL_MCP_TEXT_MODEL": "glm-4.7",
        "CRAWL_MCP_VISION_MODEL": "glm-4.6v"
      }
    }
  }
}
```

### 环境变量

| 变量 | 说明 | 必需 | 默认值 |
|------|------|------|--------|
| `CRAWL_MCP_API_KEY` | API 密钥 | 否* | - |
| `CRAWL_MCP_BASE_URL` | API 基础 URL | 否 | `https://api.openai.com/v1` |
| `CRAWL_MCP_TEXT_MODEL` | 文本模型名称 | 否 | `glm-4.7` |
| `CRAWL_MCP_VISION_MODEL` | 图片分析模型名称 | 否 | `glm-4.6v` |

> *不配置时爬取和搜索功能完全正常，仅 LLM 后处理和图片分析不可用。
>
> **向后兼容**：旧变量名 (`OPENAI_API_KEY` 等) 仍可用但会发出弃用警告。

## LLM 后处理（实验性功能）

`crawl_single` 和 `crawl_batch` 支持可选的 `llm_config` 参数：

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
- `schema`: 可选的 JSON Schema（用于结构化数据提取）

**前提条件**：必须配置 `CRAWL_MCP_API_KEY`，否则会优雅跳过并在结果中返回 `llm_skipped` 提示。

## 搜索功能

### extract_url - 轻量级 URL 提取

适用于静态页面、文章、博客等不需要 JS 渲染的场景。

```json
{
  "name": "extract_url",
  "arguments": {
    "url": "https://example.com/article",
    "fmt": "text_markdown"
  }
}
```

**参数说明**：
- `url`: 要提取的网页 URL
- `fmt`: 输出格式（可选）
  - `text_markdown`: Markdown 格式（默认）
  - `text_plain`: 纯文本
  - `text_rich`: 富文本
  - `text`: 原始 HTML
  - `content`: 原始字节

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

### search_images - 图片搜索

搜索图片，支持下载到本地和 AI 分析。

```json
{
  "name": "search_images",
  "arguments": {
    "query": "cute cat",
    "max_results": 10,
    "download": true,
    "download_count": 5,
    "analyze": true,
    "analysis_prompt": "描述这张图片的内容和风格"
  }
}
```

**返回格式**：
```json
{
  "success": true,
  "query": "cute cat",
  "search_results": {"count": 10, "results": [...]},
  "download_results": {"total": 5, "downloaded": 5, ...},
  "analysis_results": {"count": 5, "results": [...]}
}
```

### search_books / search_videos

图书搜索和视频搜索，用法与 `search_text` 类似。

## 开发

```bash
uv sync
uv run pytest
uv run python -m crawl4ai_mcp.fastmcp_server --http
```

## 许可证

MIT License
