#!/usr/bin/env python3
"""Crawl4AI - Enhanced web crawler with SPA support."""

import argparse
import asyncio
import logging
import sys
import re
import time
from pathlib import Path
from typing import Optional

from async_crawler import crawl_single_async, crawl_website_async
from utils import URLValidator, OutputPathGenerator
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ContentProcessor:
    """简洁的内容处理器，支持HTML内容提取和处理"""
    
    def __init__(self):
        self.soup = None
    
    def process_html_content(self, html_content: str) -> dict:
        """处理HTML内容，提取有用信息"""
        try:
            self.soup = BeautifulSoup(html_content, 'html.parser')
            
            return {
                "title": self._extract_title(),
                "main_content": self._extract_main_content(),
                "api_docs": self._extract_api_docs(),
                "navigation": self._extract_navigation(),
                "contact_info": self._extract_contact_info(),
                "statistics": self._extract_statistics(),
                "cleaned_content": self._clean_content()
            }
        except Exception as e:
            return {"error": f"处理HTML内容失败: {e}"}
    
    def _extract_title(self) -> str:
        """提取标题"""
        if not self.soup:
            return "无标题"
        title_tag = self.soup.find('title')
        return title_tag.get_text().strip() if title_tag else "无标题"
    
    def _extract_main_content(self) -> str:
        """提取主要内容"""
        if not self.soup:
            return ""
        
        # 查找主要内容容器
        containers = self.soup.find_all(['div', 'section', 'main', 'article'], 
                                      class_=lambda x: x and any(keyword in x.lower() 
                                      for keyword in ['content', 'main', 'container', 'wrapper']))
        
        content_elements = []
        for container in containers:
            text = container.get_text(strip=True)
            if len(text) > 100:
                content_elements.append(text)
        
        # 如果没有找到容器，从body提取
        if not content_elements:
            body = self.soup.find('body')
            if body:
                content_elements.append(body.get_text(strip=True))
        
        return "\n\n".join(content_elements[:5])
    
    def _extract_api_docs(self) -> list:
        """提取API文档相关信息"""
        if not self.soup:
            return []
        
        api_info = []
        api_elements = self.soup.find_all(string=re.compile(r'API|文档|接口', re.I))
        
        for element in api_elements:
            parent = element.parent
            if parent:
                text = parent.get_text(strip=True)
                if 10 < len(text) < 500:
                    api_info.append(text)
        
        return list(set(api_info))
    
    def _extract_navigation(self) -> list:
        """提取导航信息"""
        if not self.soup:
            return []
        
        nav_items = []
        for link in self.soup.find_all('a', href=True):
            text = link.get_text(strip=True)
            href = link.get('href')
            
            if text and 1 < len(text) < 50:
                nav_items.append({"text": text, "href": href})
        
        return nav_items
    
    def _extract_contact_info(self) -> dict:
        """提取联系信息"""
        if not self.soup:
            return {}
        
        contact = {}
        
        # 提取邮箱
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, self.soup.get_text())
        if emails:
            contact['emails'] = list(set(emails))
        
        # 提取GitHub链接
        github_links = self.soup.find_all('a', href=re.compile(r'github\.com', re.I))
        if github_links:
            contact['github'] = [link.get('href') for link in github_links]
        
        return contact
    
    def _extract_statistics(self) -> dict:
        """提取统计信息"""
        if not self.soup:
            return {}
        
        stats = {}
        number_pattern = r'(\d+(?:\.\d+)?\s*(?:k|K|m|M|b|B|万|亿)?)'
        numbers = re.findall(number_pattern, self.soup.get_text())
        
        if numbers:
            stats['numbers'] = numbers
        
        return stats
    
    def _clean_content(self) -> str:
        """清理和格式化内容"""
        if not self.soup:
            return ""
        
        # 移除脚本和样式
        for script in self.soup(["script", "style"]):
            script.decompose()
        
        # 清理文本
        text = self.soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # 移除过短和重复的行
        cleaned_lines = []
        for line in text.split('\n'):
            line = line.strip()
            if len(line) > 10 and line not in cleaned_lines:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)


