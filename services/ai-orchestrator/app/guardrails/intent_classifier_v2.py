"""
Intent Classifier v2

抽象接口 + 规则版 + LLM 版意图分类器

设计原则：
1. 统一接口：IntentClassifier 抽象类
2. 规则版：RuleIntentClassifier（沿用现有逻辑）
3. LLM 版：LLMIntentClassifier（带缓存、降级）
4. 工厂模式：根据配置选择分类器
"""

import hashlib
import json
import re
import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = structlog.get_logger(__name__)


# ============================================================
# 数据结构
# ============================================================

class IntentLabel(str, Enum):
    """意图标签"""
    FACT_SEEKING = "fact_seeking"           # 事实性问题
    CONTEXT_PREFERENCE = "context_preference"  # 上下文偏好
    GREETING = "greeting"                   # 问候
    CLARIFICATION = "clarification"         # 澄清追问
    OUT_OF_SCOPE = "out_of_scope"           # 超出范围


@dataclass
class IntentContext:
    """意图分类上下文"""
    tenant_id: str
    site_id: str
    npc_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    npc_knowledge_domains: List[str] = field(default_factory=list)


@dataclass
class IntentResult:
    """意图分类结果"""
    label: IntentLabel
    confidence: float  # 0.0 - 1.0
    tags: List[str] = field(default_factory=list)
    reason: str = ""
    requires_evidence: bool = True
    classifier_type: str = "unknown"  # rule / llm
    latency_ms: int = 0
    cached: bool = False


# ============================================================
# 抽象接口
# ============================================================

class IntentClassifier(ABC):
    """
    意图分类器抽象接口

    所有分类器必须实现此接口
    """

    @property
    @abstractmethod
    def classifier_type(self) -> str:
        """分类器类型"""
        pass

    @abstractmethod
    async def classify(
        self,
        query: str,
        context: Optional[IntentContext] = None,
    ) -> IntentResult:
        """
        分类查询意图

        Args:
            query: 用户查询
            context: 分类上下文（可选）

        Returns:
            IntentResult
        """
        pass


# ============================================================
# 规则定义（沿用现有逻辑）
# ============================================================

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

GREETING_KEYWORDS: Set[str] = {
    "你好", "您好", "早上好", "下午好", "晚上好",
    "嗨", "哈喽", "hello", "hi",
}

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


# ============================================================
# 规则版分类器
# ============================================================

class RuleIntentClassifier(IntentClassifier):
    """
    规则版意图分类器

    基于关键词和句式模式的分类
    """

    def __init__(
        self,
        fact_keywords: Optional[Set[str]] = None,
        context_keywords: Optional[Set[str]] = None,
        greeting_keywords: Optional[Set[str]] = None,
        fact_patterns: Optional[List[str]] = None,
    ):
        self.fact_keywords = fact_keywords or FACT_SEEKING_KEYWORDS
        self.context_keywords = context_keywords or CONTEXT_PREFERENCE_KEYWORDS
        self.greeting_keywords = greeting_keywords or GREETING_KEYWORDS
        self.fact_patterns = [
            re.compile(p) for p in (fact_patterns or FACT_SEEKING_PATTERNS)
        ]
        self.forbidden_patterns = [
            re.compile(p) for p in FORBIDDEN_ASSERTION_PATTERNS
        ]

    @property
    def classifier_type(self) -> str:
        return "rule"

    async def classify(
        self,
        query: str,
        context: Optional[IntentContext] = None,
    ) -> IntentResult:
        """规则分类"""
        import time
        start = time.time()

        tags = []

        # 1. 检查问候
        for kw in self.greeting_keywords:
            if kw in query.lower():
                return IntentResult(
                    label=IntentLabel.GREETING,
                    confidence=0.9,
                    tags=["greeting"],
                    reason="检测到问候关键词",
                    requires_evidence=False,
                    classifier_type=self.classifier_type,
                    latency_ms=int((time.time() - start) * 1000),
                )

        # 2. 检查事实性关键词
        fact_indicators = []
        for keyword in self.fact_keywords:
            if keyword in query:
                fact_indicators.append(keyword)
                tags.append(f"kw:{keyword}")

        # 3. 检查事实性句式
        for pattern in self.fact_patterns:
            if pattern.match(query):
                fact_indicators.append(f"pattern:{pattern.pattern[:20]}")
                tags.append("pattern_match")

        # 4. 检查上下文偏好关键词
        context_score = sum(1 for kw in self.context_keywords if kw in query)

        # 5. 计算置信度
        fact_score = len(fact_indicators)

        latency_ms = int((time.time() - start) * 1000)

        if fact_score > 0:
            confidence = min(0.5 + fact_score * 0.1, 1.0)
            return IntentResult(
                label=IntentLabel.FACT_SEEKING,
                confidence=confidence,
                tags=tags[:5],
                reason=f"检测到 {fact_score} 个事实性指标",
                requires_evidence=True,
                classifier_type=self.classifier_type,
                latency_ms=latency_ms,
            )
        elif context_score > 0:
            confidence = min(0.5 + context_score * 0.1, 1.0)
            return IntentResult(
                label=IntentLabel.CONTEXT_PREFERENCE,
                confidence=confidence,
                tags=["context_preference"],
                reason=f"检测到 {context_score} 个上下文偏好指标",
                requires_evidence=False,
                classifier_type=self.classifier_type,
                latency_ms=latency_ms,
            )
        else:
            # 默认为 fact_seeking（保守策略）
            return IntentResult(
                label=IntentLabel.FACT_SEEKING,
                confidence=0.5,
                tags=["default"],
                reason="未检测到明确意图，默认为事实性问题",
                requires_evidence=True,
                classifier_type=self.classifier_type,
                latency_ms=latency_ms,
            )

    def contains_forbidden_assertions(self, text: str) -> List[str]:
        """检查文本是否包含禁止的史实断言"""
        matches = []
        for pattern in self.forbidden_patterns:
            found = pattern.findall(text)
            matches.extend(found)
        return matches


