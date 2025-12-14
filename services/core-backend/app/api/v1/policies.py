"""
Evidence Gate Policy API

提供策略配置的读取、更新和版本管理
数据库为真源（Source of Truth），文件系统作为 seed/导出
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import AdminOnly, ViewerOrAbove
from app.core.audit import log_audit, AuditAction, TargetType
from app.core.policy_service import PolicyService

router = APIRouter()

# 策略文件路径（用于 seed 和导出）
POLICY_DIR = Path(__file__).parent.parent.parent.parent.parent.parent / "data" / "policies"
SEED_FILE = POLICY_DIR / "evidence_gate_policy.json"


class EvidenceGatePolicy(BaseModel):
    """Evidence Gate 策略"""
    version: str
    description: str
    default_policy: Dict[str, Any]
    site_policies: Dict[str, Any] = Field(default_factory=dict)
    npc_policies: Dict[str, Any] = Field(default_factory=dict)
    intent_overrides: Dict[str, Any] = Field(default_factory=dict)


class PolicyVersionResponse(BaseModel):
    """策略版本信息"""
    version: str
    created_at: datetime
    operator: str
    is_active: bool = False


class PolicyUpdateRequest(BaseModel):
    """策略更新请求"""
    version: str
    description: str
    default_policy: Dict[str, Any]
    site_policies: Dict[str, Any] = Field(default_factory=dict)
    npc_policies: Dict[str, Any] = Field(default_factory=dict)
    intent_overrides: Dict[str, Any] = Field(default_factory=dict)
    operator: str = "admin"


def _load_seed_policy() -> Optional[Dict[str, Any]]:
    """从文件加载 seed 策略"""
    if not SEED_FILE.exists():
        return None
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/evidence-gate/active", response_model=EvidenceGatePolicy)
async def get_active_policy(db: AsyncSession = Depends(get_db)):
    """获取当前活跃策略（从数据库读取）"""
    service = PolicyService(db)
    
    # 尝试从数据库获取
    policy = await service.get_active_policy("evidence-gate")
    
    if policy:
        content = policy.content
        return EvidenceGatePolicy(
            version=policy.version,
            description=policy.description or "",
            default_policy=content.get("default_policy", {}),
            site_policies=content.get("site_policies", {}),
            npc_policies=content.get("npc_policies", {}),
            intent_overrides=content.get("intent_overrides", {}),
        )
    
    # 尝试从 seed 文件加载并导入
    seed = _load_seed_policy()
    if seed:
        await service.seed_from_file("evidence-gate")
        return EvidenceGatePolicy(**seed)
    
    # 返回默认策略
    return EvidenceGatePolicy(
        version="v1.0",
        description="默认策略",
        default_policy={
            "min_citations": 1,
            "min_score": 0.3,
            "max_soft_claims": 2,
            "strict_mode": False,
        },
    )


@router.get("/evidence-gate/versions", response_model=List[PolicyVersionResponse])
async def list_policy_versions(db: AsyncSession = Depends(get_db)):
    """列出策略版本历史（从数据库读取）"""
    service = PolicyService(db)
    policies = await service.list_versions("evidence-gate")
    
    return [
        PolicyVersionResponse(
            version=p.version,
            created_at=p.created_at,
            operator=p.operator,
            is_active=p.is_active,
        )
        for p in policies
    ]


@router.post("/evidence-gate", response_model=Dict[str, str])
async def set_active_policy(
    request: PolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminOnly = None,
):
    """设置新的活跃策略（仅管理员）"""
    # 验证必填字段
    if not request.version or not request.description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="version 和 description 为必填字段",
        )
    
    if not request.default_policy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="default_policy 为必填字段",
        )
    
    # 构建策略内容
    content = {
        "version": request.version,
        "description": request.description,
        "default_policy": request.default_policy,
        "site_policies": request.site_policies,
        "npc_policies": request.npc_policies,
        "intent_overrides": request.intent_overrides,
    }
    
    # 保存到数据库
    service = PolicyService(db)
    await service.create_version(
        name="evidence-gate",
        version=request.version,
        description=request.description,
        content=content,
        operator=request.operator,
        set_active=True,
    )
    
    # 记录审计日志
    await log_audit(
        db=db,
        actor=current_user.username,
        action=AuditAction.POLICY_CREATE,
        target_type=TargetType.POLICY,
        target_id=request.version,
        payload={"description": request.description},
    )
    
    return {"version": request.version, "status": "active"}


@router.post("/evidence-gate/rollback/{version}", response_model=Dict[str, str])
async def rollback_policy(
    version: str,
    db: AsyncSession = Depends(get_db),
    current_user: AdminOnly = None,
):
    """回滚到指定版本（仅管理员）"""
    service = PolicyService(db)
    
    # 设置目标版本为活跃
    policy = await service.set_active_version("evidence-gate", version)
    
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 {version} 不存在",
        )
    
    # 记录审计日志
    await log_audit(
        db=db,
        actor=current_user.username,
        action=AuditAction.POLICY_ROLLBACK,
        target_type=TargetType.POLICY,
        target_id=version,
        payload={"rolled_back_to": version},
    )
    
    return {"version": version, "status": "rolled_back"}


@router.post("/evidence-gate/export", response_model=Dict[str, str])
async def export_policy(
    db: AsyncSession = Depends(get_db),
    current_user: AdminOnly = None,
):
    """导出当前活跃策略到文件（仅管理员）"""
    service = PolicyService(db)
    export_path = await service.export_to_file("evidence-gate")
    
    if not export_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有活跃策略可导出",
        )
    
    return {"path": str(export_path), "status": "exported"}
