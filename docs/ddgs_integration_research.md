# ddgs 包集成搜索功能 - 深度调研报告

## 一、ddgs 包概述

### 1.1 基本信息

| 项目 | 说明 |
|------|------|
| **包名** | `duckduckgo-search` (PyPI) / `ddgs` (GitHub) |
| **最新版本** | 8.1.1 (2025年持续更新) |
| **Python 要求** | >= 3.9 (PyPI) / >= 3.10 (GitHub) |
| **开源协议** | 未明确声明，教育用途 |
| **GitHub** | https://github.com/deedy5/ddgs |
| **PyPI** | https://pypi.org/project/duckduckgo-search/ |

### 1.2 功能定位

DDGS (Dux Distributed Global Search) 是一个**元搜索引擎库**，聚合了多个 Web 搜索服务的搜索结果：

| 搜索类型 | 支持的后端 |
|----------|-----------|
| `text()` | `bing`, `brave`, `duckduckgo`, `google`, `wikipedia`, `yandex`, `yahoo` |
| `images()` | `duckduckgo` |
| `videos()` | `duckduckgo` |
| `news()` | `bing`, `duckduckgo`, `yahoo` |
| `books()` | `annasarchive` |

---

## 二、核心 API 接口

### 2.1 DDGS 类初始化

```python
from ddgs import DDGS

# 基本用法
ddgs = DDGS()

# 支持代理
ddgs = DDGS(
    proxy="http://user:pass@example.com:3128",  # 支持 http/https/socks5
    timeout=10,                                  # 超时时间
    verify=True                                  # SSL 验证
)

# Tor Browser 代理别名
ddgs = DDGS(proxy="tb")  # "tb" 是 "socks5://127.0.0.1:9150" 的别名
```

### 2.2 文本搜索

```python
results = DDGS().text(
    query="live free or die",
    region="wt-wt",           # 区域: wt-wt(无区域), us-en, uk-en, cn-zh, etc.
    safesearch="moderate",    # on, moderate, off
    timelimit=None,           # d(天), w(周), m(月), y(年)
    max_results=10,
    page=1,
    backend="auto"            # auto, html, lite
)
```

**返回格式：**
```python
[
    {
        "title": "News, sport, celebrities and gossip | The Sun",
        "href": "https://www.thesun.co.uk/",
        "body": "Get the latest news, exclusives, sport..."
    },
    ...
]
```

### 2.3 图片搜索

```python
results = DDGS().images(
    query="butterfly",
    region="wt-wt",
    safesearch="moderate",
    timelimit="m",
    max_results=10,
    size=None,              # Small, Medium, Large, Wallpaper
    color="Monochrome",     # 颜色过滤
    type_image=None,        # photo, clipart, gif, transparent, line
    layout=None,            # Square, Tall, Wide
    license_image=None      # Creative Commons 许可证
)
```

**返回格式：**
```python
[
    {
        "title": "...",
        "image": "https://...",
        "thumbnail": "https://...",
        "url": "https://...",
        "height": 3860,
        "width": 4044,
        "source": "Bing"
    },
    ...
]
```

### 2.4 视频搜索

```python
results = DDGS().videos(
    query="cars",
    region="wt-wt",
    safesearch="moderate",
    timelimit="w",
    max_results=10,
    resolution="high",      # high, standard
    duration="medium",       # short, medium, long
    license_videos=None      # creativeCommon, youtube
)
```

### 2.5 新闻搜索

```python
results = DDGS().news(
    query="sanctions",
    region="wt-wt",
    safesearch="moderate",
    timelimit="d",           # d, w, m
    max_results=20
)
```

**返回格式：**
```python
[
    {
        "date": "2024-07-03T16:25:22+00:00",
        "title": "Murdoch's Sun Endorses Starmer's Labour...",
        "body": "Rupert Murdoch's Sun newspaper...",
        "url": "https://www.msn.com/...",
        "image": "https://...",
        "source": "Bloomberg on MSN.com"
    },
    ...
]
```

---

## 三、与现有项目集成方案

### 3.1 项目架构对比

| 维度 | 现有 crawl-mcp | ddgs 集成后 |
|------|----------------|-------------|
| **核心功能** | 网页爬取 | 网页搜索 + 爬取 |
| **入口点** | URL 已知 | 通过搜索发现 URL |
| **数据源** | crawl4ai (单网页) | 多搜索引擎聚合 |
| **异步支持** | ✅ (AsyncWebCrawler) | ❌ (同步，但支持并发) |
| **LLM 集成** | ✅ (后处理) | 需自己实现 |
| **MCP 工具** | `crawl_single`, `crawl_batch`, `crawl_site` | 新增 `search_*` 系列 |

### 3.2 推荐集成架构

