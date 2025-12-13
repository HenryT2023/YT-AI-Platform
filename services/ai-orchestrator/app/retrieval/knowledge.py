"""
知识库检索

使用 Qdrant 向量数据库进行语义检索
"""

from typing import Any, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.llm import get_llm_client

logger = get_logger(__name__)


class KnowledgeRetriever:
    """知识库检索器"""

    def __init__(self):
        self.client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY,
        )
        self.collection = settings.QDRANT_COLLECTION
        self.llm = get_llm_client()

    async def search(
        self,
        query: str,
        domains: Optional[List[str]] = None,
        top_k: int = 5,
        score_threshold: float = 0.7,
    ) -> List[dict[str, Any]]:
        """
        语义检索相关文档

        Args:
            query: 查询文本
            domains: 知识领域过滤
            top_k: 返回结果数量
            score_threshold: 相似度阈值

        Returns:
            相关文档列表
        """
        try:
            # 生成查询向量
            query_vector = await self.llm.embed(query)

            # 构建过滤条件
            query_filter = None
            if domains:
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="domain",
                            match=MatchAny(any=domains),
                        )
                    ]
                )

            # 执行检索
            results = await self.client.search(
                collection_name=self.collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=score_threshold,
            )

            # 格式化结果
            docs = []
            for result in results:
                payload = result.payload or {}
                docs.append({
                    "id": result.id,
                    "score": result.score,
                    "title": payload.get("title", ""),
                    "content": payload.get("content", ""),
                    "domain": payload.get("domain", ""),
                    "source": payload.get("source", ""),
                })

            logger.debug(
                "knowledge_search",
                query_length=len(query),
                domains=domains,
                results_count=len(docs),
            )

            return docs

        except Exception as e:
            logger.error("knowledge_search_error", error=str(e))
            return []

    async def close(self) -> None:
        """关闭连接"""
        await self.client.close()
