"""
检索模块

提供多种检索策略：
- trgm: PostgreSQL pg_trgm 相似度检索
- qdrant: Qdrant 向量语义检索
- hybrid: 混合检索（trgm + qdrant）
"""

from app.retrieval.base import (
    RetrievalStrategy,
    RetrievalResult,
    RetrievalProvider,
)
from app.retrieval.qdrant_client import (
    QdrantClient,
    get_qdrant_client,
)
from app.retrieval.hybrid import (
    HybridRetriever,
    get_hybrid_retriever,
)

__all__ = [
    "RetrievalStrategy",
    "RetrievalResult",
    "RetrievalProvider",
    "QdrantClient",
    "get_qdrant_client",
    "HybridRetriever",
    "get_hybrid_retriever",
]
