"""
LLM Provider 统一抽象接口

设计原则：
1. 统一接口，支持多种 LLM 后端
2. 内置超时、重试、错误分类
3. 可观测性：审计记录
4. 降级支持：LLM 不可用时返回标准错误
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class LLMErrorType(str, Enum):
    """LLM 错误类型"""

    AUTH = "auth"              # 认证错误（API Key 无效）
    NETWORK = "network"        # 网络错误
    TIMEOUT = "timeout"        # 超时
    RATE_LIMIT = "rate_limit"  # 限流
    SERVER = "server"          # 服务端错误
    INVALID_REQUEST = "invalid_request"  # 请求参数错误
    CONTENT_FILTER = "content_filter"    # 内容过滤
    UNKNOWN = "unknown"        # 未知错误


@dataclass
class LLMError(Exception):
    """LLM 错误"""

    error_type: LLMErrorType
    message: str
    status_code: Optional[int] = None
    raw_error: Optional[Any] = None
    retryable: bool = False

    def __str__(self) -> str:
        return f"[{self.error_type.value}] {self.message}"


@dataclass
class LLMRequest:
    """LLM 请求"""

    system_prompt: str
    user_message: str
    context: Dict[str, Any] = field(default_factory=dict)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    max_tokens: int = 1000
    temperature: float = 0.7
    trace_id: Optional[str] = None
    npc_id: Optional[str] = None


@dataclass
class LLMResponse:
    """LLM 响应"""

    text: str
    model: str
    tokens_input: int = 0
    tokens_output: int = 0
    finish_reason: str = "stop"
    latency_ms: int = 0
    raw_response: Optional[Dict[str, Any]] = None

    @property
    def tokens_total(self) -> int:
        return self.tokens_input + self.tokens_output


@dataclass
class LLMAuditRecord:
    """LLM 调用审计记录"""

    trace_id: str
    provider: str
    model: str
    request_hash: str
    tokens_input: int
    tokens_output: int
    latency_ms: int
    status: str  # success / error
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class LLMProvider(ABC):
    """
    LLM Provider 统一抽象接口

    所有 LLM 后端必须实现此接口
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者名称"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型名称"""
        pass

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        生成回复

        Args:
            request: LLM 请求

        Returns:
            LLMResponse: 生成的回复

        Raises:
            LLMError: LLM 调用失败
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: 是否健康
        """
        pass

    async def generate_with_fallback(
        self,
        request: LLMRequest,
        fallback_text: str = "抱歉，服务暂时不可用，请稍后再试。",
    ) -> LLMResponse:
        """
        带降级的生成

        LLM 不可用时返回降级响应而非抛出异常
        """
        try:
            return await self.generate(request)
        except LLMError:
            return LLMResponse(
                text=fallback_text,
                model=self.model_name,
                tokens_input=0,
                tokens_output=0,
                finish_reason="fallback",
                latency_ms=0,
            )
