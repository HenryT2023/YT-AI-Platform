"""
告警评估 API

提供系统告警评估、事件查询、静默管理接口
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import OperatorOrAbove, ViewerOrAbove
from app.core.tenant_scope import RequiredScope
from app.core.alerts_evaluator import (
    AlertsEvaluator,
    EvaluationResult,
    send_webhook_notification,
)
from app.core.alerts_manager import (
    AlertsManager,
    create_silence,
    list_silences,
    delete_silence,
    list_alert_events,
    get_alert_event,
)
from app.core.audit import log_audit

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])


# ============================================================
# Response Models
# ============================================================

class AlertItem(BaseModel):
    """告警项"""
    code: str
    name: str
    severity: str
    category: str
    description: str
    window: str
    current_value: Any
    threshold: Optional[float]
    unit: Optional[str]
    condition: str
    triggered_at: datetime
    recommended_actions: List[str]


class MetricsSnapshotResponse(BaseModel):
    """指标快照响应"""
    timestamp: datetime
    tenant_id: str
    site_id: Optional[str]
    health: Dict[str, str]
    llm: Dict[str, float]
    gate: Dict[str, float]
    vector: Dict[str, Any]
    embedding: Dict[str, float]
    feedback: Dict[str, int]


class EvaluationResponse(BaseModel):
    """评估结果响应"""
    timestamp: datetime
    tenant_id: str
    site_id: Optional[str]
    window: str
    active_alerts: List[AlertItem]
    alert_count: int
    alerts_by_severity: Dict[str, int]
    metrics_snapshot: MetricsSnapshotResponse
    rules_evaluated: int
    webhook_sent: bool = False


class AlertRuleItem(BaseModel):
    """告警规则项"""
    code: str
    name: str
    category: str
    severity: str
    description: str
    metric: str
    condition: str
    threshold: Optional[float]
    unit: Optional[str]
    window: str
    recommended_actions: List[str]


class AlertRulesResponse(BaseModel):
    """告警规则列表响应"""
    version: str
    rule_count: int
    rules: List[AlertRuleItem]


class AlertEventResponse(BaseModel):
    """告警事件响应"""
    id: str
    tenant_id: str
    site_id: Optional[str]
    alert_code: str
    severity: str
    status: str
    window: str
    current_value: Optional[float]
    threshold: Optional[float]
    condition: Optional[str]
    unit: Optional[str]
    dedup_key: str
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: Optional[datetime]
    context: Dict[str, Any]
    webhook_sent: Optional[str]
    webhook_sent_at: Optional[datetime]
    created_at: datetime


class AlertEventsListResponse(BaseModel):
    """告警事件列表响应"""
    items: List[AlertEventResponse]
    total: int


class SilenceCreateRequest(BaseModel):
    """创建静默请求"""
    tenant_id: str = Field(..., description="租户 ID")
    site_id: Optional[str] = Field(None, description="站点 ID（空表示全局）")
    alert_code: Optional[str] = Field(None, description="告警码（空表示匹配所有）")
    severity: Optional[str] = Field(None, description="告警级别（空表示匹配所有）")
    duration_minutes: int = Field(60, ge=1, le=10080, description="静默时长（分钟），最长 7 天")
    reason: Optional[str] = Field(None, description="静默原因")
    created_by: str = Field("admin_console", description="创建者")


class SilenceResponse(BaseModel):
    """静默规则响应"""
    id: str
    tenant_id: str
    site_id: Optional[str]
    alert_code: Optional[str]
    severity: Optional[str]
    starts_at: datetime
    ends_at: datetime
    reason: Optional[str]
    created_by: str
    created_at: datetime
    is_active: bool


class SilencesListResponse(BaseModel):
    """静默规则列表响应"""
    items: List[SilenceResponse]
    total: int


class EvaluateAndPersistResponse(BaseModel):
    """评估并持久化响应"""
    timestamp: datetime
    tenant_id: str
    site_id: Optional[str]
    window: str
    total_alerts: int
    new_alerts: int
    updated_alerts: int
    resolved_alerts: int
    silenced_alerts: int
    webhook_sent: bool
    context: Dict[str, Any]


# ============================================================
# API Endpoints
# ============================================================

@router.get("/evaluate", response_model=EvaluationResponse)
async def evaluate_alerts(
    scope: RequiredScope,
    range: str = Query("15m", description="评估窗口，如 15m, 1h, 24h"),
    send_webhook: bool = Query(False, description="是否发送 webhook 通知"),
    db: AsyncSession = Depends(get_db),
) -> EvaluationResponse:
    """
    评估告警规则
    
    基于配置化规则评估系统指标，返回当前活跃告警列表和指标快照。
    
    支持的时间窗口：
    - 15m: 15 分钟
    - 1h: 1 小时
    - 24h: 24 小时
    
    告警级别：
    - critical: 严重，需立即处理
    - high: 高，需尽快处理
    - medium: 中，需关注
    - low: 低，可延后处理
    """
    tenant_id = scope.tenant_id
    site_id = scope.site_id
    log = logger.bind(tenant_id=tenant_id, site_id=site_id, range=range)
    log.info("alerts_evaluation_requested")
    
    evaluator = AlertsEvaluator(db)
    result = await evaluator.evaluate(
        tenant_id=tenant_id,
        site_id=site_id,
        window=range,
    )
    
    # 发送 webhook 通知（如果请求且有 critical/high 告警）
    webhook_sent = False
    if send_webhook and result.active_alerts:
        webhook_sent = await send_webhook_notification(
            alerts=result.active_alerts,
            tenant_id=tenant_id,
            site_id=site_id,
        )
        
        # 记录审计日志
        if webhook_sent:
            await log_audit(
                db=db,
                actor="system",
                action="alerts.webhook_sent",
                target_type="alerts",
                target_id=f"{tenant_id}:{site_id or 'all'}",
                payload={
                    "alert_count": len(result.active_alerts),
                    "critical_count": sum(1 for a in result.active_alerts if a.severity == "critical"),
                    "high_count": sum(1 for a in result.active_alerts if a.severity == "high"),
                },
            )
    
    # 如果有 critical 告警，记录审计日志
    critical_alerts = [a for a in result.active_alerts if a.severity == "critical"]
    if critical_alerts:
        await log_audit(
            db=db,
            actor="system",
            action="alerts.critical_detected",
            target_type="alerts",
            target_id=f"{tenant_id}:{site_id or 'all'}",
            payload={
                "alert_codes": [a.code for a in critical_alerts],
                "window": range,
            },
        )
    
    # 构建响应
    result_dict = result.to_dict()
    
    return EvaluationResponse(
        timestamp=result.timestamp,
        tenant_id=result.tenant_id,
        site_id=result.site_id,
        window=result.window,
        active_alerts=[
            AlertItem(
                code=a.code,
                name=a.name,
                severity=a.severity,
                category=a.category,
                description=a.description,
                window=a.window,
                current_value=a.current_value,
                threshold=a.threshold,
                unit=a.unit,
                condition=a.condition,
                triggered_at=a.triggered_at,
                recommended_actions=a.recommended_actions,
            )
            for a in result.active_alerts
        ],
        alert_count=len(result.active_alerts),
        alerts_by_severity=result_dict["alerts_by_severity"],
        metrics_snapshot=MetricsSnapshotResponse(
            timestamp=result.metrics_snapshot.timestamp,
            tenant_id=result.metrics_snapshot.tenant_id,
            site_id=result.metrics_snapshot.site_id,
            health=result_dict["metrics_snapshot"]["health"],
            llm=result_dict["metrics_snapshot"]["llm"],
            gate=result_dict["metrics_snapshot"]["gate"],
            vector=result_dict["metrics_snapshot"]["vector"],
            embedding=result_dict["metrics_snapshot"]["embedding"],
            feedback=result_dict["metrics_snapshot"]["feedback"],
        ),
        rules_evaluated=result.rules_evaluated,
        webhook_sent=webhook_sent,
    )


@router.get("/rules", response_model=AlertRulesResponse)
async def list_alert_rules(
    db: AsyncSession = Depends(get_db),
) -> AlertRulesResponse:
    """
    获取告警规则列表
    
    返回当前配置的所有告警规则
    """
    evaluator = AlertsEvaluator(db)
    
    rules = [
        AlertRuleItem(
            code=r.code,
            name=r.name,
            category=r.category,
            severity=r.severity,
            description=r.description,
            metric=r.metric,
            condition=r.condition,
            threshold=r.threshold,
            unit=r.unit,
            window=r.window,
            recommended_actions=r.recommended_actions,
        )
        for r in evaluator.rules
    ]
    
    return AlertRulesResponse(
        version="0.1",
        rule_count=len(rules),
        rules=rules,
    )


@router.get("/summary")
async def get_alerts_summary(
    scope: RequiredScope,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    获取告警摘要
    
    快速检查当前是否有活跃告警，用于仪表盘展示
    """
    tenant_id = scope.tenant_id
    site_id = scope.site_id
    evaluator = AlertsEvaluator(db)
    result = await evaluator.evaluate(
        tenant_id=tenant_id,
        site_id=site_id,
        window="15m",
    )
    
    return {
        "timestamp": result.timestamp.isoformat(),
        "tenant_id": tenant_id,
        "site_id": site_id,
        "has_alerts": len(result.active_alerts) > 0,
        "alert_count": len(result.active_alerts),
        "alerts_by_severity": result.to_dict()["alerts_by_severity"],
        "critical_codes": [a.code for a in result.active_alerts if a.severity == "critical"],
        "high_codes": [a.code for a in result.active_alerts if a.severity == "high"],
    }


