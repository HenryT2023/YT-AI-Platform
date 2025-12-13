"""
LLM Adapter 工厂
"""

from functools import lru_cache
from typing import Optional

from app.core.config import settings
from app.llm.base import BaseLLMAdapter
from app.llm.baidu import BaiduLLMAdapter


@lru_cache
def get_llm_adapter(provider: Optional[str] = None) -> BaseLLMAdapter:
    """
    获取 LLM Adapter

    Args:
        provider: LLM 提供商，默认使用配置中的 LLM_PROVIDER

    Returns:
        BaseLLMAdapter: LLM Adapter 实例
    """
    provider = provider or settings.LLM_PROVIDER

    if provider == "baidu":
        return BaiduLLMAdapter()

    # 默认使用百度（v0.1.0 占位）
    # TODO: 添加其他提供商支持
    return BaiduLLMAdapter()
