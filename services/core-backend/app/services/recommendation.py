"""
推荐服务 (Recommendation Service)

基于规则引擎的智能推荐，根据游客画像、节气和行为数据
推荐任务、话题和成就目标。
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, not_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    VisitorProfile,
    VisitorTag,
    Achievement,
    UserAchievement,
    Quest,
    QuestSubmission,
    SolarTerm,
    FarmingKnowledge,
)
from app.services.context import ContextService


class RecommendationService:
    """推荐服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.context_service = ContextService(session)

    async def get_home_recommendations(
        self,
        tenant_id: str,
        site_id: str,
        visitor_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        """
        获取首页聚合推荐数据

        Returns:
            包含节气贴士、推荐任务、成就提示的聚合数据
        """
        # 构建上下文
        context = await self.context_service.build_context(
            tenant_id=tenant_id,
            site_id=site_id,
            visitor_id=visitor_id,
        )

        # 获取节气相关内容
        solar_term_content = await self._get_solar_term_content(
            tenant_id, site_id, context["environment"]["solar_term"]
        )

        # 获取推荐任务
        recommended_quests = await self._get_recommended_quests(
            tenant_id, site_id, visitor_id, context["user"]
        )

        # 获取成就进度提示
        achievement_hints = await self._get_achievement_hints(
            tenant_id, site_id, visitor_id
        )

        # 获取推荐话题
        topics = await self._get_recommended_topics(
            context["user"], context["environment"]
        )

        return {
            "solar_term": solar_term_content,
            "recommended_quests": recommended_quests,
            "achievement_hints": achievement_hints,
            "topics": topics,
            "greeting": self._generate_greeting(context),
        }

    async def _get_solar_term_content(
        self,
        tenant_id: str,
        site_id: str,
        solar_term: dict[str, Any],
    ) -> dict[str, Any]:
        """获取节气相关内容"""
        term_code = solar_term.get("code")

        # 获取相关农耕知识
        knowledge_result = await self.session.execute(
            select(FarmingKnowledge)
            .where(
                FarmingKnowledge.tenant_id == tenant_id,
                FarmingKnowledge.site_id == site_id,
                FarmingKnowledge.solar_term_code == term_code,
                FarmingKnowledge.is_active == True,
            )
            .order_by(FarmingKnowledge.sort_order)
            .limit(3)
        )
        knowledge_items = knowledge_result.scalars().all()

        return {
            "name": solar_term.get("name"),
            "description": solar_term.get("description"),
            "farming_advice": solar_term.get("farming_advice"),
            "poem": solar_term.get("poem"),
            "customs": solar_term.get("cultural_customs", {}).get("customs", []),
            "foods": solar_term.get("cultural_customs", {}).get("foods", []),
            "related_knowledge": [
                {
                    "id": str(k.id),
                    "title": k.title,
                    "category": k.category,
                    "content": k.content[:100] + "..." if len(k.content) > 100 else k.content,
                }
                for k in knowledge_items
            ],
        }

    async def _get_recommended_quests(
        self,
        tenant_id: str,
        site_id: str,
        visitor_id: Optional[UUID],
        user_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """获取推荐任务"""
        # 获取用户已完成的任务 ID
        completed_quest_ids = []
        if visitor_id:
            completed_result = await self.session.execute(
                select(QuestSubmission.quest_id)
                .where(
                    QuestSubmission.tenant_id == tenant_id,
                    QuestSubmission.site_id == site_id,
                    QuestSubmission.visitor_id == visitor_id,
                    QuestSubmission.status == "approved",
                )
            )
            completed_quest_ids = [row[0] for row in completed_result.fetchall()]

        # 查询未完成的活跃任务
        query = select(Quest).where(
            Quest.tenant_id == tenant_id,
            Quest.site_id == site_id,
            Quest.status == "active",
        )

        if completed_quest_ids:
            query = query.where(not_(Quest.id.in_(completed_quest_ids)))

        query = query.order_by(Quest.sort_order).limit(5)

        result = await self.session.execute(query)
        quests = result.scalars().all()

        # 根据用户标签计算推荐理由
        user_tags = set(user_context.get("tags", []))

        recommendations = []
        for quest in quests:
            reason = self._calculate_quest_reason(quest, user_tags, user_context)
            recommendations.append({
                "id": str(quest.id),
                "title": quest.title,
                "description": quest.description,
                "type": quest.type,
                "difficulty": quest.difficulty,
                "estimated_duration": quest.estimated_duration,
                "reward_points": quest.reward_points,
                "reason": reason,
            })

        return recommendations

    def _calculate_quest_reason(
        self,
        quest: Quest,
        user_tags: set[str],
        user_context: dict[str, Any],
    ) -> str:
        """计算任务推荐理由"""
        quest_tags = set(quest.tags or [])

        # 标签匹配
        matched_tags = user_tags & quest_tags
        if matched_tags:
            return f"基于您的兴趣「{'、'.join(list(matched_tags)[:2])}」推荐"

        # 新手推荐
        if user_context.get("stats", {}).get("quest_completed_count", 0) == 0:
            if quest.difficulty == "easy":
                return "适合新手的入门任务"

        # 难度匹配
        completed_count = user_context.get("stats", {}).get("quest_completed_count", 0)
        if completed_count >= 5 and quest.difficulty == "hard":
            return "挑战高难度任务"
        elif completed_count >= 2 and quest.difficulty == "medium":
            return "进阶任务推荐"

        return "热门任务"

    async def _get_achievement_hints(
        self,
        tenant_id: str,
        site_id: str,
        visitor_id: Optional[UUID],
    ) -> list[dict[str, Any]]:
        """获取成就进度提示"""
        if not visitor_id:
            return []

        # 获取用户已解锁的成就 ID
        unlocked_result = await self.session.execute(
            select(UserAchievement.achievement_id)
            .where(
                UserAchievement.tenant_id == tenant_id,
                UserAchievement.site_id == site_id,
                UserAchievement.user_id == visitor_id,
            )
        )
        unlocked_ids = [row[0] for row in unlocked_result.fetchall()]

        # 获取用户画像统计
        profile_result = await self.session.execute(
            select(VisitorProfile)
            .where(
                VisitorProfile.tenant_id == tenant_id,
                VisitorProfile.site_id == site_id,
                VisitorProfile.visitor_id == visitor_id,
            )
        )
        profile = profile_result.scalar_one_or_none()

        if not profile:
            return []

        # 查询未解锁的计数型成就
        query = select(Achievement).where(
            Achievement.tenant_id == tenant_id,
            Achievement.site_id == site_id,
            Achievement.is_active == True,
            Achievement.rule_type == "count",
        )

        if unlocked_ids:
            query = query.where(not_(Achievement.id.in_(unlocked_ids)))

        result = await self.session.execute(query.limit(5))
        achievements = result.scalars().all()

        hints = []
        for ach in achievements:
            rule_config = ach.rule_config or {}
            event = rule_config.get("event", "")
            threshold = rule_config.get("threshold", 0)

            # 计算当前进度
            current = 0
            if event == "quest_completed":
                current = profile.quest_completed_count or 0
            elif event == "check_in":
                current = profile.check_in_count or 0
            elif event == "npc_interaction":
                current = profile.npc_interaction_count or 0

            if current > 0 and current < threshold:
                progress_pct = int((current / threshold) * 100)
                remaining = threshold - current
                hints.append({
                    "id": str(ach.id),
                    "name": ach.name,
                    "description": ach.description,
                    "icon": ach.icon,
                    "progress": f"{current}/{threshold}",
                    "progress_pct": progress_pct,
                    "hint": f"再{self._get_action_name(event)}{remaining}次即可解锁",
                })

        # 按进度排序，接近完成的优先
        hints.sort(key=lambda x: x["progress_pct"], reverse=True)
        return hints[:3]

    def _get_action_name(self, event: str) -> str:
        """获取事件对应的动作名称"""
        mapping = {
            "quest_completed": "完成任务",
            "check_in": "打卡",
            "npc_interaction": "与NPC对话",
        }
        return mapping.get(event, "操作")

    async def _get_recommended_topics(
        self,
        user_context: dict[str, Any],
        env_context: dict[str, Any],
    ) -> list[str]:
        """获取推荐对话话题"""
        topics = []

        # 基于节气的话题
        solar_term = env_context.get("solar_term", {})
        term_name = solar_term.get("name")
        if term_name:
            topics.append(f"{term_name}的农耕习俗")
            customs = solar_term.get("cultural_customs", {}).get("customs", [])
            if customs:
                topics.append(customs[0])

        # 基于时段的话题
        time_cn = env_context.get("time_of_day_cn")
        if time_cn == "清晨":
            topics.append("晨起养生之道")
        elif time_cn == "夜间":
            topics.append("夜游祠堂的故事")

        # 基于用户标签的话题
        tags = user_context.get("tags", [])
        if "亲子" in tags:
            topics.append("适合孩子的农耕体验")
        if "摄影" in tags or "摄影爱好者" in tags:
            topics.append("最佳拍摄点推荐")
        if "历史" in tags or "文化" in tags:
            topics.append("徽派建筑的历史")

        # 基于行为的话题
        recent_quests = user_context.get("recent_quests", [])
        if recent_quests:
            topics.append(f"关于「{recent_quests[0]}」的更多故事")

        return topics[:5]

    def _generate_greeting(self, context: dict[str, Any]) -> str:
        """生成个性化问候语"""
        user = context.get("user", {})
        env = context.get("environment", {})

        time_cn = env.get("time_of_day_cn", "")
        term_name = env.get("solar_term", {}).get("name", "")
        name = user.get("name")

        greeting_parts = []

        # 时段问候
        time_greetings = {
            "清晨": "早安",
            "上午": "上午好",
            "中午": "中午好",
            "下午": "下午好",
            "傍晚": "傍晚好",
            "夜间": "晚上好",
        }
        greeting_parts.append(time_greetings.get(time_cn, "您好"))

        # 称呼
        if name:
            greeting_parts[0] += f"，{name}"
        else:
            greeting_parts[0] += "，欢迎来到严田"

        # 节气提示
        if term_name:
            greeting_parts.append(f"今日正值{term_name}时节")

        # 个性化提示
        if not user.get("is_anonymous"):
            quest_count = user.get("stats", {}).get("quest_completed_count", 0)
            if quest_count == 0:
                greeting_parts.append("开启您的研学之旅吧")
            elif quest_count < 3:
                greeting_parts.append("继续探索更多精彩")
            else:
                greeting_parts.append("欢迎回来，资深探索者")

        return "，".join(greeting_parts) + "！"
