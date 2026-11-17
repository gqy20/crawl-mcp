# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-11-17

### Added
- **Benchmark 机制**：`scripts/bench.py` 跑代表性渠道（政府政策、学术期刊、代码托管、
  公众号）的完整降级链路和搜索查询，结果渲染到 `docs/BENCHMARK.md`，
  明细追加到 `docs/bench-history.jsonl`
  - `quick`（默认，7 个 URL + 5 个 query）/ `--full`（16 个 URL）/ `--no-cloud` / `--no-write`
  - 文档自动更新：pre-commit hook（改 `src/**/*.py` 时重跑，源码未变则跳过，
    结果随提交一起提交）+ Claude Code Stop hook（会话结束自动重跑）
  - 网络不可用时保留上次结果，不阻塞提交
- `crawl` CLI：终端/脚本直接爬取和搜索，复用 MCP 同一套核心
  - `crawl <url>` 单页 Markdown 到 stdout；多 URL 自动批量输出 JSON
  - `--browser` 强制浏览器、`--json` 完整结果、`crawl search <query>` 网页搜索
  - `crawl site <url> [--depth] [--pages]` 站内递归爬取，输出 JSON
  - `crawl search --news/--books/--videos` 覆盖全部搜索类型
  - `crawl images <query> [--download]` 图片搜索/下载，下载项输出本地路径和大小，
    供多模态模型/CLI 直接查看（内置 analyze 保留在 MCP）
  - `--version` 版本输出；全命令支持 `--help`
  - `--browser` 与 `--cloud` 互斥，避免两个强制模式同时传入时的歧义
  - 进度日志导到 stderr，stdout 纯净可接管道；失败退出码 1
- **Crawl4AI Cloud 兜底路径**（可选）：本地快速提取失败或内容不足时，
  若配置了 `CRAWL4AI_API_KEY`，先调 Cloud `/scrape`（~1-2s，云端自动选引擎），
  成功即返回，失败继续走本地浏览器（~15-23s）
  - 降级链路变为「快速提取 → Cloud 兜底 → 浏览器」
  - 返回 `method="cloud_fallback"` 标记实际路径
  - 批量场景命中限速（429）自动熔断，剩余项交回浏览器路径
  - `CRAWL4AI_CLOUD_FALLBACK=0` 可关闭；未配置 key 时不发起 Cloud 调用，
    降级链路保持「快速提取 → 浏览器」
  - CLI 新增 `crawl --cloud <url>` 强制走 Cloud
- **Cloud 多 key 轮换**：`CRAWL4AI_API_KEY` 支持逗号分隔多个 key，调用量按轮询均摊到各账号
  （用于叠加多个账号的免费额度）；某个 key 额度耗尽（HTTP 402）或被限速（429）时
  自动换下一个 key 重试，其他错误（如 404）不重试
- `.env` 自动加载（`python-dotenv`）：进程入口（CLI / MCP 服务器）启动时加载，
  已存在的环境变量优先不覆盖。`uv run` 本身也会注入 `.env`
- **搜索后端可控**：`search_*` 全部暴露 `backend`（指定搜索引擎引擎，逗号分隔）和 `page`（翻页），
  参数口径与 ddgs 自带 MCP server 一致
  - `backend` 留空 = auto；调用方指定的引擎排最前，失败后再接内置降级池
  - `search_images` 新增 `license_image`（授权过滤：public/share/sharecommercially 等）
  - `search_videos` 新增 `resolution` / `duration` / `license_videos`
  - `search_images` 改走统一搜索包装器，顺带获得引擎降级（原来没有）
  - `crawl search` 加 `--backend` / `--page`，`crawl images` 加 `--backend` / `--page` / `--license-image`
- **搜索算子说明**：工具描述里写清 `query` 原样透传给引擎，可用 `site:` / `filetype:` /
  `intitle:` / `"精确短语"` / `-排除词` 等原生算子（是否生效取决于命中的引擎，可用 `backend` 指定）

