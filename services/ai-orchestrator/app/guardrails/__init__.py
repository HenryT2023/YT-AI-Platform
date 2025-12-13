"""
护栏模块

- 意图分类器：fact_seeking vs context_preference
- 证据闸门：事实性问题必须证据先行
- 输出校验器：检查文化准确性
- 策略加载器：per-site/per-npc 配置
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
from app.guardrails.intent_classifier_v2 import (
    IntentLabel,
    IntentResult,
    IntentContext,
    IntentClassifier,
    RuleIntentClassifier,
    LLMIntentClassifier,
    get_rule_classifier,
)
from app.guardrails.evidence_gate_v2 import (
    EvidenceGateV2,
    EvidenceGateResult as EvidenceGateResultV2,
    get_evidence_gate_v2,
)
from app.guardrails.evidence_gate_v3 import (
    EvidenceGateV3,
    EvidenceGateResult as EvidenceGateResultV3,
    get_evidence_gate_v3,
)
from app.guardrails.policy_loader import (
    PolicyLoader,
    EvidenceGatePolicy,
    AppliedRule,
    get_policy_loader,
)

__all__ = [
    # v1 (legacy)
    "QueryIntent",
    "IntentClassification",
    "QueryIntentClassifier",
    "get_intent_classifier",
    "classify_query_intent",
    "EvidenceGate",
    "EvidenceGateResult",
    "get_evidence_gate",
    # v2 (LLM intent classifier)
    "IntentLabel",
    "IntentResult",
    "IntentContext",
    "IntentClassifier",
    "RuleIntentClassifier",
    "LLMIntentClassifier",
    "get_rule_classifier",
    "EvidenceGateV2",
    "EvidenceGateResultV2",
    "get_evidence_gate_v2",
    # v3 (policy-based)
    "EvidenceGateV3",
    "EvidenceGateResultV3",
    "get_evidence_gate_v3",
    "PolicyLoader",
    "EvidenceGatePolicy",
    "AppliedRule",
    "get_policy_loader",
]
