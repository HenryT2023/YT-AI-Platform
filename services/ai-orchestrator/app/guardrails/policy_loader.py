"""
Evidence Gate Policy Loader

策略加载器：支持热更新（缓存 + TTL）

功能：
1. 从 JSON 文件加载策略配置
2. 支持 per-site/per-npc 配置
3. 缓存 + TTL 热更新
4. 策略版本追踪
"""

import json
import hashlib
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = structlog.get_logger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class NPCPolicy:
    """NPC 级别策略"""
    npc_id: str
    description: str = ""
    min_citations: int = 1
    min_score: float = 0.3
    max_soft_claims: int = 2
    strict_mode: bool = False
    allowed_soft_claims: List[str] = field(default_factory=list)
    fallback_templates: Dict[str, str] = field(default_factory=dict)


@dataclass
class SitePolicy:
    """站点级别策略"""
    site_id: str
    description: str = ""
    min_citations: int = 1
    min_score: float = 0.3
    max_soft_claims: int = 2
    strict_mode: bool = False
    allowed_soft_claims: List[str] = field(default_factory=list)
    fallback_templates: Dict[str, str] = field(default_factory=dict)
    npcs: Dict[str, NPCPolicy] = field(default_factory=dict)


@dataclass
class IntentOverride:
    """意图级别覆盖"""
    intent: str
    min_citations: int = 0
    requires_evidence: bool = False
    requires_filtering: bool = False


