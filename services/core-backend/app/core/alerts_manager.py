"""
告警管理器

在 alerts_evaluator 基础上增加：
- 告警事件存储（alerts_events）
- 告警去重（同一 dedup_key 在 firing 状态不重复通知）
- 告警静默（alerts_silences）
- 上下文记录（active_release_id, active_experiment_id）
"""

import os
import httpx
import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.alerts import AlertEvent, AlertSilence, AlertStatus
from app.database.models.release import Release, ReleaseStatus
from app.database.models.experiment import Experiment, ExperimentStatus
from app.core.alerts_evaluator import (
    AlertsEvaluator,
    Alert,
    EvaluationResult,
    MetricsSnapshot,
)

logger = structlog.get_logger(__name__)


class AlertsManager:
    """
    告警管理器
    
    职责：
    1. 调用 AlertsEvaluator 评估告警
    2. 加载静默规则，过滤被静默的告警
    3. 去重：同一 dedup_key 的 firing 告警不重复通知
    4. 写入告警事件到 alerts_events
    5. 记录上下文（active_release_id, active_experiment_id）
    6. 发送 webhook 通知（仅新告警）
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.evaluator = AlertsEvaluator(db)
    
    async def evaluate_and_persist(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        window: str = "15m",
        send_webhook: bool = True,
    ) -> Dict[str, Any]:
        """
        评估告警并持久化
        
        Returns:
            {
                "evaluation": EvaluationResult,
                "new_alerts": List[AlertEvent],  # 新触发的告警
                "updated_alerts": List[AlertEvent],  # 更新的告警
                "resolved_alerts": List[AlertEvent],  # 解决的告警
                "silenced_alerts": List[Alert],  # 被静默的告警
                "webhook_sent": bool,
            }
        """
        log = logger.bind(tenant_id=tenant_id, site_id=site_id, window=window)
        log.info("alerts_manager_evaluate_start")
        
        now = datetime.utcnow()
        
        # 1. 评估告警
        result = await self.evaluator.evaluate(tenant_id, site_id, window)
        
        # 2. 加载静默规则
        silences = await self._load_active_silences(tenant_id, site_id, now)
        
        # 3. 过滤被静默的告警
        active_alerts, silenced_alerts = self._apply_silences(
            result.active_alerts, silences
        )
        
        # 4. 获取上下文（active release / experiment）
        context = await self._get_context(tenant_id, site_id, result.metrics_snapshot)
        
        # 5. 处理告警事件（去重、写入）
        new_alerts, updated_alerts, resolved_alerts = await self._process_alert_events(
            tenant_id=tenant_id,
            site_id=site_id,
            window=window,
            active_alerts=active_alerts,
            context=context,
            now=now,
        )
        
        # 6. 发送 webhook（仅新告警且 critical/high）
        webhook_sent = False
        if send_webhook and new_alerts:
            webhook_sent = await self._send_webhook_for_new_alerts(
                new_alerts=new_alerts,
                tenant_id=tenant_id,
                site_id=site_id,
                context=context,
            )
        
        await self.db.commit()
        
        log.info(
            "alerts_manager_evaluate_complete",
            total_alerts=len(result.active_alerts),
            silenced=len(silenced_alerts),
            new=len(new_alerts),
            updated=len(updated_alerts),
            resolved=len(resolved_alerts),
            webhook_sent=webhook_sent,
        )
        
        return {
            "evaluation": result,
            "new_alerts": new_alerts,
            "updated_alerts": updated_alerts,
            "resolved_alerts": resolved_alerts,
            "silenced_alerts": silenced_alerts,
            "webhook_sent": webhook_sent,
            "context": context,
        }
    
    async def _load_active_silences(
        self,
        tenant_id: str,
        site_id: Optional[str],
        now: datetime,
    ) -> List[AlertSilence]:
        """加载当前生效的静默规则"""
        conditions = [
            AlertSilence.tenant_id == tenant_id,
            AlertSilence.starts_at <= now,
            AlertSilence.ends_at >= now,
        ]
        
        # site_id 匹配：精确匹配或为空（全局静默）
        if site_id:
            conditions.append(
                or_(
                    AlertSilence.site_id == site_id,
                    AlertSilence.site_id.is_(None),
                )
            )
        
        stmt = select(AlertSilence).where(and_(*conditions))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    def _apply_silences(
        self,
        alerts: List[Alert],
        silences: List[AlertSilence],
    ) -> tuple[List[Alert], List[Alert]]:
        """
        应用静默规则
        
        Returns:
            (active_alerts, silenced_alerts)
        """
        if not silences:
            return alerts, []
        
        active = []
        silenced = []
        
        for alert in alerts:
            is_silenced = False
            for silence in silences:
                if silence.matches(alert.code, alert.severity):
                    is_silenced = True
                    break
            
            if is_silenced:
                silenced.append(alert)
            else:
                active.append(alert)
        
        return active, silenced
    
    async def _get_context(
        self,
        tenant_id: str,
        site_id: Optional[str],
        snapshot: MetricsSnapshot,
    ) -> Dict[str, Any]:
        """获取告警上下文"""
        context = {
            "metrics_snapshot": snapshot.to_dict(),
        }
        
        # 获取 active release
        try:
            release_stmt = select(Release).where(
                and_(
                    Release.tenant_id == tenant_id,
                    Release.status == ReleaseStatus.ACTIVE,
                )
            )
            if site_id:
                release_stmt = release_stmt.where(Release.site_id == site_id)
            release_stmt = release_stmt.limit(1)
            
            result = await self.db.execute(release_stmt)
            release = result.scalar_one_or_none()
            
            if release:
                context["active_release_id"] = release.id
                context["active_release_name"] = release.name
        except Exception as e:
            logger.warning("get_active_release_failed", error=str(e))
        
        # 获取 active experiment
        try:
            exp_stmt = select(Experiment).where(
                and_(
                    Experiment.tenant_id == tenant_id,
                    Experiment.status == ExperimentStatus.ACTIVE.value,
                )
            )
            if site_id:
                exp_stmt = exp_stmt.where(Experiment.site_id == site_id)
            exp_stmt = exp_stmt.limit(1)
            
            result = await self.db.execute(exp_stmt)
            experiment = result.scalar_one_or_none()
            
            if experiment:
                context["active_experiment_id"] = experiment.id
                context["active_experiment_name"] = experiment.name
        except Exception as e:
            logger.warning("get_active_experiment_failed", error=str(e))
        
        return context
    
    def _make_dedup_key(
        self,
        tenant_id: str,
        site_id: Optional[str],
        alert_code: str,
        window: str,
    ) -> str:
        """生成去重键"""
        return f"{tenant_id}|{site_id or 'all'}|{alert_code}|{window}"
    
    async def _process_alert_events(
        self,
        tenant_id: str,
        site_id: Optional[str],
        window: str,
        active_alerts: List[Alert],
        context: Dict[str, Any],
        now: datetime,
    ) -> tuple[List[AlertEvent], List[AlertEvent], List[AlertEvent]]:
        """
        处理告警事件
        
        Returns:
            (new_alerts, updated_alerts, resolved_alerts)
        """
        new_events = []
        updated_events = []
        resolved_events = []
        
        # 当前触发的告警 codes
        current_alert_codes: Set[str] = {a.code for a in active_alerts}
        
        # 查询现有 firing 事件
        existing_stmt = select(AlertEvent).where(
            and_(
                AlertEvent.tenant_id == tenant_id,
                AlertEvent.window == window,
                AlertEvent.status == AlertStatus.FIRING,
            )
        )
        if site_id:
            existing_stmt = existing_stmt.where(AlertEvent.site_id == site_id)
        
        result = await self.db.execute(existing_stmt)
        existing_events = {e.alert_code: e for e in result.scalars().all()}
        
        # 处理当前触发的告警
        for alert in active_alerts:
            dedup_key = self._make_dedup_key(tenant_id, site_id, alert.code, window)
            
            if alert.code in existing_events:
                # 已存在 firing 事件，更新 last_seen_at
                event = existing_events[alert.code]
                event.last_seen_at = now
                event.current_value = alert.current_value
                event.context = context
                updated_events.append(event)
            else:
                # 新告警，创建事件
                event = AlertEvent(
                    tenant_id=tenant_id,
                    site_id=site_id,
                    alert_code=alert.code,
                    severity=alert.severity,
                    status=AlertStatus.FIRING,
                    window=window,
                    current_value=alert.current_value,
                    threshold=alert.threshold,
                    condition=alert.condition,
                    unit=alert.unit,
                    dedup_key=dedup_key,
                    first_seen_at=now,
                    last_seen_at=now,
                    context={
                        **context,
                        "recommended_actions": alert.recommended_actions,
                    },
                )
                self.db.add(event)
                new_events.append(event)
        
        # 处理已解决的告警（之前 firing，现在不在 active 中）
        for code, event in existing_events.items():
            if code not in current_alert_codes:
                event.status = AlertStatus.RESOLVED
                event.resolved_at = now
                resolved_events.append(event)
        
        return new_events, updated_events, resolved_events
    
    async def _send_webhook_for_new_alerts(
        self,
        new_alerts: List[AlertEvent],
        tenant_id: str,
        site_id: Optional[str],
        context: Dict[str, Any],
    ) -> bool:
        """
        为新告警发送 webhook
        
        仅发送 critical/high 级别
        """
        url = os.environ.get("ALERT_WEBHOOK_URL")
        if not url:
            return False
        
        # 过滤 critical/high 级别
        critical_alerts = [
            a for a in new_alerts
            if a.severity in ("critical", "high")
        ]
        
        if not critical_alerts:
            # 标记为 skipped
            for alert in new_alerts:
                alert.webhook_sent = "skipped"
            return True
        
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": tenant_id,
            "site_id": site_id,
            "alert_count": len(critical_alerts),
            "alerts": [
                {
                    "code": a.alert_code,
                    "severity": a.severity,
                    "current_value": a.current_value,
                    "threshold": a.threshold,
                    "condition": a.condition,
                    "unit": a.unit,
                    "first_seen_at": a.first_seen_at.isoformat() if a.first_seen_at else None,
                }
                for a in critical_alerts
            ],
            "context": {
                "active_release_id": context.get("active_release_id"),
                "active_release_name": context.get("active_release_name"),
                "active_experiment_id": context.get("active_experiment_id"),
                "active_experiment_name": context.get("active_experiment_name"),
            },
        }
        
        now = datetime.utcnow()
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            
            # 标记为 sent
            for alert in critical_alerts:
                alert.webhook_sent = "sent"
                alert.webhook_sent_at = now
            
            logger.info("webhook_notification_sent", alert_count=len(critical_alerts))
            return True
        
        except Exception as e:
            # 标记为 failed
            for alert in critical_alerts:
                alert.webhook_sent = "failed"
            
            logger.warning("webhook_notification_failed", error=str(e))
            return False


# ============================================================
# 静默管理
# ============================================================

async def create_silence(
    db: AsyncSession,
    tenant_id: str,
    site_id: Optional[str],
    ends_at: datetime,
    alert_code: Optional[str] = None,
    severity: Optional[str] = None,
    reason: Optional[str] = None,
    created_by: str = "admin_console",
    starts_at: Optional[datetime] = None,
) -> AlertSilence:
    """创建静默规则"""
    silence = AlertSilence(
        tenant_id=tenant_id,
        site_id=site_id,
        alert_code=alert_code,
        severity=severity,
        starts_at=starts_at or datetime.utcnow(),
        ends_at=ends_at,
        reason=reason,
        created_by=created_by,
    )
    db.add(silence)
    await db.commit()
    await db.refresh(silence)
    return silence


async def list_silences(
    db: AsyncSession,
    tenant_id: str,
    site_id: Optional[str] = None,
    active_only: bool = True,
) -> List[AlertSilence]:
    """列出静默规则"""
    conditions = [AlertSilence.tenant_id == tenant_id]
    
    if site_id:
        conditions.append(
            or_(
                AlertSilence.site_id == site_id,
                AlertSilence.site_id.is_(None),
            )
        )
    
    if active_only:
        now = datetime.utcnow()
        conditions.append(AlertSilence.starts_at <= now)
        conditions.append(AlertSilence.ends_at >= now)
    
    stmt = select(AlertSilence).where(and_(*conditions)).order_by(AlertSilence.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_silence(
    db: AsyncSession,
    silence_id: str,
) -> bool:
    """删除静默规则"""
    stmt = select(AlertSilence).where(AlertSilence.id == silence_id)
    result = await db.execute(stmt)
    silence = result.scalar_one_or_none()
    
    if not silence:
        return False
    
    await db.delete(silence)
    await db.commit()
    return True


# ============================================================
# 事件查询
# ============================================================

async def list_alert_events(
    db: AsyncSession,
    tenant_id: str,
    site_id: Optional[str] = None,
    status: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
) -> List[AlertEvent]:
    """列出告警事件"""
    conditions = [AlertEvent.tenant_id == tenant_id]
    
    if site_id:
        conditions.append(AlertEvent.site_id == site_id)
    
    if status:
        conditions.append(AlertEvent.status == status)
    
    if since:
        conditions.append(AlertEvent.first_seen_at >= since)
    
    stmt = (
        select(AlertEvent)
        .where(and_(*conditions))
        .order_by(AlertEvent.first_seen_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_alert_event(
    db: AsyncSession,
    event_id: str,
) -> Optional[AlertEvent]:
    """获取单个告警事件"""
    stmt = select(AlertEvent).where(AlertEvent.id == event_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