# ============================================================
# LLM 版分类器
# ============================================================

# LLM 分类 Prompt
INTENT_CLASSIFICATION_PROMPT = """你是一个意图分类器。请分析用户的查询，判断其意图类型。

## 意图类型

1. **fact_seeking** - 事实性问题
   - 询问具体的历史事实、时间、人物、事件
   - 需要证据支撑的问题
   - 例如："严氏是什么时候迁到这里的？"、"始祖是谁？"

2. **context_preference** - 上下文偏好问题
   - 询问建议、偏好、感受
   - 依赖上下文的追问
   - 例如："你觉得这里怎么样？"、"还有什么有趣的故事？"

3. **greeting** - 问候
   - 打招呼、寒暄
   - 例如："你好"、"早上好"

4. **clarification** - 澄清追问
   - 对之前回答的追问
   - 例如："你刚才说的是什么意思？"、"能详细说说吗？"

5. **out_of_scope** - 超出范围
   - 与文化、历史、旅游无关的问题
   - 例如："今天股票怎么样？"、"帮我写代码"

## 输出格式

请以 JSON 格式输出，包含以下字段：
```json
{
  "label": "fact_seeking",
  "confidence": 0.85,
  "tags": ["历史", "时间"],
  "reason": "用户询问具体的迁徙时间，属于事实性问题"
}
```

## 用户查询

{query}

## 上下文信息

NPC 知识领域：{domains}
对话历史：{history}

请分析并输出 JSON："""


