"""Crawler 类 - 核心爬虫逻辑"""

import asyncio
from typing import List, Dict, Any, Optional
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from openai import AsyncOpenAI
from .llm_config import get_llm_config, get_default_llm_config


def _run_async(coro):
    """
    运行异步函数的辅助函数，兼容已有事件循环的环境
    使用 nest_asyncio 允许嵌套事件循环
    """
    try:
        asyncio.get_running_loop()
        import nest_asyncio

        nest_asyncio.apply()
        return asyncio.get_event_loop().run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _calculate_success_rate(results: List[Dict[str, Any]]) -> str:
    """计算成功率"""
    if not results:
        return "0%"
    successful = sum(1 for r in results if r["success"])
    return f"{successful / len(results) * 100:.1f}%"


def _parse_llm_config(llm_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """解析 llm_config，兼容字符串和字典两种格式

    Args:
        llm_config: 可以是 Dict、JSON 字符串、或纯文本字符串

    Returns:
        解析后的字典，如果输入是纯文本则当作 instruction
    """
    if llm_config is None:
        return None

    # 如果已经是字典，直接返回
    if isinstance(llm_config, dict):
        return llm_config

    # 如果是字符串，尝试解析
    if isinstance(llm_config, str):
        import json

        try:
            # 尝试解析为 JSON 对象
            return json.loads(llm_config)
        except json.JSONDecodeError:
            # 解析失败，当作纯文本 instruction
            return {"instruction": llm_config}

    # 其他类型，尝试转换为字符串再处理
    return {"instruction": str(llm_config)}


class Crawler:
    """统一的爬虫类，整合单页、整站、批量爬取功能"""

    def _create_config(self, enhanced: bool = False) -> CrawlerRunConfig:
        """创建爬虫配置"""
        markdown_generator = DefaultMarkdownGenerator(
            options={
                "citations": False,
                "body_width": None,
                "ignore_links": False,
            }
        )
        return CrawlerRunConfig(
            markdown_generator=markdown_generator,
            page_timeout=60000,
            delay_before_return_html=5.0 if not enhanced else 15.0,
        )

    def _add_llm_strategy(
        self, config: CrawlerRunConfig, llm_config: Optional[Dict[str, Any]]
    ) -> CrawlerRunConfig:
        """
        为配置添加 LLM 提取策略

        Args:
            config: 基础爬虫配置
            llm_config: LLM 配置（可选），支持字典、JSON 字符串或纯文本

        Returns:
            添加了 LLM 策略的配置（原地修改或返回原配置）
        """
        # 兼容处理：解析字符串格式的配置
        llm_config = _parse_llm_config(llm_config)
        if not llm_config:
            return config

        from crawl4ai.extraction_strategy import LLMExtractionStrategy
        from crawl4ai import LLMConfig as Crawl4AILLMConfig

        llm = get_llm_config(llm_config)
        # crawl4ai 的 LLMConfig 使用 provider 参数，格式为 "openai/model-name"
        provider = f"openai/{llm.model}" if "/" not in llm.model else llm.model
        crawl4ai_llm_config = Crawl4AILLMConfig(
            provider=provider,
            api_token=llm.api_key,
            base_url=llm.base_url,
        )

        extraction_strategy = LLMExtractionStrategy(
            llm_config=crawl4ai_llm_config,
            instruction=llm.instruction or "Extract and summarize the main content",
            schema=llm.schema,
        )
        config.extraction_strategy = extraction_strategy
        return config

    async def _crawl(
        self,
        url: str,
        enhanced: bool = False,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        内部异步爬取方法

        Args:
            url: 目标 URL
            enhanced: 是否使用增强模式 (更长等待时间)
            llm_config: LLM 配置字典（可选）

        Returns:
            包含 success, markdown, title, (可选) llm_result 的字典
        """
        config = self._create_config(enhanced)
        config = self._add_llm_strategy(config, llm_config)

        # 重试机制：最多重试 3 次，只对网络错误重试
        max_retries = 3

        for attempt in range(max_retries + 1):  # +1 因为第一次不是重试
            try:
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await crawler.arun(url=url, config=config)

                    response = {
                        "success": result.success,
                        "markdown": result.markdown.raw_markdown
                        if result.success
                        else "",
                        "title": result.metadata.get("title", "")
                        if result.success
                        else "",
                        "error": result.error_message if not result.success else None,
                    }

                    # 如果使用了 LLM 提取，添加结果
                    if llm_config and result.success and result.extracted_content:
                        try:
                            import json

                            response["llm_result"] = json.loads(
                                result.extracted_content
                            )
                        except (json.JSONDecodeError, TypeError):
                            response["llm_result"] = {"raw": result.extracted_content}

                    return response

            except Exception as e:
                error_msg = str(e)

                # 只对 ERR_NETWORK_CHANGED 相关错误重试
                is_network_error = (
                    "ERR_NETWORK_CHANGED" in error_msg
                    or "ERR_INTERNET_DISCONNECTED" in error_msg
                    or "ERR_CONNECTION_RESET" in error_msg
                    or "ERR_TIMED_OUT" in error_msg
                )

                # 如果是网络错误且还有重试次数，等待后重试
                if is_network_error and attempt < max_retries:
                    await asyncio.sleep(2**attempt)  # 指数退避: 1s, 2s, 4s
                    continue

                # 其他错误或重试用尽，抛出异常
                raise

    def _call_llm(
        self, content: str, instruction: str, schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        调用 LLM 处理文本内容

        Args:
            content: 要处理的内容
            instruction: 处理指令
            schema: 可选的 JSON Schema

        Returns:
            处理结果字典
        """
        from openai import OpenAI
        from .llm_config import get_default_llm_config

        llm_cfg = get_default_llm_config()
        client = OpenAI(api_key=llm_cfg.api_key, base_url=llm_cfg.base_url)

        messages = [
            {"role": "system", "content": "你是一个专业的文本处理助手。"},
            {"role": "user", "content": f"指令：{instruction}\n\n内容：\n{content}"},
        ]

        if schema:
            messages[0]["content"] += f"\n\n请按照以下 JSON Schema 返回结果：{schema}"

        try:
            response = client.chat.completions.create(
                model=llm_cfg.model,
                messages=messages,
                temperature=0.3,
            )
            result_text = response.choices[0].message.content

            # 尝试解析为 JSON
            if schema:
                try:
                    import json

                    return {"success": True, "data": json.loads(result_text)}
                except json.JSONDecodeError:
                    return {"success": True, "content": result_text}
            else:
                return {"success": True, "summary": result_text}

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": content,  # 失败时返回原内容
            }

    async def _call_llm_batch(
        self,
        items: List[Dict[str, Any]],
        instruction: str,
        schema: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        并行调用 LLM 处理多个文本内容

        Args:
            items: 要处理的项目列表，每个项目需要包含 'markdown' 字段
            instruction: 处理指令
            schema: 可选的 JSON Schema
            max_concurrent: 最大并发数

        Returns:
            处理结果列表，每个结果包含 summary 或 error
        """
        llm_cfg = get_default_llm_config()
        client = AsyncOpenAI(api_key=llm_cfg.api_key, base_url=llm_cfg.base_url)

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_item(item: Dict[str, Any]) -> Dict[str, Any]:
            """处理单个项目"""
            async with semaphore:
                content = item.get("markdown", "")

                messages = [
                    {
                        "role": "system",
                        "content": "你是一个专业的文本处理助手。",
                    },
                    {
                        "role": "user",
                        "content": f"指令：{instruction}\n\n内容：\n{content}",
                    },
                ]

                if schema:
                    messages[0]["content"] += (
                        f"\n\n请按照以下 JSON Schema 返回结果：{schema}"
                    )

                try:
                    response = await client.chat.completions.create(
                        model=llm_cfg.model, messages=messages, temperature=0.3
                    )
                    result_text = response.choices[0].message.content

                    # 尝试解析为 JSON
                    if schema:
                        try:
                            import json

                            return {"success": True, "data": json.loads(result_text)}
                        except json.JSONDecodeError:
                            return {"success": True, "content": result_text}
                    else:
                        return {"success": True, "summary": result_text}

                except Exception as e:
                    return {"success": False, "error": str(e)}

        # 并行处理所有项目
        tasks = [process_item(item) for item in items]
        results = await asyncio.gather(*tasks)

        return list(results)

    def _call_llm_batch_sync(
        self,
        items: List[Dict[str, Any]],
        instruction: str,
        schema: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        并行调用 LLM 处理多个文本内容（同步封装）

        Args:
            items: 要处理的项目列表
            instruction: 处理指令
            schema: 可选的 JSON Schema
            max_concurrent: 最大并发数

        Returns:
            处理结果列表
        """
        return _run_async(
            self._call_llm_batch(items, instruction, schema, max_concurrent)
        )

    def postprocess_markdown(
        self, markdown: str, instruction: str, schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        对 Markdown 内容进行 LLM 后处理

        Args:
            markdown: Markdown 内容
            instruction: 处理指令
            schema: 可选的 JSON Schema

        Returns:
            处理结果，包含 summary 或 data 字段
        """
        if not instruction or not instruction.strip():
            return {
                "success": True,
                "original_markdown": markdown,
                "skipped": "No instruction provided",
            }

        # 直接调用同步的 _call_llm
        return self._call_llm(markdown, instruction, schema)

    def crawl_single(
        self,
        url: str,
        enhanced: bool = False,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        爬取单个网页 (同步封装)

        新设计：先快速爬取 Markdown，然后可选地进行 LLM 后处理

        Args:
            url: 网页 URL
            enhanced: 是否使用增强 SPA 模式
            llm_config: LLM 配置（可选），支持:
                - Dict: {"instruction": "...", "schema": {...}}
                - JSON 字符串: '{"instruction": "..."}'
                - 纯文本: "总结页面"（自动作为 instruction）

        Returns:
            爬取结果字典，包含:
            - success, markdown, title, error（爬取结果）
            - llm_summary 或 llm_data（LLM 处理结果，如果提供 llm_config）
        """
        # 解析 llm_config
        parsed_llm_config = _parse_llm_config(llm_config)

        # 第一步：快速爬取（不使用 LLM 策略）
        crawl_result = _run_async(self._crawl(url, enhanced, llm_config=None))

        # 第二步：如果有 LLM 配置，对 Markdown 进行后处理
        if parsed_llm_config and crawl_result["success"]:
            instruction = parsed_llm_config.get("instruction", "")
            schema = parsed_llm_config.get("schema")

            if instruction:  # 只有有 instruction 时才处理
                llm_result = self.postprocess_markdown(
                    crawl_result["markdown"], instruction, schema
                )

                # 将 LLM 结果合并到响应中
                if llm_result.get("success"):
                    if "summary" in llm_result:
                        crawl_result["llm_summary"] = llm_result["summary"]
                    if "data" in llm_result:
                        crawl_result["llm_data"] = llm_result["data"]
                    if "content" in llm_result:
                        crawl_result["llm_content"] = llm_result["content"]
                else:
                    crawl_result["llm_error"] = llm_result.get("error", "Unknown error")

        return crawl_result

    async def _crawl_site(
        self, url: str, depth: int = 2, pages: int = 10, concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        内部整站爬取方法

        Args:
            url: 起始 URL
            depth: 最大爬取深度
            pages: 最大页面数
            concurrent: 并发数

        Returns:
            爬取统计信息
        """
        # TODO: 实现完整的整站爬取逻辑（深度优先/广度优先、URL 去重、并发控制）
        # 当前简化实现：仅爬取首页
        visited = set()
        results = []

        async def crawl_with_depth(target_url: str, current_depth: int):
            if current_depth > depth or len(results) >= pages:
                return
            if target_url in visited:
                return

            visited.add(target_url)
            result = await self._crawl(target_url)
            results.append(result)

        await crawl_with_depth(url, 0)

        successful = sum(1 for r in results if r["success"])

        return {
            "successful_pages": successful,
            "total_pages": len(results),
            "success_rate": _calculate_success_rate(results),
            "results": results,
        }

    def crawl_site(
        self, url: str, depth: int = 2, pages: int = 10, concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        爬取整个网站 (同步封装)

        Args:
            url: 起始 URL
            depth: 最大爬取深度
            pages: 最大页面数
            concurrent: 并发数

        Returns:
            爬取统计信息
        """
        return _run_async(
            self._crawl_site(url, depth=depth, pages=pages, concurrent=concurrent)
        )

    async def _crawl_batch(
        self,
        urls: List[str],
        concurrent: int = 3,
        llm_config: Optional[Dict[str, Any]] = None,
        llm_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        内部批量爬取方法 - 使用 arun_many 实现真正的异步并行

        新设计：先快速爬取所有页面，然后对成功的页面进行 LLM 后处理

        Args:
            urls: URL 列表
            concurrent: 网页爬取并发数
            llm_config: LLM 配置字典（可选）
            llm_concurrent: LLM 处理并发数

        Returns:
            爬取结果列表
        """
        if not urls:
            return []

        from crawl4ai.async_dispatcher import SemaphoreDispatcher

        # 创建配置（不包含 LLM 策略，保持快速爬取）
        config = self._create_config(enhanced=False)

        # 创建并发控制器
        dispatcher = SemaphoreDispatcher(semaphore_count=concurrent)

        # 使用 arun_many 实现真正的并行爬取
        async with AsyncWebCrawler(verbose=False) as crawler:
            results = await crawler.arun_many(
                urls=urls, config=config, dispatcher=dispatcher
            )

        # 将 CrawlResultContainer 转换为我们的格式
        formatted_results = []
        for r in results:
            response = {
                "success": r.success,
                "markdown": r.markdown.raw_markdown if r.success else "",
                "title": r.metadata.get("title", "") if r.success else "",
                "error": r.error_message if not r.success else None,
            }
            formatted_results.append(response)

        # 第二阶段：如果有 LLM 配置，对成功的页面进行并行后处理
        parsed_llm_config = _parse_llm_config(llm_config)
        if parsed_llm_config and parsed_llm_config.get("instruction"):
            instruction = parsed_llm_config["instruction"]
            schema = parsed_llm_config.get("schema")

            # 筛选出成功的结果
            successful_results = [
                (i, r) for i, r in enumerate(formatted_results) if r["success"]
            ]

            if successful_results:
                # 使用并行批处理
                llm_results = await self._call_llm_batch(
                    [{"markdown": r["markdown"]} for _, r in successful_results],
                    instruction,
                    schema,
                    max_concurrent=llm_concurrent,
                )

                # 将结果合并回原数组
                for idx, (original_index, _) in enumerate(successful_results):
                    llm_result = llm_results[idx]
                    if llm_result.get("success"):
                        if "summary" in llm_result:
                            formatted_results[original_index]["llm_summary"] = (
                                llm_result["summary"]
                            )
                        if "data" in llm_result:
                            formatted_results[original_index]["llm_data"] = llm_result[
                                "data"
                            ]
                        if "content" in llm_result:
                            formatted_results[original_index]["llm_content"] = (
                                llm_result["content"]
                            )
                    else:
                        formatted_results[original_index]["llm_error"] = llm_result.get(
                            "error", "Unknown error"
                        )

        return formatted_results

    def crawl_batch(
        self,
        urls: List[str],
        concurrent: int = 3,
        llm_config: Optional[Dict[str, Any]] = None,
        llm_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        批量爬取多个网页 (同步封装)

        Args:
            urls: URL 列表
            concurrent: 网页爬取并发数
            llm_config: LLM 配置字典（可选）
            llm_concurrent: LLM 处理并发数

        Returns:
            爬取结果列表
        """
        return _run_async(
            self._crawl_batch(
                urls,
                concurrent=concurrent,
                llm_config=llm_config,
                llm_concurrent=llm_concurrent,
            )
        )
