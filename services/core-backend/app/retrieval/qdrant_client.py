"""
Qdrant 客户端

提供向量检索和索引管理功能
"""

import hashlib
import structlog
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from qdrant_client import QdrantClient as QdrantSDK
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings
from app.retrieval.base import RetrievalProvider, RetrievalResult, RetrievalStrategy

logger = structlog.get_logger(__name__)

# 向量维度（根据 embedding 模型确定）
VECTOR_DIM = 1024  # text-embedding-3-small / bge-large-zh


@dataclass
class EmbeddingResult:
    """Embedding 结果"""
    text: str
    vector: List[float]
    model: str


class QdrantRetriever(RetrievalProvider):
    """
    Qdrant 向量检索提供者

    功能：
    1. 向量语义检索
    2. Collection 管理
    3. 向量 upsert/delete
    """

    def __init__(
        self,
        url: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_provider: Optional[Any] = None,
    ):
        self.url = url or settings.QDRANT_URL
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self.embedding_provider = embedding_provider

        # 初始化 Qdrant 客户端
        self._client: Optional[QdrantSDK] = None
        self._connected = False

    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.QDRANT

    async def _get_client(self) -> QdrantSDK:
        """获取 Qdrant 客户端（懒加载）"""
        if self._client is None:
            self._client = QdrantSDK(url=self.url, timeout=30)
            self._connected = True
            logger.info("qdrant_client_connected", url=self.url)
        return self._client

    async def ensure_collection(self) -> bool:
        """确保 collection 存在"""
        client = await self._get_client()
        try:
            collections = client.get_collections()
            existing = [c.name for c in collections.collections]

            if self.collection_name not in existing:
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=VECTOR_DIM,
                        distance=qdrant_models.Distance.COSINE,
                    ),
                )
                logger.info("qdrant_collection_created", collection=self.collection_name)
            return True
        except Exception as e:
            logger.error("qdrant_ensure_collection_error", error=str(e))
            return False

    async def search(
        self,
        query: str,
        tenant_id: str,
        site_id: str,
        limit: int = 5,
        min_score: float = 0.3,
        domains: Optional[List[str]] = None,
    ) -> List[RetrievalResult]:
        """
        向量语义检索

        Args:
            query: 查询文本
            tenant_id: 租户 ID
            site_id: 站点 ID
            limit: 返回数量限制
            min_score: 最小分数阈值
            domains: 知识领域过滤

        Returns:
            检索结果列表
        """
        log = logger.bind(query=query[:50], tenant_id=tenant_id, site_id=site_id)

        try:
            # 1. 获取查询向量
            query_vector = await self._get_embedding(query)
            if not query_vector:
                log.warning("qdrant_search_no_embedding")
                return []

            # 2. 构建过滤条件
            must_conditions = [
                qdrant_models.FieldCondition(
                    key="tenant_id",
                    match=qdrant_models.MatchValue(value=tenant_id),
                ),
                qdrant_models.FieldCondition(
                    key="site_id",
                    match=qdrant_models.MatchValue(value=site_id),
                ),
            ]

            if domains:
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key="domains",
                        match=qdrant_models.MatchAny(any=domains),
                    )
                )

            # 3. 执行检索
            client = await self._get_client()
            results = client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qdrant_models.Filter(must=must_conditions),
                limit=limit,
                score_threshold=min_score,
                with_payload=True,
            )

            # 4. 转换结果
            items = []
            for hit in results:
                payload = hit.payload or {}
                items.append(RetrievalResult(
                    id=str(hit.id),
                    source_type=payload.get("source_type", "evidence"),
                    source_ref=payload.get("source_ref"),
                    title=payload.get("title"),
                    excerpt=payload.get("excerpt", ""),
                    score=hit.score,
                    strategy=RetrievalStrategy.QDRANT,
                    confidence=payload.get("confidence", 1.0),
                    verified=payload.get("verified", False),
                    tags=payload.get("tags", []),
                    metadata={"qdrant_id": str(hit.id)},
                    qdrant_score=hit.score,
                ))

            log.info("qdrant_search_complete", hit_count=len(items))
            return items

        except Exception as e:
            log.error("qdrant_search_error", error=str(e))
            return []

    async def upsert(
        self,
        evidence_id: str,
        text: str,
        tenant_id: str,
        site_id: str,
        source_type: str = "evidence",
        source_ref: Optional[str] = None,
        title: Optional[str] = None,
        excerpt: Optional[str] = None,
        confidence: float = 1.0,
        verified: bool = False,
        tags: Optional[List[str]] = None,
        domains: Optional[List[str]] = None,
    ) -> bool:
        """
        插入或更新向量

        Args:
            evidence_id: 证据 ID
            text: 待向量化文本
            tenant_id: 租户 ID
            site_id: 站点 ID
            其他: payload 字段

        Returns:
            是否成功
        """
        log = logger.bind(evidence_id=evidence_id)

        try:
            # 1. 获取向量
            vector = await self._get_embedding(text)
            if not vector:
                log.warning("qdrant_upsert_no_embedding")
                return False

            # 2. 构建 point
            point_id = self._generate_point_id(evidence_id)
            point = qdrant_models.PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "evidence_id": evidence_id,
                    "tenant_id": tenant_id,
                    "site_id": site_id,
                    "source_type": source_type,
                    "source_ref": source_ref,
                    "title": title,
                    "excerpt": excerpt or text[:500],
                    "confidence": confidence,
                    "verified": verified,
                    "tags": tags or [],
                    "domains": domains or [],
                },
            )

            # 3. Upsert
            client = await self._get_client()
            client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )

            log.info("qdrant_upsert_success", point_id=point_id)
            return True

        except Exception as e:
            log.error("qdrant_upsert_error", error=str(e))
            return False

    async def delete(self, evidence_id: str) -> bool:
        """删除向量"""
        log = logger.bind(evidence_id=evidence_id)

        try:
            point_id = self._generate_point_id(evidence_id)
            client = await self._get_client()
            client.delete(
                collection_name=self.collection_name,
                points_selector=qdrant_models.PointIdsList(points=[point_id]),
            )
            log.info("qdrant_delete_success", point_id=point_id)
            return True
        except Exception as e:
            log.error("qdrant_delete_error", error=str(e))
            return False

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            client = await self._get_client()
            client.get_collections()
            return True
        except Exception:
            return False

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        获取文本向量

        优先使用注入的 embedding_provider，否则使用默认实现
        """
        if self.embedding_provider:
            return await self.embedding_provider.embed(text)

        # 默认实现：调用 embedding API
        return await self._default_embedding(text)

    async def _default_embedding(self, text: str) -> Optional[List[float]]:
        """
        默认 embedding 实现

        使用 OpenAI 或 Baidu embedding API
        """
        import httpx

        # 优先使用 OpenAI
        if settings.OPENAI_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={
                            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "text-embedding-3-small",
                            "input": text[:8000],
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return data["data"][0]["embedding"]
            except Exception as e:
                logger.error("openai_embedding_error", error=str(e))

        # 回退：使用 Baidu embedding
        if settings.BAIDU_API_KEY and settings.BAIDU_SECRET_KEY:
            try:
                # 获取 access_token
                async with httpx.AsyncClient(timeout=30) as client:
                    token_resp = await client.post(
                        "https://aip.baidubce.com/oauth/2.0/token",
                        params={
                            "grant_type": "client_credentials",
                            "client_id": settings.BAIDU_API_KEY,
                            "client_secret": settings.BAIDU_SECRET_KEY,
                        },
                    )
                    if token_resp.status_code != 200:
                        return None
                    access_token = token_resp.json().get("access_token")

                    # 调用 embedding API
                    embed_resp = await client.post(
                        f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/embeddings/embedding-v1?access_token={access_token}",
                        json={"input": [text[:1000]]},
                    )
                    if embed_resp.status_code == 200:
                        data = embed_resp.json()
                        if "data" in data and len(data["data"]) > 0:
                            return data["data"][0]["embedding"]
            except Exception as e:
                logger.error("baidu_embedding_error", error=str(e))

        logger.warning("no_embedding_provider_available")
        return None

    def _generate_point_id(self, evidence_id: str) -> str:
        """生成 Qdrant point ID（UUID 格式）"""
        # 使用 evidence_id 的 hash 作为 point_id
        hash_bytes = hashlib.md5(evidence_id.encode()).hexdigest()
        # 转换为 UUID 格式
        return f"{hash_bytes[:8]}-{hash_bytes[8:12]}-{hash_bytes[12:16]}-{hash_bytes[16:20]}-{hash_bytes[20:32]}"


# ============================================================
# 全局实例
# ============================================================

_qdrant_instance: Optional[QdrantRetriever] = None


def get_qdrant_client(
    url: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> QdrantRetriever:
    """获取 Qdrant 客户端实例"""
    global _qdrant_instance

    if _qdrant_instance is None:
        _qdrant_instance = QdrantRetriever(
            url=url,
            collection_name=collection_name,
        )

    return _qdrant_instance


def reset_qdrant_client() -> None:
    """重置 Qdrant 客户端（用于测试）"""
    global _qdrant_instance
    _qdrant_instance = None
