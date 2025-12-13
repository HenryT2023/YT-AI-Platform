"""
Evidence Gate v3

证据闸门：事实性问题必须证据先行，否则强制保守

v3 改进：
1. 支持策略配置（per-site/per-npc）
2. 策略热更新（缓存 + TTL）
3. 审计日志（policy_version + applied_rule）
4. 软断言支持（allowed_soft_claims）
"""

import re
import structlog
from dataclasses import dataclass, field, asdict
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
)
from app.guardrails.policy_loader import (
    PolicyLoader,
    AppliedRule,
    get_policy_loader,
)

logger = structlog.get_logger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class EvidenceGateResult:
    """证据闸门结果"""

    passed: bool                      # 是否通过
    policy_mode: PolicyMode           # 强制的策略模式
    intent: IntentLabel               # 查询意图
    intent_confidence: float          # 意图置信度
    reason: str                       # 原因
    citations_count: int              # 引用数量
    citations_score: float            # 引用平均分数
    forbidden_assertions: List[str]   # 检测到的禁止断言
    soft_claims_used: List[str]       # 使用的软断言
    requires_filtering: bool          # 是否需要过滤输出
    classifier_type: str              # 分类器类型（rule/llm）
    cached: bool                      # 是否命中缓存

    # 审计字段
    policy_version: str = ""          # 策略版本
    policy_hash: str = ""             # 策略 hash
    applied_rule: Optional[Dict[str, Any]] = None  # 应用的规则


# ============================================================
# Evidence Gate v3
# ============================================================

