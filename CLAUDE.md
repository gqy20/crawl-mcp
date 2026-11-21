# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 开发命令

```bash
# 安装依赖
uv sync

# 运行测试（所有测试）
uv run pytest

# 运行特定测试文件
uv run pytest tests/unit/test_crawler_v2.py

# 运行特定测试类/函数
uv run pytest tests/unit/test_unified_crawl.py::TestUnifiedCrawlSingleFallback::test_fast_path_returns_markdown_format

# 带覆盖率报告的测试
uv run pytest -v --cov=src/crawl4ai_mcp --cov-report=term-missing

# 代码检查和格式化
uv run ruff check .
uv run ruff format .

# 运行 MCP 服务器（开发调试，HTTP 模式）
uv run python -m crawl4ai_mcp.fastmcp_server --http

# 运行 MCP 服务器（生产模式，STDIO）
uv run crawl-mcp

# CLI（终端直接爬取/搜索，复用同一套核心）
uv run crawl https://example.com          # 单页 Markdown 到 stdout
uv run crawl search "关键词" -n 5          # 网页搜索

# 跑基准测试，更新 docs/BENCHMARK.md（quick：16 用例 + 2 站内 + 6 query，约 2 分钟）
uv run python scripts/bench.py
uv run python scripts/bench.py --full      # 完整数据集
```

### Benchmark 机制

`scripts/bench.py` 跑一遍代表性渠道（政府政策、学术期刊、代码托管、agent 工具文档、
公众号）的完整降级链路和搜索查询，把结果渲染成 `docs/BENCHMARK.md`，
明细追加到 `docs/bench-history.jsonl`。

**用例数据集在 `scripts/bench.yml`**（加/改用例只动这个文件，不用碰 Python），
加载成 `(渠道, URL, 预期, 关键内容)` 四元组：

- `expect: null` → 期望成功且正文 ≥200 字；配 `expect_text: "短语"`
  则正文还必须包含该短语（抓到了 ≠ 抓对了，借鉴 Firecrawl 数据集的 truth_text）
- `expect: "http_404"`（或列表）→ **已知问题站点的回归用例**，期望失败且
  `error_code` 匹配。这类用例（中科院空模板、网信办失效页、Hetzner 定价迁移）
  不是要跑通，而是要保证「失败得对」——`error_code` 变了就是判定逻辑退化。
  quick 16 个用例，full 51 个。数据集来源：~/.claude / ~/.codex 会话日志里
  高频抓取的站点挖掘（agent 工具文档类占了日常爬取大头，全部理应 fast 秒开），
  外加公开 benchmark（WCXB 七类页面、TRACE 九大类）点名的页面类型：
  电商商品页、论坛（HN/SO）、新闻（BBC/NPR）、SaaS 营销页、招聘页、
  视频页（Bilibili）、流媒体 JSON-LD（Spotify）、百科（Wikipedia/百度百科）、
  财经（CoinMarketCap）、医疗（Mayo）、旅游（TripAdvisor）、云定价（AWS/Azure/GCP）、
  开发者社区（dev.to）、文档平台（语雀）、AI 实验室（z.ai 登录墙）
- `sites:` → 站内爬取用例（`crawl_site` 快速 BFS），成功页 ≥3 算符合预期

表格里的 `分段耗时` 是 `fast / cloud / browser` 三段各花了多久，
一眼看出慢在降级链路的哪一环。

自动更新已接好两处，**改完代码不需要手动维护文档**：

- **pre-commit hook**：改动 `src/**/*.py` 或 `scripts/bench.{py,yml}` 时自动重跑
  （源码指纹未变则跳过），生成结果 `git add` 后随本次提交一起提交；
  网络不通时保留上次结果，不阻塞提交；
  **工作区有未暂存改动时整体跳过**——pre-commit 会 stash 未暂存改动，
  hook 里写 docs 或 `git add` 都会让 stash 恢复冲突并中止提交，
  所以先 `git add` 全部改动再 commit
- **Claude Code Stop hook**（`.claude/settings.json`）：会话结束时同样自动重跑

`.bench-stamp` 存源码指纹（已 gitignore），用于判断是否需要重跑。

## 项目架构

### 核心设计：自动降级爬取 + 可选 LLM 插件

降级链路：

1. **阶段 0：快速提取**（~0.3-0.6s）— 基于 `ddgs.extract()`，适用于静态页面
2. **阶段 0.5：Cloud 兜底**（~1-2s）— 快速提取失败或内容不足时，若配置了 `CRAWL4AI_API_KEY`
   则先调 Crawl4AI Cloud `/scrape`，成功即返回，失败继续走浏览器
