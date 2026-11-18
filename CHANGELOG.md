# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-11-17

### Added

- **Crawl4AI Cloud 兜底**：快速提取失败/内容不足时先调 Cloud `/scrape`（~1-2s），
  失败再走本地浏览器；未配置 `CRAWL4AI_API_KEY` 不发请求。
  `CRAWL4AI_CLOUD_FALLBACK=0` 关闭；`CRAWL4AI_CLOUD_BUDGET` 控制整段预算
  （默认 10s，超时让位浏览器，实测 SciDirect 35.4s→21.1s）；
  多 key 逗号分隔轮询均摊，402/429 自动换 key；批量命中 429 熔断交回浏览器。
  CLI `crawl --cloud` 强制走 Cloud
- **失败可判定、可缓存**：`error_code`（含新增 `http_402`）+ `hint` 下一步建议；
  负缓存确定性失败（404/空内容/挑战页，TTL `CRAWL_MCP_NEG_TTL` 默认 300s）；
  域名级故障（DNS/连接拒绝）连续 2 次记域名记忆，直接返回 `method="domain_memo"`；
  缓存命中返回 `cached` / `cached_age`
- **降级按错误类型分流**：404/401 直接失败不降级；DNS/连接拒绝只试 Cloud
  跳过浏览器（本地浏览器同一条网络）。实测网信办失效页 10.8s→0.2s
- **抓取缓存**：按 URL+参数落盘，历史会话实测 51% 抓取是重复 URL；
  `CRAWL_MCP_CACHE` / `CRAWL_MCP_CACHE_TTL` / `CRAWL_MCP_CACHE_DIR` 可配
- **`crawl` CLI**：单页 Markdown / 多 URL 批量 / 搜索 / 图片下载子命令，
  stdout 纯净可接管道，失败退出码 1，`--quiet` 关进度
- **搜索后端可控**：`search_*` 暴露 `backend` / `page`，失败按分类换引擎池重试。
  池只用 ddgs 实际注册的引擎名——bing/google/yandex 在 ddgs 9.x 被禁用，
  写入会被静默回退 auto（等于没换引擎），有测试拿 `ddgs.engines.ENGINES` 锁定；
  换池重测 12/12 命中。搜索结果按链接去重
- **`crawl_site` 快速 BFS**：入口页快速提取成功时，从 Markdown 提站内链接、
  逐层批量爬取（每页自动降级），静态站 ~0.5s/页；SPA/失败退回浏览器 BFS
- **Benchmark 机制**：`scripts/bench.py` 跑数据集渲染 `docs/BENCHMARK.md`，
  明细追加 `docs/bench-history.jsonl`；数据集外置 `scripts/bench.yml`
  （quick 16 / full 51 个用例 + 6 个 query + 2 个站内爬取用例，
  含「预期失败」的已知问题回归锁和 `expect_text` 关键内容断言，
  数据集来自 ~/.claude/~/.codex 会话日志高频站挖掘，并对照公开 benchmark
  WCXB/TRACE 的网站池补齐电商/论坛/新闻/SaaS/招聘，再拓宽到视频/流媒体 JSON-LD/
  百科/财经/医疗/旅游/云定价/开发者社区/文档平台，含知乎反爬回归锁）；
  pre-commit / Stop hook 自动重跑，源码+数据集指纹未变则跳过，网络不通不阻塞提交
- `crawl site --concurrent`：CLI 站内爬取暴露并发参数（与 MCP 工具对齐）
- 正文清洗 `clean_markdown()`、分段耗时 `timings`、`.env` 自动加载（python-dotenv）
- **登录墙/空状态壳识别**：AI 站点高发的「假成功」——渲染成功、字数过阈值，
  内容却是未登录空状态（z.ai 匿名首页 312 字空画廊）。`looks_like_login_wall()`
  判定后降级浏览器渲染（实测 312 字壳 → 1981 字正文）；新增 `error_code=login_wall`
  （hint 建议带 cookie 或用官方 API），进短期粘性负缓存
