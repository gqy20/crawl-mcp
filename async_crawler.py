#!/usr/bin/env python3
"""Async parallel web crawler for efficient content extraction."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from urllib.parse import urljoin, urlparse

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from utils import OutputPathGenerator, URLValidator, create_output_directory

logger = logging.getLogger(__name__)


@dataclass
class CrawlTask:
    """爬取任务数据类"""
    url: str
    depth: int
    parent_url: Optional[str] = None
    
    def __hash__(self):
        return hash(self.url)
    
    def __eq__(self, other):
        return isinstance(other, CrawlTask) and self.url == other.url


@dataclass
class CrawlResult:
    """爬取结果数据类"""
    url: str
    title: str
    content_length: int
    links_count: int
    success: bool
    error: Optional[str] = None
    depth: int = 0
    filename: Optional[str] = None


class AsyncParallelCrawler:
    """异步并行爬取器"""
    
    def __init__(self, 
                 max_concurrent: int = 5,
                 max_depth: int = 2,
                 max_pages: int = 50,
                 delay: float = 1.0,
                 timeout: int = 30):
        """
        初始化异步并行爬取器
        
        Args:
            max_concurrent: 最大并发数
            max_depth: 最大爬取深度
            max_pages: 最大页面数量
            delay: 请求间隔
            timeout: 请求超时时间
        """
        self.max_concurrent = max_concurrent
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        
        # 状态管理
        self.visited_urls: Set[str] = set()
        self.pending_tasks: Set[CrawlTask] = set()
        self.completed_results: List[CrawlResult] = []
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.checkpoint_file: Optional[str] = None
        
        # 统计信息
        self.start_time = 0
        self.total_processed = 0
        
    def _normalize_url(self, url: str) -> str:
        """标准化URL"""
        return URLValidator.normalize_url(url)
    
    def _is_same_domain(self, url1: str, url2: str) -> bool:
        """检查是否为同一域名"""
        domain1 = urlparse(url1).netloc.lower()
        domain2 = urlparse(url2).netloc.lower()
        return domain1 == domain2
    
    def _should_crawl_url(self, url: str, base_url: str, 
                         include_patterns: Optional[List[str]] = None,
                         exclude_patterns: Optional[List[str]] = None) -> bool:
        """判断是否应该爬取该URL"""
        # 基本检查
        if not URLValidator.is_valid_url(url):
            return False
        
        if not self._is_same_domain(url, base_url):
            return False
        
        # 排除模式检查
        if exclude_patterns:
            for pattern in exclude_patterns:
                if pattern in url:
                    return False
        
        # 包含模式检查
        if include_patterns:
            return any(pattern in url for pattern in include_patterns)
        
        return True
    
    async def _extract_links(self, content: str, base_url: str) -> List[str]:
        """从内容中提取链接"""
        links = []
        try:
            import re
            # 使用正则表达式提取链接
            link_pattern = r'href=["\']([^"\']+)["\']'
            matches = re.findall(link_pattern, content)
            
            for match in matches:
                # 转换为绝对URL
                absolute_url = urljoin(base_url, match)
                # 只保留同域名的链接
                if self._is_same_domain(absolute_url, base_url):
                    normalized_url = self._normalize_url(absolute_url)
                    if normalized_url not in links:
                        links.append(normalized_url)
        except Exception as e:
            logger.debug(f"Link extraction error: {e}")
        return links
    
    async def _crawl_single_page(self, task: CrawlTask, output_dir: Path) -> Tuple[CrawlResult, List[str]]:
        """爬取单个页面"""
        async with self.semaphore:
            try:
                # 创建爬取器配置
                # 禁用内容过滤器，获取原始内容
                markdown_generator = DefaultMarkdownGenerator(
                    options={
                        "citations": False,
                        "body_width": None,
                        "ignore_links": False,
                        "include_raw_html": False,
                        "escape_html": True,
                        "only_text": False
                    }
                )
                
                config = CrawlerRunConfig(
                    markdown_generator=markdown_generator,
                    page_timeout=60000,
                    delay_before_return_html=5.0,
                    js_code="""
                    // 等待React应用加载完成
                    await new Promise(resolve => setTimeout(resolve, 5000));
                    
                    // 等待API文档内容加载
                    const waitForDocs = () => {
                        return new Promise((resolve) => {
                            const checkDocs = () => {
                                // 检查是否有API文档相关内容
                                const hasDocs = document.body.innerText.includes('API') || 
                                              document.body.innerText.includes('文档') ||
                                              document.body.innerText.includes('限流');
                                if (hasDocs) {
                                    resolve();
                                } else {
                                    setTimeout(checkDocs, 1000);
                                }
                            };
                            checkDocs();
                        });
                    };
                    
                    await waitForDocs();
                    
                    // 尝试点击API文档标签
                    const apiTabs = document.querySelectorAll('*');
                    for (let el of apiTabs) {
                        if (el.textContent && el.textContent.includes('API') && el.textContent.includes('文档')) {
                            el.click();
                            await new Promise(resolve => setTimeout(resolve, 2000));
                            break;
                        }
                    }
                    
                    // 滚动到页面底部以触发懒加载
                    window.scrollTo(0, document.body.scrollHeight);
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    
                    // 滚动回顶部
                    window.scrollTo(0, 0);
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    """
                )
                
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await crawler.arun(url=task.url, config=config)
                    
                    if result.success:
                        # 优先使用raw_markdown，其次使用fit_markdown
                        content = (result.markdown.raw_markdown or 
                                 result.markdown.fit_markdown or 
                                 str(result.markdown))
                        
                        # 生成文件名
                        filename = OutputPathGenerator.generate_filename(task.url)
                        file_path = output_dir / filename
                        
                        # 保存内容
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(f"# {result.metadata.get('title', 'Untitled')}\n\n")
                            f.write(f"**URL:** {task.url}\n\n")
                            f.write(f"**爬取深度:** {task.depth}\n\n")
                            f.write(f"**爬取时间:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                            f.write("---\n\n")
                            f.write(content)
                            
                            # 添加参考链接
                            if hasattr(result.markdown, 'references_markdown'):
                                f.write("\n\n## 参考链接\n\n")
                                f.write(result.markdown.references_markdown)
                        
                        # 提取内部链接 - 使用Crawl4AI提供的链接信息
                        internal_links = []
                        if hasattr(result, 'links') and result.links:
                            # 优先使用Crawl4AI提供的内部链接
                            internal_links_raw = result.links.get('internal', [])
                            
                            # 确保链接是字符串格式
                            for link in internal_links_raw:
                                if isinstance(link, str):
                                    internal_links.append(link)
                                elif isinstance(link, dict) and 'href' in link:
                                    internal_links.append(link['href'])
                            
                            # 如果没有内部链接，尝试从所有链接中筛选
                            if not internal_links:
                                all_links_raw = result.links.get('all', [])
                                for link in all_links_raw:
                                    link_url = link if isinstance(link, str) else link.get('href', '') if isinstance(link, dict) else ''
                                    if link_url and self._is_same_domain(link_url, task.url):
                                        internal_links.append(link_url)
                        
                        # 如果仍然没有链接，使用我们的备用提取方法
                        if not internal_links and hasattr(result, 'html'):
                            internal_links = await self._extract_links(result.html, task.url)
                        
                        logger.debug(f"Found {len(internal_links)} internal links on {task.url}")
                        
                        crawl_result = CrawlResult(
                            url=task.url,
                            title=result.metadata.get('title', 'Untitled'),
                            content_length=len(content),
                            links_count=len(result.links.get('internal', [])),
                            success=True,
                            depth=task.depth,
                            filename=filename
                        )
                        
                        return crawl_result, internal_links
                    else:
                        crawl_result = CrawlResult(
                            url=task.url,
                            title="",
                            content_length=0,
                            links_count=0,
                            success=False,
                            error=result.error_message,
                            depth=task.depth
                        )
                        return crawl_result, []
                        
            except Exception as e:
                crawl_result = CrawlResult(
                    url=task.url,
                    title="",
                    content_length=0,
                    links_count=0,
                    success=False,
                    error=str(e),
                    depth=task.depth
                )
                return crawl_result, []
            finally:
                # 添加延迟
                if self.delay > 0:
                    await asyncio.sleep(self.delay)
    
    async def crawl_single_page(self, url: str, output_dir: Optional[str] = None) -> Dict:
        """
        爬取单个页面
        
        Args:
            url: 目标URL
            output_dir: 输出目录
            
        Returns:
            爬取结果
        """
        url = self._normalize_url(url)
        
        # 创建输出目录
        if output_dir is None:
            output_path = create_output_directory(url, "single")
        else:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        
        task = CrawlTask(url=url, depth=0)
        result, _ = await self._crawl_single_page(task, output_path)
        
        return {
            "success": result.success,
            "url": result.url,
            "title": result.title,
            "content_length": result.content_length,
            "links_count": result.links_count,
            "filename": result.filename,
            "output_dir": str(output_path),
            "error": result.error
        }
    
    async def crawl_website_parallel(self, 
                                   start_url: str,
                                   output_dir: Optional[str] = None,
                                   include_patterns: Optional[List[str]] = None,
                                   exclude_patterns: Optional[List[str]] = None) -> Dict:
        """
        并行爬取整个网站
        
        Args:
            start_url: 起始URL
            output_dir: 输出目录
            include_patterns: 包含模式
            exclude_patterns: 排除模式
            
        Returns:
            爬取统计结果
        """
        try:
            self.start_time = time.time()
            start_url = self._normalize_url(start_url)
            
            # 创建输出目录
            if output_dir is None:
                output_path = create_output_directory(start_url, "website")
            else:
                output_path = Path(output_dir)
                output_path.mkdir(parents=True, exist_ok=True)
            
            # 设置检查点文件
            self.checkpoint_file = str(output_path / "crawl_checkpoint.json")
            
            # 尝试加载检查点
            checkpoint_loaded = await self._load_checkpoint(output_path)
            
            if not checkpoint_loaded:
                # 初始化任务队列
                initial_task = CrawlTask(url=start_url, depth=0)
                self.pending_tasks.add(initial_task)
                logger.info("开始新的爬取任务")
            else:
                logger.info("从检查点恢复爬取任务")
            
            # 并行处理任务
            while self.pending_tasks and len(self.completed_results) < self.max_pages:
                # 获取当前批次的任务
                current_batch = list(self.pending_tasks)[:self.max_concurrent]
                self.pending_tasks -= set(current_batch)
                
                # 并行执行当前批次
                tasks = [
                    self._crawl_single_page(task, output_path) 
                    for task in current_batch
                ]
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 处理结果
                for task, result_tuple in zip(current_batch, batch_results):
                    if isinstance(result_tuple, Exception):
                        result = CrawlResult(
                            url=task.url,
                            title="",
                            content_length=0,
                            links_count=0,
                            success=False,
                            error=str(result_tuple),
                            depth=task.depth
                        )
                        links = []
                    else:
                        result, links = result_tuple
                    
                    self.completed_results.append(result)
                    self.visited_urls.add(task.url)
                    
                    # 如果成功且深度未达到最大值，添加新任务
                    if (result.success and 
                        task.depth < self.max_depth and 
                        len(self.completed_results) < self.max_pages):
                        
                        # 处理提取的链接
                        for link in links:
                            should_crawl = self._should_crawl_url(link, start_url, include_patterns, exclude_patterns)
                            is_visited = link in self.visited_urls
                            file_exists = self._is_file_exists(link, output_path)
                            within_limit = len(self.completed_results) + len(self.pending_tasks) < self.max_pages
                            
                            logger.debug(f"Checking link {link}: crawl={should_crawl}, visited={is_visited}, file_exists={file_exists}, limit={within_limit}")
                            
                            # 如果文件已存在，跳过爬取但添加到已访问集合
                            if file_exists:
                                self.visited_urls.add(link)
                                logger.debug(f"Skipping {link} - file already exists")
                                continue
                            
                            if (should_crawl and not is_visited and within_limit):
                                new_task = CrawlTask(
                                    url=link,
                                    depth=task.depth + 1,
                                    parent_url=task.url
                                )
                                self.pending_tasks.add(new_task)
                                logger.debug(f"Added task: {link} (depth {task.depth + 1})")
            
            # 生成统计信息
            end_time = time.time()
            stats = self._generate_stats(start_url, end_time - self.start_time, output_path)
            
            # 保存索引文件
            await self._save_index(stats, output_path)
            
            return stats
            
        except Exception as e:
            # 返回错误信息
            return {
                "success": False,
                "error": str(e),
                "start_url": start_url,
                "total_pages": 0,
                "successful_pages": 0,
                "failed_pages": 0,
                "total_duration": 0.0,
                "pages": []
            }
    
    def _generate_stats(self, start_url: str, duration: float, output_path: Path) -> Dict:
        """生成统计信息"""
        successful_results = [r for r in self.completed_results if r.success]
        failed_results = [r for r in self.completed_results if not r.success]
        
        return {
            "success": True,
            "start_url": start_url,
            "crawl_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.start_time)),
            "duration": f"{duration:.2f}秒",
            "total_pages": len(self.completed_results),
            "successful_pages": len(successful_results),
            "failed_pages": len(failed_results),
            "success_rate": f"{len(successful_results)/len(self.completed_results)*100:.1f}%" if self.completed_results else "0%",
            "total_content_length": sum(r.content_length for r in successful_results),
            "total_links": sum(r.links_count for r in successful_results),
            "average_content_length": sum(r.content_length for r in successful_results) / len(successful_results) if successful_results else 0,
            "total_duration": duration,
            "output_directory": str(output_path),
            "pages": [asdict(result) for result in self.completed_results]
        }
    
    async def _save_index(self, stats: Dict, output_path: Path):
        """保存索引文件"""
        index_file = output_path / "crawl_index.json"
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        # 保存检查点文件
        if self.checkpoint_file:
            await self._save_checkpoint()
    
    async def _save_checkpoint(self):
        """保存检查点文件"""
        if not self.checkpoint_file:
            return
            
        checkpoint_data = {
            "timestamp": time.time(),
            "visited_urls": list(self.visited_urls),
            "pending_tasks": [{
                "url": task.url,
                "depth": task.depth,
                "parent_url": task.parent_url
            } for task in self.pending_tasks],
            "completed_results": [asdict(result) for result in self.completed_results],
            "stats": {
                "total_processed": self.total_processed,
                "start_time": self.start_time
            }
        }
        
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
            logger.info(f"检查点已保存: {self.checkpoint_file}")
        except Exception as e:
            logger.warning(f"保存检查点失败: {e}")
    
    async def _load_checkpoint(self, output_path: Path) -> bool:
        """加载检查点文件"""
        if not self.checkpoint_file or not Path(self.checkpoint_file).exists():
            return False
            
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            
            # 恢复状态
            self.visited_urls = set(checkpoint_data.get("visited_urls", []))
            self.pending_tasks = set()
            for task_data in checkpoint_data.get("pending_tasks", []):
                self.pending_tasks.add(CrawlTask(
                    url=task_data["url"],
                    depth=task_data["depth"],
                    parent_url=task_data.get("parent_url")
                ))
            
            # 恢复已完成的结果
            self.completed_results = []
            for result_data in checkpoint_data.get("completed_results", []):
                self.completed_results.append(CrawlResult(**result_data))
            
            # 恢复统计信息
            stats = checkpoint_data.get("stats", {})
            self.total_processed = stats.get("total_processed", 0)
            self.start_time = stats.get("start_time", time.time())
            
            logger.info(f"检查点已加载: {len(self.visited_urls)} 个已访问URL, {len(self.pending_tasks)} 个待处理任务")
            return True
            
        except Exception as e:
            logger.warning(f"加载检查点失败: {e}")
            return False
    
    def _get_existing_files(self, output_path: Path) -> Set[str]:
        """获取已存在的文件对应的URL集合"""
        existing_files = set()
        if not output_path.exists():
            return existing_files
            
        for file_path in output_path.glob("*.md"):
            # 从文件名还原URL（简化版本）
            filename = file_path.stem
            # 这里可以根据实际命名规则改进URL还原逻辑
            # 暂时使用文件名作为URL的标识
            existing_files.add(filename)
        
        return existing_files
    
    def _is_file_exists(self, url: str, output_path: Path) -> bool:
        """检查URL对应的文件是否已存在"""
        filename = OutputPathGenerator.generate_filename(url)
        file_path = output_path / filename
        return file_path.exists()


# 便捷函数
async def crawl_single_async(url: str, output_dir: Optional[str] = None) -> Dict:
    """异步爬取单个页面的便捷函数"""
    crawler = AsyncParallelCrawler()
    return await crawler.crawl_single_page(url, output_dir)


async def crawl_website_async(url: str, 
                            output_dir: Optional[str] = None,
                            max_concurrent: int = 5,
                            max_depth: int = 2,
                            max_pages: int = 50,
                            delay: float = 1.0,
                            include_patterns: Optional[List[str]] = None,
                            exclude_patterns: Optional[List[str]] = None) -> Dict:
    """异步爬取网站的便捷函数"""
    crawler = AsyncParallelCrawler(
        max_concurrent=max_concurrent,
        max_depth=max_depth,
        max_pages=max_pages,
        delay=delay
    )
    return await crawler.crawl_website_parallel(
        url, output_dir, include_patterns, exclude_patterns
    )