"""
研学任务服务

处理任务进度、验证、奖励等业务逻辑
"""

from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.quest import Quest, QuestStep
from app.domain.visitor import Visitor, VisitorQuest

logger = get_logger(__name__)


class QuestService:
    """研学任务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_available_quests(
        self,
        site_id: str,
        visitor_id: Optional[UUID] = None,
    ) -> List[Quest]:
        """获取可用任务列表"""
        query = select(Quest).where(
            Quest.site_id == site_id,
            Quest.status == "published",
            Quest.deleted_at.is_(None),
        ).order_by(Quest.sort_order)

        result = await self.db.execute(query)
        quests = list(result.scalars().all())

        # TODO: 根据 visitor 的完成情况过滤前置任务
        return quests

    async def start_quest(
        self,
        visitor_id: UUID,
        quest_id: UUID,
    ) -> VisitorQuest:
        """开始任务"""
        # 检查是否已开始
        existing = await self.db.execute(
            select(VisitorQuest).where(
                VisitorQuest.visitor_id == visitor_id,
                VisitorQuest.quest_id == quest_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Quest already started")

        visitor_quest = VisitorQuest(
            visitor_id=visitor_id,
            quest_id=quest_id,
            status="in_progress",
            current_step=1,
        )
        self.db.add(visitor_quest)
        await self.db.flush()
        await self.db.refresh(visitor_quest)

        logger.info("quest_started", visitor_id=str(visitor_id), quest_id=str(quest_id))
        return visitor_quest

    async def submit_step(
        self,
        visitor_id: UUID,
        quest_id: UUID,
        step_number: int,
        answer: Optional[str] = None,
        location: Optional[dict[str, float]] = None,
    ) -> dict[str, Any]:
        """提交任务步骤"""
        # 获取任务进度
        result = await self.db.execute(
            select(VisitorQuest).where(
                VisitorQuest.visitor_id == visitor_id,
                VisitorQuest.quest_id == quest_id,
            )
        )
        visitor_quest = result.scalar_one_or_none()
        if not visitor_quest:
            raise ValueError("Quest not started")

        if visitor_quest.status == "completed":
            raise ValueError("Quest already completed")

        if step_number != visitor_quest.current_step:
            raise ValueError(f"Expected step {visitor_quest.current_step}, got {step_number}")

        # 获取步骤信息
        step_result = await self.db.execute(
            select(QuestStep).where(
                QuestStep.quest_id == quest_id,
                QuestStep.step_number == step_number,
            )
        )
        step = step_result.scalar_one_or_none()
        if not step:
            raise ValueError(f"Step {step_number} not found")

        # 验证答案
        validation = step.validation or {}
        passed = self._validate_step(validation, answer, location)

        if passed:
            # 更新进度
            progress = visitor_quest.progress or {}
            progress[str(step_number)] = {
                "completed": True,
                "answer": answer,
            }
            visitor_quest.progress = progress

            # 检查是否完成所有步骤
            total_steps_result = await self.db.execute(
                select(QuestStep).where(QuestStep.quest_id == quest_id)
            )
            total_steps = len(list(total_steps_result.scalars().all()))

            if step_number >= total_steps:
                visitor_quest.status = "completed"
                from datetime import datetime, timezone
                visitor_quest.completed_at = datetime.now(timezone.utc)
                logger.info("quest_completed", visitor_id=str(visitor_id), quest_id=str(quest_id))
            else:
                visitor_quest.current_step = step_number + 1

            await self.db.flush()

        return {
            "passed": passed,
            "current_step": visitor_quest.current_step,
            "status": visitor_quest.status,
            "hints": step.hints if not passed else None,
        }

    def _validate_step(
        self,
        validation: dict[str, Any],
        answer: Optional[str],
        location: Optional[dict[str, float]],
    ) -> bool:
        """验证步骤"""
        validation_type = validation.get("type", "manual")

        if validation_type == "answer":
            correct = validation.get("correct_answer", "").lower()
            return answer and answer.lower() == correct

        elif validation_type == "location":
            if not location:
                return False
            target_lat = validation.get("lat")
            target_lng = validation.get("lng")
            radius = validation.get("radius_meters", 50)
            # 简化的距离计算
            if target_lat and target_lng:
                from math import radians, sin, cos, sqrt, atan2
                R = 6371000  # 地球半径（米）
                lat1, lon1 = radians(location["lat"]), radians(location["lng"])
                lat2, lon2 = radians(target_lat), radians(target_lng)
                dlat, dlon = lat2 - lat1, lon2 - lon1
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                distance = R * c
                return distance <= radius
            return False

        elif validation_type == "manual":
            # 手动验证，默认通过
            return True

        return False
