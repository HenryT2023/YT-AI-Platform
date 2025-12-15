"""
Release Client

用于从 core-backend 获取 active release 配置
支持轻量缓存（TTL 60s）
"""

import asyncio
import time
import structlog
from typing import Any, Dict, Optional
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class RuntimeConfig:
    """运行态配置"""
    release_id: Optional[str] = None
    release_name: Optional[str] = None
    evidence_gate_policy_version: Optional[str] = None
    prompt_version: Optional[str] = None
    experiment_id: Optional[str] = None
    retrieval_defaults: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.retrieval_defaults is None:
            self.retrieval_defaults = {}


class ReleaseClient:
    """Release 客户端（带缓存）"""
    
    def __init__(self, cache_ttl: int = 60):
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[RuntimeConfig, float]] = {}
        self._lock = asyncio.Lock()
    
    def _cache_key(self, tenant_id: str, site_id: str, npc_id: Optional[str] = None) -> str:
        return f"{tenant_id}:{site_id}:{npc_id or ''}"
    
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        _, cached_at = self._cache[key]
        return time.time() - cached_at < self.cache_ttl
    
    async def get_runtime_config(
        self,
        tenant_id: str,
        site_id: str,
        npc_id: Optional[str] = None,
    ) -> RuntimeConfig:
        """
        获取运行态配置
        
        优先从缓存读取，若缓存过期则从 core-backend 获取
        """
        log = logger.bind(tenant_id=tenant_id, site_id=site_id, npc_id=npc_id)
        cache_key = self._cache_key(tenant_id, site_id, npc_id)
        
        # 检查缓存
        if self._is_cache_valid(cache_key):
            config, _ = self._cache[cache_key]
            log.debug("runtime_config_cache_hit", release_id=config.release_id)
            return config
        
        # 从 core-backend 获取
        async with self._lock:
            # 双重检查
            if self._is_cache_valid(cache_key):
                config, _ = self._cache[cache_key]
                return config
            
            config = await self._fetch_config(tenant_id, site_id, npc_id)
            self._cache[cache_key] = (config, time.time())
            log.debug("runtime_config_fetched", release_id=config.release_id)
            return config
    
    async def _fetch_config(
        self,
        tenant_id: str,
        site_id: str,
        npc_id: Optional[str] = None,
    ) -> RuntimeConfig:
        """从 core-backend 获取配置"""
        log = logger.bind(tenant_id=tenant_id, site_id=site_id)
        
        try:
            async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                params = {
                    "tenant_id": tenant_id,
                    "site_id": site_id,
                }
                if npc_id:
                    params["npc_id"] = npc_id
                
                response = await client.get(
                    f"{settings.CORE_BACKEND_URL}/api/v1/runtime/config",
                    params=params,
                    headers={
                        "X-Tenant-ID": tenant_id,
                        "X-Site-ID": site_id,
                    },
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return RuntimeConfig(
                        release_id=data.get("release_id"),
                        release_name=data.get("release_name"),
                        evidence_gate_policy_version=data.get("evidence_gate_policy_version"),
                        prompt_version=data.get("prompt_version"),
                        experiment_id=data.get("experiment_id"),
                        retrieval_defaults=data.get("retrieval_defaults", {}),
                    )
                else:
                    log.warning("runtime_config_fetch_failed", status=response.status_code)
        except Exception as e:
            log.warning("runtime_config_fetch_error", error=str(e))
        
        # 返回空配置（fallback）
        return RuntimeConfig()
    
    def invalidate_cache(self, tenant_id: str, site_id: str):
        """使缓存失效"""
        # 清除该 tenant/site 的所有缓存
        keys_to_remove = [
            k for k in self._cache.keys()
            if k.startswith(f"{tenant_id}:{site_id}:")
        ]
        for key in keys_to_remove:
            del self._cache[key]


# 全局单例
_release_client: Optional[ReleaseClient] = None


def get_release_client() -> ReleaseClient:
    """获取 ReleaseClient 单例"""
    global _release_client
    if _release_client is None:
        _release_client = ReleaseClient()
    return _release_client
