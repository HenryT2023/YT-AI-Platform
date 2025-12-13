"""
运行态配置 API

提供给 orchestrator 调用，获取当前 active release 的配置
"""

import structlog
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.runtime_config import RuntimeConfigService

logger = structlog.get_logger(__name__)
router = APIRouter()


class RuntimeConfigResponse(BaseModel):
    """运行态配置响应"""
    release_id: Optional[str] = None
    release_name: Optional[str] = None
    evidence_gate_policy_version: Optional[str] = None
    prompt_version: Optional[str] = None
    experiment_id: Optional[str] = None
    retrieval_defaults: Dict[str, Any] = {}


@router.get("/config", response_model=RuntimeConfigResponse)
async def get_runtime_config(
    tenant_id: str = Query(...),
    site_id: str = Query(...),
    npc_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    获取运行态配置
    
    orchestrator 在处理 npc/chat 请求前调用此接口获取当前配置
    """
    service = RuntimeConfigService(db)
    config = await service.get_config(
        tenant_id=tenant_id,
        site_id=site_id,
        npc_id=npc_id,
    )
    
    return RuntimeConfigResponse(
        release_id=config.release_id,
        release_name=config.release_name,
        evidence_gate_policy_version=config.evidence_gate_policy_version,
        prompt_version=config.prompt_version,
        experiment_id=config.experiment_id,
        retrieval_defaults=config.retrieval_defaults,
    )
