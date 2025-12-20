"""
向量存储服务 (Vector Store)

封装 Qdrant 向量数据库操作，提供统一的向量存储和检索接口。
"""

from typing import Any, Optional
from uuid import UUID

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.services.embedding import EmbeddingService, get_embedding_service

logger = get_logger(__name__)


# Collection 配置
COLLECTIONS = {
    "knowledge": {
        "description": "农耕知识、文化内容",
        "vector_size": 1536,
    },
    "npc_persona": {
        "description": "NPC 人设片段",
        "vector_size": 1536,
    },
    "quest_content": {
        "description": "任务描述和步骤",
        "vector_size": 1536,
    },
}


class SearchResult:
    """检索结果"""

    def __init__(
        self,
        id: str,
        score: float,
        content: str,
        metadata: dict[str, Any],
    ):
        self.id = id
        self.score = score
        self.content = content
        self.metadata = metadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score,
            "content": self.content,
            "metadata": self.metadata,
        }


class VectorStore:
    """向量存储服务"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self.host = host or settings.QDRANT_HOST
        self.port = port or settings.QDRANT_PORT
        self.embedding_service = embedding_service or get_embedding_service()
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        """获取 Qdrant 客户端"""
        if self._client is None:
            self._client = QdrantClient(host=self.host, port=self.port)
        return self._client

    async def init_collections(self):
        """初始化所有 Collections"""
        for name, config in COLLECTIONS.items():
            await self.create_collection(name, config["vector_size"])

    async def create_collection(
        self,
        collection_name: str,
        vector_size: int = 1536,
    ) -> bool:
        """创建 Collection"""
        try:
            # 检查是否已存在
            collections = self.client.get_collections().collections
            exists = any(c.name == collection_name for c in collections)

            if exists:
                logger.info("collection_exists", collection=collection_name)
                return True

            # 创建 Collection
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

            logger.info("collection_created", collection=collection_name)
            return True

        except Exception as e:
            logger.error("create_collection_error", collection=collection_name, error=str(e))
            return False

    async def upsert(
        self,
        collection_name: str,
        id: str,
        content: str,
        metadata: dict[str, Any],
        vector: Optional[list[float]] = None,
    ) -> bool:
        """
        插入或更新向量

        Args:
            collection_name: Collection 名称
            id: 文档 ID
            content: 文档内容
            metadata: 元数据
            vector: 向量（如果不提供，会自动生成）

        Returns:
            是否成功
        """
        try:
            # 生成向量
            if vector is None:
                vector = await self.embedding_service.embed_text(content)

            # 构建 payload
            payload = {
                "content": content,
                **metadata,
            }

            # 插入向量
            self.client.upsert(
                collection_name=collection_name,
                points=[
                    models.PointStruct(
                        id=id,
                        vector=vector,
                        payload=payload,
                    )
                ],
            )

            logger.debug("vector_upserted", collection=collection_name, id=id)
            return True

        except Exception as e:
            logger.error("upsert_error", collection=collection_name, id=id, error=str(e))
            return False

    async def upsert_batch(
        self,
        collection_name: str,
        documents: list[dict[str, Any]],
    ) -> int:
        """
        批量插入向量

        Args:
            collection_name: Collection 名称
            documents: 文档列表，每个文档包含 id, content, metadata

        Returns:
            成功插入的数量
        """
        if not documents:
            return 0

        try:
            # 提取内容并批量生成向量
            contents = [doc.get("content", "") for doc in documents]
            vectors = await self.embedding_service.embed_batch(contents)

            # 构建 points
            points = []
            for i, doc in enumerate(documents):
                points.append(
                    models.PointStruct(
                        id=doc["id"],
                        vector=vectors[i],
                        payload={
                            "content": doc.get("content", ""),
                            **doc.get("metadata", {}),
                        },
                    )
                )

            # 批量插入
            self.client.upsert(
                collection_name=collection_name,
                points=points,
            )

            logger.info(
                "batch_upserted",
                collection=collection_name,
                count=len(points),
            )
            return len(points)

        except Exception as e:
            logger.error("batch_upsert_error", collection=collection_name, error=str(e))
            return 0

    async def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
        score_threshold: float = 0.5,
    ) -> list[SearchResult]:
        """
        语义检索

        Args:
            collection_name: Collection 名称
            query: 查询文本
            top_k: 返回数量
            filters: 过滤条件
            score_threshold: 分数阈值

        Returns:
            检索结果列表
        """
        try:
            # 生成查询向量
            query_vector = await self.embedding_service.embed_text(query)

            # 构建过滤条件
            qdrant_filter = None
            if filters:
                conditions = []
                for key, value in filters.items():
                    if isinstance(value, list):
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchAny(any=value),
                            )
                        )
                    else:
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchValue(value=value),
                            )
                        )
                qdrant_filter = models.Filter(must=conditions)

            # 执行检索
            results = self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=qdrant_filter,
                score_threshold=score_threshold,
            )

            # 转换结果
            search_results = []
            for hit in results:
                payload = hit.payload or {}
                search_results.append(
                    SearchResult(
                        id=str(hit.id),
                        score=hit.score,
                        content=payload.get("content", ""),
                        metadata={k: v for k, v in payload.items() if k != "content"},
                    )
                )

            logger.debug(
                "search_completed",
                collection=collection_name,
                query_length=len(query),
                results_count=len(search_results),
            )

            return search_results

        except Exception as e:
            logger.error("search_error", collection=collection_name, error=str(e))
            return []

    async def delete(
        self,
        collection_name: str,
        ids: list[str],
    ) -> bool:
        """删除向量"""
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=models.PointIdsList(points=ids),
            )
            logger.info("vectors_deleted", collection=collection_name, count=len(ids))
            return True
        except Exception as e:
            logger.error("delete_error", collection=collection_name, error=str(e))
            return False

    async def get_collection_info(self, collection_name: str) -> Optional[dict[str, Any]]:
        """获取 Collection 信息"""
        try:
            info = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status.value,
            }
        except UnexpectedResponse:
            return None
        except Exception as e:
            logger.error("get_collection_info_error", collection=collection_name, error=str(e))
            return None

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False


# 全局单例
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """获取 VectorStore 单例"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
