"""
缓存性能验证测试

验证场景：
1. 同一 NPC 连续对话 N 次，tool_calls 数量下降
2. 缓存命中率统计
3. 延迟对比
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock

from app.cache import RedisCache, CacheKeyBuilder, CacheKey
from app.cache.keys import CACHE_TTL
from app.tools.resilient_client import (
    ResilientToolClient,
    ToolConfig,
    TOOL_CONFIGS,
)
from app.tools.schemas import ToolContext


class TestCacheKeyBuilder:
    """缓存 Key 构建器测试"""

    def setup_method(self):
        self.builder = CacheKeyBuilder()

    def test_npc_profile_key(self):
        """测试 NPC Profile Key"""
        key = self.builder.npc_profile("tenant1", "site1", "ancestor_yan")
        assert key == "yantian:tenant1:site1:npc_profile:ancestor_yan"

    def test_prompt_active_key(self):
        """测试 Prompt Active Key"""
        key = self.builder.prompt_active("tenant1", "site1", "ancestor_yan")
        assert key == "yantian:tenant1:site1:prompt:ancestor_yan:active"

    def test_site_map_key(self):
        """测试 Site Map Key"""
        key = self.builder.site_map("tenant1", "site1")
        assert key == "yantian:tenant1:site1:site_map:default"

    def test_evidence_key(self):
        """测试 Evidence Key（基于查询 hash）"""
        key1 = self.builder.evidence("tenant1", "site1", "严氏家训")
        key2 = self.builder.evidence("tenant1", "site1", "严氏家训")
        key3 = self.builder.evidence("tenant1", "site1", "王家匠人")

        # 相同查询应该生成相同 Key
        assert key1 == key2
        # 不同查询应该生成不同 Key
        assert key1 != key3

    def test_ttl_config(self):
        """测试 TTL 配置"""
        assert CACHE_TTL[CacheKey.NPC_PROFILE] == 300
        assert CACHE_TTL[CacheKey.PROMPT_ACTIVE] == 300
        assert CACHE_TTL[CacheKey.SITE_MAP] == 600
        assert CACHE_TTL[CacheKey.EVIDENCE] == 60


class TestToolConfigs:
    """工具配置测试"""

    def test_timeout_configs(self):
        """测试超时配置"""
        assert TOOL_CONFIGS["get_prompt_active"].timeout_ms == 200
        assert TOOL_CONFIGS["get_npc_profile"].timeout_ms == 300
        assert TOOL_CONFIGS["get_site_map"].timeout_ms == 300
        assert TOOL_CONFIGS["retrieve_evidence"].timeout_ms == 800
        assert TOOL_CONFIGS["log_user_event"].timeout_ms == 150

    def test_cacheable_configs(self):
        """测试可缓存配置"""
        assert TOOL_CONFIGS["get_prompt_active"].cacheable is True
        assert TOOL_CONFIGS["get_npc_profile"].cacheable is True
        assert TOOL_CONFIGS["get_site_map"].cacheable is True
        assert TOOL_CONFIGS["retrieve_evidence"].cacheable is True
        assert TOOL_CONFIGS["log_user_event"].cacheable is False


class TestResilientToolClient:
    """弹性工具客户端测试"""

    @pytest.fixture
    def mock_cache(self):
        """Mock 缓存"""
        cache = AsyncMock(spec=RedisCache)
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock(return_value=True)
        cache.is_connected = True
        return cache

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return ResilientToolClient()

    @pytest.fixture
    def ctx(self):
        """创建测试上下文"""
        return ToolContext(
            tenant_id="yantian",
            site_id="yantian-main",
            trace_id="test-trace-001",
        )

    @pytest.mark.asyncio
    async def test_cache_hit_reduces_calls(self, client, ctx, mock_cache):
        """测试缓存命中减少调用次数"""
        # 模拟缓存命中
        cached_profile = {
            "npc_id": "ancestor_yan",
            "name": "严氏先祖",
            "display_name": "严氏先祖",
            "npc_type": "ancestor",
            "knowledge_domains": ["家族历史"],
        }
        mock_cache.get = AsyncMock(return_value=cached_profile)

        with patch.object(client, '_get_cache', return_value=mock_cache):
            with patch.object(client, '_do_call') as mock_call:
                # 第一次调用应该命中缓存，不调用 _do_call
                result = await client.call_tool(
                    "get_npc_profile",
                    {"npc_id": "ancestor_yan"},
                    ctx,
                )

                assert result.success is True
                assert result.output == cached_profile
                mock_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_records(self, client, ctx):
        """测试审计记录"""
        # 清空审计
        client.clear_audits()

        # 模拟调用
        with patch.object(client, '_do_call') as mock_call:
            from app.tools.schemas import ToolCallResult, ToolAudit

            mock_call.return_value = ToolCallResult(
                success=True,
                output={"npc_id": "test"},
                audit=ToolAudit(tool_name="get_npc_profile", latency_ms=50),
            )

            await client.call_tool("get_npc_profile", {"npc_id": "test"}, ctx)

        audits = client.get_audits()
        assert len(audits) == 1
        assert audits[0]["name"] == "get_npc_profile"
        assert audits[0]["status"] == "success"


class TestPerformanceVerification:
    """性能验证测试"""

    @pytest.mark.asyncio
    async def test_consecutive_calls_cache_improvement(self):
        """
        测试连续调用的缓存改进

        场景：同一 NPC 连续对话 5 次
        预期：第 2-5 次调用应该命中缓存，tool_calls 数量下降
        """
        # 模拟数据
        npc_profile = {
            "npc_id": "ancestor_yan",
            "name": "严氏先祖",
            "display_name": "严氏先祖",
            "npc_type": "ancestor",
            "knowledge_domains": ["家族历史"],
        }
        prompt_info = {
            "prompt_text": "你是严氏先祖...",
            "version": 1,
            "metadata": {"source": "prompt_registry"},
        }

        # 创建 Mock 缓存
        cache_store = {}

        async def mock_get(key):
            return cache_store.get(key)

        async def mock_set(key, value, ttl=None):
            cache_store[key] = value
            return True

        mock_cache = AsyncMock(spec=RedisCache)
        mock_cache.get = mock_get
        mock_cache.set = mock_set
        mock_cache.is_connected = True

        client = ResilientToolClient()

        ctx = ToolContext(
            tenant_id="yantian",
            site_id="yantian-main",
            trace_id="test-trace",
        )

        # 统计
        actual_calls = 0

        async def mock_do_call(tool_name, input_data, ctx, timeout):
            nonlocal actual_calls
            actual_calls += 1

            from app.tools.schemas import ToolCallResult, ToolAudit

            if tool_name == "get_npc_profile":
                return ToolCallResult(
                    success=True,
                    output=npc_profile,
                    audit=ToolAudit(tool_name=tool_name, latency_ms=50),
                )
            elif tool_name == "get_prompt_active":
                return ToolCallResult(
                    success=True,
                    output=prompt_info,
                    audit=ToolAudit(tool_name=tool_name, latency_ms=30),
                )
            return ToolCallResult(success=False, error="Unknown tool")

        with patch.object(client, '_get_cache', return_value=mock_cache):
            with patch.object(client, '_do_call', side_effect=mock_do_call):
                # 连续调用 5 次
                for i in range(5):
                    client.clear_audits()

                    # 调用 get_npc_profile
                    await client.call_tool(
                        "get_npc_profile",
                        {"npc_id": "ancestor_yan"},
                        ctx,
                    )

                    # 调用 get_prompt_active
                    await client.call_tool(
                        "get_prompt_active",
                        {"npc_id": "ancestor_yan"},
                        ctx,
                    )

                    audits = client.get_audits()
                    cache_hits = sum(1 for a in audits if a.get("cache_hit"))

                    print(f"Call {i + 1}: actual_calls={actual_calls}, cache_hits={cache_hits}")

        # 验证：第一次调用 2 次，后续 4 次应该全部命中缓存
        # 总共应该只有 2 次实际调用
        assert actual_calls == 2, f"Expected 2 actual calls, got {actual_calls}"

    def test_ttl_table(self):
        """输出 TTL 表"""
        print("\n=== 缓存 TTL 配置表 ===")
        print(f"{'工具名称':<25} {'超时(ms)':<10} {'TTL(s)':<10} {'可缓存':<10}")
        print("-" * 55)

        for tool_name, config in TOOL_CONFIGS.items():
            ttl = config.cache_ttl if config.cacheable else "-"
            print(f"{tool_name:<25} {config.timeout_ms:<10} {ttl:<10} {config.cacheable}")

        print("\n=== 缓存 Key 规范 ===")
        print("格式: {prefix}:{tenant_id}:{site_id}:{resource_type}:{resource_id}")
        print("示例:")
        builder = CacheKeyBuilder()
        print(f"  NPC Profile: {builder.npc_profile('tenant1', 'site1', 'ancestor_yan')}")
        print(f"  Prompt:      {builder.prompt_active('tenant1', 'site1', 'ancestor_yan')}")
        print(f"  Site Map:    {builder.site_map('tenant1', 'site1')}")
        print(f"  Evidence:    {builder.evidence('tenant1', 'site1', '严氏家训')}")