### Changed
- 重依赖懒加载：crawl4ai 改为浏览器/LLM 路径按需 import，openai 仅图片分析时 import，
  `__init__.py` 改 PEP 562 懒导出（公开 API 不变）
  - 快速提取路径导入链不再连带 crawl4ai/fastmcp/openai，CLI 冷启动端到端 ~1-2s
  - 测试套件同步提速（不再为纯快速路径用例加载浏览器栈）
- 类型注解现代化（ruff --fix）：`Dict[str, Any]` → `dict[str, Any]` 等
- `pyproject.toml` 显式固定 ruff 规则集（`E4,E7,E9,F,C4`）：ruff 新版本默认规则变化
  会让 CI 行为漂移；dev 依赖钉 `ruff>=0.17.5,<0.18`
- README 补充浏览器依赖说明：浏览器降级路径需先 `playwright install chromium`
- 新增依赖：`httpx>=0.27.0`（Cloud 客户端）、`python-dotenv>=1.0.0`（.env 加载）

### Added
- **Benchmark 用例带预期**：`(渠道, URL, 预期)` 三元组，`成功` 要求正文 ≥200 字，
  `失败·<error_code>` 是**已知问题站点的回归用例**（中科院空模板、网信办失效页）——
  不要求跑通，只要求「失败得对」，`error_code` 变了就是判定逻辑退化
- **Benchmark 表格加分段耗时**：`fast / cloud / browser` 三段各花多久，
  一眼看出慢在降级链路哪一环；「较上次」改为只和同模式历史比

### Added
- **失败处置建议**：CLI 抓取失败时，除了原始错误还打印 `error_code` 对应的下一步建议
  （如 `http_404` → 换入口页重新定位，`tls_error` → 查本机证书链，
  `empty_content` → 重试无用换页面），错误不再只是一句看不懂的英文

### Added
- **降级按错误类型分流**：快速提取拿到 `http_404`/`http_401` 直接失败（换出口也没用），
  拿到 `dns_error`/`connection_refused` 只试 Cloud、跳过浏览器（本地浏览器同一条网络，
  干等也是白等）——实测网信办失效页 10.8s → 0.2s
- **负缓存**：确定性失败（404/401/空内容）和短期粘性失败（挑战/反爬）也缓存，
  TTL `CRAWL_MCP_NEG_TTL`（默认 300s），重试不必再走整条降级链路；超时/限速不缓存
- **域名记忆**：同一域名连续 2 次确定性失败就记住结论，之后直接返回
  （`method="domain_memo"`），不再为同一个域名耗时间
- **失败建议 `hint`**：MCP 返回和 CLI 都给出「下一步该干嘛」
  （换路径 / 换出口 / 修本机证书链 / 退避重试）
- **缓存时效 `cached_age`**：命中缓存时返回条目距今多少秒，避免把旧数据当新的
- **CLI `--quiet`**：不刷浏览器进度日志，管道场景更干净
- `CRAWL4AI_CLOUD_BUDGET` 环境变量：Cloud 兜底整段预算可配（默认 10s）
- **Benchmark 增强**：按渠道分组的表格 + 与上次逐行对比（标出变慢/变快）、
  缓存命中小节（冷启动 vs 命中）、批量吞吐小节（`crawl_batch` 相对逐个抓的加速比）、
  `--repeat` 重复搜索看命中率

### Changed
- **Cloud 兜底加整段预算（10s）**：降级链路里 Cloud 只是中间一环，后面还排着浏览器。
  实测 Cloud 正常 1.6-5.5s，偶尔 20s+（排队/限速），干等会拖垮整体。
  超出预算就让位给浏览器路径——实测国新办 28.4s→17.3s，SciDirect 35.4s→21.1s，
  成功率不变（21/21）

### Fixed
- **`error_code` 把 JS 壳页误判成空内容**：crawl4ai 的
  `script_heavy_shell` 现在归到 `js_challenge`（换浏览器/换路径有用），
  而不是 `empty_content`（重试没用）——两者处置策略不同
