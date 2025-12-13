"""
反馈自动分派规则加载器

从 JSON 配置文件加载分派规则，支持缓存和 TTL
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# 配置
POLICY_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "policies" / "feedback_routing_policy_v0.1.json"
CACHE_TTL_SECONDS = 300  # 5 分钟缓存

# 缓存
_policy_cache: Optional[Dict[str, Any]] = None
_policy_cache_time: float = 0


@dataclass
class RoutingResult:
    """分派结果"""
    assignee: Optional[str] = None
    group: Optional[str] = None
    sla_hours: int = 24
    matched_rule_id: Optional[str] = None


def load_policy(force_reload: bool = False) -> Dict[str, Any]:
    """
    加载分派规则配置
    
    支持缓存，TTL 5 分钟
    """
    global _policy_cache, _policy_cache_time
    
    now = time.time()
    if not force_reload and _policy_cache and (now - _policy_cache_time) < CACHE_TTL_SECONDS:
        return _policy_cache
    
    try:
        if POLICY_PATH.exists():
            with open(POLICY_PATH, "r", encoding="utf-8") as f:
                _policy_cache = json.load(f)
                _policy_cache_time = now
                logger.info("feedback_routing_policy_loaded", path=str(POLICY_PATH))
                return _policy_cache
        else:
            logger.warning("feedback_routing_policy_not_found", path=str(POLICY_PATH))
            return get_default_policy()
    except Exception as e:
        logger.error("feedback_routing_policy_load_error", error=str(e))
        return get_default_policy()


def get_default_policy() -> Dict[str, Any]:
    """获取默认策略"""
    return {
        "default_sla_hours": 24,
        "default_group": "support",
        "rules": [
            {
                "id": "default",
                "conditions": {},
                "action": {
                    "group": "support",
                    "sla_hours": 24,
                },
                "priority": 0,
            }
        ],
    }


def match_rule(
    severity: str,
    feedback_type: str,
    site_id: Optional[str] = None,
    npc_id: Optional[str] = None,
) -> RoutingResult:
    """
    匹配分派规则
    
    Args:
        severity: 严重程度 (low/medium/high/critical)
        feedback_type: 反馈类型 (correction/fact_error/missing_info/...)
        site_id: 站点 ID（可选）
        npc_id: NPC ID（可选）
        
    Returns:
        RoutingResult
    """
    policy = load_policy()
    rules = policy.get("rules", [])
    
    # 按优先级排序（高优先级在前）
    sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)
    
    for rule in sorted_rules:
        conditions = rule.get("conditions", {})
        
        # 检查条件匹配
        if not _match_conditions(conditions, severity, feedback_type, site_id, npc_id):
            continue
        
        # 匹配成功
        action = rule.get("action", {})
        return RoutingResult(
            assignee=action.get("assignee"),
            group=action.get("group", policy.get("default_group", "support")),
            sla_hours=action.get("sla_hours", policy.get("default_sla_hours", 24)),
            matched_rule_id=rule.get("id"),
        )
    
    # 无匹配，返回默认
    return RoutingResult(
        group=policy.get("default_group", "support"),
        sla_hours=policy.get("default_sla_hours", 24),
        matched_rule_id="default",
    )


def _match_conditions(
    conditions: Dict[str, Any],
    severity: str,
    feedback_type: str,
    site_id: Optional[str],
    npc_id: Optional[str],
) -> bool:
    """检查条件是否匹配"""
    # 空条件匹配所有
    if not conditions:
        return True
    
    # 检查 severity
    if "severity" in conditions:
        if conditions["severity"] != severity:
            return False
    
    # 检查 type
    if "type" in conditions:
        if conditions["type"] != feedback_type:
            return False
    
    # 检查 site_id
    if "site_id" in conditions:
        if conditions["site_id"] != site_id:
            return False
    
    # 检查 npc_id
    if "npc_id" in conditions:
        if conditions["npc_id"] != npc_id:
            return False
    
    return True


def get_routing_for_feedback(
    severity: str,
    feedback_type: str,
    site_id: Optional[str] = None,
    npc_id: Optional[str] = None,
) -> RoutingResult:
    """
    获取反馈的分派结果
    
    这是对外的主要接口
    """
    result = match_rule(severity, feedback_type, site_id, npc_id)
    logger.info(
        "feedback_routing_matched",
        severity=severity,
        feedback_type=feedback_type,
        site_id=site_id,
        matched_rule=result.matched_rule_id,
        assignee=result.assignee,
        group=result.group,
        sla_hours=result.sla_hours,
    )
    return result
