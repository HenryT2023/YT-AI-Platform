"""
红队测试：证据闸门验证

测试目标：
1. 事实性问题无证据时必须返回 conservative
2. 上下文偏好问题可以正常回答
3. 禁止输出无证据的史实断言
"""

import json
import pytest
from pathlib import Path
from typing import List

from app.guardrails import (
    QueryIntent,
    QueryIntentClassifier,
    EvidenceGate,
    classify_query_intent,
    get_evidence_gate,
)
from app.agent.schemas import CitationItem, PolicyMode


# ==================
# 加载测试用例
# ==================

def load_redteam_cases() -> List[dict]:
    """加载红队测试用例"""
    cases_path = Path(__file__).parent / "redteam_cases.json"
    with open(cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


REDTEAM_CASES = load_redteam_cases()


# ==================
# 意图分类测试
# ==================

class TestQueryIntentClassifier:
    """测试意图分类器"""

    @pytest.fixture
    def classifier(self):
        return QueryIntentClassifier()

    @pytest.mark.parametrize("case", [
        c for c in REDTEAM_CASES if c["expected_intent"] == "fact_seeking"
    ], ids=lambda c: c["id"])
    def test_fact_seeking_intent(self, classifier, case):
        """测试事实性问题识别"""
        result = classifier.classify(case["query"])

        assert result.intent == QueryIntent.FACT_SEEKING, (
            f"Case {case['id']}: 期望 fact_seeking，实际 {result.intent.value}\n"
            f"Query: {case['query']}\n"
            f"Reason: {result.reason}"
        )

    @pytest.mark.parametrize("case", [
        c for c in REDTEAM_CASES if c["expected_intent"] == "context_preference"
    ], ids=lambda c: c["id"])
    def test_context_preference_intent(self, classifier, case):
        """测试上下文偏好问题识别"""
        result = classifier.classify(case["query"])

        assert result.intent == QueryIntent.CONTEXT_PREFERENCE, (
            f"Case {case['id']}: 期望 context_preference，实际 {result.intent.value}\n"
            f"Query: {case['query']}\n"
            f"Reason: {result.reason}"
        )


# ==================
# 证据闸门测试
# ==================

class TestEvidenceGate:
    """测试证据闸门"""

    @pytest.fixture
    def gate(self):
        return EvidenceGate(min_citations_for_fact=1)

    @pytest.mark.parametrize("case", [
        c for c in REDTEAM_CASES
        if c["expected_intent"] == "fact_seeking" and c["expected_policy_mode"] == "conservative"
    ], ids=lambda c: c["id"])
    def test_fact_seeking_no_evidence_blocked(self, gate, case):
        """测试事实性问题无证据时被阻止"""
        # 无证据
        citations = []

        result = gate.check_before_llm(case["query"], citations)

        assert not result.passed, (
            f"Case {case['id']}: 期望被阻止，实际通过\n"
            f"Query: {case['query']}\n"
            f"Reason: {result.reason}"
        )
        assert result.policy_mode == PolicyMode.CONSERVATIVE, (
            f"Case {case['id']}: 期望 conservative，实际 {result.policy_mode.value}"
        )

    @pytest.mark.parametrize("case", [
        c for c in REDTEAM_CASES
        if c["expected_intent"] == "fact_seeking"
    ], ids=lambda c: c["id"])
    def test_fact_seeking_with_evidence_passed(self, gate, case):
        """测试事实性问题有证据时通过"""
        # 有证据
        citations = [
            CitationItem(
                evidence_id="ev-001",
                title="严氏族谱",
                source_ref="族谱:1",
                confidence=0.9,
            )
        ]

        result = gate.check_before_llm(case["query"], citations)

        assert result.passed, (
            f"Case {case['id']}: 期望通过，实际被阻止\n"
            f"Query: {case['query']}\n"
            f"Reason: {result.reason}"
        )
        assert result.policy_mode == PolicyMode.NORMAL, (
            f"Case {case['id']}: 期望 normal，实际 {result.policy_mode.value}"
        )

    @pytest.mark.parametrize("case", [
        c for c in REDTEAM_CASES
        if c["expected_intent"] == "context_preference"
    ], ids=lambda c: c["id"])
    def test_context_preference_no_evidence_passed(self, gate, case):
        """测试上下文偏好问题无证据时也能通过"""
        # 无证据
        citations = []

        result = gate.check_before_llm(case["query"], citations)

        assert result.passed, (
            f"Case {case['id']}: 期望通过，实际被阻止\n"
            f"Query: {case['query']}\n"
            f"Reason: {result.reason}"
        )


# ==================
# 禁止断言检测测试
# ==================

class TestForbiddenAssertions:
    """测试禁止断言检测"""

    @pytest.fixture
    def classifier(self):
        return QueryIntentClassifier()

    @pytest.mark.parametrize("text,expected_count", [
        ("严氏始祖于公元1368年迁入", 1),
        ("距今已有600年历史", 1),
        ("第15代传人", 1),
        ("康熙年间建造", 1),
        ("乾隆三十年重修", 1),
        ("洪武二年迁徙", 1),
        ("这是一个普通的句子", 0),
        ("严氏家训很有意义", 0),
    ])
    def test_detect_forbidden_assertions(self, classifier, text, expected_count):
        """测试禁止断言检测"""
        matches = classifier.contains_forbidden_assertions(text)

        assert len(matches) >= expected_count, (
            f"期望检测到 >= {expected_count} 个断言，实际 {len(matches)}\n"
            f"Text: {text}\n"
            f"Matches: {matches}"
        )


# ==================
# 输出过滤测试
# ==================

class TestOutputFiltering:
    """测试输出过滤"""

    @pytest.fixture
    def gate(self):
        return EvidenceGate()

    @pytest.mark.parametrize("input_text,should_filter", [
        ("严氏始祖于公元1368年迁入严田", True),
        ("距今已有600年历史", True),
        ("第15代传人继承了家业", True),
        ("康熙年间建造了祠堂", True),
        ("严氏家训教导我们要孝顺父母", False),
    ])
    def test_filter_forbidden_assertions(self, gate, input_text, should_filter):
        """测试过滤禁止断言"""
        filtered = gate.filter_forbidden_assertions(input_text)

        if should_filter:
            assert filtered != input_text, (
                f"期望被过滤，实际未变化\n"
                f"Input: {input_text}\n"
                f"Output: {filtered}"
            )
        else:
            assert filtered == input_text, (
                f"期望不变，实际被过滤\n"
                f"Input: {input_text}\n"
                f"Output: {filtered}"
            )


# ==================
# 保守响应测试
# ==================

class TestConservativeResponse:
    """测试保守响应生成"""

    @pytest.fixture
    def gate(self):
        return EvidenceGate()

    def test_fact_seeking_conservative_response(self, gate):
        """测试事实性问题的保守响应"""
        response = gate.get_conservative_response(
            intent=QueryIntent.FACT_SEEKING,
            query="严氏始祖是哪一年迁来的？",
            npc_name="严氏先祖",
        )

        assert "族谱" in response or "文献" in response or "史料" in response
        assert "严氏先祖" in response

    def test_context_preference_conservative_response(self, gate):
        """测试上下文偏好问题的保守响应"""
        response = gate.get_conservative_response(
            intent=QueryIntent.CONTEXT_PREFERENCE,
            query="你觉得家训怎么样？",
            npc_name="严氏先祖",
        )

        assert "严氏先祖" in response


# ==================
# 集成测试
# ==================

class TestEvidenceGateIntegration:
    """证据闸门集成测试"""

    @pytest.fixture
    def gate(self):
        return EvidenceGate()

    def test_full_flow_fact_seeking_no_evidence(self, gate):
        """完整流程：事实性问题无证据"""
        query = "严氏始祖是哪一年迁到严田的？"
        citations = []

        # 1. 检查前置闸门
        result = gate.check_before_llm(query, citations)

        assert result.intent == QueryIntent.FACT_SEEKING
        assert not result.passed
        assert result.policy_mode == PolicyMode.CONSERVATIVE

        # 2. 获取保守响应
        response = gate.get_conservative_response(
            intent=result.intent,
            query=query,
            npc_name="严氏先祖",
        )

        assert len(response) > 0

    def test_full_flow_fact_seeking_with_evidence(self, gate):
        """完整流程：事实性问题有证据"""
        query = "严氏始祖是哪一年迁到严田的？"
        citations = [
            CitationItem(
                evidence_id="ev-001",
                title="严氏族谱",
                source_ref="族谱:1",
                confidence=0.9,
            )
        ]

        # 1. 检查前置闸门
        result = gate.check_before_llm(query, citations)

        assert result.intent == QueryIntent.FACT_SEEKING
        assert result.passed
        assert result.policy_mode == PolicyMode.NORMAL

    def test_full_flow_context_preference(self, gate):
        """完整流程：上下文偏好问题"""
        query = "你觉得严氏家训对现代人有什么启发？"
        citations = []

        # 1. 检查前置闸门
        result = gate.check_before_llm(query, citations)

        assert result.intent == QueryIntent.CONTEXT_PREFERENCE
        assert result.passed
        assert result.policy_mode == PolicyMode.NORMAL

        # 2. 检查后置闸门（假设 LLM 输出了史实断言）
        llm_output = "严氏家训很有启发，它是公元1500年制定的。"
        post_result = gate.check_after_llm(
            query=query,
            response_text=llm_output,
            citations=citations,
            intent=result.intent,
        )

        # 应该检测到禁止断言
        assert not post_result.passed
        assert len(post_result.forbidden_assertions) > 0


# ==================
# 运行所有红队用例
# ==================

@pytest.mark.parametrize("case", REDTEAM_CASES, ids=lambda c: c["id"])
def test_redteam_case(case):
    """运行单个红队测试用例"""
    classifier = QueryIntentClassifier()
    gate = EvidenceGate(min_citations_for_fact=1)

    # 分类意图
    intent_result = classifier.classify(case["query"])

    # 检查意图是否符合预期
    expected_intent = QueryIntent(case["expected_intent"])
    assert intent_result.intent == expected_intent, (
        f"Case {case['id']}: 意图不匹配\n"
        f"期望: {expected_intent.value}\n"
        f"实际: {intent_result.intent.value}\n"
        f"Query: {case['query']}"
    )

    # 无证据时检查闸门
    citations = []
    gate_result = gate.check_before_llm(case["query"], citations)

    # 检查策略模式是否符合预期
    expected_mode = PolicyMode(case["expected_policy_mode"])
    assert gate_result.policy_mode == expected_mode, (
        f"Case {case['id']}: 策略模式不匹配\n"
        f"期望: {expected_mode.value}\n"
        f"实际: {gate_result.policy_mode.value}\n"
        f"Query: {case['query']}"
    )
