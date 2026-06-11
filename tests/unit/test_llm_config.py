"""LLM 配置模块的单元测试

覆盖：
  1. 新变量名 CRAWL_MCP_* 的读取
  2. API Key 未配置时返回 None（优雅降级）
  3. 默认值回退
"""

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
        """测试从 CRAWL_MCP_* 环境变量获取配置"""
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "sk-new-key")
        monkeypatch.setenv("CRAWL_MCP_BASE_URL", "https://custom.api.com/v1")
        monkeypatch.setenv("CRAWL_MCP_TEXT_MODEL", "gpt-4o")
        monkeypatch.setenv("CRAWL_MCP_VISION_MODEL", "glm-5v")

        config = get_default_llm_config()
        assert config.api_key == "sk-new-key"
        assert config.base_url == "https://custom.api.com/v1"
        assert config.model == "gpt-4o"
        assert config.vision_model == "glm-5v"

    def test_missing_api_key_returns_none(self, monkeypatch):
        """测试 API Key 未设置时返回 None（优雅降级）"""
        monkeypatch.delenv("CRAWL_MCP_API_KEY", raising=False)

        result = get_default_llm_config()
        assert result is None

    def test_fallback_default_values(self, monkeypatch):
        """测试部分变量缺失时使用硬编码默认值"""
        monkeypatch.setenv("CRAWL_MCP_API_KEY", "sk-env-key")
        monkeypatch.delenv("CRAWL_MCP_BASE_URL", raising=False)
        monkeypatch.delenv("CRAWL_MCP_TEXT_MODEL", raising=False)
        monkeypatch.delenv("CRAWL_MCP_VISION_MODEL", raising=False)

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

        # 传入业务参数但无 API Key → 返回 None
        result = get_llm_config({"instruction": "测试"})
        assert result is None
