"""
LLM Provider 模块

统一的 LLM 服务提供者抽象，支持多种后端：
- 百度 ERNIE Bot
- OpenAI
- Qwen
- Ollama
"""

from app.providers.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMError,
    LLMErrorType,
    LLMAuditRecord,
)
from app.providers.llm.factory import get_llm_provider

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMError",
    "LLMErrorType",
    "LLMAuditRecord",
    "get_llm_provider",
]
