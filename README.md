# crawl_mcp

基于 crawl4ai 和 FastMCP 的 MCP 服务器，提供网页爬取和 AI 分析功能。

## 功能

- **crawl_single** - 爬取单个网页，返回 Markdown 格式
- **crawl_site** - 递归爬取整个网站
- **crawl_batch** - 批量爬取多个网页（异步并行）
- **LLM 集成** - AI 驱动的内容提取和摘要（先快速爬取，后可选处理）
- **自动重试** - 网络错误自动重试（指数退避）

## LLM 处理设计

爬取和 LLM 处理分离，确保快速响应：

1. **快速爬取**（2-10秒）- 始终返回原始 Markdown
2. **可选后处理** - 如提供 `llm_config`，对 Markdown 进行 AI 处理

这种设计确保即使不使用 LLM，爬取也始终快速完成。

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
      "command": "uv",
      "args": ["--directory", "/path/to/crawl4ai", "run", "crawl-mcp", "--http"],
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

## 开发

```bash
uv sync
uv run pytest
uv run python -m crawl4ai_mcp.fastmcp_server --http
```

## 许可证

MIT License
