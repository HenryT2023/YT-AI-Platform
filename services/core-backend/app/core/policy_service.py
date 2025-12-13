"""
Policy 服务层

提供 Evidence Gate Policy 的数据库操作，作为真源（Source of Truth）
"""

import json
import structlog
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.policy import Policy

logger = structlog.get_logger(__name__)

# Seed 文件路径
SEED_DIR = Path(__file__).parent.parent.parent.parent / "data" / "policies"
SEED_FILE = SEED_DIR / "evidence_gate_policy.json"


class PolicyService:
    """Policy 服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_active_policy(self, name: str = "evidence-gate") -> Optional[Policy]:
        """获取当前活跃策略"""
        query = select(Policy).where(
            Policy.name == name,
            Policy.is_active == True,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def list_versions(self, name: str = "evidence-gate") -> List[Policy]:
        """列出所有版本"""
        query = select(Policy).where(
            Policy.name == name,
        ).order_by(Policy.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create_version(
        self,
        name: str,
        version: str,
        description: str,
        content: Dict[str, Any],
        operator: str,
        set_active: bool = True,
    ) -> Policy:
        """创建新版本"""
        log = logger.bind(name=name, version=version, operator=operator)
        
        # 如果设置为活跃，先取消其他版本的活跃状态
        if set_active:
            await self.db.execute(
                update(Policy)
                .where(Policy.name == name, Policy.is_active == True)
                .values(is_active=False)
            )
        
        # 创建新版本
        policy = Policy(
            id=str(uuid4()),
            name=name,
            version=version,
            description=description,
            content=content,
            is_active=set_active,
            operator=operator,
            created_at=datetime.utcnow(),
        )
        
        self.db.add(policy)
        await self.db.commit()
        await self.db.refresh(policy)
        
        log.info("policy_version_created", policy_id=policy.id, is_active=set_active)
        
        return policy
    
    async def set_active_version(self, name: str, version: str) -> Optional[Policy]:
        """设置活跃版本（用于回滚）"""
        log = logger.bind(name=name, version=version)
        
        # 查找目标版本
        query = select(Policy).where(
            Policy.name == name,
            Policy.version == version,
        )
        result = await self.db.execute(query)
        target = result.scalar_one_or_none()
        
        if not target:
            log.warning("policy_version_not_found")
            return None
        
        # 取消其他版本的活跃状态
        await self.db.execute(
            update(Policy)
            .where(Policy.name == name, Policy.is_active == True)
            .values(is_active=False)
        )
        
        # 设置目标版本为活跃
        target.is_active = True
        await self.db.commit()
        await self.db.refresh(target)
        
        log.info("policy_version_activated", policy_id=target.id)
        
        return target
    
    async def seed_from_file(self, name: str = "evidence-gate") -> Optional[Policy]:
        """从文件导入 seed 数据（仅当 DB 为空时）"""
        log = logger.bind(name=name)
        
        # 检查是否已有数据
        existing = await self.list_versions(name)
        if existing:
            log.info("policy_seed_skipped", reason="data_exists", count=len(existing))
            return None
        
        # 检查 seed 文件
        if not SEED_FILE.exists():
            log.warning("policy_seed_file_not_found", path=str(SEED_FILE))
            return None
        
        # 读取 seed 文件
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            seed_data = json.load(f)
        
        # 创建初始版本
        policy = await self.create_version(
            name=name,
            version=seed_data.get("version", "v1.0"),
            description=seed_data.get("description", "Seed from file"),
            content=seed_data,
            operator="seed",
            set_active=True,
        )
        
        log.info("policy_seeded_from_file", policy_id=policy.id, version=policy.version)
        
        return policy
    
    async def export_to_file(self, name: str = "evidence-gate") -> Optional[Path]:
        """导出当前活跃策略到文件"""
        log = logger.bind(name=name)
        
        active = await self.get_active_policy(name)
        if not active:
            log.warning("no_active_policy_to_export")
            return None
        
        # 确保目录存在
        SEED_DIR.mkdir(parents=True, exist_ok=True)
        
        # 导出文件
        export_file = SEED_DIR / f"{name}_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(active.content, f, indent=2, ensure_ascii=False)
        
        log.info("policy_exported", path=str(export_file), version=active.version)
        
        return export_file


async def get_policy_service(db: AsyncSession) -> PolicyService:
    """依赖注入：获取 PolicyService"""
    return PolicyService(db)
