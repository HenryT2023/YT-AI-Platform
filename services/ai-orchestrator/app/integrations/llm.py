"""
LLM 客户端抽象层

支持多种 LLM 提供商：OpenAI、Qwen、Ollama
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TokenUsage:
    """Token 使用统计"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    usage: Optional[TokenUsage] = None
    model: Optional[str] = None
    finish_reason: Optional[str] = None


class LLMClient(ABC):
    """LLM 客户端抽象基类"""

    @abstractmethod
    async def chat(
        self,
        messages: List[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送对话请求"""
        pass

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """生成文本嵌入向量"""
        pass


class OpenAIClient(LLMClient):
    """OpenAI 客户端"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
        )
        self.model = settings.OPENAI_MODEL
        self.embedding_model = settings.EMBEDDING_MODEL

    async def chat(
        self,
        messages: List[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送对话请求到 OpenAI"""
        logger.debug("openai_chat_request", model=self.model, message_count=len(messages))

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return LLMResponse(
            content=choice.message.content or "",
            usage=usage,
            model=response.model,
            finish_reason=choice.finish_reason,
        )

    async def embed(self, text: str) -> List[float]:
        """生成文本嵌入向量"""
        response = await self.client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        return response.data[0].embedding


class QwenClient(LLMClient):
    """阿里云 Qwen 客户端（兼容 OpenAI 接口）"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.QWEN_API_KEY,
            base_url=settings.QWEN_API_BASE,
        )
        self.model = settings.QWEN_MODEL

    async def chat(
        self,
        messages: List[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送对话请求到 Qwen"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return LLMResponse(
            content=choice.message.content or "",
            usage=usage,
            model=response.model,
            finish_reason=choice.finish_reason,
        )

    async def embed(self, text: str) -> List[float]:
        """Qwen 嵌入（使用 OpenAI 兼容接口）"""
        response = await self.client.embeddings.create(
            model="text-embedding-v2",
            input=text,
        )
        return response.data[0].embedding


def get_llm_client() -> LLMClient:
    """根据配置获取 LLM 客户端"""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "openai":
        return OpenAIClient()
    elif provider == "qwen":
        return QwenClient()
    else:
        logger.warning(f"Unknown LLM provider: {provider}, falling back to OpenAI")
        return OpenAIClient()