# ============================================================
# 评估并持久化（带去重、静默、事件写入）
# ============================================================

@router.post("/evaluate-persist", response_model=EvaluateAndPersistResponse)
async def evaluate_and_persist_alerts(
    scope: RequiredScope,
    range: str = Query("15m", description="评估窗口"),
    send_webhook: bool = Query(True, description="是否发送 webhook 通知"),
    db: AsyncSession = Depends(get_db),
) -> EvaluateAndPersistResponse:
    """
    评估告警并持久化到数据库
    
    与 /evaluate 不同，此接口会：
    1. 应用静默规则，过滤被静默的告警
    2. 去重：同一告警在 firing 状态不重复通知
    3. 写入告警事件到 alerts_events 表
    4. 记录上下文（active_release_id, active_experiment_id）
    5. 仅对新告警发送 webhook
    
    适用于定时任务调用
    """
    tenant_id = scope.tenant_id
    site_id = scope.site_id
    log = logger.bind(tenant_id=tenant_id, site_id=site_id, range=range)
    log.info("alerts_evaluate_persist_requested")
    
    manager = AlertsManager(db)
    result = await manager.evaluate_and_persist(
        tenant_id=tenant_id,
        site_id=site_id,
        window=range,
        send_webhook=send_webhook,
    )
    
    evaluation = result["evaluation"]
    
    return EvaluateAndPersistResponse(
        timestamp=evaluation.timestamp,
        tenant_id=tenant_id,
        site_id=site_id,
        window=range,
        total_alerts=len(evaluation.active_alerts),
        new_alerts=len(result["new_alerts"]),
        updated_alerts=len(result["updated_alerts"]),
        resolved_alerts=len(result["resolved_alerts"]),
        silenced_alerts=len(result["silenced_alerts"]),
        webhook_sent=result["webhook_sent"],
        context=result["context"],
    )