- **JS 壳误判成功**：快速提取偶尔只拿到 "JavaScript is disabled" 这类占位提示，
  长度超过阈值会被当成正文返回。现在单独识别（内容 ≤800 字且提示语在开头 300 字内），
  判为失败并继续降级
- 搜索空结果：ddgs 默认后端不稳，同一 query 时常返回 "No results found."。
  失败后不再原地重试，依次换后端池重试：先 `auto`，再按分类换显式引擎池
  （文本 `brave,startpage` → `duckduckgo,mojeek` → `yahoo,wikipedia`；新闻 `duckduckgo,yahoo` → `bing`；
  图片 `duckduckgo` → `bing`；视频 `duckduckgo`；图书 `annasarchive`）
  - 池里的引擎名必须用 ddgs **实际注册**的：`bing` / `google` / `yandex` 在 ddgs 9.x
    被标记 `disabled=True`，写进 backend 会被静默丢弃并回退 auto（等于没换引擎）。
    新增测试拿 `ddgs.engines.ENGINES` 逐个核对池里的名字，上游再禁用引擎时立刻失败
  - 相应把 `search_text` 30s → 45s，`search_news` / `search_books` / `search_videos` 20s → 30s
- `LLMConfig.model` 默认值与实际生效的 `glm-4.7` 不一致，统一为 `glm-4.7`

### Added
- **抓取缓存**（`cache.py`）：成功抓取过的 URL 按 `URL + 参数` 缓存在本地，
  重复抓取直接命中（实测 0.24s → 0.00s），命中时返回 `cached: true`
  - 实测历史会话里 51% 的外部抓取是重复 URL，缓存能省掉这些请求，Cloud 计费场景下等于省额度
  - `CRAWL_MCP_CACHE=0` 关闭，`CRAWL_MCP_CACHE_TTL` 调有效期，`CRAWL_MCP_CACHE_DIR` 换目录
- **正文清洗**（`content.py`）：去掉链接定义块、短导航行、固定 boilerplate，压缩连续空行；
  列表、表格、标题等正文结构原样保留
- **分段耗时** `timings`：返回各降级阶段耗时，如 `{"fast": 0.3, "cloud": 2.8, "browser": 26.4}`
- **错误归类** `error_code`：把错误文本映射成稳定取值（`http_403` / `js_challenge` /
  `antibot` / `empty_content` / `tls_error` / `rate_limited` 等），
  调用方可据此区分「换个方式有用」和「重试也没用」

### Docs
- README 重写：精简定位性表述，按爬取 / 搜索 / 可选分组工具表，
  补 Cloud 兜底路径与性能数据
- CLAUDE.md 同步架构说明：降级链路补上 Cloud 阶段，修正 `run_async()` 命名，
  发布流程改为 `git tag v<version>`
- CLI `--help` 打磨：根命令补子命令与示例，`-n/--max-results`、`--output-dir`
  补默认值说明，参数帮助措辞与实际行为对齐
- README 注明：快速提取路径拿不到 HTML `<title>`，`title` 可能为空

### Verified
在以下依赖组合下跑通全部 288 个测试，并实测 MCP 服务器启动、浏览器降级、站内爬取、
CLI 爬取/搜索/图片下载：
- crawl4ai 0.9.5 / fastmcp 4.2.0 / ddgs 9.16.1 / playwright 1.65.2（当前最新）
- crawl4ai 0.8.6 / fastmcp 3.4.2 / ddgs 9.14.1 / playwright 1.55.0（`pyproject.toml` 下限）
- `pyproject.toml` 的版本下限保持不变，兼容两端；推荐使用 4.x / 0.9.x
- crawl4ai 0.9.0 的 breaking changes 仅针对自托管 Docker HTTP 服务器，pip SDK 用法不受影响；
  0.9.5 修复了 BFS 深爬 `max_pages` 计数（`crawl_site` 受益）


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