- **提取质量**（文字/格式）：`enhanced=True` 接 crawl4ai
  `PruningContentFilter` 剪导航/boilerplate（实测 Wikipedia 导航行 32%→0.8%、
  BBC 38%→0；代价是图片一并剪掉，普通浏览器路径保留图）、`wait_for` 等正文
  实文本出现即返回替代盲等（浏览器耗时砍半：BBC 20.3s→9.3s、百度百科 21.9s→
  7.7s、语雀 18.6s→6.7s）、`magic`（随机 UA+拟人信号）+ `remove_overlay_elements`
  删弹窗/cookie 同意横幅；浏览器路径补上与 fast 路径同一套 `clean_markdown`；
  清洗新增 ASCII 表格残留清理（Wikipedia 105 处 ─│┬ → 3，markdown 表格分隔行
  不受影响）。已知限制：fast 路径（ddgs.extract）不输出图片，要图片走浏览器路径
- **正文区域/整页控制**（`crawl_single` 新参数，`crawl_batch` 支持前两个）：
  `css_selector` 只提取匹配元素（如 `article`）、`excluded_selector` 排除噪声
  区域（实测 BBC 文章页链接 100→10）、`scan_full_page` 滚动加载整页（实测
  dev.to 无限滚动首页 50k→111k 字）。全部只在浏览器路径生效，fast 成功时忽略
- **登录态 cookie**：环境变量 `CRAWL_MCP_COOKIES`（Playwright 格式 JSON 数组），
  所有浏览器路径自动携带（httpbin 回显验证）。登录墙识别（`login_wall`）的
  `hint` 会指向它；格式错只告警不阻断爬取。认证仍只从环境变量读，
  不接受工具参数传入
- **完整登录态**：环境变量 `CRAWL_MCP_STORAGE_STATE`（Playwright storage_state
  文件，`playwright codegen --save-storage` 登录一次导出，含 localStorage——
  SPA token 常在那里），与 `CRAWL_MCP_COOKIES` 可同时配（httpbin 回显验证）。
  不直接复用本地浏览器 profile（Playwright 起隔离临时实例，Chrome 锁 profile
  且版本不配会拒启）
- CLI `crawl --css` / `--exclude-css` / `--full-page`（单页全三个，批量前两个），
  只在浏览器路径生效
- **登录态仓库**（`auth_store.py` + `crawl auth` 子命令）：登录态统一放
  `~/.crawl_mcp/auth/`（`CRAWL_MCP_AUTH_DIR` 可覆盖），每站点一个 storage_state
  文件，爬取时按 URL 的 domain 自动匹配注入——爬 zhihu.com 只带 zhihu 的
  登录态，不全局广播（全局 env 两变量保留为兜底）。缓存键指纹覆盖目录状态，
  文件增删改即缓存失效。三个子命令：
  - `crawl auth import --from chrome|chromium|firefox [--site 域名]`：
    直接从本地已登录浏览器解析。装了 `rookie-cookies`（Rust 核心，
    调研对比 browser_cookie3/yt-dlp/HackBrowserData 后的最优维护方案）
    时优先用它，失败回落内置实现；Firefox cookies.sqlite 明文直读；
    Chrome v10 固定 key 可解，v11 需解锁 keyring（**锁定时任何库都读不到**——
    rookie 实测同样失败，这是 OS 层约束；文档给 secret-tool 解锁指引），
    失败清晰告警并提示 playwright codegen 兜底；过期 cookie 不导，
    已有 codegen 导出的文件不覆盖
  - `crawl auth list`：站点 / cookie 数 / 更新时间 / 域名一览
  - `crawl auth check <名称> --url <登录后页面>`：真实请求探测，
    复用降级链路判定（有效 ✓ / 已失效·登录墙 ✗）

### Fixed（0.2.1 内）

- **登录态变更不撞旧缓存**：`CRAWL4AI` 正/负缓存键加入登录态指纹
  （`CRAWL_MCP_COOKIES` + `CRAWL_MCP_STORAGE_STATE` 的 hash，cookie 值不进键）。
  此前登录墙站点失败进负缓存（300s）后配好 cookie 立即重试，会命中旧失败
  结果、看起来像 cookie 没生效；端到端验证配 cookie 后立即重新请求
- **浏览器路径登录墙终检**：带过期/无效登录态渲染出的页面，字数够但内容是
  登录引导壳，此前按 `success=True` 假成功返回；现在 fast/Cloud 之后浏览器
  结果同样过 `looks_like_login_wall` 把关，降为 `error_code=login_wall` 失败，
  hint 指向重新配置/导出登录态

