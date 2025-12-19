#!/usr/bin/env python3
"""
Quest Submit Smoke Test (v0.2.1)

验收脚本：测试 quest_id 校验、Redis 防刷、时间格式

Usage:
    cd services/core-backend
    python scripts/quest_submit_smoke.py

Prerequisites:
    - core-backend 运行在 localhost:8000
    - Redis 运行
    - 数据库中有 seed 数据（或脚本会尝试创建）
"""

import asyncio
import httpx
import sys
from datetime import datetime
from typing import Optional

# ============================================================
# 配置
# ============================================================

BASE_URL = "http://localhost:8000/api/v1"
TENANT_ID = "yantian"
SITE_ID = "yantian-main"

# 测试用 session_id（每次运行生成新的）
TEST_SESSION_ID = f"smoke_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# 颜色输出
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def log_pass(msg: str):
    print(f"{GREEN}✓ PASS{RESET}: {msg}")


def log_fail(msg: str):
    print(f"{RED}✗ FAIL{RESET}: {msg}")


def log_info(msg: str):
    print(f"{YELLOW}ℹ INFO{RESET}: {msg}")


# ============================================================
# 测试用例
# ============================================================

async def get_valid_quest_id(client: httpx.AsyncClient) -> Optional[str]:
    """获取一个有效的 quest_id"""
    url = f"{BASE_URL}/public/quests?tenant_id={TENANT_ID}&site_id={SITE_ID}"
    resp = await client.get(url)
    
    if resp.status_code != 200:
        log_info(f"获取 Quest 列表失败: {resp.status_code}")
        return None
    
    quests = resp.json()
    if not quests:
        log_info("没有可用的 Quest，请先 seed 数据")
        return None
    
    quest_id = quests[0].get("quest_id")
    log_info(f"使用 quest_id: {quest_id}")
    return quest_id


async def test_submit_valid_quest(client: httpx.AsyncClient, quest_id: str) -> bool:
    """测试 1: 提交有效 quest_id → 200"""
    url = f"{BASE_URL}/public/quests/{quest_id}/submit"
    payload = {
        "tenant_id": TENANT_ID,
        "site_id": SITE_ID,
        "session_id": TEST_SESSION_ID,
        "proof_type": "text",
        "proof_payload": {"answer": "smoke test answer"},
    }
    
    resp = await client.post(url, json=payload)
    
    if resp.status_code == 200:
        data = resp.json()
        log_pass(f"提交有效 quest_id → 200")
        log_info(f"  submission_id: {data.get('submission_id')}")
        log_info(f"  status: {data.get('status')}")
        log_info(f"  created_at: {data.get('created_at')}")
        
        # 验证时间格式
        created_at = data.get("created_at")
        if created_at and ("+" in created_at or "Z" in created_at):
            log_pass("时间格式包含时区信息 (ISO 8601)")
        else:
            log_fail(f"时间格式缺少时区信息: {created_at}")
            return False
        
        return True
    else:
        log_fail(f"提交有效 quest_id 失败: {resp.status_code} - {resp.text}")
        return False


async def test_submit_invalid_quest(client: httpx.AsyncClient) -> bool:
    """测试 2: 提交无效 quest_id → 400"""
    invalid_quest_id = "non_existent_quest_12345"
    url = f"{BASE_URL}/public/quests/{invalid_quest_id}/submit"
    payload = {
        "tenant_id": TENANT_ID,
        "site_id": SITE_ID,
        "session_id": TEST_SESSION_ID,
        "proof_type": "text",
        "proof_payload": {"answer": "test"},
    }
    
    resp = await client.post(url, json=payload)
    
    if resp.status_code == 400:
        detail = resp.json().get("detail", "")
        log_pass(f"提交无效 quest_id → 400")
        log_info(f"  detail: {detail}")
        return True
    else:
        log_fail(f"提交无效 quest_id 应返回 400，实际: {resp.status_code} - {resp.text}")
        return False