class EvidenceGateV3:
    """
    证据闸门 v3

    支持：
    1. 策略配置（per-site/per-npc）
    2. 策略热更新
    3. 审计日志
    4. 软断言
    """

    def __init__(
        self,
        policy_loader: Optional[PolicyLoader] = None,
        use_llm_classifier: Optional[bool] = None,
        llm_provider=None,
        cache_client=None,
    ):
        self.policy_loader = policy_loader or get_policy_loader()
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

    def _get_citations_score(self, citations: List[CitationItem]) -> float:
        """计算引用平均分数"""
        if not citations:
            return 0.0
        scores = [c.score for c in citations if hasattr(c, 'score') and c.score is not None]
        if not scores:
            return 0.5  # 默认分数
        return sum(scores) / len(scores)

    async def check_before_llm(
        self,
        query: str,
        citations: List[CitationItem],
        context: Optional[IntentContext] = None,
        site_id: Optional[str] = None,
        npc_id: Optional[str] = None,
    ) -> EvidenceGateResult:
        """
        LLM 调用前检查

        决定是否允许 LLM 生成，以及应该使用什么策略模式

        Args:
            query: 用户查询
            citations: 检索到的引用
            context: 意图分类上下文
            site_id: 站点 ID（用于策略查找）
            npc_id: NPC ID（用于策略查找）

        Returns:
            EvidenceGateResult
        """
        log = logger.bind(query=query[:50], site_id=site_id, npc_id=npc_id)

        # 1. 加载策略
        policy = self.policy_loader.load()
        _site_id = site_id or (context.site_id if context else settings.DEFAULT_SITE_ID)
        _npc_id = npc_id or (context.npc_id if context else None)

        # 2. 分类意图
        classifier = self._get_classifier()
        intent_result = await classifier.classify(query, context)

        log.info(
            "intent_classified",
            intent=intent_result.label.value,
            confidence=intent_result.confidence,
            classifier=intent_result.classifier_type,
            cached=intent_result.cached,
        )

        # 3. 获取应用的规则
        applied_rule = self.policy_loader.get_applied_rule(
            site_id=_site_id,
            npc_id=_npc_id,
            intent=intent_result.label.value,
        )

        # 4. 获取上下文策略
        context_policy = policy.get_policy_for_context(_site_id, _npc_id)
        min_citations = applied_rule.min_citations
        min_score = applied_rule.min_score

        # 5. 检查意图覆盖
        intent_override = policy.get_intent_override(intent_result.label.value)
        if intent_override and not intent_override.requires_evidence:
            # 该意图不需要证据
            return EvidenceGateResult(
                passed=True,
                policy_mode=PolicyMode.NORMAL,
                intent=intent_result.label,
                intent_confidence=intent_result.confidence,
                reason=f"{intent_result.label.value} 意图无需证据",
                citations_count=len(citations),
                citations_score=self._get_citations_score(citations),
                forbidden_assertions=[],
                soft_claims_used=[],
                requires_filtering=intent_override.requires_filtering,
                classifier_type=intent_result.classifier_type,
                cached=intent_result.cached,
                policy_version=policy.version,
                policy_hash=policy._hash,
                applied_rule=asdict(applied_rule),
            )

        citations_count = len(citations)
        citations_score = self._get_citations_score(citations)

        log.debug(
            "policy_applied",
            min_citations=min_citations,
            min_score=min_score,
            actual_citations=citations_count,
            actual_score=citations_score,
            policy_version=policy.version,
        )

        # 6. 根据意图检查证据
        if intent_result.label == IntentLabel.FACT_SEEKING:
            # 事实性问题：必须有足够证据且分数达标
            if citations_count >= min_citations and citations_score >= min_score:
                return EvidenceGateResult(
                    passed=True,
                    policy_mode=PolicyMode.NORMAL,
                    intent=intent_result.label,
                    intent_confidence=intent_result.confidence,
                    reason="事实性问题，有足够证据支撑",
                    citations_count=citations_count,
                    citations_score=citations_score,
                    forbidden_assertions=[],
                    soft_claims_used=[],
                    requires_filtering=False,
                    classifier_type=intent_result.classifier_type,
                    cached=intent_result.cached,
                    policy_version=policy.version,
                    policy_hash=policy._hash,
                    applied_rule=asdict(applied_rule),
                )
            else:
                reason_parts = []
                if citations_count < min_citations:
                    reason_parts.append(f"引用数不足（需要 {min_citations}，实际 {citations_count}）")
                if citations_score < min_score:
                    reason_parts.append(f"引用分数不足（需要 {min_score:.2f}，实际 {citations_score:.2f}）")

                return EvidenceGateResult(
                    passed=False,
                    policy_mode=PolicyMode.CONSERVATIVE,
                    intent=intent_result.label,
                    intent_confidence=intent_result.confidence,
                    reason="事实性问题，" + "；".join(reason_parts),
                    citations_count=citations_count,
                    citations_score=citations_score,
                    forbidden_assertions=[],
                    soft_claims_used=[],
                    requires_filtering=False,
                    classifier_type=intent_result.classifier_type,
                    cached=intent_result.cached,
                    policy_version=policy.version,
                    policy_hash=policy._hash,
                    applied_rule=asdict(applied_rule),
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
                citations_score=citations_score,
                forbidden_assertions=[],
                soft_claims_used=[],
                requires_filtering=False,
                classifier_type=intent_result.classifier_type,
                cached=intent_result.cached,
                policy_version=policy.version,
                policy_hash=policy._hash,
                applied_rule=asdict(applied_rule),
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
                citations_score=citations_score,
                forbidden_assertions=[],
                soft_claims_used=[],
                requires_filtering=False,
                classifier_type=intent_result.classifier_type,
                cached=intent_result.cached,
                policy_version=policy.version,
                policy_hash=policy._hash,
                applied_rule=asdict(applied_rule),
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
                citations_score=citations_score,
                forbidden_assertions=[],
                soft_claims_used=[],
                requires_filtering=True,
                classifier_type=intent_result.classifier_type,
                cached=intent_result.cached,
                policy_version=policy.version,
                policy_hash=policy._hash,
                applied_rule=asdict(applied_rule),
            )

    async def check_after_llm(
        self,
        query: str,
        response_text: str,
        citations: List[CitationItem],
        intent: IntentLabel,
        site_id: Optional[str] = None,
        npc_id: Optional[str] = None,
    ) -> EvidenceGateResult:
        """
        LLM 调用后检查

        检查输出是否包含无证据的史实断言

        Args:
            query: 用户查询
            response_text: LLM 响应文本
            citations: 引用列表
            intent: 查询意图
            site_id: 站点 ID
            npc_id: NPC ID

        Returns:
            EvidenceGateResult
        """
        log = logger.bind(query=query[:50])

        # 加载策略
        policy = self.policy_loader.load()
        _site_id = site_id or settings.DEFAULT_SITE_ID
        context_policy = policy.get_policy_for_context(_site_id, npc_id)

        citations_count = len(citations)
        citations_score = self._get_citations_score(citations)

        # 获取允许的软断言
        allowed_soft_claims = context_policy.get("allowed_soft_claims", [])
        max_soft_claims = context_policy.get("max_soft_claims", 2)
        strict_mode = context_policy.get("strict_mode", False)

        # 检查禁止的史实断言
        forbidden = self.rule_classifier.contains_forbidden_assertions(response_text)

        # 检查使用的软断言
        soft_claims_used = []
        for claim in allowed_soft_claims:
            if claim in response_text:
                soft_claims_used.append(claim)

        # 应用的规则
        applied_rule = self.policy_loader.get_applied_rule(_site_id, npc_id, intent.value)

        # 判断逻辑
        if intent == IntentLabel.CONTEXT_PREFERENCE:
            if forbidden and citations_count == 0:
                # 有禁止断言但无证据
                if strict_mode:
                    # 严格模式：直接拒绝
                    log.warning(
                        "forbidden_assertions_detected_strict",
                        assertions=forbidden[:5],
                    )
                    return EvidenceGateResult(
                        passed=False,
                        policy_mode=PolicyMode.CONSERVATIVE,
                        intent=intent,
                        intent_confidence=1.0,
                        reason=f"严格模式：检测到 {len(forbidden)} 个无证据的史实断言",
                        citations_count=citations_count,
                        citations_score=citations_score,
                        forbidden_assertions=forbidden[:5],
                        soft_claims_used=soft_claims_used,
                        requires_filtering=True,
                        classifier_type="rule",
                        cached=False,
                        policy_version=policy.version,
                        policy_hash=policy._hash,
                        applied_rule=asdict(applied_rule),
                    )
                elif len(soft_claims_used) <= max_soft_claims:
                    # 非严格模式：如果使用了软断言，可以通过
                    log.info(
                        "soft_claims_allowed",
                        soft_claims=soft_claims_used,
                        forbidden=forbidden[:3],
                    )
                    return EvidenceGateResult(
                        passed=True,
                        policy_mode=PolicyMode.NORMAL,
                        intent=intent,
                        intent_confidence=1.0,
                        reason=f"使用了 {len(soft_claims_used)} 个软断言，允许通过",
                        citations_count=citations_count,
                        citations_score=citations_score,
                        forbidden_assertions=forbidden[:5],
                        soft_claims_used=soft_claims_used,
                        requires_filtering=True,
                        classifier_type="rule",
                        cached=False,
                        policy_version=policy.version,
                        policy_hash=policy._hash,
                        applied_rule=asdict(applied_rule),
                    )
                else:
                    # 软断言超限
                    log.warning(
                        "soft_claims_exceeded",
                        used=len(soft_claims_used),
                        max=max_soft_claims,
                    )
                    return EvidenceGateResult(
                        passed=False,
                        policy_mode=PolicyMode.CONSERVATIVE,
                        intent=intent,
                        intent_confidence=1.0,
                        reason=f"软断言超限（使用 {len(soft_claims_used)}，最大 {max_soft_claims}）",
                        citations_count=citations_count,
                        citations_score=citations_score,
                        forbidden_assertions=forbidden[:5],
                        soft_claims_used=soft_claims_used,
                        requires_filtering=True,
                        classifier_type="rule",
                        cached=False,
                        policy_version=policy.version,
                        policy_hash=policy._hash,
                        applied_rule=asdict(applied_rule),
                    )

        return EvidenceGateResult(
            passed=True,
            policy_mode=PolicyMode.NORMAL,
            intent=intent,
            intent_confidence=1.0,
            reason="输出检查通过",
            citations_count=citations_count,
            citations_score=citations_score,
            forbidden_assertions=[],
            soft_claims_used=soft_claims_used,
            requires_filtering=False,
            classifier_type="rule",
            cached=False,
            policy_version=policy.version,
            policy_hash=policy._hash,
            applied_rule=asdict(applied_rule),
        )

    def get_conservative_response(
        self,
        intent: IntentLabel,
        query: str,
        npc_name: str = "我",
        site_id: Optional[str] = None,
        npc_id: Optional[str] = None,
    ) -> str:
        """
        获取保守模式响应（从策略配置读取）

        Args:
            intent: 查询意图
            query: 用户查询
            npc_name: NPC 名称
            site_id: 站点 ID
            npc_id: NPC ID

        Returns:
            保守模式响应文本
        """
        policy = self.policy_loader.load()
        _site_id = site_id or settings.DEFAULT_SITE_ID
        context_policy = policy.get_policy_for_context(_site_id, npc_id)

        fallback_templates = context_policy.get("fallback_templates", {})

        # 根据意图选择模板
        if intent == IntentLabel.FACT_SEEKING:
            template = fallback_templates.get(
                "fact_seeking",
                "这个问题涉及具体的历史事实，{npc_name}需要查阅资料才能准确回答。"
            )
        elif intent == IntentLabel.OUT_OF_SCOPE:
            template = fallback_templates.get(
                "out_of_scope",
                "这个问题超出了{npc_name}的知识范围。"
            )
        else:
            template = fallback_templates.get(
                "default",
                "关于这个问题，{npc_name}不太确定具体细节。"
            )

        return template.format(npc_name=npc_name)

    def filter_forbidden_assertions(
        self,
        text: str,
        npc_name: str = "我",
        site_id: Optional[str] = None,
        npc_id: Optional[str] = None,
    ) -> str:
        """
        过滤禁止的史实断言

        将无证据的史实断言替换为模糊表述或软断言

        Args:
            text: 原始文本
            npc_name: NPC 名称
            site_id: 站点 ID
            npc_id: NPC ID

        Returns:
            过滤后的文本
        """
        policy = self.policy_loader.load()
        _site_id = site_id or settings.DEFAULT_SITE_ID
        context_policy = policy.get_policy_for_context(_site_id, npc_id)

        allowed_soft_claims = context_policy.get("allowed_soft_claims", ["据说", "相传"])
        soft_prefix = allowed_soft_claims[0] if allowed_soft_claims else "据说"

        # 替换年份（添加软断言前缀）
        text = re.sub(r"公元(\d+)年", f"{soft_prefix}很久以前", text)
        text = re.sub(r"(\d{{3,4}})年", f"{soft_prefix}多年前", text)
        text = re.sub(r"距今(\d+)年", f"{soft_prefix}很多年前", text)

        # 替换代数
        text = re.sub(r"第(\d+)代", r"某一代", text)
        text = re.sub(r"第(\d+)世", r"某一世", text)

        # 替换朝代年号
        text = re.sub(
            r"(康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统)(\d*)年?间?",
            f"{soft_prefix}清朝某个时期",
            text,
        )
        text = re.sub(
            r"(洪武|永乐|正统|成化|弘治|正德|嘉靖|隆庆|万历|崇祯)(\d*)年?间?",
            f"{soft_prefix}明朝某个时期",
            text,
        )

        return text


# ============================================================
# 全局实例和工厂函数
# ============================================================

_gate_instance: Optional[EvidenceGateV3] = None


async def get_evidence_gate_v3(
    policy_loader: Optional[PolicyLoader] = None,
    llm_provider=None,
    cache_client=None,
) -> EvidenceGateV3:
    """
    获取证据闸门实例

    Args:
        policy_loader: 策略加载器
        llm_provider: LLM Provider（可选）
        cache_client: Redis 缓存客户端（可选）

    Returns:
        EvidenceGateV3
    """
    global _gate_instance

    if _gate_instance is None:
        _gate_instance = EvidenceGateV3(
            policy_loader=policy_loader,
            llm_provider=llm_provider,
            cache_client=cache_client,
        )

    return _gate_instance


def reset_evidence_gate_v3() -> None:
    """重置证据闸门实例（用于测试）"""
    global _gate_instance
    _gate_instance = None