### Changed

- **超时对齐**：浏览器页面超时 60s→30s、网络错误重试加 60s 总预算、
  `crawl_single` 工具超时 75s→120s；搜索单次引擎请求 8s + 整链总预算 25s
  （原来 4 轮池最坏 ~140s，超工具超时）
- **正文清洗先解析引用式链接**：ddgs.extract 输出 `[文字][1]` + 文末定义块
  （常为相对路径），直接删定义块会留悬空引用；现在先转成内联 `[文字](url)`
- 重依赖懒加载：crawl4ai/openai 按路径按需 import，CLI 冷启动 ~1-2s
- 新增依赖 `httpx`（Cloud 客户端）、`python-dotenv`（.env 加载）；
  ruff 规则集固定 `E4,E7,E9,F,C4`

### Fixed

- **域名记忆误伤同站页面**：404/空内容是路径级问题，只进按 URL 的负缓存，
  不再连累同站其他路径（cas.cn/tzgg 空模板曾连带 cas.cn 首页）
- `error_code` 被裸数字误触发（"timed out after 500 ms" → `http_5xx`），
  状态码正则全部锚定 HTTP 上下文
- 批量爬取跳过浏览器分支丢失原始错误（`error_code` 一律 `unknown`）
- 批量爬取缓存命中重复调 LLM（缓存键含 llm 配置，命中项已带 LLM 字段）
- `crawl --cloud` 绕过统一收尾，缺 `error_code`/`hint`/`timings` 且不写缓存
- JS 壳页误判：占位提示超长被当正文、`script_heavy_shell` 被归成
  `empty_content`（处置策略不同），分别单独识别/归入 `js_challenge`
- bench 源码指纹不含 `bench.py` 自身，改判定逻辑不触发重跑
- 搜索空结果原地重试无效，改为换后端池重试（见 Added）
- `LLMConfig.model` 默认值与实际生效的 `glm-4.7` 不一致

### Docs

- README 重写（按爬取/搜索/可选分组，补 Cloud 路径与性能数据）；
  CLAUDE.md 同步架构与 bench 机制；CLI `--help` 措辞与实际行为对齐

### Verified

- 344 个测试全过，并实测 MCP 服务器启动、浏览器降级、站内爬取、CLI 全命令
- 依赖上下限组合：crawl4ai 0.9.5 / fastmcp 4.2.0 / ddgs 9.16.1 / playwright 1.65.2
  与 pyproject 下限（crawl4ai 0.8.6 / fastmcp 3.4.2 / ddgs 9.14.1 / playwright 1.55.0）

## [0.2.0] - 2026-06-12

### Added
- `crawl_single` / `crawl_batch` 统一自动降级策略：
  - 默认先使用内部 `ddgs.extract()` 快速提取静态页面
  - 快速提取失败、内容不足或检测到 SPA 骨架页时自动 fallback 到浏览器渲染
  - 返回 `method="fast_extract"` / `method="browser_fallback"` 标记实际路径
  - fallback 项返回 `fallback_reason`，便于模型和调用方理解降级原因
- `crawl_batch` 批量智能分流：
  - 并行快速提取所有 URL
  - 只对失败/短内容/SPA 骨架页执行浏览器 fallback
  - 支持按 URL 子集区分普通浏览器模式和 enhanced 模式
- MCP 工具描述质量测试，锁定工具选择边界、参数语义和返回字段说明，避免模型可见描述退化。

### Changed
- **MCP 工具集调整为 8 个公开工具**：
  - 保留：`crawl_single`、`crawl_batch`、`crawl_site`
  - 保留：`search_text`、`search_news`、`search_books`、`search_videos`、`search_images`
  - `extract_url` 不再作为独立 MCP 工具暴露，改为 `crawl_single` / `crawl_batch` 的内部快速路径
- `crawl_single` 成为推荐的单页爬取入口，静态页走快速路径，动态页自动 fallback 到浏览器。
- `crawl_batch` 成为多个已知 URL 的批量爬取入口，避免调用方手动区分静态页和动态页。
- `crawl_site` 明确为站点入口递归爬取工具：
  - 使用浏览器 + BFS 深度策略
  - 不走快速提取路径
  - 不支持 LLM 后处理
