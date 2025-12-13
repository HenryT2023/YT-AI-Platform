"""
证据验证器

验证 AI 输出是否有足够的证据支撑
如果证据不足，触发保守回答模式
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

from app.core.logging import get_logger
from app.evidence.chain import EvidenceChainResult

logger = get_logger(__name__)


class ValidationLevel(str, Enum):
    """验证级别"""
    STRICT = "strict"  # 严格：必须有验证过的证据
    NORMAL = "normal"  # 正常：需要有证据
    RELAXED = "relaxed"  # 宽松：允许少量推测


@dataclass
class ValidationResult:
    """验证结果"""

    passed: bool
    level: ValidationLevel
    confidence: float
    reason: Optional[str] = None
    evidence_ids: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    @property
    def should_use_fallback(self) -> bool:
        """是否应该使用保守回答"""
        return not self.passed


class EvidenceValidator:
    """证据验证器"""

    # 保守回答模板
    FALLBACK_TEMPLATES = {
        "no_evidence": [
            "关于这个问题，我目前没有找到确切的记载。不过我可以告诉你一些相关的背景...",
            "这个问题涉及的内容，我需要查阅更多资料才能准确回答。",
            "抱歉，关于这个具体问题，我的记忆中没有确切的信息。",
        ],
        "low_confidence": [
            "根据我所知道的，{topic}可能是这样的，但我不太确定...",
            "我听说过一些关于{topic}的说法，但不能完全确定其准确性...",
        ],
        "unverified": [
            "关于{topic}，有这样的说法，但我无法确认其真实性...",
            "这个问题我了解一些，但建议你再向其他人求证...",
        ],
        "out_of_domain": [
            "这个问题超出了我的知识范围，我主要了解{domains}方面的内容。",
            "抱歉，我对这个领域不太熟悉。我更擅长{domains}相关的话题。",
        ],
    }

    def __init__(
        self,
        level: ValidationLevel = ValidationLevel.NORMAL,
        min_confidence: float = 0.5,
        require_verified_for_history: bool = True,
    ):
        """
        初始化验证器

        Args:
            level: 验证级别
            min_confidence: 最低可信度要求
            require_verified_for_history: 历史事实是否必须有验证过的证据
        """
        self.level = level
        self.min_confidence = min_confidence
        self.require_verified_for_history = require_verified_for_history

    def validate(
        self,
        evidence_result: EvidenceChainResult,
        query_type: Optional[str] = None,
        knowledge_domains: Optional[List[str]] = None,
    ) -> ValidationResult:
        """
        验证证据是否充分

        Args:
            evidence_result: 证据链构建结果
            query_type: 查询类型（如 historical_fact, general_info 等）
            knowledge_domains: NPC 的知识领域

        Returns:
            验证结果
        """
        chain = evidence_result.evidence_chain
        suggestions = []

        # 无证据
        if not chain.evidences:
            return ValidationResult(
                passed=False,
                level=self.level,
                confidence=0.0,
                reason="no_evidence",
                suggestions=["使用保守回答模板", "引导用户提问其他话题"],
            )

        # 可信度检查
        if chain.total_credibility < self.min_confidence:
            return ValidationResult(
                passed=False,
                level=self.level,
                confidence=chain.total_credibility,
                reason="low_confidence",
                evidence_ids=[e.id for e in chain.evidences],
                suggestions=["降低回答的确定性", "使用模糊表达"],
            )

        # 严格模式：必须有验证过的证据
        if self.level == ValidationLevel.STRICT:
            if not chain.has_verified_evidence:
                return ValidationResult(
                    passed=False,
                    level=self.level,
                    confidence=chain.total_credibility,
                    reason="unverified",
                    evidence_ids=[e.id for e in chain.evidences],
                    suggestions=["标注信息未经验证", "建议用户进一步核实"],
                )

        # 历史事实必须有验证过的证据
        if query_type == "historical_fact" and self.require_verified_for_history:
            if not chain.has_verified_evidence:
                return ValidationResult(
                    passed=False,
                    level=self.level,
                    confidence=chain.total_credibility,
                    reason="unverified",
                    evidence_ids=[e.id for e in chain.evidences],
                    suggestions=["历史事实需要验证过的来源", "使用保守表达"],
                )

        # 验证通过
        return ValidationResult(
            passed=True,
            level=self.level,
            confidence=chain.total_credibility,
            evidence_ids=[e.id for e in chain.evidences],
        )

    def get_fallback_response(
        self,
        validation_result: ValidationResult,
        topic: Optional[str] = None,
        knowledge_domains: Optional[List[str]] = None,
        custom_fallbacks: Optional[List[str]] = None,
    ) -> str:
        """
        获取保守回答

        Args:
            validation_result: 验证结果
            topic: 话题（用于模板填充）
            knowledge_domains: 知识领域
            custom_fallbacks: 自定义保守回答列表

        Returns:
            保守回答文本
        """
        # 优先使用自定义保守回答
        if custom_fallbacks:
            return custom_fallbacks[0]

        reason = validation_result.reason or "no_evidence"
        templates = self.FALLBACK_TEMPLATES.get(reason, self.FALLBACK_TEMPLATES["no_evidence"])

        template = templates[0]

        # 填充模板变量
        if topic:
            template = template.replace("{topic}", topic)
        if knowledge_domains:
            domains_str = "、".join(knowledge_domains[:3])
            template = template.replace("{domains}", domains_str)

        return template

    def classify_query(
        self,
        query: str,
        knowledge_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        分类查询类型

        Args:
            query: 用户查询
            knowledge_domains: NPC 知识领域

        Returns:
            查询分类结果
        """
        # 简单的关键词匹配（生产环境应使用更复杂的分类器）
        historical_keywords = ["历史", "年代", "朝代", "祖先", "古代", "以前", "过去", "传说"]
        factual_keywords = ["是什么", "为什么", "怎么", "如何", "多少", "几个"]
        opinion_keywords = ["觉得", "认为", "看法", "意见", "好不好", "喜欢"]

        query_type = "general_info"
        requires_evidence = True

        for kw in historical_keywords:
            if kw in query:
                query_type = "historical_fact"
                break

        for kw in opinion_keywords:
            if kw in query:
                query_type = "opinion"
                requires_evidence = False
                break

        # 检查是否在知识领域内
        in_domain = True
        if knowledge_domains:
            in_domain = any(domain in query for domain in knowledge_domains)

        return {
            "query_type": query_type,
            "requires_evidence": requires_evidence,
            "in_domain": in_domain,
            "suggested_validation_level": (
                ValidationLevel.STRICT if query_type == "historical_fact"
                else ValidationLevel.NORMAL
            ),
        }
