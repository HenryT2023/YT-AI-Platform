"""
缓存 Key 命名规范

Key 格式: {prefix}:{tenant_id}:{site_id}:{resource_type}:{resource_id}

示例:
- yantian:tenant1:site1:npc_profile:ancestor_yan
- yantian:tenant1:site1:prompt:ancestor_yan:active
- yantian:tenant1:site1:site_map:default
- yantian:tenant1:site1:evidence:query_hash
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import hashlib


class CacheKey(str, Enum):
    """缓存 Key 类型"""

    NPC_PROFILE = "npc_profile"
    PROMPT_ACTIVE = "prompt"
    SITE_MAP = "site_map"
    EVIDENCE = "evidence"
    TOOL_RESULT = "tool"


# TTL 配置（秒）
CACHE_TTL = {
    CacheKey.NPC_PROFILE: 300,      # 5 分钟 - NPC 人设变化不频繁
    CacheKey.PROMPT_ACTIVE: 300,    # 5 分钟 - Prompt 变化不频繁
    CacheKey.SITE_MAP: 600,         # 10 分钟 - 站点地图很少变化
    CacheKey.EVIDENCE: 60,          # 1 分钟 - 证据检索结果短期缓存
    CacheKey.TOOL_RESULT: 60,       # 1 分钟 - 通用工具结果
}


@dataclass
class CacheKeyBuilder:
    """缓存 Key 构建器"""

    prefix: str = "yantian"

    def build(
        self,
        key_type: CacheKey,
        tenant_id: str,
        site_id: str,
        resource_id: str,
        suffix: Optional[str] = None,
    ) -> str:
        """
        构建缓存 Key

        Args:
            key_type: Key 类型
            tenant_id: 租户 ID
            site_id: 站点 ID
            resource_id: 资源 ID
            suffix: 可选后缀

        Returns:
            完整的缓存 Key
        """
        parts = [
            self.prefix,
            tenant_id,
            site_id,
            key_type.value,
            resource_id,
        ]
        if suffix:
            parts.append(suffix)

        return ":".join(parts)

    def npc_profile(self, tenant_id: str, site_id: str, npc_id: str) -> str:
        """NPC Profile 缓存 Key"""
        return self.build(CacheKey.NPC_PROFILE, tenant_id, site_id, npc_id)

    def prompt_active(self, tenant_id: str, site_id: str, npc_id: str) -> str:
        """Active Prompt 缓存 Key"""
        return self.build(CacheKey.PROMPT_ACTIVE, tenant_id, site_id, npc_id, "active")

    def site_map(self, tenant_id: str, site_id: str) -> str:
        """Site Map 缓存 Key"""
        return self.build(CacheKey.SITE_MAP, tenant_id, site_id, "default")

    def evidence(self, tenant_id: str, site_id: str, query: str, domains: Optional[list] = None) -> str:
        """Evidence 缓存 Key（基于查询 hash）"""
        # 构建查询指纹
        query_data = f"{query}:{sorted(domains) if domains else ''}"
        query_hash = hashlib.sha256(query_data.encode()).hexdigest()[:16]
        return self.build(CacheKey.EVIDENCE, tenant_id, site_id, query_hash)

    def get_ttl(self, key_type: CacheKey) -> int:
        """获取 TTL"""
        return CACHE_TTL.get(key_type, 60)


# 全局 Key 构建器实例
key_builder = CacheKeyBuilder()
