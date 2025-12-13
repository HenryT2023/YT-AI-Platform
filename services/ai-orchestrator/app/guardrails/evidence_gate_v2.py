"""
Evidence Gate v2

证据闸门：事实性问题必须证据先行，否则强制保守

v2 改进：
1. 支持 LLM 意图分类器（通过 env 开关启用）
2. 异步接口
3. 更细粒度的意图标签
"""

import structlog
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.agent.schemas import CitationItem, PolicyMode
from app.core.config import settings
from app.guardrails.intent_classifier_v2 import (
    IntentLabel,
    IntentResult,
    IntentClassifier,
    IntentContext,
    RuleIntentClassifier,
    LLMIntentClassifier,
    get_rule_classifier,
)

logger = structlog.get_logger(__name__)


@dataclass
class EvidenceGateResult:
    """证据闸门结果"""

    passed: bool                      # 是否通过
    policy_mode: PolicyMode           # 强制的策略模式
    intent: IntentLabel               # 查询意图
    intent_confidence: float          # 意图置信度
    reason: str                       # 原因
    citations_count: int              # 引用数量
    forbidden_assertions: List[str]   # 检测到的禁止断言
    requires_filtering: bool          # 是否需要过滤输出
    classifier_type: str              # 分类器类型（rule/llm）
    cached: bool                      # 是否命中缓存


