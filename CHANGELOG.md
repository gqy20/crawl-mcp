# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
