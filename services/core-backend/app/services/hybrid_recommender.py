"""
混合推荐引擎 (Hybrid Recommender)

结合向量相似度和规则引擎，实现智能推荐。
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Quest, FarmingKnowledge, Content
from app.services.vector_store import VectorStore, get_vector_store
from app.services.context import ContextService
from app.core.logging import get_logger

logger = get_logger(__name__)


class QuestRecommendation:
    """任务推荐结果"""

    def __init__(
        self,
        quest_id: str,
        title: str,
        description: str,
        difficulty: str,
        score: float,
        reason: str,
        source: str,  # "vector" | "rule" | "hybrid"
    ):
        self.quest_id = quest_id
        self.title = title
        self.description = description
        self.difficulty = difficulty
        self.score = score
        self.reason = reason
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "score": self.score,
            "reason": self.reason,
            "source": self.source,
        }


class ContentRecommendation:
    """内容推荐结果"""

    def __init__(
        self,
        content_id: str,
        title: str,
        content_type: str,
        score: float,
        snippet: str,
        source: str,
    ):
        self.content_id = content_id
        self.title = title
        self.content_type = content_type
        self.score = score
        self.snippet = snippet
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_id": self.content_id,
            "title": self.title,
            "content_type": self.content_type,
            "score": self.score,
            "snippet": self.snippet,
            "source": self.source,
        }


class HybridRecommender:
    """混合推荐引擎"""

    def __init__(
        self,
        session: AsyncSession,
        vector_store: Optional[VectorStore] = None,
    ):
        self.session = session
        self.vector_store = vector_store or get_vector_store()
        self.context_service = ContextService(session)

    async def recommend_quests(
        self,
        visitor_id: Optional[UUID] = None,
        tenant_id: str = "yantian",
        site_id: str = "main",
        context: Optional[dict[str, Any]] = None,
        strategy: str = "hybrid",  # "vector" | "rule" | "hybrid"
        top_k: int = 5,
    ) -> list[QuestRecommendation]:
        """
        推荐任务

        Args:
            visitor_id: 游客 ID
            tenant_id: 租户 ID
            site_id: 站点 ID
            context: 上下文信息
            strategy: 推荐策略
            top_k: 返回数量

        Returns:
            推荐任务列表
        """
        recommendations: list[QuestRecommendation] = []

        # 获取上下文
        if context is None and visitor_id:
            context = await self.context_service.build_context(
                visitor_id=visitor_id,
                tenant_id=tenant_id,
                site_id=site_id,
            )

        # 向量召回
        vector_results = []
        if strategy in ["vector", "hybrid"]:
            vector_results = await self._vector_recall_quests(
                context=context,
                tenant_id=tenant_id,
                site_id=site_id,
                top_k=top_k * 2,  # 多召回一些用于过滤
            )

        # 规则召回
        rule_results = []
        if strategy in ["rule", "hybrid"]:
            rule_results = await self._rule_recall_quests(
                visitor_id=visitor_id,
                context=context,
                tenant_id=tenant_id,
                site_id=site_id,
                top_k=top_k * 2,
            )

        # 合并和去重
        seen_ids = set()
        all_results = []

        for r in vector_results:
            if r.quest_id not in seen_ids:
                seen_ids.add(r.quest_id)
                all_results.append(r)

        for r in rule_results:
            if r.quest_id not in seen_ids:
                seen_ids.add(r.quest_id)
                all_results.append(r)

        # 重排序
        all_results = self._rerank_quests(all_results, context)

        return all_results[:top_k]

    async def _vector_recall_quests(
        self,
        context: Optional[dict[str, Any]],
        tenant_id: str,
        site_id: str,
        top_k: int,
    ) -> list[QuestRecommendation]:
        """向量召回任务"""
        results = []

        # 构建查询
        query_parts = []

        if context:
            user_ctx = context.get("user", {})
            env_ctx = context.get("environment", {})

            # 用户兴趣
            tags = user_ctx.get("tags", [])
            if tags:
                query_parts.append(f"兴趣：{'、'.join(tags)}")

            # 节气
            solar_term = env_ctx.get("solar_term", {})
            if solar_term.get("name"):
                query_parts.append(f"节气：{solar_term['name']}")

        if not query_parts:
            query_parts = ["推荐任务"]

        query = " ".join(query_parts)

        try:
            search_results = await self.vector_store.search(
                collection_name="quest_content",
                query=query,
                top_k=top_k,
                filters={"tenant_id": tenant_id, "site_id": site_id},
                score_threshold=0.3,
            )

            for r in search_results:
                results.append(
                    QuestRecommendation(
                        quest_id=r.id,
                        title=r.metadata.get("title", ""),
                        description=r.content[:100],
                        difficulty=r.metadata.get("difficulty", "medium"),
                        score=r.score,
                        reason=f"与您的兴趣相关（相似度 {r.score:.0%}）",
                        source="vector",
                    )
                )
        except Exception as e:
            logger.warning("vector_recall_quests_error", error=str(e))

        return results

    async def _rule_recall_quests(
        self,
        visitor_id: Optional[UUID],
        context: Optional[dict[str, Any]],
        tenant_id: str,
        site_id: str,
        top_k: int,
    ) -> list[QuestRecommendation]:
        """规则召回任务"""
        results = []

        # 查询活跃任务
        query = select(Quest).where(
            Quest.tenant_id == tenant_id,
            Quest.site_id == site_id,
            Quest.status == "active",
        ).limit(top_k)

        result = await self.session.execute(query)
        quests = result.scalars().all()

        for quest in quests:
            score = 0.5  # 基础分
            reason = "推荐任务"

            # 根据上下文调整分数
            if context:
                user_ctx = context.get("user", {})
                env_ctx = context.get("environment", {})

                # 标签匹配
                user_tags = set(user_ctx.get("tags", []))
                quest_tags = set(quest.tags or [])
                if user_tags & quest_tags:
                    score += 0.2
                    reason = f"符合您的兴趣：{'、'.join(user_tags & quest_tags)}"

                # 难度匹配
                stats = user_ctx.get("stats", {})
                completed = stats.get("quest_completed_count", 0)
                if completed < 3 and quest.difficulty == "easy":
                    score += 0.1
                    reason = "适合新手的任务"
                elif completed >= 5 and quest.difficulty == "hard":
                    score += 0.1
                    reason = "挑战性任务"

            results.append(
                QuestRecommendation(
                    quest_id=str(quest.id),
                    title=quest.display_name or quest.name,
                    description=quest.description or "",
                    difficulty=quest.difficulty or "medium",
                    score=score,
                    reason=reason,
                    source="rule",
                )
            )

        return results

    def _rerank_quests(
        self,
        results: list[QuestRecommendation],
        context: Optional[dict[str, Any]],
    ) -> list[QuestRecommendation]:
        """重排序"""
        # 按分数降序排序
        return sorted(results, key=lambda x: x.score, reverse=True)

    async def recommend_content(
        self,
        query: str,
        tenant_id: str = "yantian",
        site_id: str = "main",
        content_type: Optional[str] = None,
        top_k: int = 5,
    ) -> list[ContentRecommendation]:
        """
        推荐内容

        基于查询语义检索相关内容
        """
        results = []

        filters = {"tenant_id": tenant_id, "site_id": site_id}
        if content_type:
            filters["content_type"] = content_type

        try:
            search_results = await self.vector_store.search(
                collection_name="knowledge",
                query=query,
                top_k=top_k,
                filters=filters,
                score_threshold=0.4,
            )

            for r in search_results:
                results.append(
                    ContentRecommendation(
                        content_id=r.id,
                        title=r.metadata.get("title", ""),
                        content_type=r.metadata.get("type", "unknown"),
                        score=r.score,
                        snippet=r.content[:200],
                        source="vector",
                    )
                )
        except Exception as e:
            logger.warning("recommend_content_error", error=str(e))

        return results

    async def find_similar(
        self,
        content: str,
        collection: str = "knowledge",
        top_k: int = 5,
        exclude_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        查找相似内容

        Args:
            content: 内容文本
            collection: Collection 名称
            top_k: 返回数量
            exclude_id: 排除的 ID

        Returns:
            相似内容列表
        """
        results = []

        try:
            search_results = await self.vector_store.search(
                collection_name=collection,
                query=content,
                top_k=top_k + 1,  # 多取一个以便排除自身
                score_threshold=0.5,
            )

            for r in search_results:
                if exclude_id and r.id == exclude_id:
                    continue
                results.append({
                    "id": r.id,
                    "score": r.score,
                    "content": r.content[:200],
                    "metadata": r.metadata,
                })
                if len(results) >= top_k:
                    break

        except Exception as e:
            logger.warning("find_similar_error", error=str(e))

        return results