3. **阶段 1：浏览器降级**（~15-23s）— 快速提取失败或内容不足时自动切换到 Playwright
4. **阶段 2：可选 LLM 插件** — 仅当提供 `llm_config` **且**配置了 `CRAWL_MCP_API_KEY` 时执行

设计取向：LLM 是可选插件而非必经环节，用户拿到 Markdown 后可自行调用任意 LLM 处理。

### 模块职责

| 模块 | 职责 | 关键类/函数 |
|------|------|-------------|
| `crawler.py` | 网页爬取核心（自动降级：快速提取→Cloud→浏览器） | `Crawler.crawl_single()`, `Crawler.crawl_batch()`, `Crawler.crawl_cloud()` |
| `searcher.py` | 搜索 + 内部快速提取（ddgs.extract，不作为 MCP 工具暴露） | `Searcher.search_text()`, `Searcher.extract_url()` |
| `cloud.py` | Crawl4AI Cloud 兜底客户端（httpx，未配置 key 时不发起请求） | `cloud_scrape()`, `cloud_enabled()` |
| `cache.py` | 抓取结果磁盘缓存（按 URL+参数，命中返回 `cached=true`） | `cache.get()`, `cache.put()`, `cache.clear()` |
| `auth_store.py` | 登录态仓库（`~/.crawl_mcp/auth/` 每站点一个 storage_state，按 URL domain 匹配注入；从本地浏览器导入） | `import_from_browser()`, `list_auths()`, `merged_state_for()` |
| `content.py` | 正文清洗、JS 壳/登录墙识别、错误归类 | `clean_markdown()`, `looks_like_js_shell()`, `looks_like_login_wall()`, `classify_error()` |
| `llm_config.py` | LLM 配置管理 | `get_default_llm_config()`, `LLMConfig` |
| `fastmcp_server.py` | MCP 服务器入口，注册所有工具 | `@mcp.tool` 装饰器 |
| `cli.py` | `crawl` CLI 入口（argparse 薄壳，转发到 Crawler/Searcher） | `main()` |

**懒加载约定**：crawl4ai 只在浏览器/LLM 路径函数内 import，openai 只在图片分析时 import，
`__init__.py` 用 PEP 562 懒导出。快速路径不得连带这些重依赖（有子进程测试锁定）。
测试 mock 浏览器/LLM 类时 patch 源模块（如 `crawl4ai.AsyncWebCrawler`），不是 `crawl4ai_mcp.crawler.*`。

**.env 加载**：`utils.load_env()` 只在进程入口（`cli.main()` / `fastmcp_server.main()`）调用，
库用法和 pytest 不受影响。注意 `uv run` 会自动把 `.env` 注入环境变量，
所以测试用 `tests/conftest.py` 的 autouse fixture 显式清除 `CRAWL4AI_API_KEY`，
避免 Cloud 兜底在测试里意外生效。

### 异步处理模式

用 `nest_asyncio` 实现嵌套事件循环兼容：

- `utils.run_async()` 统一封装异步调用
- 允许在已有事件循环的环境（如 Jupyter、某些测试框架）中运行
- 底层爬取使用 `AsyncWebCrawler.arun()` 和 `arun_many()`
- 快速提取路径（`ddgs.extract`）通过 `ThreadPoolExecutor` 并行化

### 并发控制

- **快速提取并发**：`crawl_batch` Phase 1 使用 `ThreadPoolExecutor` 并行内部 `Searcher.extract_url`
- **浏览器爬取并发**：Phase 2 使用 `SemaphoreDispatcher`（`concurrent` 参数）
- **LLM 并发**：批量 LLM 处理使用 `concurrent.futures.ThreadPoolExecutor`（`llm_concurrent` 参数）
- **图片分析并发**：`search_images` 使用 `asyncio.Semaphore`（`analyze_concurrent` 参数）

### LLM 配置格式（实验性功能）

`llm_config` 参数支持三种格式：
1. **字典**：`{"instruction": "提取产品信息", "schema": {...}}`
2. **JSON 字符串**：`'{"instruction": "总结"}'`
3. **纯文本**：`"总结页面内容"`（自动作为 `instruction`）

**安全约束**：认证配置只从环境变量读取，不允许用户传入。未配置 `CRAWL_MCP_API_KEY` 时传 `llm_config` 会跳过并返回 `llm_skipped` 提示。

### 重试机制

浏览器路径只对特定网络错误重试，最多 3 次，使用指数退避（1s、2s、4s）：

