"""
向量化服务 (Embedding Service)

将文本内容转换为向量表示，支持多种 Embedding 模型。
"""

import hashlib
from typing import Optional

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingConfig(BaseModel):
    """Embedding 配置"""
    provider: str = "openai"  # openai | dashscope | local
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    batch_size: int = 100


class EmbeddingService:
    """向量化服务"""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self._cache: dict[str, list[float]] = {}

    async def embed_text(self, text: str, use_cache: bool = True) -> list[float]:
        """
        单条文本向量化

        Args:
            text: 待向量化的文本
            use_cache: 是否使用缓存

        Returns:
            向量列表
        """
        if not text or not text.strip():
            return [0.0] * self.config.dimensions

        # 缓存检查
        cache_key = self._get_cache_key(text)
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        # 调用 Embedding API
        vector = await self._call_embedding_api([text])
        if vector:
            result = vector[0]
            if use_cache:
                self._cache[cache_key] = result
            return result

        return [0.0] * self.config.dimensions

    async def embed_batch(
        self,
        texts: list[str],
        use_cache: bool = True,
    ) -> list[list[float]]:
        """
        批量文本向量化

        Args:
            texts: 待向量化的文本列表
            use_cache: 是否使用缓存

        Returns:
            向量列表的列表
        """
        if not texts:
            return []

        results: list[list[float]] = []
        texts_to_embed: list[tuple[int, str]] = []

        # 检查缓存
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results.append([0.0] * self.config.dimensions)
                continue

            cache_key = self._get_cache_key(text)
            if use_cache and cache_key in self._cache:
                results.append(self._cache[cache_key])
            else:
                results.append([])  # 占位
                texts_to_embed.append((i, text))

        # 批量调用 API
        if texts_to_embed:
            batch_texts = [t[1] for t in texts_to_embed]

            # 分批处理
            for batch_start in range(0, len(batch_texts), self.config.batch_size):
                batch_end = min(batch_start + self.config.batch_size, len(batch_texts))
                batch = batch_texts[batch_start:batch_end]

                vectors = await self._call_embedding_api(batch)

                if vectors:
                    for j, vector in enumerate(vectors):
                        original_idx = texts_to_embed[batch_start + j][0]
                        original_text = texts_to_embed[batch_start + j][1]
                        results[original_idx] = vector

                        if use_cache:
                            cache_key = self._get_cache_key(original_text)
                            self._cache[cache_key] = vector

        # 填充失败的向量
        for i, result in enumerate(results):
            if not result:
                results[i] = [0.0] * self.config.dimensions

        return results

    async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """调用 Embedding API"""
        if self.config.provider == "openai":
            return await self._call_openai(texts)
        elif self.config.provider == "dashscope":
            return await self._call_dashscope(texts)
        else:
            logger.warning("unknown_embedding_provider", provider=self.config.provider)
            return []

    async def _call_openai(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI Embedding API"""
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            logger.error("openai_api_key_not_set")
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.model,
                        "input": texts,
                        "dimensions": self.config.dimensions,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        "openai_embedding_error",
                        status=response.status_code,
                        body=response.text[:200],
                    )
                    return []

                data = response.json()
                embeddings = data.get("data", [])

                # 按 index 排序
                embeddings.sort(key=lambda x: x.get("index", 0))
                return [e.get("embedding", []) for e in embeddings]

        except Exception as e:
            logger.error("openai_embedding_exception", error=str(e))
            return []

    async def _call_dashscope(self, texts: list[str]) -> list[list[float]]:
        """调用阿里云 DashScope Embedding API"""
        api_key = settings.DASHSCOPE_API_KEY
        if not api_key:
            logger.error("dashscope_api_key_not_set")
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "text-embedding-v2",
                        "input": {"texts": texts},
                        "parameters": {"text_type": "document"},
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        "dashscope_embedding_error",
                        status=response.status_code,
                        body=response.text[:200],
                    )
                    return []

                data = response.json()
                output = data.get("output", {})
                embeddings = output.get("embeddings", [])

                return [e.get("embedding", []) for e in embeddings]

        except Exception as e:
            logger.error("dashscope_embedding_exception", error=str(e))
            return []

    def _get_cache_key(self, text: str) -> str:
        """生成缓存 key"""
        content = f"{self.config.provider}:{self.config.model}:{text}"
        return hashlib.md5(content.encode()).hexdigest()

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()


# 全局单例
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """获取 Embedding 服务单例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
