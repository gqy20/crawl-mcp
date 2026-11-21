# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-11-21

### Added

- **Crawl4AI Cloud 兜底**：快速提取失败/内容不足时先调 Cloud `/scrape` 再降浏览器。
  `CRAWL4AI_API_KEY` 多 key 轮询（402/429 自动换，批量 429 熔断）、
  `CRAWL4AI_CLOUD_FALLBACK=0` 关闭、`CRAWL4AI_CLOUD_BUDGET` 整段预算（默认 10s）；
  CLI `crawl --cloud` 强制走 Cloud
- **失败可判定、可缓存**：`error_code`（新增 `http_402`、`login_wall`）+ `hint`
  下一步建议；负缓存确定性失败（TTL `CRAWL_MCP_NEG_TTL` 默认 300s）；域名级故障
  （DNS/连接拒绝）记域名记忆，`method="domain_memo"`；命中返回 `cached`/`cached_age`
- **降级按错误类型分流**：404/401 不降级；DNS/连接拒绝只试 Cloud、跳过本地浏览器
- **抓取缓存**：按 URL+参数落盘（历史会话实测 51% 为重复 URL）；
  `CRAWL_MCP_CACHE` / `CRAWL_MCP_CACHE_TTL` / `CRAWL_MCP_CACHE_DIR` 可配
- **`crawl` CLI**：单页 Markdown 到 stdout / 多 URL 批量 JSON / `search` / `site` /
  `images` 子命令，`--css` / `--exclude-css` / `--full-page` / `--quiet` /
  `site --concurrent`；stdout 纯净可接管道，失败退出码 1
- **搜索后端可控**：`search_*` 暴露 `backend` / `page`，失败按错误分类换引擎池
  重试（池内引擎必须 ddgs 实际注册，有测试锁定）；结果按链接去重
- **`crawl_site` 快速 BFS**：入口页 fast 成功时从 Markdown 提站内链接逐层批量爬取，
  SPA/失败退回浏览器 BFS
- **Benchmark 机制**：`scripts/bench.py` + 数据集 `scripts/bench.yml`（quick 16 /
  full 51 用例，含预期失败回归锁与 `expect_text` 关键内容断言）渲染
  `docs/BENCHMARK.md`，明细追加 `docs/bench-history.jsonl`；pre-commit / Stop hook
  自动重跑（源码+数据集指纹未变跳过，网络不通不阻塞提交）
- 正文清洗 `clean_markdown()`、分段耗时 `timings`、`.env` 自动加载（python-dotenv）
- **登录墙/空状态壳识别**：渲染成功但内容是未登录空状态的「假成功」页
  （实测 z.ai 312 字壳 → 1981 字正文），判壳后降级浏览器；`error_code=login_wall`
  进短期负缓存
- **浏览器提取质量**：`enhanced=True` 用 `PruningContentFilter` 剪导航/boilerplate；
  `wait_for` 等正文实文本出现即返回（浏览器耗时约砍半）；`magic` +
  `remove_overlay_elements` 删弹窗/同意横幅；ASCII 表格残留清理
- **正文区域控制**：`crawl_single` 新增 `css_selector` / `excluded_selector` /
  `scan_full_page`（`crawl_batch` 支持前两个），只在浏览器路径生效
- **登录态体系**：环境变量 `CRAWL_MCP_COOKIES`（cookie JSON 数组）、
  `CRAWL_MCP_STORAGE_STATE`（storage_state 文件，含 localStorage）所有浏览器路径
  自动携带，可同时配；登录态仓库 `~/.crawl_mcp/auth/`（`CRAWL_MCP_AUTH_DIR`）
  每站点一个文件、按 URL domain 匹配注入不全局广播，缓存键含登录态指纹、
  增删改即失效；`crawl auth list` / `check <名称> --url` 探测 / `import --from
  chrome|chromium|firefox`（装 rookie-cookies 优先，Firefox 明文直读，Chrome v10
  可解、v11 需解锁 keyring，已有 codegen 导出不覆盖）。认证只从环境变量/仓库读，
  不接受工具参数传入

### Changed

- **超时对齐**：浏览器页面 30s、网络错误重试总预算 60s、`crawl_single` 工具超时
  120s；搜索单引擎 8s + 整链总预算 25s（原 4 轮池最坏 ~140s 超工具超时）
- 正文清洗先解析引用式链接再删定义块（不留悬空引用）
- 重依赖懒加载（crawl4ai/openai 按路径按需 import，CLI 冷启动 ~1-2s）；
  新增依赖 `httpx`、`python-dotenv`；ruff 规则集固定 `E4,E7,E9,F,C4`

### Fixed

- pre-commit bench hook 与 stash 冲突：工作区有未暂存改动时 hook 整体跳过并提示，
  不再中止提交（原会 "Stashed changes conflicted with hook auto-fixes" 回滚）
- 缓存键加入登录态指纹：配好/更换登录态后不再命中旧失败负缓存，cookie 值不进键
- 浏览器路径登录墙终检：过期登录态渲染出的壳不再按成功返回，降为
  `error_code=login_wall` 失败
- 域名记忆误伤同站页面：404/空内容是路径级问题，只进按 URL 负缓存
- `error_code` 被裸数字误触发（"timed out after 500 ms" → `http_5xx`），状态码
  正则锚定 HTTP 上下文
- 批量爬取：跳过浏览器分支丢失原始错误、缓存命中重复调 LLM
- `crawl --cloud` 绕过统一收尾，缺 `error_code`/`hint`/`timings` 且不写缓存
- JS 壳页占位提示超长被当正文；`script_heavy_shell` 归入 `js_challenge`
- bench 源码指纹不含 `bench.py` 自身，改判定逻辑不触发重跑
- 搜索空结果原地重试无效，改为换后端池重试
- `LLMConfig.model` 默认值与实际生效的 `glm-4.7` 不一致
- `crawl --help` 子命令示例补上 `crawl auth`
- **Windows/macOS Chrome cookie 导入修复**（真机验证）：rookie-cookies 0.6 实际输出
  蛇形键 `http_only`/`same_site`，此前按驼峰读取导致 httpOnly 全丢、sameSite 全走
  默认（现在两种键名都认）；浏览器运行中活跃 profile 的库被进程锁住（OS error 32）
  时改为逐 profile 重试，跳过被锁的尽力导入；会话 cookie `expires=None` 归一 `-1`
  （此前在过滤器里 `None < float` 直接 TypeError 中断整个导入）；装了 rookie 但
  读取失败时报真实原因（锁库/keyring），不再误报"需要安装"
- **`crawl auth check` 识别长登录页**：新增 `looks_like_login_page`（标题即登录页 /
  正文是登录表单特征，不限长度），GitHub 等上千字登录页此前因字数过阈值逃过短壳
  判定被误报"有效"（实测 1526 字登录页）；渲染成功后先辨登录页再下结论，
  正常长文带登录导航不误伤

### Docs

- README 重写（按爬取/搜索/可选分组，补 Cloud 路径与性能数据）；
  CLAUDE.md 同步架构与 bench 机制

### Verified

- 433 个测试全过；依赖上下限组合验证（crawl4ai 0.9.5 / fastmcp 4.2.0 / ddgs 9.16.1 /
  playwright 1.65.2 与 pyproject 下限）

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