```
┌─────────────────────────────────────────────────────────────┐
│                     crawl-mcp MCP Server                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────┐        ┌──────────────────────┐   │
│  │   Search 模块        │        │   Crawl 模块         │   │
│  │   (新增)             │        │   (现有)             │   │
│  ├──────────────────────┤        ├──────────────────────┤   │
│  │ • search_text()      │──URL──▶│ • crawl_single()     │   │
│  │ • search_images()    │        │ • crawl_batch()      │   │
│  │ • search_videos()    │        │ • crawl_site()       │   │
│  │ • search_news()      │        │                      │   │
│  │ • search_and_crawl() │◀───────│ • postprocess_lpm()  │   │
│  └──────────────────────┘        └──────────────────────┘   │
│            ▲                                              │   │
│            │                                              │   │
│  ┌─────────┴──────────┐                                  │   │
│  │   DDGS 类          │                                  │   │
│  │   (duckduckgo_search)│                              │   │
│  └─────────────────────┘                                  │   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 新增 MCP 工具设计

```python
# 1. search_text - 文本搜索
@mcp.tool
def search_text(
    query: str,
    region: str = "wt-wt",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, str]]:
    """搜索网页，返回标题、链接和摘要"""

# 2. search_images - 图片搜索
@mcp.tool
def search_images(
    query: str,
    region: str = "wt-wt",
    max_results: int = 10,
    size: Optional[str] = None,
) -> List[Dict[str, str]]:
    """搜索图片，返回图片链接和缩略图"""

# 3. search_news - 新闻搜索
@mcp.tool
def search_news(
    query: str,
    region: str = "wt-wt",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, str]]:
    """搜索新闻，返回最新新闻"""

# 4. search_and_crawl - 搜索后爬取（组合功能）
@mcp.tool
def search_and_crawl(
    query: str,
    max_results: int = 3,
    crawl_top_n: int = 1,  # 爬取前 N 个结果
    llm_config: Optional[Dict] = None,
) -> Dict[str, Any]:
    """先搜索，然后爬取搜索结果的网页内容"""
```

### 3.4 文件结构

```
src/crawl4ai_mcp/
├── __init__.py
├── fastmcp_server.py      # 新增 search_* 工具
├── crawler.py              # 现有爬虫逻辑
├── llm_config.py           # 现有 LLM 配置
└── searcher.py             # 新增：搜索模块封装
```

---

## 四、技术可行性分析

### 4.1 优势

| 优势 | 说明 |
|------|------|
| **无需 API Key** | DuckDuckGo 不需要注册，无调用限制 |
| **多引擎聚合** | 自动轮换多个搜索引擎，提高成功率 |
| **隐私保护** | DuckDuckGo 注重隐私，不追踪用户 |
| **稳定更新** | 项目活跃维护，2025年持续更新 |
| **简单易用** | API 设计简洁，易于集成 |

### 4.2 挑战与解决方案

| 挑战 | 解决方案 |
|------|----------|
| **同步阻塞** | ddgs 是同步的，使用 `_run_async()` 包装（现有方案） |
| **网络错误** | 实现重试机制（现有 crawler 已有类似逻辑） |
| **结果质量** | 通过 LLM 后处理过滤和摘要（现有架构支持） |
| **速率限制** | 添加代理支持，使用轮换代理 |

### 4.3 异步支持

**重要发现**：ddgs 底层使用 `ThreadPoolExecutor` 实现并发，**不是真正的 async/await**。

```python
# ddgs 内部实现（伪代码）
from concurrent.futures import ThreadPoolExecutor

def _search(self, ...):
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(engine.search, ...) for engine in engines]
        results = [f.result() for f in futures]
```

**集成策略**：使用现有的 `_run_async()` 包装器，保持与 crawl 模块一致的异步风格。

```python
def _run_async(coro):
    """现有的嵌套事件循环兼容函数"""
    try:
        asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.get_event_loop().run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)

# 使用示例
def search_text(self, query: str, max_results: int = 10):
    def _sync_search():
        return DDGS().text(query, max_results=max_results)
    return _run_async(asyncio.to_thread(_sync_search))
