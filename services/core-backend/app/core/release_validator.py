"""
Release 完整性校验器

在 activate/rollback 前校验 release payload 引用的资源是否存在：
- evidence_gate_policy_version: 必须在 Policy 表中存在
- prompts_active_map: 每个 npc_id + version 必须在 NPCPrompt 表中存在
- experiment_id: 若非空，必须在 Experiment 表中存在且状态允许
- retrieval_defaults: 合法性校验（strategy/top_k 范围）
"""

import structlog
from typing import Any, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.policy import Policy
from app.database.models.npc_prompt import NPCPrompt
from app.database.models.experiment import Experiment, ExperimentStatus

logger = structlog.get_logger(__name__)


# ============================================================
# 错误码定义
# ============================================================

class ValidationErrorCode(str, Enum):
    """校验错误码"""
    MISSING_POLICY = "missing_policy"
    MISSING_PROMPT = "missing_prompt"
    MISSING_EXPERIMENT = "missing_experiment"
    INVALID_EXPERIMENT_STATUS = "invalid_experiment_status"
    INVALID_RETRIEVAL_STRATEGY = "invalid_retrieval_strategy"
    INVALID_RETRIEVAL_TOP_K = "invalid_retrieval_top_k"
    INVALID_PROMPTS_MAP_FORMAT = "invalid_prompts_map_format"
    PAYLOAD_EMPTY = "payload_empty"


# ============================================================
# Pydantic Schema
# ============================================================

class RetrievalDefaults(BaseModel):
    """检索默认配置"""
    strategy: Optional[str] = Field(None, description="检索策略: trgm, qdrant, hybrid")
    top_k: Optional[int] = Field(None, ge=1, le=50, description="返回结果数量")
    
    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = {"trgm", "qdrant", "hybrid", "semantic"}
            if v not in allowed:
                raise ValueError(f"strategy must be one of {allowed}, got '{v}'")
        return v


class ReleasePayloadSchema(BaseModel):
    """
    Release Payload 结构化 Schema
    
    用于创建和校验 release payload
    """
    evidence_gate_policy_version: Optional[str] = Field(
        None,
        description="Evidence Gate Policy 版本号",
    )
    feedback_routing_policy_version: Optional[str] = Field(
        None,
        description="Feedback Routing Policy 版本号",
    )
    prompts_active_map: Dict[str, str] = Field(
        default_factory=dict,
        description="NPC Prompt 版本映射: {npc_id: version}",
    )
    experiment_id: Optional[str] = Field(
        None,
        description="关联的实验 ID",
    )
    retrieval_defaults: Optional[RetrievalDefaults] = Field(
        None,
        description="检索默认配置",
    )
    
    @field_validator("prompts_active_map")
    @classmethod
    def validate_prompts_map(cls, v: Dict[str, str]) -> Dict[str, str]:
        """验证 prompts_active_map 格式"""
        for npc_id, version in v.items():
            if not isinstance(npc_id, str) or not npc_id:
                raise ValueError(f"Invalid npc_id: {npc_id}")
            if not isinstance(version, (str, int)):
                raise ValueError(f"Invalid version for {npc_id}: {version}")
        return v
    
    @model_validator(mode="after")
    def check_not_empty(self) -> "ReleasePayloadSchema":
        """确保至少有一个配置项"""
        has_content = any([
            self.evidence_gate_policy_version,
            self.feedback_routing_policy_version,
            self.prompts_active_map,
            self.experiment_id,
            self.retrieval_defaults,
        ])
        if not has_content:
            raise ValueError("Release payload must contain at least one config item")
        return self


# ============================================================
# 校验结果
# ============================================================

@dataclass
class ValidationError:
    """单个校验错误"""
    code: str
    detail: str
    
    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass
class ValidationResult:
    """校验结果"""
    ok: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    
    def add_error(self, code: str, detail: str):
        self.ok = False
        self.errors.append(ValidationError(code=code, detail=detail))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [e.to_dict() for e in self.errors],
        }


# ============================================================
# 校验器
# ============================================================

