#!/usr/bin/env python3
"""
P27 Release Gate 验收脚本

测试流程：
1. 创建两个 release（policy 不同）
2. activate release A，发起 5 次 npc/chat，trace 都写 release_id=A
3. activate release B，发起 5 次 npc/chat，trace 写 release_id=B
4. rollback，确认回到 A
5. metrics 按 release_id 对比
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime
from typing import Optional

# 配置
CORE_BACKEND_URL = "http://localhost:8000"
ORCHESTRATOR_URL = "http://localhost:8001"
TENANT_ID = "yantian"
SITE_ID = "yantian-main"
NPC_ID = "npc-laonong"
INTERNAL_API_KEY = "test-internal-key"

# 测试用 policy 配置
POLICY_A = {
    "evidence_gate_policy_version": "v1.0-strict",
    "prompts_active_map": {NPC_ID: "v1"},
    "retrieval_defaults": {"strategy": "hybrid", "top_k": 5},
}

POLICY_B = {
    "evidence_gate_policy_version": "v1.1-relaxed",
    "prompts_active_map": {NPC_ID: "v2"},
    "retrieval_defaults": {"strategy": "semantic", "top_k": 10},
}


def get_headers():
    return {
        "Content-Type": "application/json",
        "X-Tenant-ID": TENANT_ID,
        "X-Site-ID": SITE_ID,
        "X-Internal-API-Key": INTERNAL_API_KEY,
    }


async def create_release(name: str, payload: dict, description: str = "") -> dict:
    """创建 release"""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{CORE_BACKEND_URL}/api/v1/releases",
            headers=get_headers(),
            json={
                "tenant_id": TENANT_ID,
                "site_id": SITE_ID,
                "name": name,
                "description": description,
                "payload": payload,
            },
        )
        response.raise_for_status()
        return response.json()


async def activate_release(release_id: str) -> dict:
    """激活 release"""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{CORE_BACKEND_URL}/api/v1/releases/{release_id}/activate",
            headers=get_headers(),
        )
        response.raise_for_status()
        return response.json()


async def rollback_release(release_id: str) -> dict:
    """回滚到指定 release"""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{CORE_BACKEND_URL}/api/v1/releases/{release_id}/rollback",
            headers=get_headers(),
        )
        response.raise_for_status()
        return response.json()


async def get_active_release() -> Optional[dict]:
    """获取当前 active release"""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{CORE_BACKEND_URL}/api/v1/releases/active",
            params={"tenant_id": TENANT_ID, "site_id": SITE_ID},
            headers=get_headers(),
        )
        if response.status_code == 200:
            return response.json()
        return None


async def send_chat(query: str) -> dict:
    """发送 npc/chat 请求"""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{ORCHESTRATOR_URL}/api/v1/npc/chat",
            headers=get_headers(),
            json={
                "tenant_id": TENANT_ID,
                "site_id": SITE_ID,
                "npc_id": NPC_ID,
                "query": query,
            },
        )
        response.raise_for_status()
        return response.json()


async def get_traces_by_release(release_id: str) -> list:
    """按 release_id 获取 traces"""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{CORE_BACKEND_URL}/api/v1/trace",
            params={"release_id": release_id, "limit": 100},
            headers=get_headers(),
        )
        response.raise_for_status()
        return response.json()


async def run_test():
    """运行测试"""
    print("=" * 60)
    print("P27 Release Gate 验收测试")
    print("=" * 60)
    
    # Step 1: 创建两个 release
    print("\n[Step 1] 创建两个 release...")
    
    release_a = await create_release(
        name="Release A - Strict Mode",
        payload=POLICY_A,
        description="严格模式策略包",
    )
    print(f"  ✓ Release A 创建成功: {release_a['id']}")
    
    release_b = await create_release(
        name="Release B - Relaxed Mode",
        payload=POLICY_B,
        description="宽松模式策略包",
    )
    print(f"  ✓ Release B 创建成功: {release_b['id']}")
    
    # Step 2: 激活 Release A，发送 5 次 chat
    print("\n[Step 2] 激活 Release A，发送 5 次 chat...")
    
    await activate_release(release_a["id"])
    active = await get_active_release()
    assert active and active["id"] == release_a["id"], "Release A 激活失败"
    print(f"  ✓ Release A 已激活: {active['name']}")
    
    queries_a = [
        "你好，请介绍一下自己",
        "这里有什么好玩的地方？",
        "农耕文化是什么？",
        "你知道二十四节气吗？",
        "给我讲个故事吧",
    ]
    
    for i, query in enumerate(queries_a, 1):
        try:
            result = await send_chat(query)
            print(f"  ✓ Chat {i}/5 完成 (trace_id: {result.get('trace_id', 'N/A')[:8]}...)")
        except Exception as e:
            print(f"  ✗ Chat {i}/5 失败: {e}")
    
    # Step 3: 激活 Release B，发送 5 次 chat
    print("\n[Step 3] 激活 Release B，发送 5 次 chat...")
    
    await activate_release(release_b["id"])
    active = await get_active_release()
    assert active and active["id"] == release_b["id"], "Release B 激活失败"
    print(f"  ✓ Release B 已激活: {active['name']}")
    
    queries_b = [
        "今天天气怎么样？",
        "有什么特色美食？",
        "这里的历史有多久？",
        "你最喜欢什么季节？",
        "谢谢你的介绍",
    ]
    
    for i, query in enumerate(queries_b, 1):
        try:
            result = await send_chat(query)
            print(f"  ✓ Chat {i}/5 完成 (trace_id: {result.get('trace_id', 'N/A')[:8]}...)")
        except Exception as e:
            print(f"  ✗ Chat {i}/5 失败: {e}")
    
    # Step 4: 回滚到 Release A
    print("\n[Step 4] 回滚到 Release A...")
    
    await rollback_release(release_a["id"])
    active = await get_active_release()
    assert active and active["id"] == release_a["id"], "回滚失败"
    print(f"  ✓ 已回滚到: {active['name']}")
    
    # Step 5: 按 release_id 统计 traces
    print("\n[Step 5] 按 release_id 统计 traces...")
    
    traces_a = await get_traces_by_release(release_a["id"])
    traces_b = await get_traces_by_release(release_b["id"])
    
    print(f"  Release A traces: {len(traces_a)}")
    print(f"  Release B traces: {len(traces_b)}")
    
    # 输出示例 JSON
    print("\n" + "=" * 60)
    print("示例 JSON")
    print("=" * 60)
    
    print("\n[Release Payload 示例]")
    print(json.dumps(release_a["payload"], indent=2, ensure_ascii=False))
    
    if traces_a:
        print("\n[Trace 示例]")
        trace_sample = {
            "trace_id": traces_a[0].get("trace_id"),
            "release_id": traces_a[0].get("release_id"),
            "policy_mode": traces_a[0].get("policy_mode"),
            "status": traces_a[0].get("status"),
            "created_at": traces_a[0].get("created_at"),
        }
        print(json.dumps(trace_sample, indent=2, ensure_ascii=False))
    
    print("\n[Metrics 对比]")
    metrics = {
        "release_a": {
            "id": release_a["id"],
            "name": release_a["name"],
            "trace_count": len(traces_a),
            "success_rate": sum(1 for t in traces_a if t.get("status") == "success") / max(len(traces_a), 1),
        },
        "release_b": {
            "id": release_b["id"],
            "name": release_b["name"],
            "trace_count": len(traces_b),
            "success_rate": sum(1 for t in traces_b if t.get("status") == "success") / max(len(traces_b), 1),
        },
    }
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 60)
    print("✓ 验收测试完成")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(run_test())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
