"""
检索基础定义

定义检索策略、结果和提供者接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RetrievalStrategy(str, Enum):
    """检索策略"""
    TRGM = "trgm"       # PostgreSQL pg_trgm
    QDRANT = "qdrant"   # Qdrant 向量检索
    HYBRID = "hybrid"   # 混合检索


@dataclass
class RetrievalResult:
    """检索结果"""
    id: str
    source_type: str
    source_ref: Optional[str]
    title: Optional[str]
    excerpt: str
    score: float
    strategy: RetrievalStrategy
    confidence: float = 1.0
    verified: bool = False
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 混合检索时的分数明细
    trgm_score: Optional[float] = None
    qdrant_score: Optional[float] = None


class RetrievalProvider(ABC):
    """检索提供者抽象接口"""

    @property
    @abstractmethod
    def strategy(self) -> RetrievalStrategy:
        """返回检索策略"""
        pass

    @abstractmethod
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
        执行检索

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
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