class EnhancedSPACrawler:
    """简洁的增强SPA爬虫"""
    
    def __init__(self):
        self.crawler = None
    
    async def __aenter__(self):
        self.crawler = AsyncWebCrawler(verbose=True)
        await self.crawler.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.crawler:
            await self.crawler.__aexit__(exc_type, exc_val, exc_tb)
    
    async def crawl(self, url: str, output_dir: Optional[str] = None) -> dict:
        """爬取SPA页面"""
        logger.info("使用增强SPA模式爬取...")
        
        config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(
                options={
                    "citations": False,
                    "body_width": None,
                    "ignore_links": False,
                    "include_raw_html": True,
                    "escape_html": False
                }
            ),
            page_timeout=120000,
            delay_before_return_html=15.0,
            js_code="""
            console.log('开始增强SPA爬取...');
            
            // 等待页面加载
            await new Promise(resolve => setTimeout(resolve, 5000));
            
            // 模拟用户交互
            const simulateUserInteraction = async () => {
                // 模拟鼠标移动
                for (let i = 0; i < 10; i++) {
                    const x = Math.random() * window.innerWidth;
                    const y = Math.random() * window.innerHeight;
                    const event = new MouseEvent('mousemove', {
                        view: window,
                        bubbles: true,
                        cancelable: true,
                        clientX: x,
                        clientY: y
                    });
                    document.dispatchEvent(event);
                    await new Promise(resolve => setTimeout(resolve, 100));
                }
                
                // 模拟滚动
                window.scrollTo(0, 300);
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                window.scrollTo(0, 600);
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                // 查找并点击交互元素
                const keywords = ['API', '文档', '申请', '立即申请', '限流', '策略'];
                const allElements = document.querySelectorAll('*');
                
                for (const keyword of keywords) {
                    for (const el of allElements) {
                        if (el.textContent && el.textContent.includes(keyword)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                try {
                                    el.dispatchEvent(new MouseEvent('mouseenter', {
                                        view: window,
                                        bubbles: true,
                                        cancelable: true
                                    }));
                                    await new Promise(resolve => setTimeout(resolve, 300));
                                    
                                    el.click();
                                    console.log('点击了:', keyword);
                                    await new Promise(resolve => setTimeout(resolve, 3000));
                                    break;
                                } catch (e) {
                                    console.log('点击失败:', e);
                                }
                            }
                        }
                    }
                }
                
                // 最终滚动
                window.scrollTo(0, document.body.scrollHeight);
                await new Promise(resolve => setTimeout(resolve, 2000));
                window.scrollTo(0, 0);
                await new Promise(resolve => setTimeout(resolve, 1000));
            };
            
            await simulateUserInteraction();
            await new Promise(resolve => setTimeout(resolve, 5000));
            console.log('SPA爬取完成');
            """
        )
        
        result = await self.crawler.arun(url=url, config=config)
        
        if result.success:
            # 选择最佳内容
            content_options = [
                result.markdown.raw_markdown,
                result.markdown.fit_markdown,
                str(result.markdown),
                result.html if hasattr(result, 'html') else None
            ]
            
            best_content = max((c for c in content_options if c), key=len)
            
            if best_content:
                return await self._save_result({
                    "success": True,
                    "content": best_content,
                    "content_length": len(best_content),
                    "title": result.metadata.get('title', 'Untitled'),
                    "url": url,
                    "strategy": "enhanced_spa",
                    "metadata": result.metadata
                }, output_dir)
        
        return {"success": False, "error": "增强SPA爬取失败"}
    
    async def _save_result(self, result: dict, output_dir: Optional[str] = None) -> dict:
        """保存结果"""
        if output_dir is None:
            output_path = Path("output") / "enhanced_spa"
        else:
            output_path = Path(output_dir)
        
        output_path.mkdir(parents=True, exist_ok=True)
        filename = OutputPathGenerator.generate_filename(result["url"])
        file_path = output_path / filename
        
        # 处理内容
        processor = ContentProcessor()
        is_html = result["content"].startswith('<!DOCTYPE') or result["content"].startswith('<html')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# {result['title']}\n\n")
            f.write(f"**URL:** {result['url']}\n\n")
            f.write(f"**策略:** {result['strategy']}\n\n")
            f.write(f"**爬取时间:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**内容长度:** {result['content_length']:,} 字符\n\n")
            f.write("---\n\n")
            
            if is_html:
                processed_data = processor.process_html_content(result["content"])
                
                if processed_data.get('main_content'):
                    f.write("## 主要内容\n\n")
                    f.write(processed_data['main_content'])
                    f.write("\n\n")
                
                if processed_data.get('api_docs'):
                    f.write("## API文档信息\n\n")
                    for i, doc in enumerate(processed_data['api_docs'], 1):
                        f.write(f"{i}. {doc}\n")
                    f.write("\n\n")
                
                if processed_data.get('contact_info'):
                    f.write("## 联系信息\n\n")
                    for key, value in processed_data['contact_info'].items():
                        f.write(f"**{key}:** {value}\n")
                    f.write("\n\n")
                
                if processed_data.get('cleaned_content'):
                    f.write("## 清理后的内容\n\n")
                    f.write(processed_data['cleaned_content'][:3000])
                    f.write("\n\n...")
            else:
                f.write(result['content'])
        
        result['filename'] = filename
        result['output_path'] = str(file_path)
        return result


