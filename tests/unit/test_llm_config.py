"""LLM 配置模块的单元测试

覆盖：
  1. 新变量名 CRAWL_MCP_* 的读取
  2. 向后兼容 fallback（旧变量名 + DeprecationWarning）
  3. 新旧变量同时存在时优先使用新值
  4. API Key 未配置时返回 None（优雅降级）
"""

import warnings

from crawl4ai_mcp.llm_config import (
    LLMConfig,
    get_default_llm_config,
    get_llm_config,
)


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

    def test_get_default_from_new_env_vars(self, monkeypatch):
        """测试从新的 CRAWL_MCP_* 环境变量获取配置"""
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "sk-new-key")
        monkeypatch.setenv("CRAWL_MCP_BASE_URL", "https://custom.api.com/v1")
        monkeypatch.setenv("CRAWL_MCP_TEXT_MODEL", "gpt-4o")
        monkeypatch.setenv("CRAWL_MCP_VISION_MODEL", "glm-5v")

        config = get_default_llm_config()
        assert config.api_key == "sk-new-key"
        assert config.base_url == "https://custom.api.com/v1"
        assert config.model == "gpt-4o"
        assert config.vision_model == "glm-5v"

    def test_fallback_to_old_env_vars_with_warning(self, monkeypatch):
        """测试新变量不存在时 fallback 到旧变量名，并发出 DeprecationWarning"""
        # 只设置旧变量
        monkeypatch.delenv("CRAWL_MCP_API_KEY", raising=False)
        monkeypatch.delenv("CRAWL_MCP_BASE_URL", raising=False)
        monkeypatch.delenv("CRAWL_MCP_TEXT_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-old-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://old.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "old-model")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = get_default_llm_config()

            # 应该发出至少一个 DeprecationWarning
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert any(
                "OPENAI_API_KEY" in str(warning.message) for warning in dep_warnings
            )

        assert config.api_key == "sk-old-key"
        assert config.base_url == "https://old.openai.com/v1"
        assert config.model == "old-model"

    def test_new_var_takes_priority_over_old(self, monkeypatch):
        """测试新旧变量同时存在时，新变量优先"""
        # 先清理可能存在的旧变量（真实环境可能有残留）
        for old in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "LLM_MODEL", "VISION_MODEL"):
            monkeypatch.delenv(old, raising=False)

        # 同时设置新旧变量（值不同）
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "sk-new-priority")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-old-ignored")
        monkeypatch.setenv("CRAWL_MCP_BASE_URL", "https://new.api.com/v1")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://old.api.com/v1")
        monkeypatch.setenv("CRAWL_MCP_TEXT_MODEL", "new-model")
        monkeypatch.setenv("LLM_MODEL", "old-model")

        # 不应有 warning（因为新变量存在）
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = get_default_llm_config()
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) == 0

        assert config.api_key == "sk-new-priority"
        assert config.base_url == "https://new.api.com/v1"
        assert config.model == "new-model"

    def test_missing_api_key_returns_none(self, monkeypatch):
        """测试新旧变量都未设置 API Key 时返回 None（优雅降级）"""
        monkeypatch.delenv("CRAWL_MCP_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = get_default_llm_config()
        assert result is None

    def test_fallback_default_values(self, monkeypatch):
        """测试部分变量缺失时使用硬编码默认值"""
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "sk-env-key")
        monkeypatch.delenv("CRAWL_MCP_BASE_URL", raising=False)
        monkeypatch.delenv("CRAWL_MCP_TEXT_MODEL", raising=False)
        monkeypatch.delenv("CRAWL_MCP_VISION_MODEL", raising=False)
        # 确保旧变量也不存在
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("VISION_MODEL", raising=False)

        config = get_default_llm_config()
        assert config.api_key == "sk-env-key"
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "glm-4.7"
        assert config.vision_model == "glm-4.6v"


class TestGetLLMConfig:
    """测试合并配置"""

    def test_get_llm_config_with_instruction(self, monkeypatch):
        """测试添加 instruction 参数"""
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "sk-env-key")

        config = get_llm_config({"instruction": "总结内容"})
        assert config.api_key == "sk-env-key"  # 从环境变量
        assert config.instruction == "总结内容"  # 从参数

    def test_get_llm_config_with_none_uses_defaults(self, monkeypatch):
        """测试传入 None 时使用环境变量默认值"""
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "sk-env-key")

        config = get_llm_config(None)
        assert config.api_key == "sk-env-key"
        assert config.instruction == ""
        assert config.schema is None

    def test_get_llm_config_with_schema(self, monkeypatch):
        """测试添加 schema 参数"""
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "sk-env-key")

        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        config = get_llm_config({"schema": schema, "instruction": "提取"})
        assert config.api_key == "sk-env-key"
        assert config.schema == schema
        assert config.instruction == "提取"

    def test_get_llm_config_missing_api_key_returns_none(self, monkeypatch):
        """测试 API Key 缺失时返回 None"""
        monkeypatch.delenv("CRAWL_MCP_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # 传入业务参数但无 API Key → 返回 None
        result = get_llm_config({"instruction": "测试"})
        assert result is None
