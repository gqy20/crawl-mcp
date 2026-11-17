# crawl_mcp

基于 crawl4ai 和 FastMCP 的 MCP 服务器，提供网页爬取和搜索功能。

[![PyPI Version](https://img.shields.io/pypi/v/crawl-mcp)](https://pypi.org/project/crawl-mcp/)
[![GitHub](https://img.shields.io/badge/source-GitHub-black)](https://github.com/gqy20/crawl-mcp)

## 功能

**爬取** — 自动降级：快速提取 → 浏览器渲染

| 工具 | 用途 |
|------|------|
| `crawl_single` | 单个明确 URL 的正文提取 |
| `crawl_batch` | 多个明确 URL 的并行提取 |
| `crawl_site` | 从入口页递归爬取站内页面 |

**搜索** — 基于 ddgs，只返回摘要和链接，不抓正文

| 工具 | 用途 |
|------|------|
| `search_text` / `search_news` / `search_books` / `search_videos` | 网页 / 新闻 / 图书 / 视频搜索 |
| `search_images` | 图片搜索，支持下载到本地和 AI 分析 |

**可选** — 需要自备 API Key：`llm_config` LLM 后处理（实验性）、`search_images` 的 `analyze=true` 图片分析。

不配置任何 Key 时，全部爬取和搜索工具照常可用。

## 性能

| 场景 | 耗时 | 路径 |
|------|------|------|
| 单页（静态） | **~0.5s** | 快速提取 |
| 单页（SPA） | ~23s | 浏览器降级 |
| 单页（SPA），配了 Cloud key | ~1.2s | Cloud 兜底 |
| 10 页（全静态） | **~0.5s** | 并行快速提取 |
| 10 页（混合） | ~24s | 静态页快速 + SPA 走浏览器 |
| 各类搜索 | **~1.5-2s** | ddgs |

## 安装

```bash
pip install crawl-mcp
```

浏览器降级路径（SPA / 动态页）需要 Chromium 二进制，首次使用前装一次：

```bash
playwright install chromium   # 约 600MB，或用 crawl4ai-setup 一键安装
```

只做搜索和静态页提取不需要浏览器。

## CLI 用法

安装后附带 `crawl` 命令，与 MCP 工具共用同一套核心：

```bash
crawl https://example.com/article          # 单页，Markdown 打到 stdout
crawl https://example.com/article > page.md
crawl --json https://example.com/article   # 完整 JSON（含 title/method 等）
crawl --browser https://spa-site.com       # 强制浏览器渲染
crawl --cloud https://spa-site.com         # 强制走 Crawl4AI Cloud（需 CRAWL4AI_API_KEY）
crawl https://a.com https://b.com          # 多 URL 并行，输出 JSON
crawl site https://docs.example.com --depth 1 --pages 5   # 站内递归爬取
crawl search "python argparse" -n 5        # 网页搜索
crawl search --news "AI" -n 5              # 新闻搜索（--books / --videos 同理）
crawl images "cat" --download              # 图片搜索并下载，输出本地路径
crawl --quiet https://example.com          # 不刷浏览器进度日志（只留错误）
```

退出码：成功 0，任一失败 1。进度日志走 stderr，stdout 只有正文/JSON。`crawl-mcp` 命令仍用于启动 MCP 服务器。

## MCP 配置

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

需要 LLM 后处理或图片分析时，再加 `env`：

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

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CRAWL_MCP_API_KEY` | LLM 后处理 / 图片分析使用的 API 密钥 | - |
| `CRAWL_MCP_BASE_URL` | OpenAI 兼容 API 基础 URL | `https://api.openai.com/v1` |
| `CRAWL_MCP_TEXT_MODEL` | LLM 后处理模型名称 | `glm-4.7` |
| `CRAWL_MCP_VISION_MODEL` | 图片分析模型名称 | `glm-4.6v` |
| `CRAWL4AI_API_KEY` | Crawl4AI Cloud key，本地提取失败时的兜底路径 | - |
| `CRAWL4AI_CLOUD_FALLBACK` | 设为 `0` 关闭 Cloud 兜底 | `1` |
| `CRAWL_MCP_CACHE` | 设为 `0` 关闭抓取缓存 | `1` |
| `CRAWL_MCP_CACHE_TTL` | 正缓存有效期（秒） | `3600` |
| `CRAWL_MCP_NEG_TTL` | 负缓存/域名记忆有效期（秒） | `300` |
| `CRAWL_MCP_CACHE_DIR` | 缓存目录 | `~/.cache/crawl_mcp` |
| `CRAWL4AI_CLOUD_BUDGET` | Cloud 兜底整段预算（秒），超时让位给浏览器 | `10` |

未配置 `CRAWL_MCP_API_KEY` 时，传入 `llm_config` 会跳过 LLM 后处理并返回 `llm_skipped`，
`search_images(analyze=true)` 会返回配置错误；普通爬取和搜索不受影响。

### 抓取缓存

成功抓取过的 URL 会按 `URL + 参数` 缓存在本地，重复抓取直接命中（实测 0.24s → 0.00s），
命中时返回 `cached: true` 和 `cached_age`（缓存距今多少秒）。缓存能省掉重复请求，
Cloud 计费场景下等于直接省额度。

失败也会缓存，但只缓存「重试也没用」的那类（404、空内容、挑战页），TTL 更短
（`CRAWL_MCP_NEG_TTL`，默认 300s）；超时、限速这类波动不缓存。同一个域名连续 2 次
确定性失败后直接给出结论，不再走降级链路（`method="domain_memo"`）。

```bash
rm -rf ~/.cache/crawl_mcp   # 清空缓存
```

### Crawl4AI Cloud 兜底

本地快速提取拿不到内容时默认降级到浏览器（~15-23s）。配了 `CRAWL4AI_API_KEY` 后会先尝试
Cloud `/scrape`（~1-2s，云端自动选缓存或浏览器引擎），失败才继续走本地浏览器。返回的
`method` 字段会标记为 `cloud_fallback`。

- key 申请：https://api.crawl4ai.com/dashboard
- 计费 0.05-0.5 credit/次（社区层每月赠 1000 credit），限速 10 请求/分钟
- `CRAWL4AI_API_KEY` 支持逗号分隔多个 key，调用量轮询均摊；某个 key 额度耗尽（402）
  或被限速（429）时自动换下一个
- 不配 key 就不会调用 Cloud，行为与纯本地一致

进程启动时（CLI / MCP 服务器）自动加载项目根目录的 `.env`，已存在的环境变量优先。

## LLM 后处理（实验性）

`crawl_single` 和 `crawl_batch` 支持可选的 `llm_config`：

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
- `schema`: 可选的 JSON Schema（结构化数据提取）

未配置 `CRAWL_MCP_API_KEY` 时会跳过并在结果中返回 `llm_skipped`。

## 工具用法

### crawl_single - 单页爬取

已知一个明确 URL、需要正文 Markdown 时使用。自动降级：快速提取 → 浏览器渲染。

```json
{
  "name": "crawl_single",
  "arguments": {
    "url": "https://example.com/article"
  }
}
```

返回：

```json
{
  "success": true,
  "markdown": "# Article Title\n\nContent...",
  "title": "Article Title",
  "method": "fast_extract",
  "error_code": null,
  "timings": {"fast": 0.3}
}
```

**可选参数**：
- `enhanced`: 浏览器增强模式，适用于 SPA/慢加载页面；只在浏览器路径生效
- `prefer_fast`: 是否优先快速提取（默认 true，设 false 强制浏览器）
- `min_content_length`: 快速提取最小内容长度阈值（默认 200 字符）
- `llm_config`: LLM 后处理配置（实验性，需 API Key）

> 强制浏览器增强模式需同时设置 `prefer_fast=false` 和 `enhanced=true`。
> `fallback_reason` 仅在发生降级时返回，说明快速提取失败或内容不足的原因。
> 快速提取路径拿不到页面 HTML 的 `<title>`，`title` 可能为空；浏览器和 Cloud 路径有标题。

**字段说明**：
- `error_code`: 失败原因的归类，调用方据此决定重试策略。取值：
  `http_403` / `http_404` / `http_401` / `rate_limited` / `http_5xx` / `tls_error` /
  `js_challenge` / `antibot` / `empty_content` / `timeout` / `connection_refused` /
  `connection_reset` / `dns_error` / `no_results` / `unknown`；成功时为 `null`
- `hint`: 失败时给出的下一步建议（换路径 / 换出口 / 修证书…）
- `timings`: 各降级阶段的耗时（秒），如 `{"fast": 0.3, "cloud": 2.8, "browser": 26.4}`
- `cached`: 命中本地缓存（含负缓存）时为 `true`，此时不返回 `timings`
- `cached_age`: 缓存条目距今多少秒——数据可能是旧的，必要时用更短 TTL 重抓

### crawl_batch - 批量爬取

已知一组 URL 时使用。并行快速提取所有 URL，只把失败、内容不足或 SPA 骨架页送入后续降级。

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

返回结果列表，每项结构同 `crawl_single`。

### crawl_site - 递归爬站

只有网站入口、希望沿站内链接发现并抓取若干页面时使用。走浏览器 + BFS，不走快速提取，也不支持 LLM 后处理。

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

返回 `successful_pages`、`total_pages`、`success_rate` 和 `results`。

### search_text - 网页搜索

搜索工具只返回摘要和链接，不抓页面正文；需要正文再对结果 URL 调 `crawl_single` 或 `crawl_batch`。

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

返回：

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

返回：

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

用法同 `search_text`。返回字段由 ddgs 上游决定，通常包含标题、链接、摘要或媒体信息，会随来源变化。

## 开发

```bash
uv sync
uv run pytest
uv run python -m crawl4ai_mcp.fastmcp_server --http
```

### Benchmark

`docs/BENCHMARK.md` 由 `scripts/bench.py` 自动生成，记录代表性渠道（政府政策、学术期刊、
代码托管、公众号）的命中路径、耗时和搜索命中率。

用例带**预期**：`成功` 要求正文 ≥200 字，`失败·<error_code>` 是已知问题站点的回归用例
——不要求跑通，只要求「失败得对」，`error_code` 变了就是判定逻辑退化。

```bash
uv run python scripts/bench.py            # quick：9 个用例 + 5 个 query，约 90s
uv run python scripts/bench.py --full     # 完整数据集
uv run python scripts/bench.py --repeat 3 # 每个搜索 query 跑 3 次，看命中率
uv run python scripts/bench.py --no-write # 只打印，不写文件
```

报告含四块：按渠道分组的爬取表（带 `fast/cloud/browser` 分段耗时和与上次的对比）、
搜索命中率、缓存命中（冷启动 vs 命中）、批量吞吐（`crawl_batch` 相对逐个抓的加速比）。

文档自动更新，改完代码不用手动维护：

- 提交时 pre-commit hook 自动重跑（源码未变则跳过），结果写进本次提交
- Claude Code 会话结束时同样自动重跑（`.claude/settings.json` 的 Stop hook）

网络不可用时保留上次结果，不阻塞提交。

## 许可证

MIT License
