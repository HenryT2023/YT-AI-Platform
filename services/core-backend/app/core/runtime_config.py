"""
运行态配置服务

提供从 active release 读取配置的能力，支持 fallback 到原有逻辑
"""

import structlog
from datetime import datetime
from typing import Any, Dict, Optional
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.release_service import ReleaseService, ReleasePayload
from app.core.policy_service import PolicyService
from app.database.models.release import Release

logger = structlog.get_logger(__name__)


@dataclass
class RuntimeConfig:
    """运行态配置"""
    release_id: Optional[str] = None
    release_name: Optional[str] = None
    evidence_gate_policy_version: Optional[str] = None
    prompt_version: Optional[str] = None
    experiment_id: Optional[str] = None
    retrieval_defaults: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.retrieval_defaults is None:
            self.retrieval_defaults = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "release_id": self.release_id,
            "release_name": self.release_name,
            "evidence_gate_policy_version": self.evidence_gate_policy_version,
            "prompt_version": self.prompt_version,
            "experiment_id": self.experiment_id,
            "retrieval_defaults": self.retrieval_defaults,
        }


class RuntimeConfigService:
    """运行态配置服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.release_service = ReleaseService(db)
        self.policy_service = PolicyService(db)
    
    async def get_config(
        self,
        tenant_id: str,
        site_id: str,
        npc_id: Optional[str] = None,
    ) -> RuntimeConfig:
        """
        获取运行态配置
        
        优先从 active release 读取，若无则 fallback 到原有逻辑
        """
        log = logger.bind(tenant_id=tenant_id, site_id=site_id, npc_id=npc_id)
        
        # 尝试获取 active release
        release = await self.release_service.get_active(tenant_id, site_id)
        
        if release:
            log.debug("using_active_release", release_id=release.id)
            return await self._config_from_release(release, npc_id)
        
        # Fallback 到原有逻辑
        log.debug("no_active_release_fallback")
        return await self._config_fallback(tenant_id, site_id, npc_id)
    
    async def _config_from_release(
        self,
        release: Release,
        npc_id: Optional[str] = None,
    ) -> RuntimeConfig:
        """从 release 构建配置"""
        payload = release.payload
        
        # 获取 prompt 版本
        prompt_version = None
        if npc_id:
            prompt_version = ReleasePayload.get_prompt_version(payload, npc_id)
        
        return RuntimeConfig(
            release_id=release.id,
            release_name=release.name,
            evidence_gate_policy_version=ReleasePayload.get_policy_version(payload),
            prompt_version=prompt_version,
            experiment_id=ReleasePayload.get_experiment_id(payload),
            retrieval_defaults=ReleasePayload.get_retrieval_defaults(payload),
        )
    
    async def _config_fallback(
        self,
        tenant_id: str,
        site_id: str,
        npc_id: Optional[str] = None,
    ) -> RuntimeConfig:
        """Fallback 到原有逻辑"""
        # 获取 active policy
        policy = await self.policy_service.get_active_policy("evidence-gate")
        policy_version = policy.version if policy else None
        
        return RuntimeConfig(
            release_id=None,
            release_name=None,
            evidence_gate_policy_version=policy_version,
            prompt_version=None,
            experiment_id=None,
            retrieval_defaults={},
        )
    
    async def get_policy_version_for_release(
        self,
        tenant_id: str,
        site_id: str,
    ) -> Optional[str]:
        """
        获取当前应使用的 policy 版本
        
        优先从 active release 读取，若无则从 active policy 读取
        """
        release = await self.release_service.get_active(tenant_id, site_id)
        
        if release:
            version = ReleasePayload.get_policy_version(release.payload)
            if version:
                return version
        
        # Fallback 到 active policy
        policy = await self.policy_service.get_active_policy("evidence-gate")
        return policy.version if policy else None


async def get_runtime_config_service(db: AsyncSession) -> RuntimeConfigService:
    """依赖注入：获取 RuntimeConfigService"""
    return RuntimeConfigService(db)
