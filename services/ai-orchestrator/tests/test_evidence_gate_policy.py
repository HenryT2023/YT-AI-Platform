"""
Evidence Gate Policy 测试

测试内容：
1. 策略加载和缓存
2. per-site/per-npc 配置
3. 同一 query 不同 NPC 不同阈值
4. 审计日志（policy_version + applied_rule）
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

from app.guardrails.policy_loader import (
    PolicyLoader,
    EvidenceGatePolicy,
    AppliedRule,
    get_policy_loader,
    reset_policy_loader,
)
from app.guardrails.evidence_gate_v3 import (
    EvidenceGateV3,
    EvidenceGateResult,
    reset_evidence_gate_v3,
)
from app.guardrails.intent_classifier_v2 import IntentLabel, IntentContext
from app.agent.schemas import CitationItem, PolicyMode


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def policy_file(tmp_path):
    """创建临时策略文件"""
    policy_data = {
        "version": "test-0.1.0",
        "updated_at": "2024-12-13T00:00:00Z",
        "defaults": {
            "min_citations": 1,
            "min_score": 0.3,
            "max_soft_claims": 2,
            "allowed_soft_claims": ["据说", "相传"],
            "fallback_templates": {
                "fact_seeking": "默认：{npc_name}需要查阅资料。",
                "out_of_scope": "默认：超出{npc_name}知识范围。",
                "default": "默认：{npc_name}不确定。"
            },
            "strict_mode": False
        },
        "sites": {
            "yantian-main": {
                "description": "严田村主站点",
                "min_citations": 1,
                "min_score": 0.3,
                "npcs": {
                    "ancestor_yan": {
                        "description": "严氏先祖 - 严格",
                        "min_citations": 2,
                        "min_score": 0.5,
                        "max_soft_claims": 1,
                        "strict_mode": True,
                        "allowed_soft_claims": ["据族谱记载"],
                        "fallback_templates": {
                            "fact_seeking": "先祖版：{npc_name}须查阅族谱。",
                            "default": "先祖版：{npc_name}不敢妄言。"
                        }
                    },
                    "farmer_li": {
                        "description": "老农李伯 - 宽松",
                        "min_citations": 0,
                        "min_score": 0.2,
                        "max_soft_claims": 5,
                        "strict_mode": False,
                        "allowed_soft_claims": ["据说", "老辈人讲", "我听说"],
                        "fallback_templates": {
                            "fact_seeking": "老农版：{npc_name}不太清楚。",
                            "default": "老农版：{npc_name}说不准。"
                        }
                    }
                }
            }
        },
        "intent_overrides": {
            "greeting": {
                "min_citations": 0,
                "requires_evidence": False
            },
            "context_preference": {
                "min_citations": 0,
                "requires_evidence": False,
                "requires_filtering": True
            }
        },
        "audit": {
            "log_policy_version": True,
            "log_applied_rule": True
        }
    }

    policy_path = tmp_path / "test_policy.json"
    with open(policy_path, "w", encoding="utf-8") as f:
        json.dump(policy_data, f, ensure_ascii=False, indent=2)

    return policy_path


@pytest.fixture
def policy_loader(policy_file):
    """策略加载器"""
    reset_policy_loader()
    return PolicyLoader(policy_path=str(policy_file), cache_ttl_seconds=60)


@pytest.fixture
def evidence_gate(policy_loader):
    """证据闸门"""
    reset_evidence_gate_v3()
    return EvidenceGateV3(policy_loader=policy_loader, use_llm_classifier=False)


@pytest.fixture
def mock_citations():
    """模拟引用"""
    return [
        CitationItem(
            evidence_id="ev1",
            title="族谱记载",
            excerpt="严氏于明朝迁入",
            score=0.8,
        ),
        CitationItem(
            evidence_id="ev2",
            title="县志",
            excerpt="严田村历史",
            score=0.6,
        ),
    ]


# ============================================================
# PolicyLoader 测试
# ============================================================

class TestPolicyLoader:
    """策略加载器测试"""

    def test_load_policy(self, policy_loader):
        """测试加载策略"""
        policy = policy_loader.load()
        assert policy.version == "test-0.1.0"
        assert "yantian-main" in policy.sites

    def test_cache_hit(self, policy_loader):
        """测试缓存命中"""
        policy1 = policy_loader.load()
        policy2 = policy_loader.load()
        # 应该是同一个对象（缓存命中）
        assert policy1 is policy2

    def test_get_policy_for_context_defaults(self, policy_loader):
        """测试获取默认策略"""
        policy = policy_loader.load()
        ctx_policy = policy.get_policy_for_context("unknown-site", None)
        assert ctx_policy["min_citations"] == 1
        assert ctx_policy["min_score"] == 0.3

    def test_get_policy_for_context_site(self, policy_loader):
        """测试获取站点级策略"""
        policy = policy_loader.load()
        ctx_policy = policy.get_policy_for_context("yantian-main", None)
        assert ctx_policy["min_citations"] == 1

    def test_get_policy_for_context_npc(self, policy_loader):
        """测试获取 NPC 级策略"""
        policy = policy_loader.load()

        # ancestor_yan: 严格
        ancestor_policy = policy.get_policy_for_context("yantian-main", "ancestor_yan")
        assert ancestor_policy["min_citations"] == 2
        assert ancestor_policy["min_score"] == 0.5
        assert ancestor_policy["strict_mode"] is True

        # farmer_li: 宽松
        farmer_policy = policy.get_policy_for_context("yantian-main", "farmer_li")
        assert farmer_policy["min_citations"] == 0
        assert farmer_policy["min_score"] == 0.2
        assert farmer_policy["strict_mode"] is False

    def test_get_applied_rule(self, policy_loader):
        """测试获取应用的规则"""
        rule = policy_loader.get_applied_rule("yantian-main", "ancestor_yan", "fact_seeking")
        assert rule.policy_version == "test-0.1.0"
        assert rule.min_citations == 2
        assert rule.min_score == 0.5
        assert rule.strict_mode is True

    def test_intent_override(self, policy_loader):
        """测试意图覆盖"""
        policy = policy_loader.load()
        override = policy.get_intent_override("greeting")
        assert override is not None
        assert override.requires_evidence is False


# ============================================================
# EvidenceGateV3 测试
# ============================================================

class TestEvidenceGateV3:
    """证据闸门 v3 测试"""

    @pytest.mark.asyncio
    async def test_fact_seeking_with_enough_evidence(self, evidence_gate, mock_citations):
        """测试事实性问题有足够证据"""
        result = await evidence_gate.check_before_llm(
            query="严氏是什么时候迁来的？",
            citations=mock_citations,
            site_id="yantian-main",
            npc_id="farmer_li",  # 宽松配置
        )
        assert result.passed is True
        assert result.policy_mode == PolicyMode.NORMAL
        assert result.policy_version == "test-0.1.0"

    @pytest.mark.asyncio
    async def test_fact_seeking_insufficient_evidence_strict(self, evidence_gate):
        """测试事实性问题证据不足（严格 NPC）"""
        # ancestor_yan 需要 2 条引用
        result = await evidence_gate.check_before_llm(
            query="严氏是什么时候迁来的？",
            citations=[
                CitationItem(evidence_id="ev1", title="族谱", excerpt="...", score=0.8)
            ],  # 只有 1 条
            site_id="yantian-main",
            npc_id="ancestor_yan",
        )
        assert result.passed is False
        assert result.policy_mode == PolicyMode.CONSERVATIVE
        assert "引用数不足" in result.reason

    @pytest.mark.asyncio
    async def test_fact_seeking_low_score(self, evidence_gate):
        """测试事实性问题引用分数不足"""
        result = await evidence_gate.check_before_llm(
            query="严氏是什么时候迁来的？",
            citations=[
                CitationItem(evidence_id="ev1", title="族谱", excerpt="...", score=0.3),
                CitationItem(evidence_id="ev2", title="县志", excerpt="...", score=0.2),
            ],  # 平均分 0.25，低于 ancestor_yan 的 0.5
            site_id="yantian-main",
            npc_id="ancestor_yan",
        )
        assert result.passed is False
        assert "引用分数不足" in result.reason

    @pytest.mark.asyncio
    async def test_greeting_no_evidence_needed(self, evidence_gate):
        """测试问候无需证据"""
        result = await evidence_gate.check_before_llm(
            query="你好",
            citations=[],
            site_id="yantian-main",
            npc_id="ancestor_yan",
        )
        assert result.passed is True
        assert "无需证据" in result.reason

    @pytest.mark.asyncio
    async def test_conservative_response_per_npc(self, evidence_gate):
        """测试不同 NPC 的保守响应"""
        # ancestor_yan
        ancestor_response = evidence_gate.get_conservative_response(
            intent=IntentLabel.FACT_SEEKING,
            query="test",
            npc_name="先祖",
            site_id="yantian-main",
            npc_id="ancestor_yan",
        )
        assert "先祖版" in ancestor_response or "族谱" in ancestor_response

        # farmer_li
        farmer_response = evidence_gate.get_conservative_response(
            intent=IntentLabel.FACT_SEEKING,
            query="test",
            npc_name="李伯",
            site_id="yantian-main",
            npc_id="farmer_li",
        )
        assert "老农版" in farmer_response or "不太清楚" in farmer_response

    @pytest.mark.asyncio
    async def test_audit_fields(self, evidence_gate, mock_citations):
        """测试审计字段"""
        result = await evidence_gate.check_before_llm(
            query="严氏是什么时候迁来的？",
            citations=mock_citations,
            site_id="yantian-main",
            npc_id="farmer_li",
        )
        assert result.policy_version == "test-0.1.0"
        assert result.policy_hash != ""
        assert result.applied_rule is not None
        assert result.applied_rule["site_id"] == "yantian-main"
        assert result.applied_rule["npc_id"] == "farmer_li"


# ============================================================
# 回归测试：同一 query 不同 NPC 不同阈值
# ============================================================

class TestDifferentNPCThresholds:
    """同一 query 不同 NPC 不同阈值测试"""

    @pytest.mark.asyncio
    async def test_same_query_different_npc_different_result(self, evidence_gate):
        """同一查询，不同 NPC，不同结果"""
        query = "严氏是什么时候迁来的？"
        citations = [
            CitationItem(evidence_id="ev1", title="族谱", excerpt="...", score=0.4)
        ]

        # farmer_li: min_citations=0, min_score=0.2 -> 应该通过
        farmer_result = await evidence_gate.check_before_llm(
            query=query,
            citations=citations,
            site_id="yantian-main",
            npc_id="farmer_li",
        )
        assert farmer_result.passed is True, f"farmer_li 应该通过，实际: {farmer_result.reason}"

        # ancestor_yan: min_citations=2, min_score=0.5 -> 应该失败
        ancestor_result = await evidence_gate.check_before_llm(
            query=query,
            citations=citations,
            site_id="yantian-main",
            npc_id="ancestor_yan",
        )
        assert ancestor_result.passed is False, f"ancestor_yan 应该失败，实际: {ancestor_result.reason}"

    @pytest.mark.asyncio
    async def test_same_query_different_site(self, evidence_gate, policy_loader):
        """同一查询，不同站点"""
        query = "这里有什么历史？"

        # yantian-main: 有配置
        result1 = await evidence_gate.check_before_llm(
            query=query,
            citations=[],
            site_id="yantian-main",
            npc_id=None,
        )

        # unknown-site: 使用默认配置
        result2 = await evidence_gate.check_before_llm(
            query=query,
            citations=[],
            site_id="unknown-site",
            npc_id=None,
        )

        # 两者都应该失败（事实性问题无证据）
        assert result1.passed is False
        assert result2.passed is False

    @pytest.mark.asyncio
    async def test_applied_rule_differs_per_npc(self, evidence_gate):
        """验证 applied_rule 因 NPC 不同而不同"""
        query = "严氏是什么时候迁来的？"
        citations = []

        farmer_result = await evidence_gate.check_before_llm(
            query=query,
            citations=citations,
            site_id="yantian-main",
            npc_id="farmer_li",
        )

        ancestor_result = await evidence_gate.check_before_llm(
            query=query,
            citations=citations,
            site_id="yantian-main",
            npc_id="ancestor_yan",
        )

        # 验证 applied_rule 不同
        assert farmer_result.applied_rule["min_citations"] == 0
        assert ancestor_result.applied_rule["min_citations"] == 2

        assert farmer_result.applied_rule["strict_mode"] is False
        assert ancestor_result.applied_rule["strict_mode"] is True


# ============================================================
# 软断言测试
# ============================================================

class TestSoftClaims:
    """软断言测试"""

    @pytest.mark.asyncio
    async def test_soft_claims_allowed(self, evidence_gate):
        """测试允许的软断言"""
        result = await evidence_gate.check_after_llm(
            query="这里有什么故事？",
            response_text="据说，严氏于明朝迁入此地。相传，始祖是一位学者。",
            citations=[],
            intent=IntentLabel.CONTEXT_PREFERENCE,
            site_id="yantian-main",
            npc_id="farmer_li",  # max_soft_claims=5
        )
        assert result.passed is True
        assert len(result.soft_claims_used) > 0

    @pytest.mark.asyncio
    async def test_strict_mode_rejects_forbidden(self, evidence_gate):
        """测试严格模式拒绝禁止断言"""
        result = await evidence_gate.check_after_llm(
            query="这里有什么故事？",
            response_text="严氏于公元1368年迁入此地。",  # 包含禁止断言
            citations=[],
            intent=IntentLabel.CONTEXT_PREFERENCE,
            site_id="yantian-main",
            npc_id="ancestor_yan",  # strict_mode=True
        )
        assert result.passed is False
        assert "严格模式" in result.reason
