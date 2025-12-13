"""
Query Intent Classifier

规则版意图分类器：
- fact_seeking: 事实性问题，需要证据支撑
- context_preference: 上下文偏好问题，可使用会话记忆

核心约束：
- 事实性问题必须证据先行，否则强制保守
- 上下文偏好问题可使用记忆，但禁止输出具体史实断言
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class QueryIntent(str, Enum):
    """查询意图"""

    FACT_SEEKING = "fact_seeking"           # 事实性问题
    CONTEXT_PREFERENCE = "context_preference"  # 上下文偏好


@dataclass
class IntentClassification:
    """意图分类结果"""

    intent: QueryIntent
    confidence: float  # 0.0 - 1.0
    reason: str
    fact_indicators: List[str]  # 触发 fact_seeking 的关键词
    requires_evidence: bool


# ==================
# 规则定义
# ==================

# 事实性问题关键词（需要证据）
FACT_SEEKING_KEYWORDS: Set[str] = {
    # 时间相关
    "哪一年", "什么时候", "何时", "几年", "多少年", "年代", "朝代",
    "什么年间", "哪个朝代", "历史上", "古时候",
    # 人物相关
    "谁是", "是谁", "哪位", "什么人", "祖先", "先祖", "族谱",
    "第几代", "几世祖", "始祖", "开基祖", "迁徙",
    # 事件相关
    "发生了什么", "怎么回事", "什么事件", "历史事件",
    "战争", "灾难", "迁移", "建村", "开基",
    # 地点相关
    "在哪里", "什么地方", "哪个村", "从哪里来", "迁自",
    # 数量相关
    "多少人", "几个", "多少代", "多少年", "几百年",
    # 验证相关
    "是真的吗", "真的吗", "确实", "史实", "记载", "文献",
    "族谱记载", "家谱", "县志", "府志",
    # 具体事实
    "具体", "详细", "准确", "确切", "精确",
}

# 事实性问题句式模式
FACT_SEEKING_PATTERNS: List[str] = [
    r".*是什么时候.*",
    r".*是哪一年.*",
    r".*是谁.*",
    r".*有多少.*",
    r".*第几代.*",
    r".*从哪里.*来.*",
    r".*迁.*到.*",
    r".*建于.*",
    r".*始于.*",
    r".*距今.*年.*",
    r".*有.*年历史.*",
    r".*记载.*",
    r".*史料.*",
    r".*文献.*",
    r".*族谱.*说.*",
    r".*家谱.*记.*",
]

# 上下文偏好关键词（可使用记忆）
CONTEXT_PREFERENCE_KEYWORDS: Set[str] = {
    # 偏好相关
    "喜欢", "感兴趣", "想了解", "想听", "想知道",
    "有趣", "好玩", "有意思",
    # 建议相关
    "推荐", "建议", "应该", "怎么办", "如何",
    # 情感相关
    "感觉", "觉得", "认为", "看法", "意见",
    # 闲聊相关
    "你好", "谢谢", "再见", "聊聊", "说说",
    # 追问（依赖上下文）
    "刚才", "之前", "上面", "前面", "继续",
    "还有吗", "还有什么", "接着说", "然后呢",
}

# 禁止在无证据时输出的史实断言模式
FORBIDDEN_ASSERTION_PATTERNS: List[str] = [
    r"公元\d+年",
    r"\d{3,4}年",
    r"距今\d+年",
    r"第\d+代",
    r"第\d+世",
    r"始祖.*名.*",
    r"开基祖.*",
    r"从.*迁.*到.*",
    r"建于.*年",
    r"始于.*年",
    r".*朝.*年间",
    r"康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统",
    r"洪武|永乐|正统|成化|弘治|正德|嘉靖|隆庆|万历|崇祯",
]


class QueryIntentClassifier:
    """
    查询意图分类器

    规则版实现，基于关键词和句式模式
    """

    def __init__(
        self,
        fact_keywords: Optional[Set[str]] = None,
        context_keywords: Optional[Set[str]] = None,
        fact_patterns: Optional[List[str]] = None,
    ):
        self.fact_keywords = fact_keywords or FACT_SEEKING_KEYWORDS
        self.context_keywords = context_keywords or CONTEXT_PREFERENCE_KEYWORDS
        self.fact_patterns = [
            re.compile(p) for p in (fact_patterns or FACT_SEEKING_PATTERNS)
        ]
        self.forbidden_patterns = [
            re.compile(p) for p in FORBIDDEN_ASSERTION_PATTERNS
        ]

    def classify(self, query: str) -> IntentClassification:
        """
        分类查询意图

        Args:
            query: 用户查询

        Returns:
            IntentClassification
        """
        query_lower = query.lower()
        fact_indicators = []

        # 1. 检查事实性关键词
        for keyword in self.fact_keywords:
            if keyword in query:
                fact_indicators.append(keyword)

        # 2. 检查事实性句式
        for pattern in self.fact_patterns:
            if pattern.match(query):
                fact_indicators.append(f"pattern:{pattern.pattern[:20]}")

        # 3. 检查上下文偏好关键词
        context_score = sum(1 for kw in self.context_keywords if kw in query)

        # 4. 计算置信度
        fact_score = len(fact_indicators)

        if fact_score > 0:
            # 有事实性指标，判定为 fact_seeking
            confidence = min(0.5 + fact_score * 0.1, 1.0)
            return IntentClassification(
                intent=QueryIntent.FACT_SEEKING,
                confidence=confidence,
                reason=f"检测到 {fact_score} 个事实性指标",
                fact_indicators=fact_indicators[:5],
                requires_evidence=True,
            )
        elif context_score > 0:
            # 有上下文偏好指标
            confidence = min(0.5 + context_score * 0.1, 1.0)
            return IntentClassification(
                intent=QueryIntent.CONTEXT_PREFERENCE,
                confidence=confidence,
                reason=f"检测到 {context_score} 个上下文偏好指标",
                fact_indicators=[],
                requires_evidence=False,
            )
        else:
            # 默认为 fact_seeking（保守策略）
            return IntentClassification(
                intent=QueryIntent.FACT_SEEKING,
                confidence=0.5,
                reason="未检测到明确意图，默认为事实性问题",
                fact_indicators=[],
                requires_evidence=True,
            )

    def contains_forbidden_assertions(self, text: str) -> List[str]:
        """
        检查文本是否包含禁止的史实断言

        Args:
            text: 待检查文本

        Returns:
            匹配到的断言列表
        """
        matches = []
        for pattern in self.forbidden_patterns:
            found = pattern.findall(text)
            matches.extend(found)
        return matches


# 全局实例
_classifier: Optional[QueryIntentClassifier] = None


def get_intent_classifier() -> QueryIntentClassifier:
    """获取全局意图分类器"""
    global _classifier
    if _classifier is None:
        _classifier = QueryIntentClassifier()
    return _classifier


def classify_query_intent(query: str) -> IntentClassification:
    """分类查询意图（便捷函数）"""
    return get_intent_classifier().classify(query)