- `ERR_NETWORK_CHANGED`
- `ERR_CONNECTION_RESET`
- `ERR_INTERNET_DISCONNECTED`
- `ERR_TIMED_OUT`

重试有总预算 `BROWSER_RETRY_BUDGET`（60s），页面超时 30s——整条链路
（fast ~1s + Cloud ≤10s + 浏览器重试 ≤60s + 最后一次尝试 ≤45s）收在
`crawl_single` 工具超时 120s 内。

搜索路径（`Searcher._search_wrapper`）失败时按分类换后端池重试
（`BACKEND_POOLS`，见下文工具列表）。单次引擎请求超时 `SEARCH_TIMEOUT`（8s），
整条降级链总预算 `SEARCH_BUDGET`（25s）：第一轮必跑，之后每轮先看预算，
超了就带着已有错误返回，不会拖过 MCP 工具超时（search_text 45s / 其余 30s）。

### MCP 工具列表

| 工具 | 功能 | 关键参数 |
|------|------|----------|
| `crawl_single` | 单个明确 URL 的正文提取（快速提取→Cloud→浏览器） | `url`, `enhanced`, `llm_config`(实验性), `prefer_fast`, `min_content_length`, `css_selector`, `excluded_selector`, `scan_full_page` |
| `crawl_batch` | 多个明确 URL 的批量正文提取（并行快速提取，失败项继续降级） | `urls`, `concurrent`, `llm_config`(实验性), `llm_concurrent`, `prefer_fast`, `min_content_length`, `css_selector`, `excluded_selector` |
| `crawl_site` | 从入口页递归发现并爬取站内页面（快速 BFS 优先，SPA 退回浏览器 BFS，不支持 LLM） | `url`, `depth`, `pages`, `concurrent` |
| `search_text` | 通用网页搜索，只返回摘要和链接 | `query`, `region`, `safesearch`, `timelimit`, `max_results`, `page`, `backend` |
| `search_news` | 新闻搜索，只返回摘要和来源链接 | `query`, `region`, `safesearch`, `timelimit`, `max_results`, `page`, `backend` |
| `search_books` | 图书/电子书搜索 | `query`, `region`, `max_results`, `page`, `backend` |
| `search_videos` | 视频搜索 | `query`, `region`, `safesearch`, `timelimit`, `max_results`, `page`, `backend`, `resolution`, `duration`, `license_videos` |
| `search_images` | 图片搜索+下载+分析 | `query`, `region`, `safesearch`, `timelimit`, `max_results`, `size`, `color`, `type_image`, `layout`, `license_image`, `page`, `backend`, `download`, `analyze`, `analyze_concurrent` |

选择规则：
- 单个已知 URL：`crawl_single`
- 多个已知 URL：`crawl_batch`
- 只有入口页、需要沿站内链接发现页面：`crawl_site`
- 只需要找链接/素材，不需要正文：先用 `search_*`
- `enhanced=True` 只影响浏览器路径；强制浏览器增强模式需同时设置 `prefer_fast=False`
- `css_selector` / `excluded_selector` / `scan_full_page` 同样只在浏览器路径生效
  （快速提取不支持选择器，fast 成功时被忽略）。`css_selector` 指定正文区域
  （如 `article`）、`excluded_selector` 排除噪声区域（如 `nav,footer,aside`，
  实测 BBC 文章页链接 100→10）、`scan_full_page=True` 滚动加载整页
  （无限滚动/长列表，实测 dev.to 首页 50k→111k 字）
- `query` 原样透传给引擎，可用搜索引擎原生算子（`site:` / `filetype:` / `intitle:` / `"短语"` / `-排除`），
  算子是否生效取决于实际命中的引擎，用 `backend` 指定
- `backend` 留空 = auto（自动挑引擎），失败后按分类降级换池重试（见 `searcher.BACKEND_POOLS`）。
  **池里的引擎名必须是 ddgs 实际注册的**（bing/google/yandex 在 ddgs 9.x 已被 `disabled=True`，
  写进去会被静默丢弃并回退 auto），有测试锁定这一点

### 环境变量