# ============================================================
# 告警事件 API
# ============================================================

@router.get("/events", response_model=AlertEventsListResponse)
async def list_events(
    scope: RequiredScope,
    status: Optional[str] = Query(None, description="状态过滤: firing, resolved"),
    since: Optional[str] = Query(None, description="起始时间，如 2024-01-01T00:00:00"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
    db: AsyncSession = Depends(get_db),
) -> AlertEventsListResponse:
    """
    获取告警事件列表
    
    用于查询历史告警和复盘
    """
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid since format: {since}",
            )
    
    events = await list_alert_events(
        db=db,
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        status=status,
        since=since_dt,
        limit=limit,
    )
    
    items = [
        AlertEventResponse(
            id=e.id,
            tenant_id=e.tenant_id,
            site_id=e.site_id,
            alert_code=e.alert_code,
            severity=e.severity,
            status=e.status.value if hasattr(e.status, 'value') else e.status,
            window=e.window,
            current_value=e.current_value,
            threshold=e.threshold,
            condition=e.condition,
            unit=e.unit,
            dedup_key=e.dedup_key,
            first_seen_at=e.first_seen_at,
            last_seen_at=e.last_seen_at,
            resolved_at=e.resolved_at,
            context=e.context or {},
            webhook_sent=e.webhook_sent,
            webhook_sent_at=e.webhook_sent_at,
            created_at=e.created_at,
        )
        for e in events
    ]
    
    return AlertEventsListResponse(items=items, total=len(items))


