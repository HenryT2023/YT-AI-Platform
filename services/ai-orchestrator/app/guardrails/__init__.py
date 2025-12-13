"""
护栏模块

- 意图分类器：fact_seeking vs context_preference
- 证据闸门：事实性问题必须证据先行
- 输出校验器：检查文化准确性
"""

from app.guardrails.intent_classifier import (
    QueryIntent,
    IntentClassification,
    QueryIntentClassifier,
    get_intent_classifier,
    classify_query_intent,
)
from app.guardrails.evidence_gate import (
    EvidenceGate,
    EvidenceGateResult,
    get_evidence_gate,
)

__all__ = [
    "QueryIntent",
    "IntentClassification",
    "QueryIntentClassifier",
    "get_intent_classifier",
    "classify_query_intent",
    "EvidenceGate",
    "EvidenceGateResult",
    "get_evidence_gate",
]