class EvidenceGateV2:
    """
    证据闸门 v2

    支持 LLM 意图分类器，带降级和缓存
    """

    def __init__(
        self,
        min_citations_for_fact: int = 1,
        use_llm_classifier: Optional[bool] = None,
        llm_provider=None,
        cache_client=None,
    ):
        self.min_citations = min_citations_for_fact
        self.use_llm = use_llm_classifier if use_llm_classifier is not None else settings.INTENT_CLASSIFIER_USE_LLM

        # 初始化分类器
        self.rule_classifier = RuleIntentClassifier()

        if self.use_llm:
            self.llm_classifier = LLMIntentClassifier(
                llm_provider=llm_provider,
                cache_client=cache_client,
                cache_ttl=settings.INTENT_CLASSIFIER_CACHE_TTL,
                fallback_classifier=self.rule_classifier,
            )
        else:
            self.llm_classifier = None

    def _get_classifier(self) -> IntentClassifier:
        """获取当前使用的分类器"""
        if self.use_llm and self.llm_classifier:
            return self.llm_classifier
        return self.rule_classifier

    async def check_before_llm(
        self,
        query: str,
        citations: List[CitationItem],
        context: Optional[IntentContext] = None,
    ) -> EvidenceGateResult:
        """
        LLM 调用前检查

        决定是否允许 LLM 生成，以及应该使用什么策略模式

        Args:
            query: 用户查询
            citations: 检索到的引用
            context: 意图分类上下文

        Returns:
            EvidenceGateResult
        """
        log = logger.bind(query=query[:50])

        # 1. 分类意图
        classifier = self._get_classifier()
        intent_result = await classifier.classify(query, context)

        log.info(
            "intent_classified",
            intent=intent_result.label.value,
            confidence=intent_result.confidence,
            classifier=intent_result.classifier_type,
            cached=intent_result.cached,
        )

        citations_count = len(citations)

        # 2. 根据意图检查证据
        if intent_result.label == IntentLabel.FACT_SEEKING:
            # 事实性问题：必须有证据
            if citations_count >= self.min_citations:
                return EvidenceGateResult(
                    passed=True,
                    policy_mode=PolicyMode.NORMAL,
                    intent=intent_result.label,
                    intent_confidence=intent_result.confidence,
                    reason="事实性问题，有足够证据支撑",
                    citations_count=citations_count,
                    forbidden_assertions=[],
                    requires_filtering=False,
                    classifier_type=intent_result.classifier_type,
                    cached=intent_result.cached,
                )
            else:
                return EvidenceGateResult(
                    passed=False,
                    policy_mode=PolicyMode.CONSERVATIVE,
                    intent=intent_result.label,
                    intent_confidence=intent_result.confidence,
                    reason=f"事实性问题，证据不足（需要 {self.min_citations}，实际 {citations_count}）",
                    citations_count=citations_count,
                    forbidden_assertions=[],
                    requires_filtering=False,
                    classifier_type=intent_result.classifier_type,
                    cached=intent_result.cached,
                )

        elif intent_result.label == IntentLabel.GREETING:
            # 问候：直接通过
            return EvidenceGateResult(
                passed=True,
                policy_mode=PolicyMode.NORMAL,
                intent=intent_result.label,
                intent_confidence=intent_result.confidence,
                reason="问候语，无需证据",
                citations_count=citations_count,
                forbidden_assertions=[],
                requires_filtering=False,
                classifier_type=intent_result.classifier_type,
                cached=intent_result.cached,
            )

        elif intent_result.label == IntentLabel.OUT_OF_SCOPE:
            # 超出范围：保守模式
            return EvidenceGateResult(
                passed=False,
                policy_mode=PolicyMode.CONSERVATIVE,
                intent=intent_result.label,
                intent_confidence=intent_result.confidence,
                reason="问题超出知识范围",
                citations_count=citations_count,
                forbidden_assertions=[],
                requires_filtering=False,
                classifier_type=intent_result.classifier_type,
                cached=intent_result.cached,
            )

        else:
            # 上下文偏好/澄清追问：允许使用记忆，但需要过滤史实断言
            return EvidenceGateResult(
                passed=True,
                policy_mode=PolicyMode.NORMAL,
                intent=intent_result.label,
                intent_confidence=intent_result.confidence,
                reason="上下文偏好问题，允许使用会话记忆",
                citations_count=citations_count,
                forbidden_assertions=[],
                requires_filtering=True,  # 需要过滤输出中的史实断言
                classifier_type=intent_result.classifier_type,
                cached=intent_result.cached,
            )

    async def check_after_llm(
        self,
        query: str,
        response_text: str,
        citations: List[CitationItem],
        intent: IntentLabel,
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
        forbidden = self.rule_classifier.contains_forbidden_assertions(response_text)

        if intent == IntentLabel.CONTEXT_PREFERENCE and forbidden and citations_count == 0:
            # 上下文偏好问题，但输出了无证据的史实断言
            log.warning(
                "forbidden_assertions_detected",
                assertions=forbidden[:5],
            )
            return EvidenceGateResult(
                passed=False,
                policy_mode=PolicyMode.CONSERVATIVE,
                intent=intent,
                intent_confidence=1.0,
                reason=f"检测到 {len(forbidden)} 个无证据的史实断言",
                citations_count=citations_count,
                forbidden_assertions=forbidden[:5],
                requires_filtering=True,
                classifier_type="rule",
                cached=False,
            )

        return EvidenceGateResult(
            passed=True,
            policy_mode=PolicyMode.NORMAL,
            intent=intent,
            intent_confidence=1.0,
            reason="输出检查通过",
            citations_count=citations_count,
            forbidden_assertions=[],
            requires_filtering=False,
            classifier_type="rule",
            cached=False,
        )

    def get_conservative_response(
        self,
        intent: IntentLabel,
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
        if intent == IntentLabel.FACT_SEEKING:
            return (
                f"这个问题涉及具体的历史事实，{npc_name}需要查阅族谱或文献才能准确回答。"
                f"建议您询问村中管理族谱的长辈，或查阅相关史料记载。"
            )
        elif intent == IntentLabel.OUT_OF_SCOPE:
            return (
                f"这个问题超出了{npc_name}的知识范围。"
                f"如果您想了解严田村的历史文化，{npc_name}很乐意为您介绍。"
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


# ============================================================
# 全局实例和工厂函数
# ============================================================

_gate_instance: Optional[EvidenceGateV2] = None


async def get_evidence_gate_v2(
    llm_provider=None,
    cache_client=None,
) -> EvidenceGateV2:
    """
    获取证据闸门实例

    Args:
        llm_provider: LLM Provider（可选，用于 LLM 意图分类）
        cache_client: Redis 缓存客户端（可选）

    Returns:
        EvidenceGateV2
    """
    global _gate_instance

    if _gate_instance is None:
        _gate_instance = EvidenceGateV2(
            llm_provider=llm_provider,
            cache_client=cache_client,
        )

    return _gate_instance


def reset_evidence_gate() -> None:
    """重置证据闸门实例（用于测试）"""
    global _gate_instance
    _gate_instance = None