```

---

## 五、依赖和安装

### 5.1 新增依赖

```toml
[project]
dependencies = [
    "duckduckgo-search>=8.0.0",  # 新增
    # ... 现有依赖
]
```

### 5.2 可选依赖（代理支持）

```toml
[project.optional-dependencies]
proxy = [
    "requests[socks]>=2.32.0",  # 支持 socks5 代理
]
```

---

## 六、实现优先级

### Phase 1: 核心搜索功能（高优先级）

- [ ] `search_text()` - 文本搜索
- [ ] `search_news()` - 新闻搜索
- [ ] `search_and_crawl()` - 搜索+爬取组合

### Phase 2: 扩展搜索功能（中优先级）

- [ ] `search_images()` - 图片搜索
- [ ] `search_videos()` - 视频搜索

### Phase 3: 高级功能（低优先级）

- [ ] 代理支持
- [ ] 结果缓存
- [ ] LLM 驱动的结果过滤和排序

---

## 七、参考实现

### 7.1 现有类似项目

| 项目 | 地址 | 特点 |
|------|------|------|
| duckduckgo-mcp-server | https://gitcode.com/gh_mirrors/du/duckduckgo-mcp-server | 使用 mcp CLI 工具构建 |
| ddg-mcp | https://modelscope.cn/mcp/servers/@misanthropic-ai/ddg-mcp | 纯搜索功能 |

### 7.2 与现有项目的差异

| 维度 | duckduckgo-mcp-server | crawl-mcp (计划) |
|------|----------------------|------------------|
| **框架** | mcp CLI | FastMCP |
| **功能** | 仅搜索 | 搜索 + 爬取 |
| **LLM 集成** | 无 | 有（后处理） |
| **架构** | 单一职责 | 组合功能 |

---

## 八、结论与建议

### 8.1 可行性评估

| 评估项 | 结论 |
|--------|------|
| **技术可行性** | ✅ 高 - ddgs 成熟稳定，集成难度低 |
| **架构兼容性** | ✅ 高 - 可复用现有异步和 LLM 后处理逻辑 |
| **功能价值** | ✅ 高 - 填补了搜索功能空白 |
| **维护成本** | ✅ 低 - 依赖活跃维护的外部库 |

### 8.2 建议

1. **立即开始实施** - ddgs 是一个成熟、稳定的库，集成风险低
2. **保持模块化** - 搜索和爬取功能独立，便于维护
3. **复用现有架构** - 使用 `_run_async()` 和 LLM 后处理模式
4. **渐进式实现** - 先实现核心文本搜索，再扩展其他类型
5. **关注项目更新** - ddgs 活跃维护，定期检查更新

### 8.3 潜在风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| DuckDuckGo 反爬策略 | 搜索失败 | 多引擎轮换，代理支持 |
| 结果质量不稳定 | 用户体验 | LLM 过滤和排序 |
| 速率限制 | 大量请求失败 | 添加重试和代理 |

---

## 九、代码示例

### 9.1 searcher.py 模块骨架

```python
"""搜索模块 - 基于 duckduckgo-search"""

from typing import List, Dict, Any, Optional
from ddgs import DDGS
from .crawler import Crawler, _run_async


class Searcher:
    """搜索类 - 整合 ddgs 和爬虫功能"""

    def __init__(self, proxy: Optional[str] = None):
        self.ddgs = DDGS(proxy=proxy)
        self.crawler = Crawler()

    def search_text(
        self,
        query: str,
        region: str = "wt-wt",
        timelimit: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Dict[str, str]]:
        """文本搜索"""
        results = self.ddgs.text(
            query=query,
            region=region,
            timelimit=timelimit,
            max_results=max_results
        )
        return results

    def search_and_crawl(
        self,
        query: str,
        max_results: int = 5,
        crawl_top_n: int = 1,
        llm_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """搜索并爬取顶部结果"""
        # 1. 搜索
        search_results = self.search_text(query, max_results=max_results)

        if not search_results:
            return {"success": False, "error": "No search results"}

        # 2. 提取 URLs
        urls = [r["href"] for r in search_results[:crawl_top_n]]

        # 3. 批量爬取
        crawl_results = self.crawler.crawl_batch(urls, llm_config=llm_config)

        return {
            "success": True,
            "search_results": search_results,
            "crawled_content": crawl_results,
        }
```

### 9.2 FastMCP 工具注册

```python
# fastmcp_server.py 新增

from crawl4ai_mcp.searcher import Searcher

_searcher = Searcher()

@mcp.tool
def search_text(
    query: str,
    region: str = "wt-wt",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, str]]:
    """
    搜索网页

    Args:
        query: 搜索关键词
        region: 区域代码 (wt-wt, us-en, cn-zh, etc.)
        timelimit: 时间限制 (d=天, w=周, m=月, y=年)
        max_results: 最大结果数
    """
    return _searcher.search_text(query, region, timelimit, max_results)


@mcp.tool
def search_and_crawl(
    query: str,
    max_results: int = 5,
    crawl_top_n: int = 1,
    llm_config: Optional[Union[Dict, str]] = None,
) -> Dict[str, Any]:
    """
    搜索并爬取网页内容

    先搜索获取 URL 列表，然后爬取前 N 个结果的完整内容
    """
    return _searcher.search_and_crawl(query, max_results, crawl_top_n, llm_config)
```

---

*调研完成时间: 2025-01-02*
