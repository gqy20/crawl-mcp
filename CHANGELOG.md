# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
