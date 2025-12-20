"""
站点管理服务 (Site Manager)

提供站点 CRUD、初始化、统计等功能。
"""

from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Site,
    SiteStatsDaily,
    Quest,
    NPCProfile,
    Achievement,
    VisitorProfile,
    VisitorCheckIn,
    Conversation,
    Message,
    UserAchievement,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class SiteManager:
    """站点管理服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============================================================
    # 站点 CRUD
    # ============================================================

    async def list_sites(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Site], int]:
        """列出站点"""
        query = select(Site).where(Site.tenant_id == tenant_id)

        if status:
            query = query.where(Site.status == status)

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        # 分页
        query = query.offset(offset).limit(limit).order_by(Site.created_at.desc())
        result = await self.session.execute(query)
        sites = list(result.scalars().all())

        return sites, total

    async def get_site(self, site_id: str) -> Optional[Site]:
        """获取站点详情"""
        result = await self.session.execute(
            select(Site).where(Site.id == site_id)
        )
        return result.scalar_one_or_none()

    async def create_site(
        self,
        tenant_id: str,
        site_id: str,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        config: Optional[dict] = None,
        theme: Optional[dict] = None,
        features: Optional[dict] = None,
    ) -> Site:
        """创建站点"""
        site = Site(
            id=site_id,
            tenant_id=tenant_id,
            name=name,
            display_name=display_name or name,
            description=description,
            config=config or {},
            theme=theme or {},
            features=features or {
                "quest_enabled": True,
                "npc_enabled": True,
                "iot_enabled": False,
            },
            status="active",
        )

        self.session.add(site)
        await self.session.commit()
        await self.session.refresh(site)

        logger.info("site_created", site_id=site_id, tenant_id=tenant_id)
        return site

    async def update_site(
        self,
        site_id: str,
        **kwargs,
    ) -> Optional[Site]:
        """更新站点"""
        site = await self.get_site(site_id)
        if not site:
            return None

        allowed_fields = [
            "name", "display_name", "description", "logo_url",
            "config", "theme", "features", "operating_hours",
            "contact_info", "location_lat", "location_lng",
            "address", "timezone", "status",
        ]

        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(site, key, value)

        site.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(site)

        logger.info("site_updated", site_id=site_id)
        return site

    async def delete_site(self, site_id: str, soft: bool = True) -> bool:
        """删除站点（默认软删除）"""
        site = await self.get_site(site_id)
        if not site:
            return False

        if soft:
            site.status = "disabled"
            site.updated_at = datetime.utcnow()
        else:
            await self.session.delete(site)

        await self.session.commit()
        logger.info("site_deleted", site_id=site_id, soft=soft)
        return True

    # ============================================================
    # 站点配置
    # ============================================================

    async def get_site_config(self, site_id: str) -> Optional[dict[str, Any]]:
        """获取站点配置"""
        site = await self.get_site(site_id)
        if not site:
            return None

        return {
            "id": site.id,
            "tenant_id": site.tenant_id,
            "name": site.name,
            "display_name": site.display_name,
            "description": site.description,
            "logo_url": site.logo_url,
            "config": site.config,
            "theme": site.theme,
            "features": site.features,
            "operating_hours": site.operating_hours,
            "contact_info": site.contact_info,
            "location": {
                "lat": site.location_lat,
                "lng": site.location_lng,
                "address": site.address,
            },
            "timezone": site.timezone,
            "status": site.status,
        }

    async def update_site_config(
        self,
        site_id: str,
        config: Optional[dict] = None,
        theme: Optional[dict] = None,
        features: Optional[dict] = None,
    ) -> Optional[Site]:
        """更新站点配置"""
        site = await self.get_site(site_id)
        if not site:
            return None

        if config is not None:
            site.config = {**site.config, **config}
        if theme is not None:
            site.theme = {**site.theme, **theme}
        if features is not None:
            site.features = {**site.features, **features}

        site.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(site)

        return site

    # ============================================================
    # 站点统计
    # ============================================================

    async def get_site_stats(
        self,
        site_id: str,
        period: str = "7d",  # "1d" | "7d" | "30d"
    ) -> dict[str, Any]:
        """获取站点统计"""
        site = await self.get_site(site_id)
        if not site:
            return {}

        # 计算日期范围
        days = {"1d": 1, "7d": 7, "30d": 30}.get(period, 7)
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        # 查询统计数据
        result = await self.session.execute(
            select(SiteStatsDaily).where(
                SiteStatsDaily.site_id == site_id,
                SiteStatsDaily.stat_date >= start_date,
                SiteStatsDaily.stat_date <= end_date,
            ).order_by(SiteStatsDaily.stat_date)
        )
        stats_list = list(result.scalars().all())

        # 汇总
        totals = {
            "visitor_uv": 0,
            "visitor_pv": 0,
            "new_visitors": 0,
            "quest_started": 0,
            "quest_completed": 0,
            "npc_conversations": 0,
            "npc_messages": 0,
            "achievements_unlocked": 0,
            "check_ins": 0,
        }

        daily_data = []
        for stat in stats_list:
            totals["visitor_uv"] += stat.visitor_uv
            totals["visitor_pv"] += stat.visitor_pv
            totals["new_visitors"] += stat.new_visitors
            totals["quest_started"] += stat.quest_started
            totals["quest_completed"] += stat.quest_completed
            totals["npc_conversations"] += stat.npc_conversations
            totals["npc_messages"] += stat.npc_messages
            totals["achievements_unlocked"] += stat.achievements_unlocked
            totals["check_ins"] += stat.check_ins

            daily_data.append({
                "date": stat.stat_date.isoformat(),
                "visitor_uv": stat.visitor_uv,
                "visitor_pv": stat.visitor_pv,
                "quest_completed": stat.quest_completed,
                "npc_conversations": stat.npc_conversations,
            })

        # 实时统计（如果没有历史数据）
        if not stats_list:
            totals = await self._calculate_realtime_stats(site_id, site.tenant_id)

        return {
            "site_id": site_id,
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "totals": totals,
            "daily": daily_data,
        }

    async def _calculate_realtime_stats(
        self,
        site_id: str,
        tenant_id: str,
    ) -> dict[str, int]:
        """计算实时统计"""
        stats = {
            "visitor_uv": 0,
            "visitor_pv": 0,
            "new_visitors": 0,
            "quest_started": 0,
            "quest_completed": 0,
            "npc_conversations": 0,
            "npc_messages": 0,
            "achievements_unlocked": 0,
            "check_ins": 0,
        }

        # 访客数
        visitor_count = await self.session.scalar(
            select(func.count()).select_from(VisitorProfile).where(
                VisitorProfile.tenant_id == tenant_id,
                VisitorProfile.site_id == site_id,
            )
        )
        stats["visitor_uv"] = visitor_count or 0

        # 对话数
        conv_count = await self.session.scalar(
            select(func.count()).select_from(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.site_id == site_id,
            )
        )
        stats["npc_conversations"] = conv_count or 0

        # 打卡数
        checkin_count = await self.session.scalar(
            select(func.count()).select_from(VisitorCheckIn).where(
                VisitorCheckIn.tenant_id == tenant_id,
                VisitorCheckIn.site_id == site_id,
            )
        )
        stats["check_ins"] = checkin_count or 0

        return stats

    async def record_daily_stats(self, site_id: str) -> Optional[SiteStatsDaily]:
        """记录每日统计快照"""
        site = await self.get_site(site_id)
        if not site:
            return None

        today = date.today()

        # 检查是否已存在
        existing = await self.session.scalar(
            select(SiteStatsDaily).where(
                SiteStatsDaily.site_id == site_id,
                SiteStatsDaily.stat_date == today,
            )
        )

        if existing:
            return existing

        # 计算统计
        stats = await self._calculate_realtime_stats(site_id, site.tenant_id)

        # 创建记录
        daily_stat = SiteStatsDaily(
            site_id=site_id,
            stat_date=today,
            **stats,
        )

        self.session.add(daily_stat)
        await self.session.commit()
        await self.session.refresh(daily_stat)

        return daily_stat

    # ============================================================
    # 站点初始化
    # ============================================================

    async def init_site(
        self,
        site_id: str,
        template: str = "default",  # "default" | "minimal" | "full"
    ) -> dict[str, Any]:
        """
        初始化站点基础数据

        Args:
            site_id: 站点 ID
            template: 初始化模板

        Returns:
            初始化结果
        """
        site = await self.get_site(site_id)
        if not site:
            return {"success": False, "error": "Site not found"}

        result = {
            "success": True,
            "site_id": site_id,
            "template": template,
            "created": {
                "npcs": 0,
                "quests": 0,
                "achievements": 0,
            },
        }

        tenant_id = site.tenant_id

        # 根据模板初始化
        if template in ["default", "full"]:
            # 创建默认 NPC
            npcs_created = await self._init_default_npcs(tenant_id, site_id)
            result["created"]["npcs"] = npcs_created

            # 创建默认任务
            quests_created = await self._init_default_quests(tenant_id, site_id)
            result["created"]["quests"] = quests_created

            # 创建默认成就
            achievements_created = await self._init_default_achievements(tenant_id, site_id)
            result["created"]["achievements"] = achievements_created

        logger.info("site_initialized", site_id=site_id, template=template, result=result)
        return result

    async def _init_default_npcs(self, tenant_id: str, site_id: str) -> int:
        """初始化默认 NPC"""
        default_npcs = [
            {
                "npc_id": f"{site_id}_guide",
                "name": "导游小李",
                "role": "景区导游",
                "intro": "热情的景区导游，熟悉这里的每一个角落。",
                "avatar_emoji": "👨‍🦱",
            },
            {
                "npc_id": f"{site_id}_elder",
                "name": "村长伯伯",
                "role": "村中长者",
                "intro": "德高望重的村长，见证了村庄的变迁。",
                "avatar_emoji": "👴",
            },
        ]

        count = 0
        for npc_data in default_npcs:
            # 检查是否已存在
            existing = await self.session.scalar(
                select(NPCProfile).where(
                    NPCProfile.npc_id == npc_data["npc_id"],
                    NPCProfile.tenant_id == tenant_id,
                )
            )
            if existing:
                continue

            npc = NPCProfile(
                tenant_id=tenant_id,
                site_id=site_id,
                npc_id=npc_data["npc_id"],
                name=npc_data["name"],
                role=npc_data["role"],
                intro=npc_data["intro"],
                avatar_emoji=npc_data["avatar_emoji"],
                persona={},
                status="active",
            )
            self.session.add(npc)
            count += 1

        if count > 0:
            await self.session.commit()

        return count

    async def _init_default_quests(self, tenant_id: str, site_id: str) -> int:
        """初始化默认任务"""
        default_quests = [
            {
                "name": "welcome_quest",
                "display_name": "欢迎来到这里",
                "description": "完成新手引导，了解基本功能。",
                "quest_type": "onboarding",
                "category": "tutorial",
                "difficulty": "easy",
            },
            {
                "name": "first_chat",
                "display_name": "第一次对话",
                "description": "与任意一位村民进行对话。",
                "quest_type": "interaction",
                "category": "social",
                "difficulty": "easy",
            },
        ]

        count = 0
        for quest_data in default_quests:
            # 检查是否已存在
            existing = await self.session.scalar(
                select(Quest).where(
                    Quest.name == quest_data["name"],
                    Quest.tenant_id == tenant_id,
                    Quest.site_id == site_id,
                )
            )
            if existing:
                continue

            quest = Quest(
                tenant_id=tenant_id,
                site_id=site_id,
                **quest_data,
                status="active",
            )
            self.session.add(quest)
            count += 1

        if count > 0:
            await self.session.commit()

        return count

    async def _init_default_achievements(self, tenant_id: str, site_id: str) -> int:
        """初始化默认成就"""
        default_achievements = [
            {
                "name": "first_visit",
                "display_name": "初来乍到",
                "description": "首次访问站点",
                "category": "exploration",
                "tier": "bronze",
                "rule_type": "count",
                "rule_config": {"event": "visit", "threshold": 1},
            },
            {
                "name": "first_chat",
                "display_name": "初次交流",
                "description": "完成第一次 NPC 对话",
                "category": "social",
                "tier": "bronze",
                "rule_type": "count",
                "rule_config": {"event": "npc_chat", "threshold": 1},
            },
        ]

        count = 0
        for ach_data in default_achievements:
            # 检查是否已存在
            existing = await self.session.scalar(
                select(Achievement).where(
                    Achievement.name == ach_data["name"],
                    Achievement.tenant_id == tenant_id,
                    Achievement.site_id == site_id,
                )
            )
            if existing:
                continue

            achievement = Achievement(
                tenant_id=tenant_id,
                site_id=site_id,
                **ach_data,
            )
            self.session.add(achievement)
            count += 1

        if count > 0:
            await self.session.commit()

        return count
