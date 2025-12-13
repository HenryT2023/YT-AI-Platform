"""
LLM Adapter 基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Citation:
    """引用"""

    evidence_id: str
    title: Optional[str] = None
    source_ref: Optional[str] = None
    excerpt: Optional[str] = None


@dataclass
class LLMResponse:
    """LLM 响应"""

    text: str
    citations: List[Citation] = field(default_factory=list)
    tokens_used: int = 0
    model: str = ""
    finish_reason: str = "stop"
    raw_response: Optional[Dict[str, Any]] = None


class BaseLLMAdapter(ABC):
    """LLM Adapter 基类"""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        生成回复

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息
            context: 上下文信息
            citations: 可引用的证据列表
            max_tokens: 最大生成 token 数
            temperature: 温度参数

        Returns:
            LLMResponse: 生成的回复
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
