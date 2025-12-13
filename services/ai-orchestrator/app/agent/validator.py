"""
输出校验器

校验 LLM 输出，确保文化准确性和安全性
"""

import re
from typing import List, Optional

from app.agent.schemas import PolicyMode, ValidationResult, CitationItem
from app.core.config import settings


class OutputValidator:
    """输出校验器"""

    # 敏感词列表
    SENSITIVE_KEYWORDS = [
        "政治", "宗教争议", "迷信", "封建糟粕",
        "色情", "暴力", "赌博", "毒品",
    ]

    # 保守回答模板
    CONSERVATIVE_TEMPLATES = [
        "这个问题我不太清楚，建议您询问村中其他长辈。",
        "关于这个问题，我了解不多，或可查阅相关文献资料。",
        "此事我不甚了了，您可以向村里的老人打听。",
    ]

    # 拒绝回答模板
    REFUSE_TEMPLATES = [
        "抱歉，这个话题不在我的知识范围内。",
        "这个问题不太适合讨论，我们聊点别的吧。",
    ]

    def __init__(
        self,
        min_evidence_count: int = 1,
        min_confidence_threshold: float = 0.5,
        require_verified_for_history: bool = True,
    ):
        self.min_evidence_count = min_evidence_count
        self.min_confidence_threshold = min_confidence_threshold
        self.require_verified_for_history = require_verified_for_history

    def validate(
        self,
        text: str,
        citations: List[CitationItem],
        query: str,
        npc_persona: Optional[dict] = None,
    ) -> ValidationResult:
        """
        校验输出

        Args:
            text: LLM 生成的文本
            citations: 引用的证据
            query: 原始用户问题
            npc_persona: NPC 人设配置

        Returns:
            ValidationResult: 校验结果
        """
        # 1. 检查敏感词
        if self._contains_sensitive_content(text) or self._contains_sensitive_content(query):
            return ValidationResult(
                valid=False,
                policy_mode=PolicyMode.REFUSE,
                reason="contains_sensitive_content",
                filtered_text=self._get_refuse_template(),
            )

        # 2. 检查证据充分性
        if not self._has_sufficient_evidence(citations):
            return ValidationResult(
                valid=True,
                policy_mode=PolicyMode.CONSERVATIVE,
                reason="insufficient_evidence",
                filtered_text=self._get_conservative_template(npc_persona),
            )

        # 3. 检查历史相关问题是否有验证过的证据
        if self._is_history_related(query) and self.require_verified_for_history:
            if not self._has_verified_evidence(citations):
                return ValidationResult(
                    valid=True,
                    policy_mode=PolicyMode.CONSERVATIVE,
                    reason="history_requires_verified_evidence",
                    filtered_text=self._get_conservative_template(npc_persona),
                )

        # 4. 检查 NPC 禁止话题
        if npc_persona:
            forbidden_topics = npc_persona.get("constraints", {}).get("forbidden_topics", [])
            for topic in forbidden_topics:
                if topic.lower() in query.lower() or topic.lower() in text.lower():
                    return ValidationResult(
                        valid=False,
                        policy_mode=PolicyMode.REFUSE,
                        reason=f"forbidden_topic:{topic}",
                        filtered_text=self._get_refuse_template(),
                    )

        # 5. 通过校验
        return ValidationResult(
            valid=True,
            policy_mode=PolicyMode.NORMAL,
        )

    def _contains_sensitive_content(self, text: str) -> bool:
        """检查是否包含敏感内容"""
        text_lower = text.lower()
        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword in text_lower:
                return True
        return False

    def _has_sufficient_evidence(self, citations: List[CitationItem]) -> bool:
        """检查证据是否充分"""
        if len(citations) < self.min_evidence_count:
            return False

        # 检查平均置信度
        if citations:
            avg_confidence = sum(c.confidence for c in citations) / len(citations)
            if avg_confidence < self.min_confidence_threshold:
                return False

        return True

    def _has_verified_evidence(self, citations: List[CitationItem]) -> bool:
        """检查是否有验证过的证据"""
        # 简化实现：检查是否有高置信度证据
        for c in citations:
            if c.confidence >= 0.9:
                return True
        return False

    def _is_history_related(self, query: str) -> bool:
        """检查是否为历史相关问题"""
        history_keywords = [
            "历史", "祖先", "先祖", "族谱", "家谱",
            "古代", "传说", "起源", "来历", "由来",
        ]
        query_lower = query.lower()
        for keyword in history_keywords:
            if keyword in query_lower:
                return True
        return False

    def _get_conservative_template(self, npc_persona: Optional[dict] = None) -> str:
        """获取保守回答模板"""
        if npc_persona:
            fallback_responses = npc_persona.get("fallback_responses", [])
            if fallback_responses:
                return fallback_responses[0]

        import random
        return random.choice(self.CONSERVATIVE_TEMPLATES)

    def _get_refuse_template(self) -> str:
        """获取拒绝回答模板"""
        import random
        return random.choice(self.REFUSE_TEMPLATES)