@dataclass
class EvidenceGatePolicy:
    """完整策略配置"""
    version: str
    updated_at: str
    defaults: Dict[str, Any]
    sites: Dict[str, SitePolicy]
    intent_overrides: Dict[str, IntentOverride]
    audit: Dict[str, bool]

    # 计算属性
    _hash: str = ""

    def get_policy_for_context(
        self,
        site_id: str,
        npc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取特定上下文的策略

        优先级：NPC > Site > Defaults
        """
        result = dict(self.defaults)

        # 站点级覆盖
        if site_id in self.sites:
            site_policy = self.sites[site_id]
            result.update({
                "min_citations": site_policy.min_citations,
                "min_score": site_policy.min_score,
                "max_soft_claims": site_policy.max_soft_claims,
                "strict_mode": site_policy.strict_mode,
                "allowed_soft_claims": site_policy.allowed_soft_claims or result.get("allowed_soft_claims", []),
                "fallback_templates": {**result.get("fallback_templates", {}), **site_policy.fallback_templates},
            })

            # NPC 级覆盖
            if npc_id and npc_id in site_policy.npcs:
                npc_policy = site_policy.npcs[npc_id]
                result.update({
                    "min_citations": npc_policy.min_citations,
                    "min_score": npc_policy.min_score,
                    "max_soft_claims": npc_policy.max_soft_claims,
                    "strict_mode": npc_policy.strict_mode,
                    "allowed_soft_claims": npc_policy.allowed_soft_claims or result.get("allowed_soft_claims", []),
                    "fallback_templates": {**result.get("fallback_templates", {}), **npc_policy.fallback_templates},
                })

        return result

    def get_intent_override(self, intent: str) -> Optional[IntentOverride]:
        """获取意图级别覆盖"""
        return self.intent_overrides.get(intent)


@dataclass
class AppliedRule:
    """应用的规则（用于审计）"""
    policy_version: str
    policy_hash: str
    site_id: str
    npc_id: Optional[str]
    min_citations: int
    min_score: float
    max_soft_claims: int
    strict_mode: bool
    intent_override: Optional[str] = None
    applied_at: str = ""

    def __post_init__(self):
        if not self.applied_at:
            self.applied_at = datetime.utcnow().isoformat()


# ============================================================
# 策略加载器
# ============================================================

class PolicyLoader:
    """
    策略加载器

    支持：
    1. 从文件加载策略
    2. 缓存 + TTL 热更新
    3. 策略版本追踪
    """

    def __init__(
        self,
        policy_path: Optional[str] = None,
        cache_ttl_seconds: int = 60,
    ):
        self.policy_path = Path(policy_path) if policy_path else self._default_policy_path()
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)

        self._cached_policy: Optional[EvidenceGatePolicy] = None
        self._cache_time: Optional[datetime] = None
        self._file_mtime: Optional[float] = None

    def _default_policy_path(self) -> Path:
        """默认策略文件路径"""
        # 从 ai-orchestrator 向上找到 data/policies
        current = Path(__file__).resolve()
        for _ in range(5):
            current = current.parent
            policy_file = current / "data" / "policies" / "evidence_gate_policy_v0.1.json"
            if policy_file.exists():
                return policy_file
        # 回退到相对路径
        return Path("data/policies/evidence_gate_policy_v0.1.json")

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if self._cached_policy is None or self._cache_time is None:
            return False

        # 检查 TTL
        if datetime.utcnow() - self._cache_time > self.cache_ttl:
            return False

        # 检查文件是否被修改
        try:
            current_mtime = self.policy_path.stat().st_mtime
            if self._file_mtime and current_mtime != self._file_mtime:
                return False
        except FileNotFoundError:
            return False

        return True

    def _parse_policy(self, data: Dict[str, Any]) -> EvidenceGatePolicy:
        """解析策略 JSON"""
        # 解析站点
        sites = {}
        for site_id, site_data in data.get("sites", {}).items():
            npcs = {}
            for npc_id, npc_data in site_data.get("npcs", {}).items():
                npcs[npc_id] = NPCPolicy(
                    npc_id=npc_id,
                    description=npc_data.get("description", ""),
                    min_citations=npc_data.get("min_citations", 1),
                    min_score=npc_data.get("min_score", 0.3),
                    max_soft_claims=npc_data.get("max_soft_claims", 2),
                    strict_mode=npc_data.get("strict_mode", False),
                    allowed_soft_claims=npc_data.get("allowed_soft_claims", []),
                    fallback_templates=npc_data.get("fallback_templates", {}),
                )

            sites[site_id] = SitePolicy(
                site_id=site_id,
                description=site_data.get("description", ""),
                min_citations=site_data.get("min_citations", 1),
                min_score=site_data.get("min_score", 0.3),
                max_soft_claims=site_data.get("max_soft_claims", 2),
                strict_mode=site_data.get("strict_mode", False),
                allowed_soft_claims=site_data.get("allowed_soft_claims", []),
                fallback_templates=site_data.get("fallback_templates", {}),
                npcs=npcs,
            )

        # 解析意图覆盖
        intent_overrides = {}
        for intent, override_data in data.get("intent_overrides", {}).items():
            intent_overrides[intent] = IntentOverride(
                intent=intent,
                min_citations=override_data.get("min_citations", 0),
                requires_evidence=override_data.get("requires_evidence", False),
                requires_filtering=override_data.get("requires_filtering", False),
            )

        # 计算 hash
        policy_hash = hashlib.md5(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:8]

        return EvidenceGatePolicy(
            version=data.get("version", "unknown"),
            updated_at=data.get("updated_at", ""),
            defaults=data.get("defaults", {}),
            sites=sites,
            intent_overrides=intent_overrides,
            audit=data.get("audit", {}),
            _hash=policy_hash,
        )

    def load(self) -> EvidenceGatePolicy:
        """
        加载策略（带缓存）

        Returns:
            EvidenceGatePolicy
        """
        if self._is_cache_valid():
            return self._cached_policy

        log = logger.bind(policy_path=str(self.policy_path))

        try:
            with open(self.policy_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            policy = self._parse_policy(data)

            # 更新缓存
            self._cached_policy = policy
            self._cache_time = datetime.utcnow()
            self._file_mtime = self.policy_path.stat().st_mtime

            log.info(
                "policy_loaded",
                version=policy.version,
                hash=policy._hash,
                sites=list(policy.sites.keys()),
            )

            return policy

        except FileNotFoundError:
            log.warning("policy_file_not_found", fallback="defaults")
            return self._default_policy()

        except json.JSONDecodeError as e:
            log.error("policy_parse_error", error=str(e), fallback="defaults")
            return self._default_policy()

    def _default_policy(self) -> EvidenceGatePolicy:
        """默认策略（文件不存在时使用）"""
        return EvidenceGatePolicy(
            version="default",
            updated_at=datetime.utcnow().isoformat(),
            defaults={
                "min_citations": 1,
                "min_score": 0.3,
                "max_soft_claims": 2,
                "allowed_soft_claims": ["据说", "相传", "传说"],
                "fallback_templates": {
                    "fact_seeking": "这个问题涉及具体的历史事实，{npc_name}需要查阅资料才能准确回答。",
                    "out_of_scope": "这个问题超出了{npc_name}的知识范围。",
                    "default": "关于这个问题，{npc_name}不太确定具体细节。",
                },
                "strict_mode": False,
            },
            sites={},
            intent_overrides={},
            audit={"log_policy_version": True, "log_applied_rule": True},
            _hash="default",
        )

    def reload(self) -> EvidenceGatePolicy:
        """强制重新加载策略"""
        self._cached_policy = None
        self._cache_time = None
        return self.load()

    def get_applied_rule(
        self,
        site_id: str,
        npc_id: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> AppliedRule:
        """
        获取应用的规则（用于审计）

        Args:
            site_id: 站点 ID
            npc_id: NPC ID
            intent: 意图类型

        Returns:
            AppliedRule
        """
        policy = self.load()
        context_policy = policy.get_policy_for_context(site_id, npc_id)

        intent_override = None
        if intent:
            override = policy.get_intent_override(intent)
            if override:
                intent_override = intent
                # 意图覆盖 min_citations
                context_policy["min_citations"] = override.min_citations

        return AppliedRule(
            policy_version=policy.version,
            policy_hash=policy._hash,
            site_id=site_id,
            npc_id=npc_id,
            min_citations=context_policy.get("min_citations", 1),
            min_score=context_policy.get("min_score", 0.3),
            max_soft_claims=context_policy.get("max_soft_claims", 2),
            strict_mode=context_policy.get("strict_mode", False),
            intent_override=intent_override,
        )


# ============================================================
# 全局实例
# ============================================================

_loader_instance: Optional[PolicyLoader] = None


def get_policy_loader(
    policy_path: Optional[str] = None,
    cache_ttl_seconds: int = 60,
) -> PolicyLoader:
    """获取策略加载器实例"""
    global _loader_instance

    if _loader_instance is None:
        _loader_instance = PolicyLoader(
            policy_path=policy_path,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    return _loader_instance


def reset_policy_loader() -> None:
    """重置策略加载器（用于测试）"""
    global _loader_instance
    _loader_instance = None


def get_policy_version() -> str:
    """获取当前策略版本（用于 trace snapshot）"""
    loader = get_policy_loader()
    policy = loader.load()
    return policy.version if policy else "unknown"