class LLMIntentClassifier(IntentClassifier):
    """
    LLM 版意图分类器

    特性：
    1. 调用 LLM 进行意图分类
    2. 缓存结果（TTL 5 分钟）
    3. 失败时降级到规则分类器
    """

    def __init__(
        self,
        llm_provider=None,
        cache_client=None,
        cache_ttl: int = 300,  # 5 分钟
        fallback_classifier: Optional[IntentClassifier] = None,
    ):
        self.llm_provider = llm_provider
        self.cache_client = cache_client
        self.cache_ttl = cache_ttl
        self.fallback = fallback_classifier or RuleIntentClassifier()

    @property
    def classifier_type(self) -> str:
        return "llm"

    def _build_cache_key(
        self,
        query: str,
        context: Optional[IntentContext] = None,
    ) -> str:
        """构建缓存 key"""
        parts = [
            context.tenant_id if context else "default",
            context.site_id if context else "default",
            context.npc_id if context and context.npc_id else "default",
            hashlib.md5(query.encode()).hexdigest()[:16],
        ]
        return f"yantian:intent:{':'.join(parts)}"

    async def _get_cached(self, cache_key: str) -> Optional[IntentResult]:
        """从缓存获取"""
        if not self.cache_client:
            return None

        try:
            cached = await self.cache_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                return IntentResult(
                    label=IntentLabel(data["label"]),
                    confidence=data["confidence"],
                    tags=data.get("tags", []),
                    reason=data.get("reason", ""),
                    requires_evidence=data.get("requires_evidence", True),
                    classifier_type="llm",
                    latency_ms=0,
                    cached=True,
                )
        except Exception as e:
            logger.warning("cache_get_error", error=str(e))
        return None

    async def _set_cached(
        self,
        cache_key: str,
        result: IntentResult,
    ) -> None:
        """写入缓存"""
        if not self.cache_client:
            return

        try:
            data = {
                "label": result.label.value,
                "confidence": result.confidence,
                "tags": result.tags,
                "reason": result.reason,
                "requires_evidence": result.requires_evidence,
            }
            await self.cache_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(data, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning("cache_set_error", error=str(e))

    def _build_prompt(
        self,
        query: str,
        context: Optional[IntentContext] = None,
    ) -> str:
        """构建 LLM Prompt"""
        domains = ""
        history = ""

        if context:
            if context.npc_knowledge_domains:
                domains = "、".join(context.npc_knowledge_domains)
            if context.conversation_history:
                history_lines = []
                for msg in context.conversation_history[-3:]:
                    role = "用户" if msg.get("role") == "user" else "NPC"
                    history_lines.append(f"{role}: {msg.get('content', '')[:50]}")
                history = "\n".join(history_lines)

        return INTENT_CLASSIFICATION_PROMPT.format(
            query=query,
            domains=domains or "无",
            history=history or "无",
        )

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        return None

    async def classify(
        self,
        query: str,
        context: Optional[IntentContext] = None,
    ) -> IntentResult:
        """LLM 分类（带缓存和降级）"""
        import time
        start = time.time()

        log = logger.bind(query=query[:50])

        # 1. 检查缓存
        cache_key = self._build_cache_key(query, context)
        cached_result = await self._get_cached(cache_key)
        if cached_result:
            log.debug("intent_cache_hit")
            return cached_result

        # 2. 调用 LLM
        if not self.llm_provider:
            log.warning("llm_provider_not_set", fallback="rule")
            return await self.fallback.classify(query, context)

        try:
            from app.providers.llm.base import LLMRequest

            prompt = self._build_prompt(query, context)
            request = LLMRequest(
                system_prompt="你是一个精确的意图分类器。只输出 JSON，不要其他内容。",
                user_message=prompt,
                max_tokens=200,
                temperature=0.1,  # 低温度保证一致性
            )

            response = await self.llm_provider.generate(request)
            latency_ms = int((time.time() - start) * 1000)

            # 3. 解析响应
            parsed = self._parse_llm_response(response.text)
            if not parsed:
                log.warning("llm_response_parse_failed", fallback="rule")
                return await self.fallback.classify(query, context)

            # 4. 构建结果
            label_str = parsed.get("label", "fact_seeking")
            try:
                label = IntentLabel(label_str)
            except ValueError:
                label = IntentLabel.FACT_SEEKING

            result = IntentResult(
                label=label,
                confidence=float(parsed.get("confidence", 0.7)),
                tags=parsed.get("tags", []),
                reason=parsed.get("reason", ""),
                requires_evidence=label in [IntentLabel.FACT_SEEKING],
                classifier_type=self.classifier_type,
                latency_ms=latency_ms,
                cached=False,
            )

            # 5. 写入缓存
            await self._set_cached(cache_key, result)

            log.info(
                "intent_classified_llm",
                label=result.label.value,
                confidence=result.confidence,
                latency_ms=latency_ms,
            )

            return result

        except Exception as e:
            log.error("llm_classify_error", error=str(e), fallback="rule")
            # 降级到规则分类器
            return await self.fallback.classify(query, context)


# ============================================================
# 工厂函数
# ============================================================

_classifier_instance: Optional[IntentClassifier] = None


async def get_intent_classifier_v2(
    use_llm: bool = False,
    llm_provider=None,
    cache_client=None,
) -> IntentClassifier:
    """
    获取意图分类器

    Args:
        use_llm: 是否使用 LLM 分类器
        llm_provider: LLM Provider 实例
        cache_client: Redis 缓存客户端

    Returns:
        IntentClassifier
    """
    global _classifier_instance

    if use_llm:
        return LLMIntentClassifier(
            llm_provider=llm_provider,
            cache_client=cache_client,
        )
    else:
        if _classifier_instance is None:
            _classifier_instance = RuleIntentClassifier()
        return _classifier_instance


def get_rule_classifier() -> RuleIntentClassifier:
    """获取规则分类器（同步版本）"""
    return RuleIntentClassifier()
