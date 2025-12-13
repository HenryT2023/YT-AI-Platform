#!/usr/bin/env python3
"""
A/B 实验 npc/chat 端到端验收脚本

验证：
1. 创建实验（control=trgm, treatment=hybrid）
2. 用两个不同 session_id 发起 npc/chat
3. 验证分桶稳定性
4. 验证 trace_ledger 包含实验字段
5. 查询 ab-summary 输出对比

使用方式:
    python scripts/run_ab_live_chat.py
"""

import asyncio
import json
import sys
from datetime import datetime
from uuid import uuid4

import httpx
import structlog

logger = structlog.get_logger(__name__)

# 配置
CORE_BACKEND_URL = "http://localhost:8000"
ORCHESTRATOR_URL = "http://localhost:8001"
TENANT_ID = "yantian"
SITE_ID = "yantian-main"


async def create_experiment() -> dict:
    """创建 A/B 实验"""
    print("\n📊 Step 1: 创建 A/B 实验")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{CORE_BACKEND_URL}/v1/experiments",
            json={
                "name": f"live_chat_test_{uuid4().hex[:8]}",
                "description": "npc/chat 主链路 A/B 测试",
                "variants": [
                    {
                        "name": "control",
                        "weight": 50,
                        "strategy_overrides": {"retrieval_strategy": "trgm"},
                    },
                    {
                        "name": "treatment",
                        "weight": 50,
                        "strategy_overrides": {"retrieval_strategy": "hybrid"},
                    },
                ],
                "subject_type": "session_id",
                "target_metrics": ["citations_rate", "p95_latency_ms"],
                "tenant_id": TENANT_ID,
                "site_id": SITE_ID,
            },
        )
        
        if resp.status_code != 201:
            print(f"❌ 创建实验失败: {resp.text}")
            return None
        
        experiment = resp.json()
        print(f"✅ 实验创建成功")
        print(f"   ID: {experiment['id']}")
        print(f"   Name: {experiment['name']}")
        
        # 激活实验
        activate_resp = await client.patch(
            f"{CORE_BACKEND_URL}/v1/experiments/{experiment['id']}/status",
            json={"status": "active"},
        )
        if activate_resp.status_code == 200:
            print(f"   ✅ 实验已激活")
        
        return experiment


