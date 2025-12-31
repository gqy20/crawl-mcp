# crawl_mcp

基于 crawl4ai 和 FastMCP 的 MCP 服务器，提供网页爬取和 AI 分析功能。

## 功能

- **crawl_single** - 爬取单个网页，返回 Markdown 格式
- **crawl_site** - 递归爬取整个网站
- **crawl_batch** - 批量爬取多个网页
- **LLM 集成** - 支持 AI 驱动的内容提取和摘要
- **自动重试** - 网络错误自动重试（指数退避）

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

## 可用工具

### crawl_single

```json
{
  "tool": "crawl_single",
  "arguments": {
    "url": "https://example.com",
    "enhanced": false,
    "llm_config": {
      "instruction": "总结页面内容"
    }
  }
}
```

### crawl_site

```json
{
  "tool": "crawl_site",
  "arguments": {
    "url": "https://example.com",
    "depth": 2,
    "pages": 10,
    "concurrent": 3
  }
}
```

### crawl_batch

```json
{
  "tool": "crawl_batch",
  "arguments": {
    "urls": ["https://example.com/1", "https://example.com/2"],
    "concurrent": 3
  }
}
```

## LLM 配置

所有工具支持可选的 `llm_config` 参数：

```json
{
  "api_key": "sk-xxx",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
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

## 开发

```bash
# 安装依赖
uv sync

# 运行测试
uv run pytest

# 启动 HTTP 服务器
uv run python -m crawl4ai_mcp.fastmcp_server --http
```

## 依赖

- Python 3.12+
- crawl4ai >= 0.7.8
- FastMCP >= 0.1.0

## 许可证

MIT License
