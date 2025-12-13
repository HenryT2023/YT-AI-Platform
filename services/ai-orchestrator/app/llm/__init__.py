"""
LLM Adapter 模块

提供多种 LLM 后端的统一接口
"""

from app.llm.base import BaseLLMAdapter, LLMResponse
from app.llm.baidu import BaiduLLMAdapter
from app.llm.factory import get_llm_adapter

__all__ = [
    "BaseLLMAdapter",
    "LLMResponse",
    "BaiduLLMAdapter",
    "get_llm_adapter",
]