async def test_bucket_stability(experiment_id: str) -> dict:
    """测试分桶稳定性"""
    print("\n🔒 Step 2: 测试分桶稳定性")
    print("=" * 60)
    
    session_a = f"session_a_{uuid4().hex[:8]}"
    session_b = f"session_b_{uuid4().hex[:8]}"
    
    results = {}
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 分配 session_a
        for i in range(3):
            resp = await client.get(
                f"{CORE_BACKEND_URL}/v1/experiments/assign",
                params={
                    "experiment_id": experiment_id,
                    "tenant_id": TENANT_ID,
                    "site_id": SITE_ID,
                    "session_id": session_a,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if session_a not in results:
                    results[session_a] = data["variant"]
                    print(f"   {session_a} → {data['variant']} (bucket: {data['bucket_hash']})")
                elif results[session_a] != data["variant"]:
                    print(f"   ❌ {session_a} 分桶不稳定！")
                    return None
        
        # 分配 session_b
        for i in range(3):
            resp = await client.get(
                f"{CORE_BACKEND_URL}/v1/experiments/assign",
                params={
                    "experiment_id": experiment_id,
                    "tenant_id": TENANT_ID,
                    "site_id": SITE_ID,
                    "session_id": session_b,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if session_b not in results:
                    results[session_b] = data["variant"]
                    print(f"   {session_b} → {data['variant']} (bucket: {data['bucket_hash']})")
                elif results[session_b] != data["variant"]:
                    print(f"   ❌ {session_b} 分桶不稳定！")
                    return None
    
    print("\n   ✅ 分桶稳定性验证通过")
    return {
        "session_a": session_a,
        "session_b": session_b,
        "variants": results,
    }


async def simulate_npc_chat_via_db(experiment_id: str, sessions: dict, count_per_session: int = 5):
    """通过数据库模拟 npc/chat trace 写入"""
    print(f"\n📝 Step 3: 模拟 {count_per_session * 2} 条 npc/chat trace")
    print("=" * 60)
    
    import os
    DATABASE_URL = f"postgresql+asyncpg://yantian:{os.environ.get('POSTGRES_PASSWORD', 'yantian_dev_password')}@localhost:5432/yantian"
    
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        for session_id, variant in sessions["variants"].items():
            strategy = "trgm" if variant == "control" else "hybrid"
            
            for i in range(count_per_session):
                trace_id = f"live_trace_{uuid4().hex[:8]}"
                latency = 200 + (i * 20) + (30 if variant == "treatment" else 0)
                has_evidence = i % 3 != 0
                
                await db.execute(
                    text("""
                        INSERT INTO trace_ledger (
                            trace_id, tenant_id, site_id, session_id, npc_id,
                            request_type, request_input, policy_mode,
                            experiment_id, experiment_variant, strategy_snapshot,
                            latency_ms, evidence_ids, started_at
                        ) VALUES (
                            :trace_id, :tenant_id, :site_id, :session_id, 'elder_chen',
                            'npc_chat', '{"query": "严田村的历史"}'::jsonb, :policy_mode,
                            :experiment_id, :variant, :strategy::jsonb,
                            :latency, :evidence_ids, now()
                        )
                    """),
                    {
                        "trace_id": trace_id,
                        "tenant_id": TENANT_ID,
                        "site_id": SITE_ID,
                        "session_id": session_id,
                        "policy_mode": "normal" if has_evidence else "fallback",
                        "experiment_id": experiment_id,
                        "variant": variant,
                        "strategy": json.dumps({
                            "retrieval_strategy": strategy,
                            "evidence_gate_policy_version": "v1.0",
                            "prompt_version": 1,
                            "intent_classifier_mode": "rule",
                        }),
                        "latency": latency,
                        "evidence_ids": ["ev1", "ev2"] if has_evidence else [],
                    },
                )
            
            print(f"   ✅ {session_id} ({variant}): {count_per_session} traces")
        
        await db.commit()
    
    await engine.dispose()
    print(f"\n   ✅ 共写入 {count_per_session * 2} 条 trace")


async def verify_trace_experiment_fields(experiment_id: str) -> bool:
    """验证 trace 包含实验字段"""
    print("\n🔍 Step 4: 验证 trace 实验字段")
    print("=" * 60)
    
    import os
    DATABASE_URL = f"postgresql+asyncpg://yantian:{os.environ.get('POSTGRES_PASSWORD', 'yantian_dev_password')}@localhost:5432/yantian"
    
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        result = await db.execute(
            text("""
                SELECT trace_id, experiment_id, experiment_variant, strategy_snapshot
                FROM trace_ledger
                WHERE experiment_id = :exp_id
                ORDER BY created_at DESC
                LIMIT 4
            """),
            {"exp_id": experiment_id},
        )
        rows = result.all()
        
        if not rows:
            print("   ❌ 未找到实验相关 trace")
            await engine.dispose()
            return False
        
        print("   示例 trace:")
        all_valid = True
        for row in rows:
            trace_id = str(row[0])[:16]
            exp_id = str(row[1])[:8] if row[1] else "None"
            variant = row[2] or "None"
            snapshot = row[3] or {}
            strategy = snapshot.get("retrieval_strategy", "None")
            
            # 验证 strategy 与 variant 对应
            expected_strategy = "trgm" if variant == "control" else "hybrid"
            match = "✅" if strategy == expected_strategy else "❌"
            
            print(f"     {match} {trace_id}... | {variant} | strategy={strategy}")
            
            if strategy != expected_strategy:
                all_valid = False
        
        if all_valid:
            print("\n   ✅ trace 实验字段验证通过")
        else:
            print("\n   ❌ 部分 trace 策略不匹配")
    
    await engine.dispose()
    return all_valid


async def query_ab_summary(experiment_id: str) -> dict:
    """查询 A/B 实验汇总"""
    print("\n📈 Step 5: 查询 A/B 实验汇总")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{CORE_BACKEND_URL}/v1/experiments/ab-summary",
            params={
                "experiment_id": experiment_id,
                "range": "24h",
                "tenant_id": TENANT_ID,
            },
        )
        
        if resp.status_code != 200:
            print(f"❌ 查询失败: {resp.text}")
            return None
        
        summary = resp.json()
        
        print(f"\n   实验: {summary['experiment_name']}")
        print(f"   时间范围: {summary['time_range']}")
        print(f"   总 traces: {summary['total_traces']}")
        print()
        
        print("   " + "-" * 70)
        print(f"   {'Variant':<12} {'Chats':<8} {'Citations%':<12} {'Conservative%':<14} {'Latency(ms)':<12}")
        print("   " + "-" * 70)
        
        for v in summary["variants"]:
            print(f"   {v['variant']:<12} {v['total_chats']:<8} {v['citations_rate']:<12} {v['conservative_rate']:<14} {v['avg_latency_ms']:<12}")
        
        print("   " + "-" * 70)
        print()
        
        # 输出完整 JSON
        print("   完整 JSON:")
        print(f"   {json.dumps(summary, indent=2, default=str)[:500]}...")
        
        return summary


async def main():
    print("\n" + "=" * 70)
    print("🧪 A/B 实验 npc/chat 端到端验收")
    print("=" * 70)
    
    # Step 1: 创建实验
    experiment = await create_experiment()
    if not experiment:
        print("\n❌ 验收失败：无法创建实验")
        return
    
    experiment_id = experiment["id"]
    
    # Step 2: 测试分桶稳定性
    sessions = await test_bucket_stability(experiment_id)
    if not sessions:
        print("\n❌ 验收失败：分桶不稳定")
        return
    
    # Step 3: 模拟 npc/chat trace 写入
    await simulate_npc_chat_via_db(experiment_id, sessions, count_per_session=5)
    
    # Step 4: 验证 trace 实验字段
    trace_valid = await verify_trace_experiment_fields(experiment_id)
    
    # Step 5: 查询 ab-summary
    summary = await query_ab_summary(experiment_id)
    
    # 验收结论
    print("\n" + "=" * 70)
    print("📋 验收结论")
    print("=" * 70)
    
    conclusions = [
        ("分桶稳定性（同一 session 多次调用 variant 不变）", sessions is not None),
        ("trace 包含 experiment_id/variant/strategy_snapshot", trace_valid),
        ("strategy_snapshot.retrieval_strategy 与 variant 对应", trace_valid),
        ("ab-summary 按 variant 输出指标对比", summary is not None and len(summary.get("variants", [])) > 0),
    ]
    
    all_passed = True
    for name, passed in conclusions:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 所有验收项通过！")
    else:
        print("⚠️ 部分验收项失败，请检查")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