| 变量 | 说明 | 必需 | 默认值 |
|------|------|------|--------|
| `CRAWL_MCP_API_KEY` | API 密钥（LLM/图片分析必需） | 否* | - |
| `CRAWL_MCP_BASE_URL` | API 基础 URL | 否 | `https://api.openai.com/v1` |
| `CRAWL_MCP_TEXT_MODEL` | 文本模型名称 | 否 | `glm-4.7` |
| `CRAWL_MCP_VISION_MODEL` | 图片分析模型名称 | 否 | `glm-4.6v` |
| `CRAWL4AI_API_KEY` | Crawl4AI Cloud key（逗号分隔多个则轮询均摊），本地提取失败时的兜底爬取路径 | 否 | - |
| `CRAWL4AI_CLOUD_FALLBACK` | `0` 关闭 Cloud 兜底 | 否 | `1` |
| `CRAWL_MCP_CACHE` | `0` 关闭抓取缓存 | 否 | `1` |
| `CRAWL_MCP_CACHE_TTL` | 正缓存有效期（秒） | 否 | `3600` |
| `CRAWL_MCP_NEG_TTL` | 负缓存/域名记忆有效期（秒） | 否 | `300` |
| `CRAWL_MCP_CACHE_DIR` | 缓存目录 | 否 | `~/.cache/crawl_mcp` |
| `CRAWL4AI_CLOUD_BUDGET` | Cloud 兜底整段预算（秒），超时让位给浏览器 | 否 | `10` |
| `CRAWL_MCP_COOKIES` | 浏览器登录态 cookie（Playwright 格式 JSON 数组，如 `[{"name":"session","value":"...","domain":".example.com"}]`），所有浏览器路径自动携带；格式错只告警不阻断。登录墙站点的 `hint` 会指向它 | 否 | - |
| `CRAWL_MCP_STORAGE_STATE` | Playwright storage_state 文件路径（完整登录态含 localStorage；`playwright codegen --save-storage` 登录一次导出），与 `CRAWL_MCP_COOKIES` 可同时配。不直接复用本地浏览器 profile（Playwright 起的是隔离临时实例） | 否 | - |
| `CRAWL_MCP_AUTH_DIR` | 登录态目录（每站点一个 storage_state）。爬取时按 URL domain 自动匹配注入（不全局广播）；`crawl auth import --from chrome/firefox` 从本地浏览器解析导入（装了 `rookie-cookies` 包时优先用——Rust 核心、全平台：Windows 含 DPAPI/App-Bound v20、macOS 含 Keychain、Linux 含 KWallet；不装则仅 Linux（内置 sqlite 解析），Windows/macOS 提示安装；装了但读取失败（浏览器运行中锁库 OS error 32、keyring 锁定）→ 逐 profile 重试跳过被锁的尽力导入，全失败时报真实原因不再误导安装提示；Chrome v10 固定 key 可解、v11 需解锁 keyring——**keyring 锁定时任何库都读不到**，桌面终端跑 `secret-tool search xdg:schema chrome_libsecret_os_crypt_password_v1` 触发解锁弹窗，或改用 codegen）、`list` 查看、`check <名称> --url` 真实探测（短壳判定 + 长登录页判定 `looks_like_login_page`，GitHub 等上千字登录页不再误报有效）。缓存键指纹含目录状态（文件增删改 → 缓存失效） | 否 | `~/.crawl_mcp/auth` |

> *不配置 `CRAWL_MCP_API_KEY` 时所有爬取/搜索功能正常，仅 LLM 后处理和图片分析不可用。
> 不配置 `CRAWL4AI_API_KEY` 时降级链路为「快速提取 → 浏览器」，不发外部请求，
> `method` 不会出现 `cloud_fallback`。

### 响应格式约定

**爬取结果**（`crawl_single` / `crawl_batch`）：
```python
{
    "success": bool,
    "markdown": str,
    "title": str,
    "error": str | None,
    # prefer_fast=True 时可能出现；prefer_fast=False 纯浏览器路径可能不存在
    "method": "fast_extract" | "cloud_fallback" | "browser_fallback" | "domain_memo",
    # 仅发生降级时出现
    "fallback_reason": str,
    # 失败原因归类（成功时为 None），取值见下
    "error_code": str | None,
    # 各阶段耗时（秒）；命中缓存时不返回
    "timings": {"fast": 0.3, "cloud": 2.8, "browser": 26.4},
    # 命中本地缓存（含负缓存）时为 True
    "cached": bool,
    # 缓存条目距今多少秒——数据可能是旧的
    "cached_age": float,
    # 失败时给出的下一步建议（换路径 / 换出口 / 修证书…）
    "hint": str,
    # 域名此前多次失败、直接给结论时，method 为 "domain_memo"
    # 可选 LLM 结果（仅当 llm_config + CRAWL_MCP_API_KEY 时出现）
    "llm_summary": str,  # 纯文本摘要
    "llm_data": dict,  # 结构化提取
    "llm_error": str,  # LLM 处理错误
    # LLM 跳过提示（传了 llm_config 但未配置 API Key）
    "llm_skipped": str,  # 跳过原因说明
}
```