async def test_rate_limit(client: httpx.AsyncClient, quest_id: str) -> bool:
    """测试 3: 1 分钟内提交 4 次 → 第 4 次返回 429"""
    # 使用新的 session_id 避免与之前测试冲突
    rate_limit_session = f"rate_limit_test_{datetime.now().strftime('%H%M%S')}"
    
    url = f"{BASE_URL}/public/quests/{quest_id}/submit"
    
    log_info(f"测试 Rate Limit (session: {rate_limit_session})")
    
    for i in range(4):
        payload = {
            "tenant_id": TENANT_ID,
            "site_id": SITE_ID,
            "session_id": rate_limit_session,
            "proof_type": "text",
            "proof_payload": {"answer": f"rate limit test {i+1}"},
        }
        
        resp = await client.post(url, json=payload)
        
        if i < 3:
            # 前 3 次应该成功
            if resp.status_code == 200:
                log_info(f"  第 {i+1} 次提交: 200 OK")
            else:
                log_fail(f"  第 {i+1} 次提交失败: {resp.status_code}")
                return False
        else:
            # 第 4 次应该被限流
            if resp.status_code == 429:
                detail = resp.json().get("detail", "")
                retry_after = resp.headers.get("Retry-After", "N/A")
                log_pass(f"第 4 次提交 → 429 (Rate Limited)")
                log_info(f"  detail: {detail}")
                log_info(f"  Retry-After: {retry_after}")
                return True
            else:
                log_fail(f"第 4 次提交应返回 429，实际: {resp.status_code} - {resp.text}")
                return False
    
    return False


async def test_time_format(client: httpx.AsyncClient) -> bool:
    """测试 4: 验证返回时间格式正确 (ISO 8601 with timezone)"""
    url = f"{BASE_URL}/public/quests/progress?tenant_id={TENANT_ID}&site_id={SITE_ID}&session_id={TEST_SESSION_ID}"
    
    resp = await client.get(url)
    
    if resp.status_code != 200:
        log_fail(f"获取进度失败: {resp.status_code}")
        return False
    
    data = resp.json()
    submissions = data.get("submissions", [])
    
    if not submissions:
        log_info("没有提交记录，跳过时间格式验证")
        return True
    
    # 检查第一条记录的时间格式
    first_sub = submissions[0]
    created_at = first_sub.get("created_at", "")
    
    # ISO 8601 with timezone: 2024-01-01T12:00:00+00:00 或 2024-01-01T12:00:00Z
    if "+" in created_at or "Z" in created_at or "-" in created_at.split("T")[-1]:
        log_pass("进度 API 时间格式正确 (ISO 8601 with timezone)")
        log_info(f"  示例: {created_at}")
        return True
    else:
        log_fail(f"时间格式缺少时区信息: {created_at}")
        return False


# ============================================================
# 主函数
# ============================================================

async def main():
    print("=" * 60)
    print("Quest Submit Smoke Test (v0.2.1)")
    print("=" * 60)
    print()
    
    results = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 获取有效的 quest_id
        quest_id = await get_valid_quest_id(client)
        
        if not quest_id:
            print()
            log_fail("无法获取有效的 quest_id，请确保数据库中有 seed 数据")
            print()
            print("提示: 运行 seed 脚本创建测试数据")
            sys.exit(1)
        
        print()
        print("-" * 40)
        print("Test 1: 提交有效 quest_id")
        print("-" * 40)
        results.append(await test_submit_valid_quest(client, quest_id))
        
        print()
        print("-" * 40)
        print("Test 2: 提交无效 quest_id")
        print("-" * 40)
        results.append(await test_submit_invalid_quest(client))
        
        print()
        print("-" * 40)
        print("Test 3: Rate Limit (4 次提交)")
        print("-" * 40)
        results.append(await test_rate_limit(client, quest_id))
        
        print()
        print("-" * 40)
        print("Test 4: 时间格式验证")
        print("-" * 40)
        results.append(await test_time_format(client))
    
    # 汇总结果
    print()
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"{GREEN}全部通过: {passed}/{total}{RESET}")
        sys.exit(0)
    else:
        print(f"{RED}部分失败: {passed}/{total}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