async def crawl_single_page(url: str, output_dir: Optional[str] = None, enhanced: bool = False):
    """爬取单个网页。"""
    logger.info(f"正在爬取单个页面: {url}")
    
    if enhanced:
        async with EnhancedSPACrawler() as crawler:
            result = await crawler.crawl(url, output_dir)
    else:
        result = await crawl_single_async(url, output_dir)
    
    if result["success"]:
        logger.info(f"成功: {result.get('title', 'N/A')}")
        logger.info(f"内容: {result['content_length']:,} 字符")
        if result.get('strategy'):
            logger.info(f"策略: {result['strategy']}")
        logger.info(f"保存至: {result.get('output_path', result.get('filepath', 'N/A'))}")
    else:
        logger.error(f"失败: {result.get('error', '未知错误')}")
        sys.exit(1)


async def crawl_website(url: str, output_dir: Optional[str] = None, 
                       max_depth: int = 2, max_pages: int = 10, 
                       max_concurrent: int = 3):
    """递归爬取整个网站。"""
    logger.info(f"正在爬取网站: {url}")
    logger.info(f"设置: 深度={max_depth}, 页面数={max_pages}, 并发={max_concurrent}")
    
    stats = await crawl_website_async(
        url, output_dir, max_concurrent, max_depth, max_pages
    )
    
    logger.info(f"完成: {stats['successful_pages']} 个页面, {stats['success_rate']} 成功率")
    logger.info(f"内容: {stats['total_content_length']:,} 字符, {stats['total_links']:,} 个链接")
    logger.info(f"耗时: {stats['total_duration']:.1f}秒")
    logger.info(f"输出: {stats['output_directory']}")


def create_parser():
    """创建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="Crawl4AI - 增强网页内容提取工具，支持SPA网站爬取",
        epilog="""使用示例:
  %(prog)s single https://example.com
  %(prog)s single https://example.com -e
  %(prog)s website https://example.com -d 2 -p 10
  %(prog)s single https://spa-example.com -e -o my_output""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-q', '--quiet', action='store_true', help='静默模式')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细输出')

    subparsers = parser.add_subparsers(dest='command', required=True, help='爬取模式')

    # 单页模式
    single = subparsers.add_parser('single', help='爬取单个网页')
    single.add_argument('url', help='目标网页 URL')
    single.add_argument('-o', help='输出目录')
    single.add_argument('-e', action='store_true', help='增强SPA模式')

    # 整站模式
    website = subparsers.add_parser('website', help='递归爬取整个网站')
    website.add_argument('url', help='起始 URL')
    website.add_argument('-o', help='输出目录')
    website.add_argument('-d', type=int, default=2, help='最大爬取深度（默认：2）')
    website.add_argument('-p', type=int, default=10, help='最大页面数（默认：10）')
    website.add_argument('-c', type=int, default=3, help='并发请求数（默认：3）')

    return parser


def main():
    """主入口函数。"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Configure logging level
    if args.quiet:
        logger.setLevel(logging.CRITICAL)
    elif args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # Validate URL
    if not URLValidator.is_valid_url(args.url):
        logger.error(f"无效的 URL: {args.url}")
        return
    
    normalized_url = URLValidator.normalize_url(args.url)
    
    try:
        if args.command == 'single':
            enhanced_mode = getattr(args, 'enhanced', False)
            asyncio.run(crawl_single_page(normalized_url, args.output, enhanced_mode))
        elif args.command == 'website':
            asyncio.run(crawl_website(
                normalized_url, 
                args.output,
                args.depth,
                args.pages,
                args.concurrent
            ))
    except KeyboardInterrupt:
        logger.info("用户中断操作")
    except Exception as e:
        logger.error(f"发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
