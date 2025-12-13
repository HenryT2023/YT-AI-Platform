"""
Release 服务层

提供发布包的创建、激活、回滚等操作
"""

import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.release import Release, ReleaseHistory, ReleaseStatus

logger = structlog.get_logger(__name__)


class ReleasePayload:
    """Release Payload 结构"""
    
    @staticmethod
    def validate(payload: Dict[str, Any]) -> bool:
        """验证 payload 结构"""
        # 必须包含至少一个配置项
        valid_keys = {
            "evidence_gate_policy_version",
            "feedback_routing_policy_version",
            "prompts_active_map",
            "experiment_id",
            "retrieval_defaults",
        }
        return any(key in payload for key in valid_keys)
    
    @staticmethod
    def get_policy_version(payload: Dict[str, Any]) -> Optional[str]:
        """获取 evidence gate policy 版本"""
        return payload.get("evidence_gate_policy_version")
    
    @staticmethod
    def get_prompt_version(payload: Dict[str, Any], npc_id: str) -> Optional[str]:
        """获取指定 NPC 的 prompt 版本"""
        prompts_map = payload.get("prompts_active_map", {})
        return prompts_map.get(npc_id)
    
    @staticmethod
    def get_experiment_id(payload: Dict[str, Any]) -> Optional[str]:
        """获取实验 ID"""
        return payload.get("experiment_id")
    
    @staticmethod
    def get_retrieval_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
        """获取检索默认配置"""
        return payload.get("retrieval_defaults", {})


class ReleaseService:
    """Release 服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(
        self,
        tenant_id: str,
        site_id: str,
        name: str,
        payload: Dict[str, Any],
        created_by: str,
        description: Optional[str] = None,
    ) -> Release:
        """创建 draft release"""
        log = logger.bind(tenant_id=tenant_id, site_id=site_id, name=name)
        
        if not ReleasePayload.validate(payload):
            raise ValueError("Invalid release payload: must contain at least one config item")
        
        release = Release(
            id=str(uuid4()),
            tenant_id=tenant_id,
            site_id=site_id,
            name=name,
            description=description,
            status=ReleaseStatus.DRAFT,
            payload=payload,
            created_by=created_by,
            created_at=datetime.utcnow(),
        )
        
        self.db.add(release)
        await self.db.commit()
        await self.db.refresh(release)
        
        log.info("release_created", release_id=release.id)
        
        return release
    
    async def get_active(self, tenant_id: str, site_id: str) -> Optional[Release]:
        """获取当前 active release"""
        query = select(Release).where(
            and_(
                Release.tenant_id == tenant_id,
                Release.site_id == site_id,
                Release.status == ReleaseStatus.ACTIVE,
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_id(self, release_id: str) -> Optional[Release]:
        """根据 ID 获取 release"""
        query = select(Release).where(Release.id == release_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def list(
        self,
        tenant_id: str,
        site_id: str,
        status: Optional[ReleaseStatus] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Release]:
        """列出 releases"""
        query = select(Release).where(
            and_(
                Release.tenant_id == tenant_id,
                Release.site_id == site_id,
            )
        )
        
        if status:
            query = query.where(Release.status == status)
        
        query = query.order_by(Release.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def activate(self, release_id: str, operator: str) -> Release:
        """激活 release（使其成为 active，旧 active 变 archived）"""
        log = logger.bind(release_id=release_id, operator=operator)
        
        # 获取目标 release
        release = await self.get_by_id(release_id)
        if not release:
            raise ValueError(f"Release not found: {release_id}")
        
        if release.status == ReleaseStatus.ACTIVE:
            log.info("release_already_active")
            return release
        
        # 获取当前 active release
        current_active = await self.get_active(release.tenant_id, release.site_id)
        previous_release_id = current_active.id if current_active else None
        
        # 归档当前 active
        if current_active:
            current_active.status = ReleaseStatus.ARCHIVED
            current_active.archived_at = datetime.utcnow()
        
        # 激活目标 release
        release.status = ReleaseStatus.ACTIVE
        release.activated_at = datetime.utcnow()
        
        # 记录历史
        history = ReleaseHistory(
            id=str(uuid4()),
            release_id=release_id,
            tenant_id=release.tenant_id,
            site_id=release.site_id,
            action="activate",
            previous_release_id=previous_release_id,
            operator=operator,
            created_at=datetime.utcnow(),
        )
        self.db.add(history)
        
        await self.db.commit()
        await self.db.refresh(release)
        
        log.info(
            "release_activated",
            previous_release_id=previous_release_id,
        )
        
        return release
    
    async def rollback(self, release_id: str, operator: str) -> Release:
        """回滚到指定 release（重新激活）"""
        log = logger.bind(release_id=release_id, operator=operator)
        
        # 获取目标 release
        release = await self.get_by_id(release_id)
        if not release:
            raise ValueError(f"Release not found: {release_id}")
        
        # 获取当前 active release
        current_active = await self.get_active(release.tenant_id, release.site_id)
        previous_release_id = current_active.id if current_active else None
        
        # 归档当前 active
        if current_active and current_active.id != release_id:
            current_active.status = ReleaseStatus.ARCHIVED
            current_active.archived_at = datetime.utcnow()
        
        # 重新激活目标 release
        release.status = ReleaseStatus.ACTIVE
        release.activated_at = datetime.utcnow()
        release.archived_at = None
        
        # 记录历史
        history = ReleaseHistory(
            id=str(uuid4()),
            release_id=release_id,
            tenant_id=release.tenant_id,
            site_id=release.site_id,
            action="rollback",
            previous_release_id=previous_release_id,
            operator=operator,
            created_at=datetime.utcnow(),
        )
        self.db.add(history)
        
        await self.db.commit()
        await self.db.refresh(release)
        
        log.info(
            "release_rolled_back",
            previous_release_id=previous_release_id,
        )
        
        return release
    
    async def get_history(
        self,
        tenant_id: str,
        site_id: str,
        limit: int = 20,
    ) -> List[ReleaseHistory]:
        """获取发布历史"""
        query = select(ReleaseHistory).where(
            and_(
                ReleaseHistory.tenant_id == tenant_id,
                ReleaseHistory.site_id == site_id,
            )
        ).order_by(ReleaseHistory.created_at.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())


async def get_release_service(db: AsyncSession) -> ReleaseService:
    """依赖注入：获取 ReleaseService"""
    return ReleaseService(db)
