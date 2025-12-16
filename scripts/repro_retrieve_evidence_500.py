#!/usr/bin/env python3
"""
P0 复现脚本：retrieve_evidence 500 错误

用于验证修复前后的行为差异

使用方法：
    python scripts/repro_retrieve_evidence_500.py

覆盖场景：
    1. strategy=trgm（应该始终成功）
    2. strategy=qdrant（Qdrant 不可用时应 fallback）
    3. strategy=hybrid（Qdrant 不可用时应 fallback）
"""

import asyncio
import time
import httpx
import sys
from typing import Optional

# 配置
CORE_BACKEND_URL = "http://localhost:8000"
TENANT_ID = "yantian"
SITE_ID = "yantian-main"
INTERNAL_API_KEY = "your-internal-api-key-change-in-production"

# 测试查询
TEST_QUERY = "严田村历史"


async def call_retrieve_evidence(
    strategy: str,
    query: str = TEST_QUERY,
) -> dict:
    """调用 retrieve_evidence 工具"""
    url = f"{CORE_BACKEND_URL}/api/tools/call"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-API-Key": INTERNAL_API_KEY,
        "X-Tenant-ID": TENANT_ID,
        "X-Site-ID": SITE_ID,
        "X-Trace-ID": f"repro-{strategy}-{int(time.time())}",
    }
    payload = {
        "tool_name": "retrieve_evidence",
        "input": {
            "query": query,
            "strategy": strategy,
            "limit": 5,
            "min_score": 0.1,
        },
        "context": {
            "tenant_id": TENANT_ID,
            "site_id": SITE_ID,
            "trace_id": headers["X-Trace-ID"],
        },
    }

    start = time.time()
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "strategy": strategy,
                "status_code": resp.status_code,
                "elapsed_ms": elapsed_ms,
                "success": resp.status_code == 200,
                "body": resp.json() if resp.status_code == 200 else resp.text[:500],
                "trace_id": headers["X-Trace-ID"],
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "strategy": strategy,
                "status_code": 0,
                "elapsed_ms": elapsed_ms,
                "success": False,
                "body": str(e),
                "trace_id": headers["X-Trace-ID"],
            }


async def call_search_content(query: str = TEST_QUERY) -> dict:
    """调用 search_content 工具"""
    url = f"{CORE_BACKEND_URL}/api/tools/call"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-API-Key": INTERNAL_API_KEY,
        "X-Tenant-ID": TENANT_ID,
        "X-Site-ID": SITE_ID,
        "X-Trace-ID": f"repro-search-{int(time.time())}",
    }
    payload = {
        "tool_name": "search_content",
        "input": {
            "query": query,
            "limit": 5,
        },
        "context": {
            "tenant_id": TENANT_ID,
            "site_id": SITE_ID,
            "trace_id": headers["X-Trace-ID"],
        },
    }

    start = time.time()
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "tool": "search_content",
                "status_code": resp.status_code,
                "elapsed_ms": elapsed_ms,
                "success": resp.status_code == 200,
                "body": resp.json() if resp.status_code == 200 else resp.text[:500],
                "trace_id": headers["X-Trace-ID"],
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "tool": "search_content",
                "status_code": 0,
                "elapsed_ms": elapsed_ms,
                "success": False,
                "body": str(e),
                "trace_id": headers["X-Trace-ID"],
            }


def print_result(result: dict, label: str):
    """打印结果"""
    status = "✅ PASS" if result["success"] else "❌ FAIL"
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"Status: {status}")
    print(f"HTTP Code: {result['status_code']}")
    print(f"Elapsed: {result['elapsed_ms']}ms")
    print(f"Trace ID: {result.get('trace_id', 'N/A')}")
    
    if result["success"]:
        body = result["body"]
        if isinstance(body, dict):
            if body.get("success"):
                output = body.get("output", {})
                items = output.get("items", [])
                strategy_used = output.get("strategy_used", output.get("search_method", "unknown"))
                fallback_reason = output.get("fallback_reason", None)
                print(f"Strategy Used: {strategy_used}")
                if fallback_reason:
                    print(f"Fallback Reason: {fallback_reason}")
                print(f"Results: {len(items)} items")
            else:
                print(f"Tool Error: {body.get('error', 'unknown')}")
    else:
        print(f"Error: {result['body'][:200]}")


async def main():
    print("=" * 60)
    print("P0 复现脚本：retrieve_evidence / search_content 500 错误")
    print("=" * 60)
    print(f"Target: {CORE_BACKEND_URL}")
    print(f"Tenant: {TENANT_ID}, Site: {SITE_ID}")
    print(f"Query: {TEST_QUERY}")

    # 检查服务是否可用
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.get(f"{CORE_BACKEND_URL}/health")
            if resp.status_code != 200:
                print(f"\n❌ core-backend 不可用: {resp.status_code}")
                sys.exit(1)
            print(f"\n✅ core-backend 健康检查通过")
    except Exception as e:
        print(f"\n❌ core-backend 连接失败: {e}")
        sys.exit(1)

    # 测试 retrieve_evidence 各策略
    strategies = ["trgm", "qdrant", "hybrid"]
    results = []

    for strategy in strategies:
        result = await call_retrieve_evidence(strategy)
        results.append(result)
        print_result(result, f"retrieve_evidence (strategy={strategy})")

    # 测试 search_content
    search_result = await call_search_content()
    print_result(search_result, "search_content")

    # 汇总
    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    
    all_passed = all(r["success"] for r in results) and search_result["success"]
    
    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f"  {status} retrieve_evidence (strategy={r['strategy']}): {r['status_code']}")
    
    status = "✅" if search_result["success"] else "❌"
    print(f"  {status} search_content: {search_result['status_code']}")

    if all_passed:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print("\n⚠️  存在失败的测试，需要修复")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
