"""并行 LLM 处理单元测试"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from crawl4ai_mcp.crawler import Crawler
from crawl4ai_mcp.searcher import Searcher


class TestCallLLMBatch:
    """测试并行 LLM 文本分析"""

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.crawler.AsyncOpenAI")
    async def test_call_llm_batch_processes_multiple_items(self, mock_openai):
        """测试并行处理多个文本"""
        # Arrange
        mock_config = MagicMock()
        mock_config.api_key = "test-key"
        mock_config.base_url = "https://api.test.com"
        mock_config.model = "test-model"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test summary"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        crawler = Crawler()
        items = [
            {"markdown": "Content 1"},
            {"markdown": "Content 2"},
            {"markdown": "Content 3"},
        ]

        # Act
        with patch(
            "crawl4ai_mcp.crawler.get_default_llm_config", return_value=mock_config
        ):
            result = await crawler._call_llm_batch(
                items, instruction="Summarize", max_concurrent=2
            )

        # Assert
        assert len(result) == 3
        assert all("summary" in r for r in result)
        # 验证并发调用
        assert mock_client.chat.completions.create.call_count == 3

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.crawler.AsyncOpenAI")
    async def test_call_llm_batch_respects_concurrency_limit(self, mock_openai):
        """测试遵守并发限制"""
        # Arrange
        mock_config = MagicMock()
        mock_config.api_key = "test-key"
        mock_config.base_url = "https://api.test.com"
        mock_config.model = "test-model"

        mock_client = AsyncMock()
        mock_openai.return_value = mock_client

        active_calls = 0
        max_active_calls = 0

        async def mock_create(*args, **kwargs):
            nonlocal active_calls, max_active_calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            await asyncio.sleep(0.01)  # 模拟异步操作
            active_calls -= 1
            return MagicMock(choices=[MagicMock(message=MagicMock(content="Done"))])

        mock_client.chat.completions.create = mock_create

        crawler = Crawler()
        items = [{"markdown": f"Content {i}"} for i in range(10)]

        # Act
        with patch(
            "crawl4ai_mcp.crawler.get_default_llm_config", return_value=mock_config
        ):
            await crawler._call_llm_batch(items, instruction="Test", max_concurrent=3)

        # Assert - 验证不会超过并发限制
        assert max_active_calls <= 3

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.crawler.AsyncOpenAI")
    async def test_call_llm_batch_handles_errors(self, mock_openai):
        """测试错误处理"""
        # Arrange
        mock_config = MagicMock()
        mock_config.api_key = "test-key"
        mock_config.base_url = "https://api.test.com"
        mock_config.model = "test-model"

        mock_client = AsyncMock()
        call_count = [0]

        async def mock_create_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("API Error")
            await asyncio.sleep(0.01)
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content=f"OK {call_count[0]}"))]
            )

        mock_client.chat.completions.create.side_effect = mock_create_side_effect
        mock_openai.return_value = mock_client

        crawler = Crawler()
        items = [
            {"markdown": "Content 1"},
            {"markdown": "Content 2"},
            {"markdown": "Content 3"},
        ]

        # Act
        with patch(
            "crawl4ai_mcp.crawler.get_default_llm_config", return_value=mock_config
        ):
            result = await crawler._call_llm_batch(items, instruction="Test")

        # Assert
        assert len(result) == 3
        # 第二个应该有错误（因为 call_count == 2 时抛出异常）
        error_results = [r for r in result if "error" in r]
        success_results = [r for r in result if "summary" in r]
        assert len(error_results) == 1
        assert len(success_results) == 2


class TestAnalyzeImagesParallel:
    """测试并行图片分析"""

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.searcher.AsyncOpenAI")
    async def test_analyze_images_parallel_processes_multiple(self, mock_openai):
        """测试并行分析多张图片"""
        # Arrange
        mock_config = MagicMock()
        mock_config.api_key = "test-key"
        mock_config.base_url = "https://api.test.com"
        mock_config.vision_model = "glm-4.6v"

        mock_client = AsyncMock()
        call_count = [0]

        async def mock_create_side_effect(*args, **kwargs):
            call_count[0] += 1
            await asyncio.sleep(0.01)
            return MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=f"Analysis {call_count[0]}"))
                ]
            )

        mock_client.chat.completions.create.side_effect = mock_create_side_effect
        mock_openai.return_value = mock_client

        searcher = Searcher()
        images = [
            {"path": "https://example.com/img1.jpg", "type": "url"},
            {"path": "https://example.com/img2.jpg", "type": "url"},
        ]

        # Act
        with patch(
            "crawl4ai_mcp.searcher.get_default_llm_config", return_value=mock_config
        ):
            result = await searcher._analyze_images_async(
                images, "Describe this", max_concurrent=2
            )

        # Assert
        assert result["count"] == 2
        assert len(result["results"]) == 2
        # 由于并行执行顺序不确定，只检查都有分析结果
        assert all("analysis" in r for r in result["results"])

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.searcher.AsyncOpenAI")
    async def test_analyze_images_with_local_files(self, mock_openai):
        """测试分析本地文件（base64 编码）"""
        # Arrange
        mock_config = MagicMock()
        mock_config.api_key = "test-key"
        mock_config.base_url = "https://api.test.com"
        mock_config.vision_model = "glm-4.6v"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Local image analysis"))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        searcher = Searcher()
        images = [{"path": "/path/to/image.jpg", "type": "local"}]

        # Mock 文件读取
        fake_image_data = b"fake_image_bytes"

        # Act
        with (
            patch(
                "crawl4ai_mcp.searcher.get_default_llm_config", return_value=mock_config
            ),
            patch(
                "builtins.open",
                MagicMock(
                    return_value=MagicMock(
                        __enter__=MagicMock(
                            return_value=MagicMock(
                                read=MagicMock(return_value=fake_image_data)
                            )
                        )
                    )
                ),
            ),
        ):
            result = await searcher._analyze_images_async(
                images, "Analyze", max_concurrent=2
            )

        # Assert
        assert result["count"] == 1
        assert len(result["results"]) == 1
        # 验证 base64 编码被使用
        call_args = mock_client.chat.completions.create.call_args
        content = call_args[1]["messages"][0]["content"]
        assert any("data:image/jpeg;base64," in str(item) for item in content)

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.searcher.AsyncOpenAI")
    async def test_analyze_images_mixed_url_and_local(self, mock_openai):
        """测试混合 URL 和本地文件"""
        # Arrange
        mock_config = MagicMock()
        mock_config.api_key = "test-key"
        mock_config.base_url = "https://api.test.com"
        mock_config.vision_model = "glm-4.6v"

        mock_client = AsyncMock()
        call_count = [0]

        async def mock_create_side_effect(*args, **kwargs):
            call_count[0] += 1
            await asyncio.sleep(0.01)
            content = "URL done" if call_count[0] == 1 else "Local done"
            return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])

        mock_client.chat.completions.create.side_effect = mock_create_side_effect
        mock_openai.return_value = mock_client

        searcher = Searcher()
        images = [
            {"path": "https://example.com/img.jpg", "type": "url"},
            {"path": "/local/img.jpg", "type": "local"},
        ]

        # Act
        with (
            patch(
                "crawl4ai_mcp.searcher.get_default_llm_config", return_value=mock_config
            ),
            patch(
                "builtins.open",
                MagicMock(
                    return_value=MagicMock(
                        __enter__=MagicMock(
                            return_value=MagicMock(read=MagicMock(return_value=b"fake"))
                        )
                    )
                ),
            ),
        ):
            result = await searcher._analyze_images_async(
                images, "Analyze", max_concurrent=2
            )

        # Assert
        assert result["count"] == 2
        assert len(result["results"]) == 2
        # 检查两个结果都有类型
        types = [r["type"] for r in result["results"]]
        assert "url" in types
        assert "local" in types


class TestSyncWrappers:
    """测试同步包装器"""

    @patch("crawl4ai_mcp.crawler._run_async")
    def test_call_llm_batch_sync_wrapper(self, mock_run_async):
        """测试 _call_llm_batch 同步包装器"""

        # Arrange
        mock_run_async.return_value = [{"summary": "Test"}]
        crawler = Crawler()

        # Act
        result = crawler._call_llm_batch_sync([], "test")

        # Assert
        mock_run_async.assert_called_once()
        assert result == [{"summary": "Test"}]

    @patch("crawl4ai_mcp.searcher._run_async")
    def test_analyze_images_sync_wrapper(self, mock_run_async):
        """测试 _analyze_images 同步包装器"""

        # Arrange
        mock_run_async.return_value = {"count": 1, "results": [{"analysis": "test"}]}
        searcher = Searcher()

        # Act
        result = searcher._analyze_images([], "test")

        # Assert
        mock_run_async.assert_called_once()
        assert result["count"] == 1
