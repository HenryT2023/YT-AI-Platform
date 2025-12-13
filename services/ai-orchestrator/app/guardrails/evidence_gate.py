"""
Evidence Gate

证据闸门：事实性问题必须证据先行，否则强制保守

核心逻辑：
1. fact_seeking 意图：
   - 必须 retrieve_evidence 命中且 citations >= 1 才能 normal
   - 否则强制 conservative

2. context_preference 意图：
   - 允许使用 session memory
   - 但禁止输出具体史实断言（如年代、人名、事件）除非有 citations
"""

import structlog
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.agent.schemas import CitationItem, PolicyMode
from app.guardrails.intent_classifier import (
    QueryIntent,
    IntentClassification,
    QueryIntentClassifier,
    get_intent_classifier,
)

logger = structlog.get_logger(__name__)


@dataclass
class EvidenceGateResult:
    """证据闸门结果"""

    passed: bool                      # 是否通过
    policy_mode: PolicyMode           # 强制的策略模式
    intent: QueryIntent               # 查询意图
    reason: str                       # 原因
    citations_count: int              # 引用数量
    forbidden_assertions: List[str]   # 检测到的禁止断言
    requires_filtering: bool          # 是否需要过滤输出


class EvidenceGate:
    """
    证据闸门

    确保事实性问题有证据支撑，防止模型编造史实
    """

    def __init__(
        self,
        min_citations_for_fact: int = 1,
        classifier: Optional[QueryIntentClassifier] = None,
    ):
        self.min_citations = min_citations_for_fact
        self.classifier = classifier or get_intent_classifier()

    def check_before_llm(
        self,
        query: str,
        citations: List[CitationItem],
    ) -> EvidenceGateResult:
        """
        LLM 调用前检查

        决定是否允许 LLM 生成，以及应该使用什么策略模式

        Args:
            query: 用户查询
            citations: 检索到的引用

        Returns:
            EvidenceGateResult
        """
        log = logger.bind(query=query[:50])

        # 1. 分类意图
        intent_result = self.classifier.classify(query)
        log.info(
            "intent_classified",
            intent=intent_result.intent.value,
            confidence=intent_result.confidence,
        )

        citations_count = len(citations)

        # 2. 根据意图检查证据
        if intent_result.intent == QueryIntent.FACT_SEEKING:
            # 事实性问题：必须有证据
            if citations_count >= self.min_citations:
                return EvidenceGateResult(
                    passed=True,
                    policy_mode=PolicyMode.NORMAL,
                    intent=intent_result.intent,
                    reason="事实性问题，有足够证据支撑",
                    citations_count=citations_count,
                    forbidden_assertions=[],
                    requires_filtering=False,
                )
            else:
                return EvidenceGateResult(
                    passed=False,
                    policy_mode=PolicyMode.CONSERVATIVE,
                    intent=intent_result.intent,
                    reason=f"事实性问题，证据不足（需要 {self.min_citations}，实际 {citations_count}）",
                    citations_count=citations_count,
                    forbidden_assertions=[],
                    requires_filtering=False,
                )
        else:
            # 上下文偏好问题：允许使用记忆，但需要过滤史实断言
            return EvidenceGateResult(
                passed=True,
                policy_mode=PolicyMode.NORMAL,
                intent=intent_result.intent,
                reason="上下文偏好问题，允许使用会话记忆",
                citations_count=citations_count,
                forbidden_assertions=[],
                requires_filtering=True,  # 需要过滤输出中的史实断言
            )

    def check_after_llm(
        self,
        query: str,
        response_text: str,
        citations: List[CitationItem],
        intent: QueryIntent,
    ) -> EvidenceGateResult:
        """
        LLM 调用后检查

        检查输出是否包含无证据的史实断言

        Args:
            query: 用户查询
            response_text: LLM 响应文本
            citations: 引用列表
            intent: 查询意图

        Returns:
            EvidenceGateResult
        """
        log = logger.bind(query=query[:50])

        citations_count = len(citations)

        # 检查禁止的史实断言
        forbidden = self.classifier.contains_forbidden_assertions(response_text)

        if intent == QueryIntent.CONTEXT_PREFERENCE and forbidden and citations_count == 0:
            # 上下文偏好问题，但输出了无证据的史实断言
            log.warning(
                "forbidden_assertions_detected",
                assertions=forbidden[:5],
            )
            return EvidenceGateResult(
                passed=False,
                policy_mode=PolicyMode.CONSERVATIVE,
                intent=intent,
                reason=f"检测到 {len(forbidden)} 个无证据的史实断言",
                citations_count=citations_count,
                forbidden_assertions=forbidden[:5],
                requires_filtering=True,
            )

        return EvidenceGateResult(
            passed=True,
            policy_mode=PolicyMode.NORMAL,
            intent=intent,
            reason="输出检查通过",
            citations_count=citations_count,
            forbidden_assertions=[],
            requires_filtering=False,
        )

    def get_conservative_response(
        self,
        intent: QueryIntent,
        query: str,
        npc_name: str = "我",
    ) -> str:
        """
        获取保守模式响应

        Args:
            intent: 查询意图
            query: 用户查询
            npc_name: NPC 名称

        Returns:
            保守模式响应文本
        """
        if intent == QueryIntent.FACT_SEEKING:
            return (
                f"这个问题涉及具体的历史事实，{npc_name}需要查阅族谱或文献才能准确回答。"
                f"建议您询问村中管理族谱的长辈，或查阅相关史料记载。"
            )
        else:
            return (
                f"关于这个问题，{npc_name}不太确定具体细节。"
                f"如果您想了解准确的历史信息，建议查阅相关文献记载。"
            )

    def filter_forbidden_assertions(
        self,
        text: str,
        npc_name: str = "我",
    ) -> str:
        """
        过滤禁止的史实断言

        将无证据的史实断言替换为模糊表述

        Args:
            text: 原始文本
            npc_name: NPC 名称

        Returns:
            过滤后的文本
        """
        import re

        # 替换年份
        text = re.sub(r"公元(\d+)年", r"很久以前", text)
        text = re.sub(r"(\d{3,4})年", r"多年前", text)
        text = re.sub(r"距今(\d+)年", r"很多年前", text)

        # 替换代数
        text = re.sub(r"第(\d+)代", r"某一代", text)
        text = re.sub(r"第(\d+)世", r"某一世", text)

        # 替换朝代年号
        text = re.sub(
            r"(康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统)(\d*)年?间?",
            r"清朝某个时期",
            text,
        )
        text = re.sub(
            r"(洪武|永乐|正统|成化|弘治|正德|嘉靖|隆庆|万历|崇祯)(\d*)年?间?",
            r"明朝某个时期",
            text,
        )

        return text


# 全局实例
_gate: Optional[EvidenceGate] = None


def get_evidence_gate() -> EvidenceGate:
    """获取全局证据闸门"""
    global _gate
    if _gate is None:
        _gate = EvidenceGate()
    return _gate
