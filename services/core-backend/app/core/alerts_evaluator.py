"""
告警评估器

基于配置化规则评估系统指标，生成告警列表
支持 tenant_id/site_id 维度
"""

import os
import yaml
import httpx
import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user_feedback import UserFeedback, FeedbackStatus
from app.database.models.trace_ledger import TraceLedger

logger = structlog.get_logger(__name__)


# ============================================================
# 数据结构
# ============================================================

class AlertSeverity(str, Enum):
    """告警级别"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class AlertRule:
    """告警规则"""
    code: str
    name: str
    category: str
    severity: str
    description: str
    metric: str
    condition: str
    threshold: Optional[float]
    unit: Optional[str] = None
    window: str = "15m"
    recommended_actions: List[str] = field(default_factory=list)


@dataclass
class Alert:
    """告警实例"""
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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "window": self.window,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "unit": self.unit,
            "condition": self.condition,
            "triggered_at": self.triggered_at.isoformat(),
            "recommended_actions": self.recommended_actions,
        }


@dataclass
class MetricsSnapshot:
    """指标快照"""
    timestamp: datetime
    tenant_id: str
    site_id: Optional[str]
    
    # Health
    healthz_status: str = "healthy"
    qdrant_status: str = "healthy"
    redis_status: str = "healthy"
    
    # LLM
    llm_success_rate: float = 100.0
    llm_fallback_rate: float = 0.0
    llm_p95_latency_ms: float = 0.0
    
    # Gate
    gate_conservative_rate: float = 0.0
    gate_refuse_rate: float = 0.0
    gate_citations_rate: float = 100.0
    
    # Vector
    vector_coverage_ratio: float = 100.0
    vector_stale_count: int = 0
    
    # Embedding
    embedding_daily_cost: float = 0.0
    embedding_rate_limited_rate: float = 0.0
    embedding_dedup_hit_rate: float = 0.0
    
    # Feedback
    feedback_overdue_count: int = 0
    feedback_pending_count: int = 0
    feedback_unassigned_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "health": {
                "healthz_status": self.healthz_status,
                "qdrant_status": self.qdrant_status,
                "redis_status": self.redis_status,
            },
            "llm": {
                "success_rate": self.llm_success_rate,
                "fallback_rate": self.llm_fallback_rate,
                "p95_latency_ms": self.llm_p95_latency_ms,
            },
            "gate": {
                "conservative_rate": self.gate_conservative_rate,
                "refuse_rate": self.gate_refuse_rate,
                "citations_rate": self.gate_citations_rate,
            },
            "vector": {
                "coverage_ratio": self.vector_coverage_ratio,
                "stale_count": self.vector_stale_count,
            },
            "embedding": {
                "daily_cost": self.embedding_daily_cost,
                "rate_limited_rate": self.embedding_rate_limited_rate,
                "dedup_hit_rate": self.embedding_dedup_hit_rate,
            },
            "feedback": {
                "overdue_count": self.feedback_overdue_count,
                "pending_count": self.feedback_pending_count,
                "unassigned_count": self.feedback_unassigned_count,
            },
        }


@dataclass
class EvaluationResult:
    """评估结果"""
    timestamp: datetime
    tenant_id: str
    site_id: Optional[str]
    window: str
    active_alerts: List[Alert]
    metrics_snapshot: MetricsSnapshot
    rules_evaluated: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "window": self.window,
            "active_alerts": [a.to_dict() for a in self.active_alerts],
            "alert_count": len(self.active_alerts),
            "alerts_by_severity": self._count_by_severity(),
            "metrics_snapshot": self.metrics_snapshot.to_dict(),
            "rules_evaluated": self.rules_evaluated,
        }
    
    def _count_by_severity(self) -> Dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for alert in self.active_alerts:
            if alert.severity in counts:
                counts[alert.severity] += 1
        return counts


# ============================================================
# 告警评估器
# ============================================================

class AlertsEvaluator:
    """告警评估器"""
    
    def __init__(self, db: AsyncSession, policy_path: Optional[str] = None):
        self.db = db
        self.policy_path = policy_path or self._default_policy_path()
        self.rules: List[AlertRule] = []
        self._load_policy()
    
    def _default_policy_path(self) -> str:
        """默认策略文件路径"""
        base_dir = Path(__file__).parent.parent.parent
        return str(base_dir / "data" / "policies" / "alerts_policy_v0.1.yaml")
    
    def _load_policy(self):
        """加载告警策略配置"""
        try:
            with open(self.policy_path, "r", encoding="utf-8") as f:
                policy = yaml.safe_load(f)
            
            self.rules = []
            for rule_config in policy.get("rules", []):
                rule = AlertRule(
                    code=rule_config["code"],
                    name=rule_config["name"],
                    category=rule_config["category"],
                    severity=rule_config["severity"],
                    description=rule_config["description"],
                    metric=rule_config["metric"],
                    condition=rule_config["condition"],
                    threshold=rule_config.get("threshold"),
                    unit=rule_config.get("unit"),
                    window=rule_config.get("window", "15m"),
                    recommended_actions=rule_config.get("recommended_actions", []),
                )
                self.rules.append(rule)
            
            logger.info("alerts_policy_loaded", rule_count=len(self.rules))
        except Exception as e:
            logger.error("alerts_policy_load_failed", error=str(e))
            self.rules = []
    
    def _parse_window(self, window: str) -> timedelta:
        """解析时间窗口"""
        if window.endswith("m"):
            return timedelta(minutes=int(window[:-1]))
        elif window.endswith("h"):
            return timedelta(hours=int(window[:-1]))
        elif window.endswith("d"):
            return timedelta(days=int(window[:-1]))
        return timedelta(minutes=15)
    
    async def evaluate(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        window: str = "15m",
    ) -> EvaluationResult:
        """
        评估告警规则
        
        Args:
            tenant_id: 租户 ID
            site_id: 站点 ID（可选）
            window: 评估窗口（如 15m, 1h, 24h）
        
        Returns:
            EvaluationResult: 评估结果
        """
        log = logger.bind(tenant_id=tenant_id, site_id=site_id, window=window)
        log.info("alerts_evaluation_start")
        
        now = datetime.utcnow()
        
        # 1. 收集指标快照
        snapshot = await self._collect_metrics(tenant_id, site_id, window)
        
        # 2. 评估每条规则
        active_alerts = []
        for rule in self.rules:
            alert = self._evaluate_rule(rule, snapshot, now)
            if alert:
                active_alerts.append(alert)
        
        # 3. 按严重程度排序
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        active_alerts.sort(key=lambda a: severity_order.get(a.severity, 99))
        
        log.info(
            "alerts_evaluation_complete",
            alert_count=len(active_alerts),
            rules_evaluated=len(self.rules),
        )
        
        return EvaluationResult(
            timestamp=now,
            tenant_id=tenant_id,
            site_id=site_id,
            window=window,
            active_alerts=active_alerts,
            metrics_snapshot=snapshot,
            rules_evaluated=len(self.rules),
        )
    
    async def _collect_metrics(
        self,
        tenant_id: str,
        site_id: Optional[str],
        window: str,
    ) -> MetricsSnapshot:
        """收集指标快照"""
        now = datetime.utcnow()
        time_delta = self._parse_window(window)
        start_time = now - time_delta
        
        snapshot = MetricsSnapshot(
            timestamp=now,
            tenant_id=tenant_id,
            site_id=site_id,
        )
        
        # 收集 trace_ledger 指标
        await self._collect_trace_metrics(snapshot, tenant_id, site_id, start_time)
        
        # 收集 feedback 指标
        await self._collect_feedback_metrics(snapshot, tenant_id, site_id)
        
        # 收集 embedding 指标（如果有）
        await self._collect_embedding_metrics(snapshot, tenant_id, site_id, start_time)
        
        # 收集 vector 指标（如果有）
        await self._collect_vector_metrics(snapshot, tenant_id, site_id)
        
        return snapshot
    
    async def _collect_trace_metrics(
        self,
        snapshot: MetricsSnapshot,
        tenant_id: str,
        site_id: Optional[str],
        start_time: datetime,
    ):
        """从 trace_ledger 收集指标"""
        try:
            conditions = [
                TraceLedger.tenant_id == tenant_id,
                TraceLedger.created_at >= start_time,
            ]
            if site_id:
                conditions.append(TraceLedger.site_id == site_id)
            
            # 总数和状态分布
            stmt = select(
                func.count(TraceLedger.id).label("total"),
                func.sum(func.cast(TraceLedger.status == "success", Integer)).label("success"),
                func.sum(func.cast(TraceLedger.status == "error", Integer)).label("error"),
                func.sum(func.cast(TraceLedger.policy_mode == "conservative", Integer)).label("conservative"),
                func.sum(func.cast(TraceLedger.policy_mode == "refuse", Integer)).label("refuse"),
            ).where(and_(*conditions))
            
            result = await self.db.execute(stmt)
            row = result.one()
            
            total = row.total or 0
            success = row.success or 0
            error = row.error or 0
            conservative = row.conservative or 0
            refuse = row.refuse or 0
            
            if total > 0:
                snapshot.llm_success_rate = round(success / total * 100, 2)
                snapshot.llm_fallback_rate = round(error / total * 100, 2)
                snapshot.gate_conservative_rate = round(conservative / total * 100, 2)
                snapshot.gate_refuse_rate = round(refuse / total * 100, 2)
                
                # 引用率（有 evidence_ids 的比例）
                citations_stmt = select(
                    func.count(TraceLedger.id)
                ).where(
                    and_(
                        *conditions,
                        TraceLedger.evidence_ids != None,
                        func.array_length(TraceLedger.evidence_ids, 1) > 0,
                    )
                )
                citations_result = await self.db.execute(citations_stmt)
                citations_count = citations_result.scalar() or 0
                snapshot.gate_citations_rate = round(citations_count / total * 100, 2)
            
            # P95 延迟
            try:
                from sqlalchemy import text as sql_text
                where_clauses = ["tenant_id = :tenant_id", "created_at >= :start_time"]
                params = {"tenant_id": tenant_id, "start_time": start_time}
                if site_id:
                    where_clauses.append("site_id = :site_id")
                    params["site_id"] = site_id
                
                where_sql = " AND ".join(where_clauses)
                p95_stmt = sql_text(f"""
                    SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
                    FROM trace_ledger
                    WHERE {where_sql} AND latency_ms IS NOT NULL
                """)
                p95_result = await self.db.execute(p95_stmt, params)
                p95_row = p95_result.one()
                if p95_row.p95 is not None:
                    snapshot.llm_p95_latency_ms = round(float(p95_row.p95), 2)
            except Exception as e:
                logger.warning("p95_latency_query_failed", error=str(e))
        
        except Exception as e:
            logger.warning("trace_metrics_collection_failed", error=str(e))
    
    async def _collect_feedback_metrics(
        self,
        snapshot: MetricsSnapshot,
        tenant_id: str,
        site_id: Optional[str],
    ):
        """收集 feedback 指标"""
        try:
            conditions = [UserFeedback.tenant_id == tenant_id]
            if site_id:
                conditions.append(UserFeedback.site_id == site_id)
            
            # 逾期数
            overdue_stmt = select(func.count(UserFeedback.id)).where(
                and_(
                    *conditions,
                    UserFeedback.overdue_flag == True,
                    UserFeedback.status.in_(["pending", "in_progress", "triaged"]),
                )
            )
            overdue_result = await self.db.execute(overdue_stmt)
            snapshot.feedback_overdue_count = overdue_result.scalar() or 0
            
            # 待处理数
            pending_stmt = select(func.count(UserFeedback.id)).where(
                and_(
                    *conditions,
                    UserFeedback.status.in_(["pending", "triaged"]),
                )
            )
            pending_result = await self.db.execute(pending_stmt)
            snapshot.feedback_pending_count = pending_result.scalar() or 0
            
            # 未分配数
            unassigned_stmt = select(func.count(UserFeedback.id)).where(
                and_(
                    *conditions,
                    UserFeedback.assignee.is_(None),
                    UserFeedback.status.in_(["pending", "triaged"]),
                )
            )
            unassigned_result = await self.db.execute(unassigned_stmt)
            snapshot.feedback_unassigned_count = unassigned_result.scalar() or 0
        
        except Exception as e:
            logger.warning("feedback_metrics_collection_failed", error=str(e))
    
    async def _collect_embedding_metrics(
        self,
        snapshot: MetricsSnapshot,
        tenant_id: str,
        site_id: Optional[str],
        start_time: datetime,
    ):
        """收集 embedding 指标"""
        try:
            from app.database.models import EmbeddingUsage
            
            conditions = [
                EmbeddingUsage.tenant_id == tenant_id,
                EmbeddingUsage.created_at >= start_time,
            ]
            if site_id:
                conditions.append(EmbeddingUsage.site_id == site_id)
            
            stmt = select(
                func.count(EmbeddingUsage.id).label("total"),
                func.sum(func.cast(EmbeddingUsage.status == "rate_limited", Integer)).label("rate_limited"),
                func.sum(func.cast(EmbeddingUsage.status == "dedup_hit", Integer)).label("dedup_hit"),
                func.sum(EmbeddingUsage.cost_estimate).label("total_cost"),
            ).where(and_(*conditions))
            
            result = await self.db.execute(stmt)
            row = result.one()
            
            total = row.total or 0
            rate_limited = row.rate_limited or 0
            dedup_hit = row.dedup_hit or 0
            
            if total > 0:
                snapshot.embedding_rate_limited_rate = round(rate_limited / total * 100, 2)
                snapshot.embedding_dedup_hit_rate = round(dedup_hit / total * 100, 2)
            
            snapshot.embedding_daily_cost = round(row.total_cost or 0, 4)
        
        except Exception as e:
            logger.warning("embedding_metrics_collection_failed", error=str(e))
    
    async def _collect_vector_metrics(
        self,
        snapshot: MetricsSnapshot,
        tenant_id: str,
        site_id: Optional[str],
    ):
        """收集 vector 指标"""
        try:
            from app.database.models import Evidence
            
            conditions = [
                Evidence.tenant_id == tenant_id,
                Evidence.deleted_at.is_(None),
            ]
            if site_id:
                conditions.append(Evidence.site_id == site_id)
            
            # 总数
            total_stmt = select(func.count(Evidence.id)).where(and_(*conditions))
            total_result = await self.db.execute(total_stmt)
            total = total_result.scalar() or 0
            
            # 已向量化数
            vectorized_stmt = select(func.count(Evidence.id)).where(
                and_(*conditions, Evidence.vector_updated_at.isnot(None))
            )
            vectorized_result = await self.db.execute(vectorized_stmt)
            vectorized = vectorized_result.scalar() or 0
            
            # 过期数
            stale_stmt = select(func.count(Evidence.id)).where(
                and_(
                    *conditions,
                    Evidence.vector_updated_at.isnot(None),
                    Evidence.updated_at > Evidence.vector_updated_at,
                )
            )
            stale_result = await self.db.execute(stale_stmt)
            stale = stale_result.scalar() or 0
            
            if total > 0:
                snapshot.vector_coverage_ratio = round(vectorized / total * 100, 2)
            snapshot.vector_stale_count = stale
        
        except Exception as e:
            logger.warning("vector_metrics_collection_failed", error=str(e))
    
    def _evaluate_rule(
        self,
        rule: AlertRule,
        snapshot: MetricsSnapshot,
        now: datetime,
    ) -> Optional[Alert]:
        """评估单条规则"""
        # 获取指标值
        value = self._get_metric_value(rule.metric, snapshot)
        if value is None:
            return None
        
        # 评估条件
        triggered = self._check_condition(value, rule.condition, rule.threshold)
        
        if triggered:
            return Alert(
                code=rule.code,
                name=rule.name,
                severity=rule.severity,
                category=rule.category,
                description=rule.description,
                window=rule.window,
                current_value=value,
                threshold=rule.threshold,
                unit=rule.unit,
                condition=rule.condition,
                triggered_at=now,
                recommended_actions=rule.recommended_actions,
            )
        
        return None
    
    def _get_metric_value(self, metric: str, snapshot: MetricsSnapshot) -> Optional[Any]:
        """获取指标值"""
        metric_map = {
            "healthz.status": snapshot.healthz_status,
            "qdrant.status": snapshot.qdrant_status,
            "redis.status": snapshot.redis_status,
            "llm.success_rate": snapshot.llm_success_rate,
            "llm.fallback_rate": snapshot.llm_fallback_rate,
            "llm.p95_latency_ms": snapshot.llm_p95_latency_ms,
            "gate.conservative_rate": snapshot.gate_conservative_rate,
            "gate.refuse_rate": snapshot.gate_refuse_rate,
            "gate.citations_rate": snapshot.gate_citations_rate,
            "vector.coverage_ratio": snapshot.vector_coverage_ratio,
            "vector.stale_count": snapshot.vector_stale_count,
            "embedding.daily_cost": snapshot.embedding_daily_cost,
            "embedding.rate_limited_rate": snapshot.embedding_rate_limited_rate,
            "embedding.dedup_hit_rate": snapshot.embedding_dedup_hit_rate,
            "feedback.overdue_count": snapshot.feedback_overdue_count,
            "feedback.pending_count": snapshot.feedback_pending_count,
            "feedback.unassigned_count": snapshot.feedback_unassigned_count,
        }
        return metric_map.get(metric)
    
    def _check_condition(
        self,
        value: Any,
        condition: str,
        threshold: Optional[float],
    ) -> bool:
        """检查条件是否满足"""
        if condition == "!= healthy":
            return value != "healthy"
        
        if threshold is None:
            return False
        
        try:
            value = float(value)
            if condition == "<":
                return value < threshold
            elif condition == ">":
                return value > threshold
            elif condition == "<=":
                return value <= threshold
            elif condition == ">=":
                return value >= threshold
            elif condition == "==":
                return value == threshold
        except (ValueError, TypeError):
            pass
        
        return False


# 需要导入 Integer
from sqlalchemy import Integer


async def send_webhook_notification(
    alerts: List[Alert],
    tenant_id: str,
    site_id: Optional[str],
    webhook_url: Optional[str] = None,
) -> bool:
    """
    发送 webhook 通知
    
    仅发送 critical/high 级别告警
    """
    url = webhook_url or os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        return False
    
    # 过滤 critical/high 级别
    critical_alerts = [a for a in alerts if a.severity in ("critical", "high")]
    if not critical_alerts:
        return True
    
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
        "site_id": site_id,
        "alert_count": len(critical_alerts),
        "alerts": [a.to_dict() for a in critical_alerts],
    }
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.info("webhook_notification_sent", alert_count=len(critical_alerts))
            return True
    except Exception as e:
        logger.warning("webhook_notification_failed", error=str(e))
        return False