`error_code` 取值：`http_402` / `http_403` / `http_404` / `http_401` / `rate_limited` / `http_5xx` /
`tls_error` / `js_challenge` / `antibot` / `login_wall` / `empty_content` / `timeout` /
`connection_refused` / `connection_reset` / `dns_error` / `no_results` / `unknown`。

### 内容质量与降级判定

快速提取拿到的不一定是正文，`content.py` 负责把关：

- **JS 壳识别**：`looks_like_js_shell()` —— 内容 ≤800 字且开头 300 字内出现
  "JavaScript is disabled" 一类提示时判为失败并降级（这类占位文本长度可能超过
  `min_content_length`，只看长度会误判成功）
- **登录墙/空状态壳识别**：`looks_like_login_wall()` —— AI 时代站点高发：
  页面渲染成功、字数过阈值，但内容是未登录空状态（空画廊占位、登录引导）。
  短内容（<600 字）+ 登录/UI 词密度高或带占位行（连续 "-"）时判为壳并降级
  浏览器（z.ai 匿名首页实测 312 字壳 → 浏览器 1981 字正文）
- **正文清洗**：`clean_markdown()` —— 引用式链接（`[文字][1]`+定义块，ddgs 默认输出）
  先解析成内联链接，再去掉链接定义块、短导航行、固定 boilerplate，
  压缩连续空行；列表、表格、标题等正文结构原样保留
- **错误归类**：`classify_error()` —— 把错误文本映射成稳定的 `error_code`，
  让调用方能区分「换个方式有用」（`http_403`、`js_challenge`）和「重试也没用」
  （`empty_content`、`http_404`）

**降级策略（按错误类型决定还要不要继续降级）**：

| 快速提取的错误 | 处置 | 理由 |
|---|---|---|
| `http_404` / `http_401` | 直接失败，不降级 | 换出口、换引擎都一样 |
| `dns_error` / `connection_refused` | 试 Cloud，跳过浏览器 | Cloud 是云端出口；本地浏览器同一条网络 |
| 其他（403 / 超时 / 内容不足…） | 走完整链路 fast → Cloud → 浏览器 | 还有救 |
| JS 壳、登录墙/空状态壳、空内容 | 走完整链路 | 浏览器可能渲染出来（z.ai 实测 312 字壳 → 1981 字正文） |

**缓存的三种条目**（`cache.py`，共用一套落盘机制，靠 namespace 区分）：

- 正缓存 `crawl`：成功结果，TTL `CRAWL_MCP_CACHE_TTL`
- 负缓存 `negative`：确定性失败（404/401/空内容）和短期粘性失败（挑战/反爬），
  TTL `CRAWL_MCP_NEG_TTL`（默认 300s）——重试也没用，不必每次重走整条降级链路
- 域名记忆 `domain`：同一域名连续 2 次**域名级**故障（`dns_error` / `connection_refused`）
  就记住结论，之后同域名直接返回，`method="domain_memo"`。
  404/空内容是**路径级**问题，只进按 URL 的负缓存，不污染域名
  （否则 cas.cn/tzgg 的空模板会连累 cas.cn 首页）；超时/限速这类波动也不进

缓存键含**登录态指纹**（`CRAWL_MCP_COOKIES`/`CRAWL_MCP_STORAGE_STATE` 的 hash，
cookie 值不进键）：配好/更换登录态后同 URL 的旧正/负缓存立即失效，不会拿
「配 cookie 前的失败负缓存」糊弄重试。登录墙在浏览器路径也有终检——带过期
登录态渲染出的壳按 `error_code=login_wall` 失败，不假成功。

**站点爬取结果**（`crawl_site`）：
```python
{
    "successful_pages": int,
    "total_pages": int,
    "success_rate": str,
    "results": [
        {
            "success": bool,
            "markdown": str,
            "title": str,
            "error": str | None,
        },
        ...,
    ],
}
```


**搜索结果**：
```python
# search_text / search_news
{"success": bool, "query": str, "count": int, "results": list, "error": str | None}

# search_images
{
    "success": bool,
    "query": str,
    "search_results": {"count": int, "results": list},
    "download_results": {...},  # 仅当 download=True
    "analysis_results": {...},  # 仅当 analyze=True
}
```

## 发布流程

1. 更新 `pyproject.toml` 中的版本号
2. 创建 git tag：`git tag v<version> && git push --tags`
3. GitHub Actions 会自动：运行测试、检查格式、验证版本号匹配、构建分发包、发布到 PyPI

或手动触发：GitHub → Actions → Publish to PyPI → Run workflow
