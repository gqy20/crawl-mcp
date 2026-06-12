# crawl_mcp

基于 crawl4ai 和 FastMCP 的 MCP 服务器，提供网页爬取和搜索功能。

[![PyPI Version](https://img.shields.io/pypi/v/crawl-mcp)](https://pypi.org/project/crawl-mcp/)
[![GitHub](https://img.shields.io/badge/source-GitHub-black)](https://github.com/gqy20/crawl-mcp)

## 功能

### 爬取工具
- **crawl_single** - 单页爬取（**自动降级**：快速提取 → 浏览器渲染）
- **crawl_site** - 递归爬取整个网站
- **crawl_batch** - 批量爬取（**自动降级**，三阶段并行优化）

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

`crawl_single` / `crawl_batch` 内置自动降级：静态页走快速路径（~0.5s），SPA 自动 fallback 到浏览器。

| 场景 | 耗时 | 说明 |
|------|------|------|
| crawl_single（静态博客） | **~0.5s** | 快速提取路径 |
| crawl_single（SPA 网站） | ~0.6s + ~23s | 快速检测失败 → 浏览器降级 |
| crawl_batch 10 页（全静态） | **~0.5s** | 并行快速提取 |
| crawl_batch 10 页（混合） | ~24s | 静态页快速 + SPA 浏览器 |
| search_text / news / books / videos | **~1.5-2s** | ddgs 搜索 |

**关键优势**：
- **无需手动选择工具**：`crawl_single` 自动判断用快速提取还是浏览器
- 静态页面享受亚秒级速度，SPA 自动降级保证完整性
- 批量爬取智能分流：静态 URL 并行快提取，失败项才走浏览器
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

## 工具用法

### crawl_single - 单页爬取（自动降级）

已知一个明确 URL、需要提取页面正文 Markdown 时使用。内置「快速提取 → 浏览器渲染」自动降级策略：

```json
{
  "name": "crawl_single",
  "arguments": {
    "url": "https://example.com/article"
  }
}
```

**返回示例**：
```json
{
  "success": true,
  "markdown": "# Article Title\n\nContent...",
  "title": "Article Title",
  "method": "fast_extract"
}
```

**可选参数**：
- `enhanced`: 浏览器增强模式，适用于 SPA/慢加载页面；只在浏览器路径生效
- `prefer_fast`: 是否优先快速提取（默认 true，设 false 强制浏览器）
- `min_content_length`: 快速提取最小内容长度阈值（默认 200 字符）
- `llm_config`: LLM 后处理配置（实验性，需 API Key）

> 若要强制浏览器增强模式，请同时设置 `prefer_fast=false` 和 `enhanced=true`。
> `fallback_reason` 仅在快速提取失败后进入浏览器 fallback 时返回。

### crawl_batch - 批量爬取多个明确 URL

已知一组 URL、需要并行抓取多个页面时使用。它会先并行快速提取所有 URL，只把失败、内容不足或 SPA 骨架页送入浏览器 fallback。

```json
{
  "name": "crawl_batch",
  "arguments": {
    "urls": [
      "https://example.com/a",
      "https://example.com/b"
    ],
    "concurrent": 3
  }
}
```

**可选参数**：
- `concurrent`: 浏览器 fallback 并发数（默认 3）
- `prefer_fast`: 是否优先快速提取（默认 true，设 false 时所有 URL 直接走浏览器）
- `min_content_length`: 快速提取最小内容长度阈值（默认 200 字符）
- `llm_config`: LLM 后处理配置（实验性，需 API Key）
- `llm_concurrent`: LLM 后处理并发数（默认 3）

返回为结果列表。`method` 仅在 `prefer_fast=true` 的快速/降级路径中出现；`fallback_reason` 仅在单项发生浏览器 fallback 时出现。

### crawl_site - 从入口页递归爬站

只有一个网站入口、希望沿站内链接发现并抓取若干页面时使用。它使用浏览器和 BFS 深度策略，不走快速提取，也不支持 LLM 后处理。

```json
{
  "name": "crawl_site",
  "arguments": {
    "url": "https://example.com",
    "depth": 2,
    "pages": 10,
    "concurrent": 3
  }
}
```

**参数**：
- `depth`: 最大链接深度（默认 2）
- `pages`: 最大页面数（默认 10）
- `concurrent`: 浏览器爬取并发数（默认 3）

返回包含 `successful_pages`、`total_pages`、`success_rate` 和 `results`。

### search_text - 通用网页搜索

适用于搜索技术文档、百科、博客、论坛、教程等网页内容。搜索工具只返回摘要和链接，不抓取页面正文；如需正文，请对结果 URL 再调用 `crawl_single` 或 `crawl_batch`。

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

图书搜索和视频搜索，用法与 `search_text` 类似。返回字段由 ddgs 上游决定，通常包含标题、链接、摘要或媒体信息，具体字段会随来源变化。

## 开发

```bash
uv sync
uv run pytest
uv run python -m crawl4ai_mcp.fastmcp_server --http
```

## 许可证

MIT License
