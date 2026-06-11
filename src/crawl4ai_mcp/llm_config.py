"""LLM 配置模块 - 管理 LLM API 密钥和模型配置

环境变量:
    CRAWL_MCP_API_KEY:      API 密钥（可选，未配置则 LLM 功能自动禁用）
    CRAWL_MCP_BASE_URL:     API 基础 URL（可选）
    CRAWL_MCP_TEXT_MODEL:   文本模型名称（可选）
    CRAWL_MCP_VISION_MODEL: 图片分析模型名称（可选）
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMConfig:
    """LLM 配置类

    支持兼容 OpenAI API 格式的各种服务商
    """

    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    instruction: str = ""
    schema: Optional[Dict[str, Any]] = None
    # 图片分析模型（可选）
    vision_model: Optional[str] = None


def get_default_llm_config() -> Optional[LLMConfig]:
    """从环境变量获取默认 LLM 配置

    环境变量:
        CRAWL_MCP_API_KEY: API 密钥（可选，未设置返回 None）
        CRAWL_MCP_BASE_URL: API 基础 URL（可选，默认 https://api.openai.com/v1）
        CRAWL_MCP_TEXT_MODEL: 模型名称（可选，默认 glm-4.7）
        CRAWL_MCP_VISION_MODEL: 图片分析模型名称（可选，默认 glm-4.6v）

    Returns:
        LLMConfig 实例，或 None（当 API Key 未配置时）
    """
    api_key = os.getenv("CRAWL_MCP_API_KEY")
    if not api_key:
        return None

    return LLMConfig(
        api_key=api_key,
        base_url=os.getenv("CRAWL_MCP_BASE_URL") or "https://api.openai.com/v1",
        model=os.getenv("CRAWL_MCP_TEXT_MODEL") or "glm-4.7",
        vision_model=os.getenv("CRAWL_MCP_VISION_MODEL") or "glm-4.6v",
    )


def get_llm_config(config: Optional[Dict[str, Any]]) -> Optional[LLMConfig]:
    """从环境变量获取 LLM 配置，合并用户提供的业务参数

    Args:
        config: 用户提供的业务配置，可选包含:
            - instruction: 提取指令
            - schema: JSON Schema (可选)

    Returns:
        LLMConfig 实例（api_key/base_url/model 从环境变量读取），
        或 None（当 API Key 未配置时）
    """
    default = get_default_llm_config()
    if default is None:
        return None

    if config is None:
        return default

    # 只接受业务参数，认证配置从环境变量读取
    return LLMConfig(
        api_key=default.api_key,
        base_url=default.base_url,
        model=default.model,
        vision_model=default.vision_model,
        instruction=config.get("instruction", ""),
        schema=config.get("schema"),
    )
