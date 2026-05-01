"""并行 LLM 处理单元测试"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from crawl4ai_mcp.crawler import Crawler
from crawl4ai_mcp.searcher import Searcher


class TestPostprocessBatchWithLLM:
    """测试批量后处理（使用原生 LLMExtractionStrategy）"""

    @pytest.mark.asyncio
    async def test_batch_postprocess_processes_multiple_items(self):
        """测试并行处理多个文本"""
        crawler = Crawler()
        items = [
            {"markdown": "Content 1"},
            {"markdown": "Content 2"},
            {"markdown": "Content 3"},
        ]

        with patch.object(
            crawler,
            "_postprocess_batch_with_llm",
            return_value=[
                {"summary": "S0", "__index__": 0},
                {"summary": "S1", "__index__": 1},
                {"summary": "S2", "__index__": 2},
            ],
        ):
            result = await crawler._postprocess_batch_with_llm(
                items, instruction="Summarize", max_concurrent=2
            )

        assert len(result) == 3
        assert all("summary" in r for r in result)

    @pytest.mark.asyncio
    async def test_batch_postprocess_handles_errors(self):
        """测试错误处理"""
        crawler = Crawler()
        items = [
            {"markdown": "Content 1"},
            {"markdown": "Content 2"},
            {"markdown": "Content 3"},
        ]

        with patch.object(
            crawler,
            "_postprocess_batch_with_llm",
            return_value=[
                {"summary": "OK 1", "__index__": 0},
                {"__error__": True, "error": "API Error", "__index__": 1},
                {"summary": "OK 3", "__index__": 2},
            ],
        ):
            result = await crawler._postprocess_batch_with_llm(
                items, instruction="Test"
            )

        assert len(result) == 3
        error_results = [r for r in result if r.get("__error__")]
        success_results = [r for r in result if not r.get("__error__")]
        assert len(error_results) == 1
        assert len(success_results) == 2

    @pytest.mark.asyncio
    async def test_batch_postprocess_empty_items(self):
        """空列表返回空"""
        crawler = Crawler()
        result = await crawler._postprocess_batch_with_llm([], instruction="test")
        assert result == []


class TestAnalyzeImagesParallel:
    """测试并行图片分析"""

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.searcher.AsyncOpenAI")
    async def test_analyze_images_parallel_processes_multiple(self, mock_openai):
        """测试并行分析多张图片"""
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

        with patch(
            "crawl4ai_mcp.searcher.get_default_llm_config", return_value=mock_config
        ):
            result = await searcher._analyze_images_async(
                images, "Describe this", max_concurrent=2
            )

        assert result["count"] == 2
        assert len(result["results"]) == 2
        assert all("analysis" in r for r in result["results"])

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.searcher.AsyncOpenAI")
    async def test_analyze_images_with_local_files(self, mock_openai):
        """测试分析本地文件（base64 编码）"""
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

        fake_image_data = b"fake_image_bytes"

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

        assert result["count"] == 1
        assert len(result["results"]) == 1
        call_args = mock_client.chat.completions.create.call_args
        content = call_args[1]["messages"][0]["content"]
        assert any("data:image/jpeg;base64," in str(item) for item in content)

    @pytest.mark.asyncio
    @patch("crawl4ai_mcp.searcher.AsyncOpenAI")
    async def test_analyze_images_mixed_url_and_local(self, mock_openai):
        """测试混合 URL 和本地文件"""
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

        assert result["count"] == 2
        types = [r["type"] for r in result["results"]]
        assert "url" in types
        assert "local" in types


class TestSyncWrappers:
    """测试同步包装器"""

    @patch("crawl4ai_mcp.searcher.run_async")
    def test_analyze_images_sync_wrapper(self, mock_run_async):
        """测试 _analyze_images 同步包装器"""
        mock_run_async.return_value = {
            "count": 1,
            "results": [{"analysis": "test"}],
        }
        searcher = Searcher()

        result = searcher._analyze_images([], "test")

        mock_run_async.assert_called_once()
        assert result["count"] == 1
