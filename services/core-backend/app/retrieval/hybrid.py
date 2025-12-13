"""
混合检索器

结合 pg_trgm 和 Qdrant 向量检索
"""

import structlog
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.base import RetrievalProvider, RetrievalResult, RetrievalStrategy
from app.retrieval.qdrant_client import QdrantRetriever, get_qdrant_client
from app.database.models.evidence import Evidence

logger = structlog.get_logger(__name__)


class HybridRetriever(RetrievalProvider):
    """
    混合检索器

    策略：
    1. 并行执行 trgm 和 qdrant 检索
    2. 合并结果，去重
    3. 重新排序（加权融合）
    """

    def __init__(
        self,
        session: AsyncSession,
        qdrant_client: Optional[QdrantRetriever] = None,
        trgm_weight: float = 0.4,
        qdrant_weight: float = 0.6,
    ):
        self.session = session
        self.qdrant = qdrant_client or get_qdrant_client()
        self.trgm_weight = trgm_weight
        self.qdrant_weight = qdrant_weight

    @property
    def strategy(self) -> RetrievalStrategy:
        return RetrievalStrategy.HYBRID

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
        混合检索

        并行执行 trgm 和 qdrant，合并去重后加权排序
        """
        log = logger.bind(query=query[:50], strategy="hybrid")

        import asyncio

        # 并行检索
        trgm_task = self._search_trgm(query, tenant_id, site_id, limit * 2, min_score, domains)
        qdrant_task = self.qdrant.search(query, tenant_id, site_id, limit * 2, min_score, domains)

        trgm_results, qdrant_results = await asyncio.gather(
            trgm_task, qdrant_task, return_exceptions=True
        )

        # 处理异常
        if isinstance(trgm_results, Exception):
            log.error("hybrid_trgm_error", error=str(trgm_results))
            trgm_results = []
        if isinstance(qdrant_results, Exception):
            log.error("hybrid_qdrant_error", error=str(qdrant_results))
            qdrant_results = []

        # 合并去重
        merged = self._merge_results(trgm_results, qdrant_results)

        # 加权排序
        merged.sort(key=lambda x: x.score, reverse=True)

        log.info(
            "hybrid_search_complete",
            trgm_count=len(trgm_results),
            qdrant_count=len(qdrant_results),
            merged_count=len(merged),
        )

        return merged[:limit]

    async def _search_trgm(
        self,
        query: str,
        tenant_id: str,
        site_id: str,
        limit: int,
        min_score: float,
        domains: Optional[List[str]],
    ) -> List[RetrievalResult]:
        """pg_trgm 检索"""
        log = logger.bind(query=query[:50], strategy="trgm")

        try:
            # 使用 pg_trgm 相似度
            similarity = func.similarity(Evidence.title + ' ' + Evidence.excerpt, query)

            stmt = (
                select(Evidence, similarity.label("score"))
                .where(
                    Evidence.tenant_id == tenant_id,
                    Evidence.site_id == site_id,
                    Evidence.deleted_at.is_(None),
                    similarity >= min_score,
                )
                .order_by(similarity.desc())
                .limit(limit)
            )

            if domains:
                stmt = stmt.where(Evidence.domains.overlap(domains))

            result = await self.session.execute(stmt)
            rows = result.all()

            items = []
            for row in rows:
                evidence = row[0]
                score = float(row[1])
                items.append(RetrievalResult(
                    id=str(evidence.id),
                    source_type=evidence.source_type,
                    source_ref=evidence.source_ref,
                    title=evidence.title,
                    excerpt=evidence.excerpt,
                    score=score,
                    strategy=RetrievalStrategy.TRGM,
                    confidence=evidence.confidence,
                    verified=evidence.verified,
                    tags=evidence.tags or [],
                    trgm_score=score,
                ))

            log.info("trgm_search_complete", hit_count=len(items))
            return items

        except Exception as e:
            log.error("trgm_search_error", error=str(e))
            return []

    def _merge_results(
        self,
        trgm_results: List[RetrievalResult],
        qdrant_results: List[RetrievalResult],
    ) -> List[RetrievalResult]:
        """
        合并检索结果

        - 去重（按 id）
        - 如果同一 id 在两个结果中都有，计算加权分数
        """
        merged: Dict[str, RetrievalResult] = {}

        # 先添加 trgm 结果
        for r in trgm_results:
            merged[r.id] = RetrievalResult(
                id=r.id,
                source_type=r.source_type,
                source_ref=r.source_ref,
                title=r.title,
                excerpt=r.excerpt,
                score=r.score * self.trgm_weight,
                strategy=RetrievalStrategy.HYBRID,
                confidence=r.confidence,
                verified=r.verified,
                tags=r.tags,
                metadata=r.metadata,
                trgm_score=r.score,
                qdrant_score=None,
            )

        # 合并 qdrant 结果
        for r in qdrant_results:
            if r.id in merged:
                # 已存在，加权融合
                existing = merged[r.id]
                existing.qdrant_score = r.score
                existing.score = (
                    (existing.trgm_score or 0) * self.trgm_weight +
                    r.score * self.qdrant_weight
                )
            else:
                # 新增
                merged[r.id] = RetrievalResult(
                    id=r.id,
                    source_type=r.source_type,
                    source_ref=r.source_ref,
                    title=r.title,
                    excerpt=r.excerpt,
                    score=r.score * self.qdrant_weight,
                    strategy=RetrievalStrategy.HYBRID,
                    confidence=r.confidence,
                    verified=r.verified,
                    tags=r.tags,
                    metadata=r.metadata,
                    trgm_score=None,
                    qdrant_score=r.score,
                )

        return list(merged.values())

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查 Qdrant
            qdrant_ok = await self.qdrant.health_check()
            # 检查数据库连接
            await self.session.execute(text("SELECT 1"))
            return qdrant_ok
        except Exception:
            return False


# ============================================================
# 工厂函数
# ============================================================

async def get_hybrid_retriever(
    session: AsyncSession,
    qdrant_client: Optional[QdrantRetriever] = None,
) -> HybridRetriever:
    """获取混合检索器实例"""
    return HybridRetriever(
        session=session,
        qdrant_client=qdrant_client,
    )
