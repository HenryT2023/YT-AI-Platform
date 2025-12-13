#!/usr/bin/env python3
"""
A/B 实验端到端验收脚本

验证：
1. 创建实验（A=trgm, B=hybrid）
2. 分桶稳定性（同一 session 多次调用 variant 不变）
3. 模拟 trace 写入（带 experiment_id/variant）
4. 查询 ab-summary 输出对比

使用方式:
    python scripts/run_ab_e2e.py
"""

import asyncio
import hashlib
import json
import sys
from datetime import datetime
from uuid import uuid4

# 添加项目路径
sys.path.insert(0, "/Users/hal/YT-AI-Platform/services/core-backend")

import httpx
import structlog

logger = structlog.get_logger(__name__)

# 配置
API_BASE = "http://localhost:8000"
TENANT_ID = "yantian"
SITE_ID = "yantian-main"


async def create_experiment() -> dict:
    """创建 A/B 实验"""
    print("\n📊 Step 1: 创建 A/B 实验")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API_BASE}/v1/experiments",
            json={
                "name": "retrieval_strategy_test",
                "description": "对比 trgm vs hybrid 检索策略",
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
                "target_metrics": ["citations_rate", "p95_latency_ms", "correction_rate"],
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
        print(f"   Status: {experiment['status']}")
        
        # 激活实验
        activate_resp = await client.patch(
            f"{API_BASE}/v1/experiments/{experiment['id']}/status",
            json={"status": "active"},
        )
        if activate_resp.status_code == 200:
            print(f"   ✅ 实验已激活")
        
        return experiment


async def test_bucket_stability(experiment_id: str) -> bool:
    """测试分桶稳定性"""
    print("\n🔒 Step 2: 测试分桶稳定性")
    print("=" * 60)
    
    test_sessions = [f"session_{i}" for i in range(5)]
    results = {}
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 第一轮分配
        print("   第一轮分配:")
        for session_id in test_sessions:
            resp = await client.get(
                f"{API_BASE}/v1/experiments/assign",
                params={
                    "experiment_id": experiment_id,
                    "tenant_id": TENANT_ID,
                    "site_id": SITE_ID,
                    "session_id": session_id,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                results[session_id] = data["variant"]
                print(f"     {session_id} → {data['variant']} (bucket: {data['bucket_hash']})")
        
        # 第二轮验证稳定性
        print("\n   第二轮验证:")
        all_stable = True
        for session_id in test_sessions:
            resp = await client.get(
                f"{API_BASE}/v1/experiments/assign",
                params={
                    "experiment_id": experiment_id,
                    "tenant_id": TENANT_ID,
                    "site_id": SITE_ID,
                    "session_id": session_id,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                expected = results[session_id]
                actual = data["variant"]
                is_new = data["is_new_assignment"]
                
                if actual == expected and not is_new:
                    print(f"     ✅ {session_id} → {actual} (稳定)")
                else:
                    print(f"     ❌ {session_id} → {actual} (期望: {expected}, is_new: {is_new})")
                    all_stable = False
    
    if all_stable:
        print("\n   ✅ 分桶稳定性验证通过")
    else:
        print("\n   ❌ 分桶稳定性验证失败")
    
    return all_stable


async def simulate_traces(experiment_id: str, count: int = 20) -> dict:
    """模拟 trace 写入"""
    print(f"\n📝 Step 3: 模拟 {count} 条 trace 写入")
    print("=" * 60)
    
    import os
    DATABASE_URL = f"postgresql+asyncpg://yantian:{os.environ.get('POSTGRES_PASSWORD', 'yantian_dev_password')}@localhost:5432/yantian"
    
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    variant_counts = {"control": 0, "treatment": 0}
    
    async with httpx.AsyncClient(timeout=30) as client:
        async with async_session() as db:
            for i in range(count):
                session_id = f"e2e_session_{i}"
                trace_id = f"e2e_trace_{uuid4().hex[:8]}"
                
                # 获取分桶
                resp = await client.get(
                    f"{API_BASE}/v1/experiments/assign",
                    params={
                        "experiment_id": experiment_id,
                        "tenant_id": TENANT_ID,
                        "site_id": SITE_ID,
                        "session_id": session_id,
                    },
                )
                
                if resp.status_code != 200:
                    continue
                
                assignment = resp.json()
                variant = assignment["variant"]
                strategy = assignment["strategy_overrides"]
                variant_counts[variant] = variant_counts.get(variant, 0) + 1
                
                # 模拟 trace 写入
                latency = 200 + (i * 10) + (50 if variant == "treatment" else 0)
                has_evidence = i % 3 != 0  # 2/3 有证据
                
                await db.execute(
                    text("""
                        INSERT INTO trace_ledger (
                            trace_id, tenant_id, site_id, session_id,
                            request_type, request_input, policy_mode,
                            experiment_id, experiment_variant, strategy_snapshot,
                            latency_ms, evidence_ids, started_at
                        ) VALUES (
                            :trace_id, :tenant_id, :site_id, :session_id,
                            'chat', '{}', :policy_mode,
                            :experiment_id, :variant, :strategy,
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
                        "strategy": json.dumps(strategy),
                        "latency": latency,
                        "evidence_ids": ["ev1", "ev2"] if has_evidence else [],
                    },
                )
            
            await db.commit()
    
    await engine.dispose()
    
    print(f"   ✅ 写入完成")
    print(f"   control: {variant_counts.get('control', 0)} 条")
    print(f"   treatment: {variant_counts.get('treatment', 0)} 条")
    
    return variant_counts


async def query_ab_summary(experiment_id: str) -> dict:
    """查询 A/B 实验汇总"""
    print("\n📈 Step 4: 查询 A/B 实验汇总")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API_BASE}/v1/experiments/ab-summary",
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
        
        return summary


async def verify_trace_replay(experiment_id: str) -> bool:
    """验证 trace 回放包含实验字段"""
    print("\n🔍 Step 5: 验证 trace 回放")
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
                LIMIT 3
            """),
            {"exp_id": experiment_id},
        )
        rows = result.all()
        
        if not rows:
            print("   ❌ 未找到实验相关 trace")
            return False
        
        print("   示例 trace:")
        for row in rows:
            print(f"     trace_id: {row[0][:20]}...")
            print(f"     experiment_id: {row[1][:8]}...")
            print(f"     variant: {row[2]}")
            print(f"     strategy: {row[3]}")
            print()
        
        print("   ✅ trace 回放包含实验字段")
    
    await engine.dispose()
    return True


async def main():
    print("\n" + "=" * 70)
    print("🧪 A/B 实验端到端验收")
    print("=" * 70)
    
    # Step 1: 创建实验
    experiment = await create_experiment()
    if not experiment:
        print("\n❌ 验收失败：无法创建实验")
        return
    
    experiment_id = experiment["id"]
    
    # Step 2: 测试分桶稳定性
    bucket_stable = await test_bucket_stability(experiment_id)
    
    # Step 3: 模拟 trace 写入
    await simulate_traces(experiment_id, count=20)
    
    # Step 4: 查询 ab-summary
    summary = await query_ab_summary(experiment_id)
    
    # Step 5: 验证 trace 回放
    trace_valid = await verify_trace_replay(experiment_id)
    
    # 验收结论
    print("\n" + "=" * 70)
    print("📋 验收结论")
    print("=" * 70)
    
    conclusions = [
        ("分桶稳定性", bucket_stable),
        ("trace 包含实验字段", trace_valid),
        ("ab-summary 输出", summary is not None and len(summary.get("variants", [])) > 0),
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
