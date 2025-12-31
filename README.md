# Crawl4AI - 简洁网页爬虫

一个简洁、简单的网页爬虫工具，用于从网站提取内容并转换为 Markdown 格式。基于 Crawl4AI 构建，具有简化的界面。

## 功能特点

- 🕷️ **单页爬取**: 从单个网页提取内容
- 🌐 **整站爬取**: 递归爬取整个网站
- 📝 **Markdown 输出**: 清晰易读的 Markdown 格式
- 🔧 **简单界面**: 干净的命令行界面，输出精简
- 📊 **智能日志**: 可配置的详细程度级别

## 安装

```bash
# 克隆仓库
git clone <repository-url>
cd crawl4ai

# 使用 uv 安装（推荐）
uv sync
```

## 快速开始

### 爬取单个页面

```bash
# 基本用法
uv run python main.py single https://docs.rs/bio/latest/bio/all.html

# 自定义输出目录
uv run python main.py single https://example.com -o my_output

# 增强SPA模式（适用于单页应用）
uv run python main.py single https://spa-example.com -e

# 详细输出（用于调试）
uv run python main.py -v single https://example.com

# 安静模式（最小输出）
uv run python main.py -q single https://example.com
```

### 爬取整个网站

```bash
# 基本网站爬取
uv run python main.py website https://docs.rs/bio/latest/bio/all.html

# 自定义设置
uv run python main.py website https://example.com -d 2 -p 10 -c 3

# 自定义输出目录
uv run python main.py website https://example.com -o website_output -d 1 -p 5
```

## 命令行选项

### 全局选项
| 参数 | 说明 |
|------|------|
| `-q` | 静默模式 |
| `-v` | 详细日志模式 |
| `-h` | 显示帮助信息 |

### 单页模式
```bash
uv run python main.py single <url> [选项]
```
| 参数 | 说明 |
|------|------|
| `url` | 目标网页 URL |
| `-o` | 输出目录（可选） |
| `-e` | 增强SPA模式 |

### 整站模式
```bash
uv run python main.py website <url> [选项]
```
| 参数 | 说明 |
|------|------|
| `url` | 起始 URL |
| `-o` | 输出目录（可选） |
| `-d` | 最大爬取深度（默认：2） |
| `-p` | 最大页面数量（默认：10） |
| `-c` | 并发请求数（默认：3） |

## 输出内容

### 单页输出
- 创建包含 Markdown 文件的目录
- 文件包含：标题、URL、爬取元数据和内容

### 整站输出
- 创建包含多个 Markdown 文件的目录
- 生成 `crawl_index.json` 包含爬取统计信息
- 每个页面保存为单独的 Markdown 文件

### 示例输出结构
```
output/
├── domain_single/
│   └── page.md
└── domain_website/
    ├── crawl_index.json
    ├── page1.md
    └── page2.md
```

## 系统要求

- Python 3.12+
- Crawl4AI >= 0.7.8
- uv（推荐）

## 许可证

MIT License
