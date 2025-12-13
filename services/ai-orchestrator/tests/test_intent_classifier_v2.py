"""
Intent Classifier v2 测试

测试内容：
1. RuleIntentClassifier 基本功能
2. LLMIntentClassifier 降级机制
3. 缓存命中
4. 测试用例集覆盖
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.guardrails.intent_classifier_v2 import (
    IntentLabel,
    IntentResult,
    IntentContext,
    IntentClassifier,
    RuleIntentClassifier,
    LLMIntentClassifier,
    get_rule_classifier,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def rule_classifier():
    """规则分类器"""
    return RuleIntentClassifier()


@pytest.fixture
def mock_llm_provider():
    """模拟 LLM Provider"""
    provider = AsyncMock()
    provider.generate = AsyncMock()
    return provider


@pytest.fixture
def mock_cache_client():
    """模拟 Redis 缓存客户端"""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.setex = AsyncMock()
    return cache


@pytest.fixture
def llm_classifier(mock_llm_provider, mock_cache_client):
    """LLM 分类器"""
    return LLMIntentClassifier(
        llm_provider=mock_llm_provider,
        cache_client=mock_cache_client,
        cache_ttl=300,
    )


@pytest.fixture
def intent_cases():
    """加载测试用例"""
    cases_path = Path(__file__).parent / "intent_cases.json"
    with open(cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


# ============================================================
# RuleIntentClassifier 测试
# ============================================================

class TestRuleIntentClassifier:
    """规则分类器测试"""

    @pytest.mark.asyncio
    async def test_classify_fact_seeking(self, rule_classifier):
        """测试事实性问题分类"""
        result = await rule_classifier.classify("严氏是什么时候迁到这里的？")
        assert result.label == IntentLabel.FACT_SEEKING
        assert result.requires_evidence is True
        assert result.classifier_type == "rule"

    @pytest.mark.asyncio
    async def test_classify_context_preference(self, rule_classifier):
        """测试上下文偏好问题分类"""
        result = await rule_classifier.classify("你觉得这里怎么样？")
        assert result.label == IntentLabel.CONTEXT_PREFERENCE
        assert result.requires_evidence is False

    @pytest.mark.asyncio
    async def test_classify_greeting(self, rule_classifier):
        """测试问候分类"""
        result = await rule_classifier.classify("你好")
        assert result.label == IntentLabel.GREETING
        assert result.requires_evidence is False

    @pytest.mark.asyncio
    async def test_classify_default_to_fact(self, rule_classifier):
        """测试默认分类为事实性（保守策略）"""
        result = await rule_classifier.classify("这个村子")
        assert result.label == IntentLabel.FACT_SEEKING
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_contains_forbidden_assertions(self, rule_classifier):
        """测试禁止断言检测"""
        text = "严氏于公元1368年迁入，距今已有600多年历史"
        assertions = rule_classifier.contains_forbidden_assertions(text)
        assert len(assertions) > 0
        assert "1368年" in assertions or "公元1368年" in str(assertions)

    @pytest.mark.asyncio
    async def test_classifier_type(self, rule_classifier):
        """测试分类器类型"""
        assert rule_classifier.classifier_type == "rule"


# ============================================================
# LLMIntentClassifier 测试
# ============================================================

class TestLLMIntentClassifier:
    """LLM 分类器测试"""

    @pytest.mark.asyncio
    async def test_fallback_when_no_provider(self):
        """测试无 LLM Provider 时降级"""
        classifier = LLMIntentClassifier(
            llm_provider=None,
            cache_client=None,
        )
        result = await classifier.classify("严氏是什么时候迁来的？")
        # 应该降级到规则分类器
        assert result.label == IntentLabel.FACT_SEEKING
        assert result.classifier_type == "rule"

    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self, mock_llm_provider, mock_cache_client):
        """测试 LLM 错误时降级"""
        mock_llm_provider.generate.side_effect = Exception("LLM Error")

        classifier = LLMIntentClassifier(
            llm_provider=mock_llm_provider,
            cache_client=mock_cache_client,
        )
        result = await classifier.classify("严氏是什么时候迁来的？")
        # 应该降级到规则分类器
        assert result.label == IntentLabel.FACT_SEEKING
        assert result.classifier_type == "rule"

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_llm_provider, mock_cache_client):
        """测试缓存命中"""
        cached_data = json.dumps({
            "label": "fact_seeking",
            "confidence": 0.9,
            "tags": ["历史"],
            "reason": "cached",
            "requires_evidence": True,
        })
        mock_cache_client.get.return_value = cached_data

        classifier = LLMIntentClassifier(
            llm_provider=mock_llm_provider,
            cache_client=mock_cache_client,
        )
        result = await classifier.classify("严氏是什么时候迁来的？")

        assert result.label == IntentLabel.FACT_SEEKING
        assert result.cached is True
        # LLM 不应该被调用
        mock_llm_provider.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_success(self, mock_llm_provider, mock_cache_client):
        """测试 LLM 成功分类"""
        from app.providers.llm.base import LLMResponse

        mock_llm_provider.generate.return_value = LLMResponse(
            text='{"label": "fact_seeking", "confidence": 0.85, "tags": ["历史"], "reason": "询问迁徙时间"}',
            model="test",
            tokens_input=100,
            tokens_output=50,
        )

        classifier = LLMIntentClassifier(
            llm_provider=mock_llm_provider,
            cache_client=mock_cache_client,
        )
        result = await classifier.classify("严氏是什么时候迁来的？")

        assert result.label == IntentLabel.FACT_SEEKING
        assert result.confidence == 0.85
        assert result.classifier_type == "llm"
        assert result.cached is False

    @pytest.mark.asyncio
    async def test_fallback_on_parse_error(self, mock_llm_provider, mock_cache_client):
        """测试 LLM 响应解析失败时降级"""
        from app.providers.llm.base import LLMResponse

        mock_llm_provider.generate.return_value = LLMResponse(
            text="这不是有效的 JSON",
            model="test",
            tokens_input=100,
            tokens_output=50,
        )

        classifier = LLMIntentClassifier(
            llm_provider=mock_llm_provider,
            cache_client=mock_cache_client,
        )
        result = await classifier.classify("严氏是什么时候迁来的？")

        # 应该降级到规则分类器
        assert result.classifier_type == "rule"

    @pytest.mark.asyncio
    async def test_classifier_type(self, llm_classifier):
        """测试分类器类型"""
        assert llm_classifier.classifier_type == "llm"


# ============================================================
# 测试用例集覆盖
# ============================================================

class TestIntentCases:
    """测试用例集覆盖测试"""

    @pytest.mark.asyncio
    async def test_fact_seeking_cases(self, rule_classifier, intent_cases):
        """测试事实性问题用例"""
        fact_cases = [c for c in intent_cases if c["expected_label"] == "fact_seeking"]
        assert len(fact_cases) >= 35, "事实性问题用例应该 >= 35 条"

        passed = 0
        for case in fact_cases:
            result = await rule_classifier.classify(case["query"])
            if result.label == IntentLabel.FACT_SEEKING:
                passed += 1

        accuracy = passed / len(fact_cases)
        assert accuracy >= 0.7, f"事实性问题准确率应该 >= 70%，实际 {accuracy:.1%}"

    @pytest.mark.asyncio
    async def test_context_preference_cases(self, rule_classifier, intent_cases):
        """测试上下文偏好问题用例"""
        pref_cases = [c for c in intent_cases if c["expected_label"] == "context_preference"]
        assert len(pref_cases) >= 25, "上下文偏好问题用例应该 >= 25 条"

        passed = 0
        for case in pref_cases:
            result = await rule_classifier.classify(case["query"])
            if result.label == IntentLabel.CONTEXT_PREFERENCE:
                passed += 1

        accuracy = passed / len(pref_cases)
        assert accuracy >= 0.6, f"上下文偏好问题准确率应该 >= 60%，实际 {accuracy:.1%}"

    @pytest.mark.asyncio
    async def test_greeting_cases(self, rule_classifier, intent_cases):
        """测试问候用例"""
        greet_cases = [c for c in intent_cases if c["expected_label"] == "greeting"]
        assert len(greet_cases) >= 10, "问候用例应该 >= 10 条"

        passed = 0
        for case in greet_cases:
            result = await rule_classifier.classify(case["query"])
            if result.label == IntentLabel.GREETING:
                passed += 1

        accuracy = passed / len(greet_cases)
        assert accuracy >= 0.8, f"问候准确率应该 >= 80%，实际 {accuracy:.1%}"

    @pytest.mark.asyncio
    async def test_total_cases_count(self, intent_cases):
        """测试用例总数"""
        assert len(intent_cases) >= 100, f"测试用例应该 >= 100 条，实际 {len(intent_cases)} 条"

    @pytest.mark.asyncio
    async def test_requires_evidence_consistency(self, rule_classifier, intent_cases):
        """测试 requires_evidence 一致性"""
        for case in intent_cases:
            result = await rule_classifier.classify(case["query"])
            if case["expected_label"] == "fact_seeking":
                # 事实性问题应该需要证据
                if result.label == IntentLabel.FACT_SEEKING:
                    assert result.requires_evidence is True


# ============================================================
# 集成测试
# ============================================================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_get_rule_classifier(self):
        """测试获取规则分类器"""
        classifier = get_rule_classifier()
        assert isinstance(classifier, RuleIntentClassifier)

    @pytest.mark.asyncio
    async def test_context_usage(self, rule_classifier):
        """测试上下文使用"""
        context = IntentContext(
            tenant_id="yantian",
            site_id="yantian-main",
            npc_id="ancestor_yan",
            npc_knowledge_domains=["历史", "族谱", "家训"],
        )
        result = await rule_classifier.classify("严氏是什么时候迁来的？", context)
        assert result.label == IntentLabel.FACT_SEEKING

    @pytest.mark.asyncio
    async def test_latency_recorded(self, rule_classifier):
        """测试延迟记录"""
        result = await rule_classifier.classify("严氏是什么时候迁来的？")
        assert result.latency_ms >= 0
