"""
操作审计服务

提供审计日志记录功能
"""

import structlog
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.admin_audit_log import AdminAuditLog

logger = structlog.get_logger(__name__)


class AuditAction:
    """审计操作类型常量"""
    # Policy 操作
    POLICY_CREATE = "policy.create"
    POLICY_ROLLBACK = "policy.rollback"
    
    # Feedback 操作
    FEEDBACK_TRIAGE = "feedback.triage"
    FEEDBACK_STATUS_UPDATE = "feedback.status_update"
    FEEDBACK_RESOLVE = "feedback.resolve"


class TargetType:
    """目标类型常量"""
    POLICY = "policy"
    FEEDBACK = "feedback"


async def log_audit(
    db: AsyncSession,
    actor: str,
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> AdminAuditLog:
    """
    记录审计日志
    
    Args:
        db: 数据库会话
        actor: 操作者标识（如 admin_console, user_id）
        action: 操作类型（如 policy.create, feedback.triage）
        target_type: 目标类型（如 policy, feedback）
        target_id: 目标 ID
        payload: 操作详情（JSON）
    
    Returns:
        创建的审计日志记录
    """
    log = logger.bind(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
    )
    
    audit_log = AdminAuditLog(
        id=str(uuid4()),
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload or {},
        created_at=datetime.utcnow(),
    )
    
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)
    
    log.info("audit_log_created", audit_id=audit_log.id)
    
    return audit_log


def sync_log_audit_to_file(
    actor: str,
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
):
    """
    同步记录审计日志到文件（用于无数据库场景）
    
    用于 Policy API 等可能没有 DB session 的场景
    """
    import json
    from pathlib import Path
    
    log_dir = Path(__file__).parent.parent.parent.parent / "data" / "audit_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
    
    log_entry = {
        "id": str(uuid4()),
        "actor": actor,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "payload": payload or {},
        "created_at": datetime.utcnow().isoformat(),
    }
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    logger.info(
        "audit_log_to_file",
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
    )
    
    return log_entry
