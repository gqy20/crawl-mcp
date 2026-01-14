"""LLM 配置模块的单元测试"""

import pytest
from crawl4ai_mcp.llm_config import LLMConfig, get_llm_config, get_default_llm_config


class TestLLMConfig:
    """测试 LLMConfig 类"""

    def test_create_llm_config_with_all_params(self):
        """测试创建包含所有参数的 LLM 配置"""
        config = LLMConfig(
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            model="test-model",
            instruction="Extract product info",
            schema={"type": "object", "properties": {}},
        )
        assert config.api_key == "sk-test"
        assert config.base_url == "https://api.example.com/v1"
        assert config.model == "test-model"
        assert config.instruction == "Extract product info"
        assert config.schema == {"type": "object", "properties": {}}

    def test_create_llm_config_with_minimal_params(self):
        """测试创建最小参数的 LLM 配置"""
        config = LLMConfig(api_key="sk-test")
        assert config.api_key == "sk-test"
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "gpt-4o-mini"
        assert config.instruction == ""
        assert config.schema is None


class TestGetDefaultLLMConfig:
    """测试从环境变量获取默认 LLM 配置"""

    def test_get_default_llm_config_from_env(self, monkeypatch):
        """测试从环境变量获取默认配置"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")

        config = get_default_llm_config()
        assert config.api_key == "sk-env-key"
        assert config.base_url == "https://custom.openai.com/v1"
        assert config.model == "gpt-4o"

    def test_get_default_llm_config_missing_api_key(self, monkeypatch):
        """测试缺少 API_KEY 时抛出异常"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(
            ValueError, match="OPENAI_API_KEY environment variable is required"
        ):
            get_default_llm_config()

    def test_get_default_llm_config_fallback_values(self, monkeypatch):
        """测试使用默认 fallback 值"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)

        config = get_default_llm_config()
        assert config.api_key == "sk-env-key"
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "glm-4.7"


class TestGetLLMConfig:
    """测试合并配置"""

    def test_get_llm_config_with_instruction(self, monkeypatch):
        """测试添加 instruction 参数"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")

        config = get_llm_config({"instruction": "总结内容"})
        assert config.api_key == "sk-env-key"  # 从环境变量
        assert config.instruction == "总结内容"  # 从参数

    def test_get_llm_config_with_none_uses_defaults(self, monkeypatch):
        """测试传入 None 时使用环境变量默认值"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")

        config = get_llm_config(None)
        assert config.api_key == "sk-env-key"
        assert config.instruction == ""
        assert config.schema is None

    def test_get_llm_config_with_schema(self, monkeypatch):
        """测试添加 schema 参数"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")

        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        config = get_llm_config({"schema": schema, "instruction": "提取"})
        assert config.api_key == "sk-env-key"
        assert config.schema == schema
        assert config.instruction == "提取"
