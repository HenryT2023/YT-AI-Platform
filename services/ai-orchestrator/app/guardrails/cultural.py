"""
文化准确性护栏

确保 AI 输出符合文化准确性要求：
1. 不编造历史事实
2. 不违反角色设定
3. 过滤敏感话题
4. 检查禁用词
"""

from dataclasses import dataclass
from typing import Any, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GuardrailResult:
    """护栏检查结果"""
    passed: bool
    reason: Optional[str] = None
    violations: Optional[List[str]] = None


class CulturalGuardrail:
    """文化准确性护栏"""

    # 默认禁用词列表
    DEFAULT_FORBIDDEN_WORDS = [
        # 政治敏感
        "政治", "政党", "选举",
        # 宗教争议
        "邪教",
        # 其他敏感
        "色情", "暴力", "赌博",
    ]

    # 角色一致性检查关键词（历史人物不应提及的现代事物）
    ANACHRONISM_KEYWORDS = [
        "手机", "电脑", "互联网", "微信", "抖音", "AI", "人工智能",
        "飞机", "汽车", "高铁", "地铁",
    ]

    def __init__(self, custom_forbidden_words: Optional[List[str]] = None):
        self.forbidden_words = self.DEFAULT_FORBIDDEN_WORDS.copy()
        if custom_forbidden_words:
            self.forbidden_words.extend(custom_forbidden_words)

    async def check(
        self,
        response: str,
        persona: dict[str, Any],
    ) -> GuardrailResult:
        """
        检查响应是否符合文化准确性要求

        Args:
            response: AI 生成的响应
            persona: NPC 人设配置

        Returns:
            检查结果
        """
        violations = []

        # 1. 检查禁用词
        persona_forbidden = persona.get("constraints", {}).get("forbidden_topics", [])
        all_forbidden = self.forbidden_words + persona_forbidden

        for word in all_forbidden:
            if word in response:
                violations.append(f"包含禁用词: {word}")

        # 2. 检查时代一致性（仅对历史人物）
        time_awareness = persona.get("constraints", {}).get("time_awareness", "flexible")
        if time_awareness == "historical":
            for keyword in self.ANACHRONISM_KEYWORDS:
                if keyword in response:
                    violations.append(f"时代不一致: 提及了现代事物 '{keyword}'")

        # 3. 检查响应长度
        max_length = persona.get("conversation_config", {}).get("max_response_length", 500)
        if len(response) > max_length * 1.5:  # 允许 50% 的容差
            violations.append(f"响应过长: {len(response)} 字符（限制 {max_length}）")

        # 4. 检查是否包含不确定性标记（如果要求必须引用来源）
        must_cite = persona.get("constraints", {}).get("must_cite_sources", False)
        if must_cite:
            # 这里可以添加更复杂的检查逻辑
            pass

        if violations:
            logger.warning(
                "guardrail_violations",
                violation_count=len(violations),
                violations=violations[:3],  # 只记录前 3 个
            )
            return GuardrailResult(
                passed=False,
                reason=violations[0],
                violations=violations,
            )

        return GuardrailResult(passed=True)

    def add_forbidden_words(self, words: List[str]) -> None:
        """添加禁用词"""
        self.forbidden_words.extend(words)