- 工具超时重新校准：
  - `crawl_single`: 75s
  - `crawl_batch`: 180s
  - `crawl_site`: 120s
  - `search_text`: 30s
  - `search_news` / `search_books` / `search_videos`: 20s
  - `search_images`: 30s
- `llm_config` 降级为实验性可选插件能力。未配置 `CRAWL_MCP_API_KEY` 时不阻断爬取，返回 `llm_skipped`。
- 环境变量统一为 `CRAWL_MCP_*`：
  - `CRAWL_MCP_API_KEY`
  - `CRAWL_MCP_BASE_URL`
  - `CRAWL_MCP_TEXT_MODEL`
  - `CRAWL_MCP_VISION_MODEL`
- FastMCP 最低版本升级：`fastmcp>=3.2.4` → `fastmcp>=3.4.2`
  - 包含 Starlette 安全下限修复（FastMCP 3.4.1）
  - 包含 JWT 私有 header 兼容修复（FastMCP 3.4.2）
- MCP 工具 docstring 全面重写，明确：
  - `crawl_single` / `crawl_batch` / `crawl_site` 的选择规则
  - `prefer_fast=False` 和 `enhanced=True` 的组合语义
  - 搜索工具只返回摘要和链接，不抓取页面正文
  - 条件字段 `method` / `fallback_reason` / `llm_*` 何时出现

### Fixed
- `crawl_site` 的 `concurrent` 参数现在实际传入 `SemaphoreDispatcher`，不再只是签名参数。
- `search_text` / `search_news` / `search_books` / `search_videos` / `search_images` 正确透传 `region`、`safesearch`、`timelimit`、`max_results` 等过滤参数。
- 批量 fallback enhanced 判定移除历史 placeholder，仅 SPA 骨架页启用 enhanced 浏览器配置。
- 修复测试中直接写入 `os.environ` 的环境变量泄漏风险。
- 修复同步 wrapper 测试中 coroutine 未关闭导致的 `RuntimeWarning`。

### Refactor
- 抽出 `_FastExtractDecision` 和 `_decide_fast_extract_next_step()`，统一单页/批量快速提取后的 fallback 决策。
- `_browser_crawl_subset()` 增加 URL 列表和 enhanced 标志长度校验，避免静默错位。
- `Searcher` 收敛 DDGS 搜索参数构造，减少搜索工具之间的重复参数组装。
- 清理 fallback 兼容层和临时集成测试，降低维护噪声。

### Docs
- README 工具用法重排，补齐 `crawl_batch` / `crawl_site` 示例和参数说明。
- CLAUDE.md 更新架构说明、工具选择规则、响应格式约定和发布流程。
- 标注 `extract_url` 为内部快速提取实现，不再作为公开 MCP 工具描述。

## [0.1.5] - 2026-05-11

### Added
- **TimeoutMiddleware**：基于 FastMCP 中间件体系的工具级超时控制
  - 支持全局默认超时 + 按工具名独立配置
  - 超时后抛出 `asyncio.TimeoutError`，可被上游中间件自动转换为 McpError
- 原生 `@mcp.tool(timeout=N)` 装饰器参数（9 个工具全覆盖）
  - 与 TimeoutMiddleware 形成双层超时防御（内层装饰器 + 外层中间件）
- 工具标签分组：爬取类 `tags={"crawl"}`，搜索类 `tags={"search"}`
- `crawl_batch` / `crawl_site` 注入 `ctx: Context` 参数，支持 `ctx.info()` 进度报告
- FastMCP 3.x 新特性测试套件（22 个测试用例）

### Changed
- HTTP 传输协议从 `"http"` 升级为 `"streamable-http"`（FastMCP 3.x 推荐传输方式）
- 超时配置从经验值改为基于 benchmark P95 数据 × 3x 安全倍数校准：
  - extract_url: 15s (7.5x) | search_text: 30s (3.75x) | search_news: 20s (7.4x)
  - search_books: 20s (10.5x) | search_videos: 20s (8.3x) | search_images: 30s (10.3x)
  - crawl_single: 120s (7.1x) | crawl_batch: 300s (27.3x) | crawl_site: 300s (~10x)

### Fixed
- **extract_url 无限挂起问题**：添加 15s 超时保护，防止 DDGS 网络异常时永久阻塞

