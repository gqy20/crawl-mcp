"""搜索模块 - 基于 ddgs"""

import base64
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

from ddgs import DDGS
from openai import OpenAI

from .llm_config import get_default_llm_config


class Searcher:
    """搜索类 - 提供网页搜索功能"""

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
            results = list(DDGS().text(query, max_results=max_results))
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
            results = list(DDGS().news(query, max_results=max_results))
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
    ) -> Dict[str, Any]:
        """
        图片搜索 + 下载 + 分析（一站式）

        Args:
            query: 搜索关键词
            region: 区域代码 (wt-wt/us-en/cn-zh等)
            max_results: 搜索结果数量
            size: 图片尺寸 (Small/Medium/Large/Wallpaper)
            color: 颜色过滤 (如 "Red", "Monochrome")
            type_image: 类型 (photo/clipart/gif/transparent/line)
            layout: 布局 (Square/Tall/Wide)
            download: 是否下载到本地
            download_count: 下载数量（默认全部）
            output_dir: 下载目录
            analyze: 是否使用图片模型分析
            analysis_prompt: 分析提示词

        Returns:
            {
                "success": True,
                "query": "...",
                "search_results": {"count": N, "results": [...]},
                "download_results": {...},      # 仅当 download=True 时
                "analysis_results": {...}       # 仅当 analyze=True 时
            }
        """
        # ========== 1. 搜索图片 ==========
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

        # 如果没有搜索结果，直接返回
        if not images:
            return result

        # ========== 2. 下载图片 ==========
        if download:
            images_to_download = images[:download_count] if download_count else images
            download_result = self._download_images(images_to_download, output_dir)
            result["download_results"] = download_result

        # ========== 3. 分析图片 ==========
        if analyze:
            # 如果下载了，分析本地文件；否则分析 URL
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

            analysis_result = self._analyze_images(images_to_analyze, analysis_prompt)
            result["analysis_results"] = analysis_result

        return result

    def _download_images(self, images: List[Dict], output_dir: str) -> Dict[str, Any]:
        """下载图片到本地"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = []
        downloaded = 0
        failed = 0

        for i, img in enumerate(images):
            url = img.get("image") or img.get("url")
            if not url:
                continue

            try:
                # 生成文件名
                ext = self._get_extension(url)
                filename = f"img_{i + 1:03d}{ext}"
                filepath = output_path / filename

                # 下载
                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()

                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                results.append(
                    {
                        "success": True,
                        "url": url,
                        "filepath": str(filepath),
                        "size": filepath.stat().st_size,
                    }
                )
                downloaded += 1

            except Exception as e:
                results.append({"success": False, "url": url, "error": str(e)})
                failed += 1

        return {
            "total": len(images),
            "downloaded": downloaded,
            "failed": failed,
            "results": results,
            "output_dir": str(output_path),
        }

    def _analyze_images(
        self, images: List[Dict[str, str]], prompt: str
    ) -> Dict[str, Any]:
        """调用图片分析模型"""
        results = []

        try:
            config = get_default_llm_config()
            # 使用 vision_model 或默认模型
            model = config.vision_model or "glm-4.6v"
            client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        except Exception as e:
            return {
                "count": len(images),
                "error": f"LLM 配置错误: {e}",
                "results": [],
            }

        for img in images:
            try:
                content = [{"type": "text", "text": prompt}]

                if img["type"] == "url":
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": img["path"]},
                        }
                    )
                else:
                    # 本地文件需要转 base64
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

                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                )

                results.append(
                    {
                        "image": img["path"],
                        "type": img["type"],
                        "analysis": response.choices[0].message.content,
                    }
                )

            except Exception as e:
                results.append(
                    {"image": img["path"], "type": img["type"], "error": str(e)}
                )

        return {"count": len(images), "results": results}

    @staticmethod
    def _get_extension(url: str) -> str:
        """从 URL 获取文件扩展名"""
        path = urlparse(url).path
        ext = Path(path).suffix.lower()
        if not ext or len(ext) > 5:
            return ".jpg"
        return ext
