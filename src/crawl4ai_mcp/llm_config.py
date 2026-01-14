"""LLM 配置模块 - 管理 LLM API 密钥和模型配置"""

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


def get_default_llm_config() -> LLMConfig:
    """从环境变量获取默认 LLM 配置

    环境变量:
        OPENAI_API_KEY: API 密钥（必需）
        OPENAI_BASE_URL: API 基础 URL（可选）
        LLM_MODEL: 模型名称（可选）
        VISION_MODEL: 图片分析模型名称（可选）

    Returns:
        LLMConfig 实例

    Raises:
        ValueError: 如果 OPENAI_API_KEY 未设置
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    return LLMConfig(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("LLM_MODEL", "glm-4.7"),
        vision_model=os.getenv("VISION_MODEL", "glm-4.6v"),
    )


def get_llm_config(config: Optional[Dict[str, Any]]) -> LLMConfig:
    """从环境变量获取 LLM 配置，合并用户提供的业务参数

    Args:
        config: 用户提供的业务配置，可选包含:
            - instruction: 提取指令
            - schema: JSON Schema (可选)

    Returns:
        LLMConfig 实例，api_key/base_url/model 从环境变量读取

    Raises:
        ValueError: 如果 OPENAI_API_KEY 环境变量未设置
    """
    default = get_default_llm_config()

    if config is None:
        return default

    # 只接受业务参数，认证配置从环境变量读取
    return LLMConfig(
        api_key=default.api_key,
        base_url=default.base_url,
        model=default.model,
        instruction=config.get("instruction", ""),
        schema=config.get("schema"),
    )