class ReleaseValidator:
    """Release 完整性校验器"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def validate(
        self,
        payload: Dict[str, Any],
        tenant_id: str,
        site_id: str,
    ) -> ValidationResult:
        """
        校验 release payload 的完整性
        
        Args:
            payload: release payload 字典
            tenant_id: 租户 ID
            site_id: 站点 ID
            
        Returns:
            ValidationResult: 校验结果
        """
        log = logger.bind(tenant_id=tenant_id, site_id=site_id)
        result = ValidationResult()
        
        # 1. 先用 Pydantic 校验基本格式
        try:
            schema = ReleasePayloadSchema(**payload)
        except Exception as e:
            result.add_error(
                ValidationErrorCode.PAYLOAD_EMPTY.value,
                f"Invalid payload format: {str(e)}",
            )
            return result
        
        # 2. 校验 evidence_gate_policy_version
        if schema.evidence_gate_policy_version:
            exists = await self._check_policy_exists(schema.evidence_gate_policy_version)
            if not exists:
                result.add_error(
                    ValidationErrorCode.MISSING_POLICY.value,
                    f"Policy version '{schema.evidence_gate_policy_version}' not found",
                )
                log.warning("policy_not_found", version=schema.evidence_gate_policy_version)
        
        # 3. 校验 prompts_active_map
        for npc_id, version in schema.prompts_active_map.items():
            exists = await self._check_prompt_exists(
                tenant_id=tenant_id,
                site_id=site_id,
                npc_id=npc_id,
                version=version,
            )
            if not exists:
                result.add_error(
                    ValidationErrorCode.MISSING_PROMPT.value,
                    f"Prompt '{npc_id}@v{version}' not found",
                )
                log.warning("prompt_not_found", npc_id=npc_id, version=version)
        
        # 4. 校验 experiment_id
        if schema.experiment_id:
            exp_result = await self._check_experiment_exists(schema.experiment_id)
            if exp_result == "not_found":
                result.add_error(
                    ValidationErrorCode.MISSING_EXPERIMENT.value,
                    f"Experiment '{schema.experiment_id}' not found",
                )
                log.warning("experiment_not_found", experiment_id=schema.experiment_id)
            elif exp_result == "invalid_status":
                result.add_error(
                    ValidationErrorCode.INVALID_EXPERIMENT_STATUS.value,
                    f"Experiment '{schema.experiment_id}' is not in active/draft status",
                )
                log.warning("experiment_invalid_status", experiment_id=schema.experiment_id)
        
        # 5. 校验 retrieval_defaults（已在 Pydantic 中校验）
        if schema.retrieval_defaults:
            if schema.retrieval_defaults.strategy:
                allowed = {"trgm", "qdrant", "hybrid", "semantic"}
                if schema.retrieval_defaults.strategy not in allowed:
                    result.add_error(
                        ValidationErrorCode.INVALID_RETRIEVAL_STRATEGY.value,
                        f"Invalid retrieval strategy: '{schema.retrieval_defaults.strategy}', must be one of {allowed}",
                    )
            if schema.retrieval_defaults.top_k is not None:
                if schema.retrieval_defaults.top_k < 1 or schema.retrieval_defaults.top_k > 50:
                    result.add_error(
                        ValidationErrorCode.INVALID_RETRIEVAL_TOP_K.value,
                        f"Invalid top_k: {schema.retrieval_defaults.top_k}, must be between 1 and 50",
                    )
        
        if result.ok:
            log.info("release_validation_passed")
        else:
            log.warning("release_validation_failed", error_count=len(result.errors))
        
        return result
    
    async def _check_policy_exists(self, version: str) -> bool:
        """检查 policy 版本是否存在"""
        query = select(Policy.id).where(Policy.version == version).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None
    
    async def _check_prompt_exists(
        self,
        tenant_id: str,
        site_id: str,
        npc_id: str,
        version: str,
    ) -> bool:
        """检查 prompt 是否存在"""
        # version 可能是字符串或整数
        try:
            version_int = int(version)
        except (ValueError, TypeError):
            return False
        
        query = select(NPCPrompt.id).where(
            and_(
                NPCPrompt.tenant_id == tenant_id,
                NPCPrompt.site_id == site_id,
                NPCPrompt.npc_id == npc_id,
                NPCPrompt.version == version_int,
                NPCPrompt.deleted_at.is_(None),
            )
        ).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None
    
    async def _check_experiment_exists(self, experiment_id: str) -> str:
        """
        检查实验是否存在且状态允许
        
        Returns:
            "ok": 存在且状态允许
            "not_found": 不存在
            "invalid_status": 存在但状态不允许
        """
        query = select(Experiment).where(Experiment.id == experiment_id).limit(1)
        result = await self.db.execute(query)
        experiment = result.scalar_one_or_none()
        
        if not experiment:
            return "not_found"
        
        # 允许 draft 和 active 状态的实验
        allowed_statuses = {ExperimentStatus.DRAFT.value, ExperimentStatus.ACTIVE.value}
        if experiment.status not in allowed_statuses:
            return "invalid_status"
        
        return "ok"


async def validate_release(
    db: AsyncSession,
    payload: Dict[str, Any],
    tenant_id: str,
    site_id: str,
) -> ValidationResult:
    """
    校验 release payload 的完整性
    
    便捷函数，供 API 层调用
    """
    validator = ReleaseValidator(db)
    return await validator.validate(payload, tenant_id, site_id)