@router.get("/events/{event_id}", response_model=AlertEventResponse)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
) -> AlertEventResponse:
    """获取单个告警事件详情"""
    event = await get_alert_event(db, event_id)
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert event not found: {event_id}",
        )
    
    return AlertEventResponse(
        id=event.id,
        tenant_id=event.tenant_id,
        site_id=event.site_id,
        alert_code=event.alert_code,
        severity=event.severity,
        status=event.status.value if hasattr(event.status, 'value') else event.status,
        window=event.window,
        current_value=event.current_value,
        threshold=event.threshold,
        condition=event.condition,
        unit=event.unit,
        dedup_key=event.dedup_key,
        first_seen_at=event.first_seen_at,
        last_seen_at=event.last_seen_at,
        resolved_at=event.resolved_at,
        context=event.context or {},
        webhook_sent=event.webhook_sent,
        webhook_sent_at=event.webhook_sent_at,
        created_at=event.created_at,
    )


# ============================================================
# 静默规则 API
# ============================================================

@router.post("/silences", response_model=SilenceResponse)
async def create_silence_rule(
    request: SilenceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OperatorOrAbove = None,
) -> SilenceResponse:
    """
    创建告警静默规则（运营人员及以上）
    
    静默规则可以按 alert_code 或 severity 匹配：
    - 指定 alert_code: 仅静默该告警
    - 指定 severity: 静默该级别的所有告警
    - 都不指定: 静默所有告警
    """
    ends_at = datetime.utcnow() + timedelta(minutes=request.duration_minutes)
    
    silence = await create_silence(
        db=db,
        tenant_id=request.tenant_id,
        site_id=request.site_id,
        alert_code=request.alert_code,
        severity=request.severity,
        ends_at=ends_at,
        reason=request.reason,
        created_by=request.created_by,
    )
    
    # 记录审计日志
    await log_audit(
        db=db,
        actor=current_user.username,
        action="alerts.silence_created",
        target_type="alerts_silence",
        target_id=silence.id,
        payload={
            "tenant_id": request.tenant_id,
            "site_id": request.site_id,
            "alert_code": request.alert_code,
            "severity": request.severity,
            "duration_minutes": request.duration_minutes,
            "reason": request.reason,
        },
    )
    
    return SilenceResponse(
        id=silence.id,
        tenant_id=silence.tenant_id,
        site_id=silence.site_id,
        alert_code=silence.alert_code,
        severity=silence.severity,
        starts_at=silence.starts_at,
        ends_at=silence.ends_at,
        reason=silence.reason,
        created_by=silence.created_by,
        created_at=silence.created_at,
        is_active=silence.is_active(),
    )


@router.get("/silences", response_model=SilencesListResponse)
async def list_silence_rules(
    scope: RequiredScope,
    active_only: bool = Query(True, description="仅返回生效中的静默"),
    db: AsyncSession = Depends(get_db),
) -> SilencesListResponse:
    """获取静默规则列表
    
    v0.2.4: 从 Header 读取 tenant/site scope
    """
    silences = await list_silences(
        db=db,
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        active_only=active_only,
    )
    
    items = [
        SilenceResponse(
            id=s.id,
            tenant_id=s.tenant_id,
            site_id=s.site_id,
            alert_code=s.alert_code,
            severity=s.severity,
            starts_at=s.starts_at,
            ends_at=s.ends_at,
            reason=s.reason,
            created_by=s.created_by,
            created_at=s.created_at,
            is_active=s.is_active(),
        )
        for s in silences
    ]
    
    return SilencesListResponse(items=items, total=len(items))


@router.delete("/silences/{silence_id}")
async def delete_silence_rule(
    silence_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OperatorOrAbove = None,
) -> Dict[str, Any]:
    """删除静默规则（运营人员及以上）"""
    success = await delete_silence(db, silence_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Silence not found: {silence_id}",
        )
    
    # 记录审计日志
    await log_audit(
        db=db,
        actor=current_user.username,
        action="alerts.silence_deleted",
        target_type="alerts_silence",
        target_id=silence_id,
        payload={},
    )
    
    return {"ok": True, "deleted_id": silence_id}
