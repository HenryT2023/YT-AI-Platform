"""
上下文构建服务 (Context Service)

聚合游客画像、节气环境、IoT 状态等多源数据，
为 AI 编排层提供统一的"世界状态"上下文。
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    VisitorProfile,
    VisitorTag,
    VisitorCheckIn,
    VisitorInteraction,
    Achievement,
    UserAchievement,
    Quest,
    QuestSubmission,
    SolarTerm,
    IoTDevice,
    DeviceStatus,
)


class ContextService:
    """上下文构建服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def build_context(
        self,
        tenant_id: str,
        site_id: str,
        visitor_id: Optional[UUID] = None,
        session_id: Optional[str] = None,
        location: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        构建完整的上下文数据

        Args:
            tenant_id: 租户 ID
            site_id: 站点 ID
            visitor_id: 游客 ID（可选，匿名游客可不传）
            session_id: 会话 ID（用于匿名游客临时画像）
            location: 当前位置（可选）

        Returns:
            结构化的上下文 JSON
        """
        user_context = await self._build_user_context(tenant_id, site_id, visitor_id)
        env_context = await self._build_environment_context(tenant_id, site_id)

        return {
            "user": user_context,
            "environment": env_context,
            "meta": {
                "tenant_id": tenant_id,
                "site_id": site_id,
                "location": location,
                "timestamp": datetime.utcnow().isoformat(),
            },
        }

    async def _build_user_context(
        self,
        tenant_id: str,
        site_id: str,
        visitor_id: Optional[UUID],
    ) -> dict[str, Any]:
        """构建用户上下文"""
        if not visitor_id:
            return {
                "is_anonymous": True,
                "name": None,
                "tags": [],
                "stats": {
                    "quest_completed_count": 0,
                    "check_in_count": 0,
                    "npc_interaction_count": 0,
                },
                "recent_quests": [],
                "unlocked_achievements": [],
            }

        # 获取游客画像
        profile_result = await self.session.execute(
            select(VisitorProfile).where(
                VisitorProfile.tenant_id == tenant_id,
                VisitorProfile.site_id == site_id,
                VisitorProfile.visitor_id == visitor_id,
            )
        )
        profile = profile_result.scalar_one_or_none()

        if not profile:
            return {
                "is_anonymous": True,
                "id": str(visitor_id),
                "name": None,
                "tags": [],
                "stats": {
                    "quest_completed_count": 0,
                    "check_in_count": 0,
                    "npc_interaction_count": 0,
                },
                "recent_quests": [],
                "unlocked_achievements": [],
            }

        # 获取标签
        tags_result = await self.session.execute(
            select(VisitorTag.tag_name).where(
                VisitorTag.tenant_id == tenant_id,
                VisitorTag.site_id == site_id,
                VisitorTag.visitor_id == visitor_id,
            )
        )
        tags = [row[0] for row in tags_result.fetchall()]

        # 获取最近完成的任务
        recent_quests_result = await self.session.execute(
            select(Quest.title)
            .join(QuestSubmission, Quest.id == QuestSubmission.quest_id)
            .where(
                QuestSubmission.tenant_id == tenant_id,
                QuestSubmission.site_id == site_id,
                QuestSubmission.visitor_id == visitor_id,
                QuestSubmission.status == "approved",
            )
            .order_by(QuestSubmission.updated_at.desc())
            .limit(5)
        )
        recent_quests = [row[0] for row in recent_quests_result.fetchall()]

        # 获取已解锁成就
        achievements_result = await self.session.execute(
            select(Achievement.name)
            .join(UserAchievement, Achievement.id == UserAchievement.achievement_id)
            .where(
                UserAchievement.tenant_id == tenant_id,
                UserAchievement.site_id == site_id,
                UserAchievement.user_id == visitor_id,
            )
            .order_by(UserAchievement.unlocked_at.desc())
            .limit(10)
        )
        unlocked_achievements = [row[0] for row in achievements_result.fetchall()]

        return {
            "is_anonymous": False,
            "id": str(visitor_id),
            "name": profile.nickname,
            "avatar": profile.avatar_url,
            "tags": tags,
            "stats": {
                "quest_completed_count": profile.quest_completed_count or 0,
                "check_in_count": profile.check_in_count or 0,
                "npc_interaction_count": profile.npc_interaction_count or 0,
                "total_points": profile.total_points or 0,
            },
            "recent_quests": recent_quests,
            "unlocked_achievements": unlocked_achievements,
            "preferences": profile.preferences or {},
        }

    async def _build_environment_context(
        self,
        tenant_id: str,
        site_id: str,
    ) -> dict[str, Any]:
        """构建环境上下文"""
        # 获取当前节气
        solar_term = await self._get_current_solar_term()

        # 获取 IoT 设备状态统计
        iot_stats = await self._get_iot_stats(tenant_id, site_id)

        # 计算时段
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 9:
            time_of_day = "early_morning"
            time_of_day_cn = "清晨"
        elif 9 <= hour < 12:
            time_of_day = "morning"
            time_of_day_cn = "上午"
        elif 12 <= hour < 14:
            time_of_day = "noon"
            time_of_day_cn = "中午"
        elif 14 <= hour < 17:
            time_of_day = "afternoon"
            time_of_day_cn = "下午"
        elif 17 <= hour < 19:
            time_of_day = "evening"
            time_of_day_cn = "傍晚"
        else:
            time_of_day = "night"
            time_of_day_cn = "夜间"

        return {
            "solar_term": solar_term,
            "time_of_day": time_of_day,
            "time_of_day_cn": time_of_day_cn,
            "current_time": now.strftime("%H:%M"),
            "current_date": now.strftime("%Y-%m-%d"),
            "iot_status": iot_stats,
        }

    async def _get_current_solar_term(self) -> dict[str, Any]:
        """获取当前节气"""
        now = datetime.now()
        month = now.month
        day = now.day

        # 精确匹配当前日期
        result = await self.session.execute(
            select(SolarTerm).where(
                SolarTerm.month == month,
                SolarTerm.day_start <= day,
                SolarTerm.day_end >= day,
            )
        )
        term = result.scalar_one_or_none()

        # 如果没有精确匹配，找当月最近的节气
        if not term:
            result = await self.session.execute(
                select(SolarTerm)
                .where(SolarTerm.month == month)
                .order_by(SolarTerm.day_start)
            )
            terms = result.scalars().all()
            if terms:
                for t in terms:
                    if day >= t.day_start:
                        term = t
                if not term:
                    term = terms[0]

        if not term:
            return {
                "code": "unknown",
                "name": "未知",
                "description": None,
                "farming_advice": None,
                "poem": None,
            }

        poem = None
        if term.poems and len(term.poems) > 0:
            poem = term.poems[0].get("content")

        return {
            "code": term.code,
            "name": term.name,
            "order": term.order,
            "description": term.description,
            "farming_advice": term.farming_advice,
            "cultural_customs": term.cultural_customs,
            "poem": poem,
        }

    async def _get_iot_stats(
        self,
        tenant_id: str,
        site_id: str,
    ) -> dict[str, Any]:
        """获取 IoT 设备状态统计"""
        # 统计各状态设备数量
        result = await self.session.execute(
            select(
                IoTDevice.status,
                func.count(IoTDevice.id).label("count"),
            )
            .where(
                IoTDevice.tenant_id == tenant_id,
                IoTDevice.site_id == site_id,
                IoTDevice.is_active == True,
            )
            .group_by(IoTDevice.status)
        )
        stats = {row[0]: row[1] for row in result.fetchall()}

        # 获取故障设备列表
        error_devices_result = await self.session.execute(
            select(IoTDevice.name, IoTDevice.device_code)
            .where(
                IoTDevice.tenant_id == tenant_id,
                IoTDevice.site_id == site_id,
                IoTDevice.status == DeviceStatus.ERROR,
                IoTDevice.is_active == True,
            )
            .limit(5)
        )
        alerts = [
            {"name": row[0], "code": row[1]}
            for row in error_devices_result.fetchall()
        ]

        return {
            "online_count": stats.get(DeviceStatus.ONLINE, 0),
            "offline_count": stats.get(DeviceStatus.OFFLINE, 0),
            "error_count": stats.get(DeviceStatus.ERROR, 0),
            "alerts": alerts,
        }

    async def get_user_context_summary(
        self,
        tenant_id: str,
        site_id: str,
        visitor_id: UUID,
    ) -> str:
        """
        生成用户上下文的自然语言摘要，用于注入 Prompt

        Returns:
            自然语言描述的用户画像摘要
        """
        user_ctx = await self._build_user_context(tenant_id, site_id, visitor_id)

        if user_ctx.get("is_anonymous"):
            return "这是一位新游客，暂无历史记录。"

        parts = []

        name = user_ctx.get("name")
        if name:
            parts.append(f'游客"{name}"')
        else:
            parts.append("这位游客")

        tags = user_ctx.get("tags", [])
        if tags:
            parts.append(f"，兴趣标签：{', '.join(tags[:3])}")

        stats = user_ctx.get("stats", {})
        quest_count = stats.get("quest_completed_count", 0)
        checkin_count = stats.get("check_in_count", 0)

        if quest_count > 0 or checkin_count > 0:
            parts.append(f"。已完成{quest_count}个任务，打卡{checkin_count}次")

        recent = user_ctx.get("recent_quests", [])
        if recent:
            parts.append(f"。最近完成的任务：{', '.join(recent[:2])}")

        achievements = user_ctx.get("unlocked_achievements", [])
        if achievements:
            parts.append(f"。已获得成就：{', '.join(achievements[:3])}")

        return "".join(parts) + "。"
