"""搜索模块 - 基于 ddgs"""

import asyncio
import base64
import concurrent.futures
import requests
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List
from urllib.parse import urlparse

from ddgs import DDGS
from openai import AsyncOpenAI

from .llm_config import get_default_llm_config
from .utils import run_async


class Searcher:
    """搜索类 - 提供网页搜索功能"""

    def _search_wrapper(
        self, search_fn: Callable, query: str, **kwargs
    ) -> Dict[str, Any]:
        """通用搜索包装器，消除 search_text/search_news 的重复逻辑"""
        try:
            ddgs = DDGS()
            results = list(search_fn(ddgs, query=query, **kwargs))
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

    def search_text(
        self,
        query: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """文本搜索"""
        return self._search_wrapper(
            lambda ddgs, **kw: ddgs.text(**kw), query, max_results=max_results
        )

    def search_news(
        self,
        query: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """新闻搜索"""
        return self._search_wrapper(
            lambda ddgs, **kw: ddgs.news(**kw), query, max_results=max_results
        )

    def extract_url(self, url: str, fmt: str = "text_markdown") -> Dict[str, Any]:
        """轻量级 URL 内容提取（基于 ddgs.extract，无需浏览器）

        适用于静态页面、文章、博客等不需要 JS 渲染的场景。
        速度比 crawl_single 快 5-10 倍（~1s vs ~8s）。

        Args:
            url: 要提取的网页 URL
            fmt: 输出格式 (text_markdown / text_plain / text_rich / text / content)
        """
        try:
            result = DDGS().extract(url, fmt=fmt)
            return {
                "success": True,
                "url": result.get("url", url),
                "content": result.get("content", ""),
                "fmt": fmt,
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "error": str(e),
            }

    def search_books(
        self,
        query: str,
        region: str = "wt-wt",
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """图书搜索"""
        return self._search_wrapper(
            lambda ddgs, **kw: ddgs.books(**kw), query, max_results=max_results
        )

    def search_videos(
        self,
        query: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """视频搜索"""
        return self._search_wrapper(
            lambda ddgs, **kw: ddgs.videos(**kw), query, max_results=max_results
        )

    def search_images(
        self,
        query: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: int = 10,
        size: Optional[str] = None,
        color: Optional[str] = None,
        type_image: Optional[str] = None,
        layout: Optional[str] = None,
        download: bool = False,
        download_count: Optional[int] = None,
        output_dir: str = "./downloads/images",
        analyze: bool = False,
        analysis_prompt: str = "详细描述这张图片的内容",
        analyze_concurrent: int = 3,
    ) -> Dict[str, Any]:
        """图片搜索 + 下载 + 分析（一站式）"""
        try:
            images = list(
                DDGS().images(
                    query=query,
                    region=region,
                    safesearch=safesearch,
                    max_results=max_results,
                    size=size,
                    color=color,
                    type_image=type_image,
                    layout=layout,
                )
            )
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": f"搜索失败: {e}",
            }

        result = {
            "success": True,
            "query": query,
            "search_results": {"count": len(images), "results": images},
        }

        if not images:
            return result

        # 下载图片
        if download:
            images_to_download = images[:download_count] if download_count else images
            result["download_results"] = self._download_images(
                images_to_download, output_dir
            )

        # 分析图片
        if analyze:
            images_to_analyze = []
            if download and result.get("download_results", {}).get("results"):
                for r in result["download_results"]["results"]:
                    if r["success"]:
                        images_to_analyze.append(
                            {"path": r["filepath"], "type": "local"}
                        )
            else:
                for img in images[:download_count] if download_count else images:
                    images_to_analyze.append({"path": img.get("image"), "type": "url"})

            result["analysis_results"] = run_async(
                self._analyze_images_async(
                    images_to_analyze,
                    analysis_prompt,
                    max_concurrent=analyze_concurrent,
                )
            )

        return result

    def _download_images(
        self, images: List[Dict], output_dir: str, max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """并行下载图片到本地"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        def download_one(idx_img):
            i, img = idx_img
            url = img.get("image") or img.get("url")
            if not url:
                return {"success": False, "url": "", "error": "No URL", "__index__": i}

            try:
                ext = self._get_extension(url)
                filename = f"img_{i + 1:03d}{ext}"
                filepath = output_path / filename

                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()

                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                return {
                    "success": True,
                    "url": url,
                    "filepath": str(filepath),
                    "size": filepath.stat().st_size,
                    "__index__": i,
                }
            except Exception as e:
                return {"success": False, "url": url, "error": str(e), "__index__": i}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrent
        ) as executor:
            futures = [
                executor.submit(download_one, (i, img)) for i, img in enumerate(images)
            ]
            results = [f.result() for f in futures]

        # 按 __index__ 排序回原顺序
        results.sort(key=lambda x: x.pop("__index__"))

        downloaded = sum(1 for r in results if r["success"])
        return {
            "total": len(images),
            "downloaded": downloaded,
            "failed": len(images) - downloaded,
            "results": results,
            "output_dir": str(output_path),
        }

    async def _analyze_images_async(
        self, images: List[Dict[str, str]], prompt: str, max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """并行调用图片分析模型"""
        try:
            config = get_default_llm_config()
            model = config.vision_model or "glm-4.6v"
            client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
        except Exception as e:
            return {"count": len(images), "error": f"LLM 配置错误: {e}", "results": []}

        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_single(img: Dict[str, str]) -> Dict[str, Any]:
            async with semaphore:
                content = [{"type": "text", "text": prompt}]

                if img["type"] == "url":
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": img["path"]},
                        }
                    )
                else:
                    with open(img["path"], "rb") as f:
                        base64_image = base64.b64encode(f.read()).decode("utf-8")
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        }
                    )

                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": content}],
                    )
                    return {
                        "image": img["path"],
                        "type": img["type"],
                        "analysis": response.choices[0].message.content,
                    }
                except Exception as e:
                    return {"image": img["path"], "type": img["type"], "error": str(e)}

        tasks = [analyze_single(img) for img in images]
        results = await asyncio.gather(*tasks)
        return {"count": len(images), "results": list(results)}

    def _analyze_images(
        self, images: List[Dict[str, str]], prompt: str
    ) -> Dict[str, Any]:
        """调用图片分析模型（同步包装器）"""
        return run_async(self._analyze_images_async(images, prompt))

    @staticmethod
    def _get_extension(url: str) -> str:
        """从 URL 获取文件扩展名"""
        path = urlparse(url).path
        ext = Path(path).suffix.lower()
        if not ext or len(ext) > 5:
            return ".jpg"
        return ext
