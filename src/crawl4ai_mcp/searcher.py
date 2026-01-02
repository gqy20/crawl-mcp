"""搜索模块 - 基于 duckduckgo-search"""

from typing import Dict, Any, Optional
from duckduckgo_search import DDGS


class Searcher:
    """搜索类 - 提供网页搜索功能"""

    def __init__(
        self,
        proxy: Optional[str] = None,
        timeout: int = 10,
    ):
        """
        初始化搜索器

        Args:
            proxy: 代理地址，支持 http/https/socks5
            timeout: 请求超时时间（秒）
        """
        self.ddgs = DDGS(proxy=proxy, timeout=timeout)

    def search_text(
        self,
        query: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        文本搜索 - 搜索通用网页内容

        适用于：技术文档、百科、博客、论坛、教程等

        Args:
            query: 搜索关键词
            region: 区域代码 (wt-wt/us-en/cn-zh/jp-jp等)
            safesearch: 安全搜索级别 (on/moderate/off)
            timelimit: 时间限制 (d=天/w/周/m/月/y=年)
            max_results: 最大结果数

        Returns:
            {"success": True/False, "query": "...", "count": N, "results": [...]}
        """
        try:
            results = list(
                self.ddgs.text(
                    query=query,
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    max_results=max_results,
                )
            )
            return {
                "success": True,
                "query": query,
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "results": [],
            }

    def search_news(
        self,
        query: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        新闻搜索 - 搜索新闻内容

        适用于：突发新闻、时事、财经、体育等时效性内容

        Args:
            query: 搜索关键词
            region: 区域代码 (同 search_text)
            safesearch: 安全搜索级别 (同 search_text)
            timelimit: 时间限制 (d=天/w/周/m/月)
            max_results: 最大结果数

        Returns:
            {"success": True/False, "query": "...", "count": N, "results": [...]}
        """
        try:
            results = list(
                self.ddgs.news(
                    keywords=query,
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    max_results=max_results,
                )
            )
            return {
                "success": True,
                "query": query,
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "results": [],
            }
