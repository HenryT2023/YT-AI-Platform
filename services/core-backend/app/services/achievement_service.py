"""
成就规则引擎服务

提供成就规则解析、检查和自动触发功能
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Achievement,
    UserAchievement,
    VisitorProfile,
    User,
)

logger = logging.getLogger(__name__)


class AchievementService:
    """成就服务"""

    def __init__(self, db: AsyncSession, tenant_id: str, site_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.site_id = site_id

    async def check_and_grant_achievements(
        self,
        user_id: UUID,
        event_name: Optional[str] = None,
        event_data: Optional[dict] = None,
    ) -> list[Achievement]:
        """
        检查并颁发成就
        
        Args:
            user_id: 用户 ID
            event_name: 触发的事件名（可选，用于事件型成就）
            event_data: 事件数据（可选）
        
        Returns:
            新解锁的成就列表
        """
        unlocked_achievements = []

        # 获取用户画像数据
        profile = await self._get_user_profile(user_id)
        if not profile:
            logger.warning(f"用户 {user_id} 没有画像数据，跳过成就检查")
            return unlocked_achievements

        # 获取所有活跃的成就
        achievements = await self._get_active_achievements()

        # 获取用户已解锁的成就 ID
        unlocked_ids = await self._get_user_unlocked_achievement_ids(user_id)

        # 逐个检查成就
        for achievement in achievements:
            if achievement.id in unlocked_ids:
                continue

            # 检查规则是否满足
            is_satisfied, progress = await self._check_rule(
                achievement, profile, event_name, event_data
            )

            if is_satisfied:
                # 颁发成就
                user_achievement = await self._grant_achievement(
                    user_id, achievement, progress, event_name
                )
                if user_achievement:
                    unlocked_achievements.append(achievement)
                    logger.info(
                        f"用户 {user_id} 解锁成就: {achievement.code} ({achievement.name})"
                    )

        return unlocked_achievements

    async def _get_user_profile(self, user_id: UUID) -> Optional[VisitorProfile]:
        """获取用户画像"""
        result = await self.db.execute(
            select(VisitorProfile).where(
                VisitorProfile.user_id == user_id,
                VisitorProfile.tenant_id == self.tenant_id,
                VisitorProfile.site_id == self.site_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_active_achievements(self) -> list[Achievement]:
        """获取所有活跃的成就"""
        result = await self.db.execute(
            select(Achievement).where(
                Achievement.tenant_id == self.tenant_id,
                Achievement.site_id == self.site_id,
                Achievement.is_active == True,
            )
        )
        return list(result.scalars().all())

    async def _get_user_unlocked_achievement_ids(self, user_id: UUID) -> set[UUID]:
        """获取用户已解锁的成就 ID 集合"""
        result = await self.db.execute(
            select(UserAchievement.achievement_id).where(
                UserAchievement.user_id == user_id,
                UserAchievement.tenant_id == self.tenant_id,
                UserAchievement.site_id == self.site_id,
            )
        )
        return {row[0] for row in result.all()}

    async def _check_rule(
        self,
        achievement: Achievement,
        profile: VisitorProfile,
        event_name: Optional[str],
        event_data: Optional[dict],
    ) -> tuple[bool, int]:
        """
        检查成就规则是否满足
        
        Returns:
            (是否满足, 当前进度)
        """
        rule_config = achievement.rule_config or {}
        rule_type = achievement.rule_type

        if rule_type == "count":
            return self._check_count_rule(rule_config, profile)
        elif rule_type == "event":
            return self._check_event_rule(rule_config, event_name, event_data)
        elif rule_type == "composite":
            return await self._check_composite_rule(
                rule_config, profile, event_name, event_data
            )
        else:
            logger.warning(f"未知的规则类型: {rule_type}")
            return False, 0

    def _check_count_rule(
        self, rule_config: dict, profile: VisitorProfile
    ) -> tuple[bool, int]:
        """检查计数型规则"""
        metric = rule_config.get("metric", "")
        threshold = rule_config.get("threshold", 0)
        operator = rule_config.get("operator", "gte")

        # 从画像中获取指标值
        metric_map = {
            "visit_count": profile.visit_count,
            "conversation_count": profile.conversation_count,
            "check_in_count": profile.check_in_count,
            "quest_completed_count": profile.quest_completed_count,
            "achievement_count": profile.achievement_count,
            "total_duration_minutes": profile.total_duration_minutes,
            "engagement_score": profile.engagement_score,
        }

        current_value = metric_map.get(metric, 0)

        # 比较
        if operator == "gte":
            is_satisfied = current_value >= threshold
        elif operator == "gt":
            is_satisfied = current_value > threshold
        elif operator == "eq":
            is_satisfied = current_value == threshold
        else:
            is_satisfied = current_value >= threshold

        return is_satisfied, int(current_value)

    def _check_event_rule(
        self,
        rule_config: dict,
        event_name: Optional[str],
        event_data: Optional[dict],
    ) -> tuple[bool, int]:
        """检查事件型规则"""
        required_event = rule_config.get("event_name", "")
        conditions = rule_config.get("conditions", {})

        if not event_name or event_name != required_event:
            return False, 0

        # 检查条件
        if conditions and event_data:
            for key, expected_value in conditions.items():
                if event_data.get(key) != expected_value:
                    return False, 0

        return True, 1

    async def _check_composite_rule(
        self,
        rule_config: dict,
        profile: VisitorProfile,
        event_name: Optional[str],
        event_data: Optional[dict],
    ) -> tuple[bool, int]:
        """检查组合型规则"""
        operator = rule_config.get("operator", "and")
        sub_rules = rule_config.get("rules", [])

        if not sub_rules:
            return False, 0

        results = []
        total_progress = 0

        for sub_rule in sub_rules:
            sub_type = sub_rule.get("type", "count")
            if sub_type == "count":
                is_satisfied, progress = self._check_count_rule(sub_rule, profile)
            elif sub_type == "event":
                is_satisfied, progress = self._check_event_rule(
                    sub_rule, event_name, event_data
                )
            else:
                is_satisfied, progress = False, 0

            results.append(is_satisfied)
            total_progress += progress

        if operator == "and":
            return all(results), total_progress
        elif operator == "or":
            return any(results), total_progress
        else:
            return all(results), total_progress

    async def _grant_achievement(
        self,
        user_id: UUID,
        achievement: Achievement,
        progress: int,
        event_name: Optional[str],
    ) -> Optional[UserAchievement]:
        """颁发成就给用户"""
        try:
            # 创建用户成就记录
            user_achievement = UserAchievement(
                tenant_id=self.tenant_id,
                site_id=self.site_id,
                user_id=user_id,
                achievement_id=achievement.id,
                progress=progress,
                progress_target=achievement.rule_config.get("threshold", progress),
                source="auto",
                source_ref=event_name,
            )

            self.db.add(user_achievement)

            # 更新游客画像的成就计数
            profile_result = await self.db.execute(
                select(VisitorProfile).where(
                    VisitorProfile.user_id == user_id,
                    VisitorProfile.tenant_id == self.tenant_id,
                    VisitorProfile.site_id == self.site_id,
                )
            )
            profile = profile_result.scalar_one_or_none()
            if profile:
                profile.achievement_count += 1

            await self.db.flush()
            return user_achievement

        except Exception as e:
            logger.error(f"颁发成就失败: {e}")
            return None

    async def update_user_progress(
        self, user_id: UUID, achievement_id: UUID, progress: int
    ) -> Optional[UserAchievement]:
        """
        更新用户成就进度（用于未解锁的成就）
        
        注意：这个方法用于追踪进度，不会自动解锁成就
        """
        result = await self.db.execute(
            select(UserAchievement).where(
                UserAchievement.user_id == user_id,
                UserAchievement.achievement_id == achievement_id,
            )
        )
        user_achievement = result.scalar_one_or_none()

        if user_achievement:
            user_achievement.progress = progress
            await self.db.flush()
            return user_achievement

        return None


async def check_achievements_for_user(
    db: AsyncSession,
    tenant_id: str,
    site_id: str,
    user_id: UUID,
    event_name: Optional[str] = None,
    event_data: Optional[dict] = None,
) -> list[Achievement]:
    """
    便捷函数：检查并颁发用户成就
    
    可以在各个业务逻辑中调用此函数来触发成就检查
    """
    service = AchievementService(db, tenant_id, site_id)
    return await service.check_and_grant_achievements(user_id, event_name, event_data)