### Refactor
- 测试清理：删除 2 个冗余测试文件（`test_crawler.py`、`test_searcher.py`），合并重叠测试
  - 净减 589 行代码，测试用例从 102 → 113 个（质量提升）
- `test_fastmcp_server.py` 重写：覆盖全部 9 个工具的注册、schema 和函数行为验证
- `test_searcher_refactor.py` 合并：统一 searcher 全部 25 个测试用例

## [0.1.4] - 2026-05-01

### Added
- `extract_url` 工具：基于 ddgs.extract() 的轻量级 URL 内容提取（无需浏览器，速度提升 5-10 倍）
  - 支持 5 种输出格式：text_markdown / text_plain / text_rich / text / content
- `search_books` 工具：图书/电子书搜索（复用 ddgs.books）
- `search_videos` 工具：视频搜索（含时长、播放量、embed 等丰富字段）

### Changed
- **依赖全面升级**：
  - crawl4ai: 0.8.5 → 0.8.6
  - ddgs: 9.10.0 → 9.14.1（BingImages 后端、DHT P2P 缓存 beta、primp HTTP 客户端升级）
  - fastmcp: 2.14.1 → 3.2.4（Provider/Transform 架构、Code Mode、Apps UI）
  - primp: 0.15.0 → 1.2.3
- Crawler 重构：用原生 `LLMExtractionStrategy` 替换自实现的 LLM 方法
  - 删除 `_call_llm`、`_call_llm_batch`、`_call_llm_batch_sync`、`postprocess_markdown`
  - 新增 `_postprocess_with_llm`：委托给原生策略，支持 block 和 schema 两种模式
  - 新增 `_postprocess_batch_with_llm`：ThreadPoolExecutor 并行处理
- Searcher 重构：
  - 提取 `_search_wrapper` 通用方法，消除 search_text/search_news 重复代码
  - `_download_images` 改为 ThreadPoolExecutor 并行下载（默认 3 并发，结果保序）
- `__init__.py` 版本号改为 `importlib.metadata` 动态读取，消除硬编码

### Fixed
- BFSDeepCrawlStrategy 返回 list 的兼容问题（arun 返回列表而非单个结果）
- LLM schema 提取时 JSON 被 Markdown 围栏包裹的解析问题
- fastmcp 3.x API 适配：`_tool_manager._tools` → `mcp.list_tools()`（异步）

## [0.1.3] - 2025-01-15

### Added
- 图片搜索功能（`search_images`），支持搜索、下载和 AI 分析
- LLM 并行处理，批量爬取时显著提升处理速度
- 图片分析并发控制参数（`analyze_concurrent`）
- CI workflow，每次提交自动运行测试和代码检查
- CHANGELOG.md 维护版本变更记录

### Changed
- 默认文本模型更新为 `glm-4.7`
- 默认视觉模型更新为 `glm-4.6v`
- 优化 publish.yml，从 CHANGELOG.md 读取 Release 内容

### Fixed
- 修复并行测试的 mock 问题

### Refactor
- 清理冗余代码和过时注释

## [0.1.2] - 2025-01-02

### Added
- `search_text` 工具：通用网页搜索
- `search_news` 工具：新闻内容搜索
- 搜索支持区域过滤（`region`）和时间限制（`timelimit`）
- 搜索支持安全搜索级别（`safesearch`）

### Changed
- 升级到 `ddgs>=9.0.0` 修复搜索超时问题

### Fixed
- DDGS API 参数名适配

## [0.1.1] - 2024-12-31

### Added
- 命令行入口点（`crawl-mcp`）
- pre-commit hooks 配置
- 文档更新：PyPI 徽章和简化的 MCP 配置说明

### Fixed
- PyPI 发布工作流问题
  - 在 publish-pypi job 中添加 checkout 步骤
  - 使用 twine 直接上传
  - 禁用 PyPI attestations
  - 移除 OIDC 认证，改用 API Token

## [0.1.0] - 2024-12-30

### Added
- 初始版本发布
- `crawl_single`：单页爬取
- `crawl_batch`：批量爬取（异步并行）
- `crawl_site`：整站爬取
- LLM 后处理支持（`llm_config` 参数）
- 两阶段处理架构：快速爬取 + 可选 AI 处理
- 网络错误自动重试（指数退避）
- GitHub Actions 自动发布到 PyPI
