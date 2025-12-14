#!/usr/bin/env python3
"""
RBAC 权限冒烟测试脚本

测试三种角色（admin/operator/viewer）对关键端点的访问权限

用法：
    # 确保 core-backend 已启动
    python scripts/rbac_smoke_test.py
    
    # 指定 API 地址
    python scripts/rbac_smoke_test.py --api-url http://localhost:8000
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

import httpx

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class TestUser:
    """测试用户"""
    username: str
    password: str
    role: str
    token: Optional[str] = None


@dataclass
class TestResult:
    """测试结果"""
    endpoint: str
    method: str
    role: str
    expected_status: int
    actual_status: int
    passed: bool
    detail: str = ""


class RBACTester:
    """RBAC 权限测试器"""
    
    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self.results: list[TestResult] = []
        
        # 测试用户（需要先创建）
        self.users = {
            "admin": TestUser("test_admin", "admin123", "super_admin"),
            "operator": TestUser("test_operator", "operator123", "operator"),
            "viewer": TestUser("test_viewer", "viewer123", "viewer"),
        }
    
    async def setup_users(self):
        """创建测试用户（通过数据库）"""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        
        from app.core.config import settings
        from app.core.security import get_password_hash
        from app.database.models.user import User
        
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            for key, user in self.users.items():
                # 检查用户是否已存在
                result = await session.execute(
                    select(User).where(User.username == user.username)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    print(f"  用户 {user.username} 已存在")
                    continue
                
                # 创建用户
                new_user = User(
                    username=user.username,
                    hashed_password=get_password_hash(user.password),
                    role=user.role,
                    display_name=f"Test {user.role}",
                    is_active=True,
                    is_verified=True,
                    status="active",
                )
                session.add(new_user)
                print(f"  创建用户 {user.username} (role={user.role})")
            
            await session.commit()
        
        await engine.dispose()
    
    async def login_users(self):
        """登录所有测试用户获取 token"""
        for key, user in self.users.items():
            try:
                resp = await self.client.post(
                    f"{self.api_url}/api/v1/auth/login",
                    json={"username": user.username, "password": user.password},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    user.token = data["access_token"]
                    print(f"  {user.username} 登录成功")
                else:
                    print(f"  {user.username} 登录失败: {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"  {user.username} 登录异常: {e}")
    
    def get_headers(self, role: str) -> dict:
        """获取指定角色的请求头"""
        user = self.users.get(role)
        if user and user.token:
            return {"Authorization": f"Bearer {user.token}"}
        return {}
    
    async def test_endpoint(
        self,
        method: str,
        path: str,
        role: str,
        expected_status: int,
        json_data: dict = None,
        params: dict = None,
    ) -> TestResult:
        """测试单个端点"""
        url = f"{self.api_url}{path}"
        headers = self.get_headers(role)
        
        try:
            if method == "GET":
                resp = await self.client.get(url, headers=headers, params=params)
            elif method == "POST":
                resp = await self.client.post(url, headers=headers, json=json_data or {})
            elif method == "DELETE":
                resp = await self.client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            passed = resp.status_code == expected_status
            detail = ""
            if not passed:
                try:
                    detail = resp.json().get("detail", resp.text[:100])
                except:
                    detail = resp.text[:100]
            
            result = TestResult(
                endpoint=path,
                method=method,
                role=role,
                expected_status=expected_status,
                actual_status=resp.status_code,
                passed=passed,
                detail=detail,
            )
        except Exception as e:
            result = TestResult(
                endpoint=path,
                method=method,
                role=role,
                expected_status=expected_status,
                actual_status=0,
                passed=False,
                detail=str(e),
            )
        
        self.results.append(result)
        return result
    
    async def run_tests(self):
        """运行所有测试"""
        print("\n" + "=" * 60)
        print("RBAC 权限测试")
        print("=" * 60)
        
        # 测试用例定义
        # (method, path, role, expected_status, json_data, params)
        test_cases = [
            # ============================================================
            # Releases API
            # ============================================================
            # viewer 只能读取
            ("GET", "/api/v1/releases", "viewer", 200, None, {"tenant_id": "yantian", "site_id": "yantian-main"}),
            ("GET", "/api/v1/releases/active", "viewer", 200, None, {"tenant_id": "yantian", "site_id": "yantian-main"}),
            
            # viewer 不能创建/激活/回滚
            ("POST", "/api/v1/releases", "viewer", 403, {
                "tenant_id": "yantian",
                "site_id": "yantian-main",
                "name": "test-release",
                "payload": {}
            }, None),
            ("POST", "/api/v1/releases/test-id/activate", "viewer", 403, None, None),
            ("POST", "/api/v1/releases/test-id/rollback", "viewer", 403, None, None),
            
            # operator 也不能创建/激活/回滚 releases（仅 admin）
            ("POST", "/api/v1/releases", "operator", 403, {
                "tenant_id": "yantian",
                "site_id": "yantian-main",
                "name": "test-release",
                "payload": {}
            }, None),
            ("POST", "/api/v1/releases/test-id/activate", "operator", 403, None, None),
            
            # admin 可以创建（会返回 400 因为 payload 不完整，但不是 403）
            ("POST", "/api/v1/releases", "admin", 400, {
                "tenant_id": "yantian",
                "site_id": "yantian-main",
                "name": "test-release",
                "payload": {}
            }, None),
            
            # ============================================================
            # Policies API
            # ============================================================
            # viewer 可以读取
            ("GET", "/api/v1/policies/evidence-gate/active", "viewer", 200, None, None),
            ("GET", "/api/v1/policies/evidence-gate/versions", "viewer", 200, None, None),
            
            # viewer 不能创建/回滚
            ("POST", "/api/v1/policies/evidence-gate", "viewer", 403, {
                "version": "test-v1",
                "description": "test",
                "default_policy": {"min_citations": 1}
            }, None),
            ("POST", "/api/v1/policies/evidence-gate/rollback/v1.0", "viewer", 403, None, None),
            
            # operator 也不能创建/回滚 policies（仅 admin）
            ("POST", "/api/v1/policies/evidence-gate", "operator", 403, {
                "version": "test-v1",
                "description": "test",
                "default_policy": {"min_citations": 1}
            }, None),
            
            # admin 可以创建
            ("POST", "/api/v1/policies/evidence-gate", "admin", 200, {
                "version": f"test-v{datetime.now().timestamp()}",
                "description": "RBAC test policy",
                "default_policy": {"min_citations": 1, "min_score": 0.3}
            }, None),
            
            # ============================================================
            # Feedback API
            # ============================================================
            # viewer 可以读取
            ("GET", "/api/v1/feedback", "viewer", 200, None, None),
            ("GET", "/api/v1/feedback/stats", "viewer", 200, None, None),
            
            # viewer 不能 triage/status
            ("POST", "/api/v1/feedback/test-id/triage", "viewer", 403, {}, None),
            ("POST", "/api/v1/feedback/test-id/status", "viewer", 403, {"status": "triaged"}, None),
            
            # operator 可以 triage（会返回 404 因为 feedback 不存在，但不是 403）
            ("POST", "/api/v1/feedback/nonexistent-id/triage", "operator", 404, {}, None),
            ("POST", "/api/v1/feedback/nonexistent-id/status", "operator", 404, {"status": "triaged"}, None),
            
            # ============================================================
            # Alerts API
            # ============================================================
            # viewer 可以读取
            ("GET", "/api/v1/alerts/rules", "viewer", 200, None, None),
            ("GET", "/api/v1/alerts/events", "viewer", 200, None, None),
            ("GET", "/api/v1/alerts/silences", "viewer", 200, None, None),
            
            # viewer 不能创建/删除静默
            ("POST", "/api/v1/alerts/silences", "viewer", 403, {
                "tenant_id": "yantian",
                "duration_minutes": 60,
                "reason": "test"
            }, None),
            ("DELETE", "/api/v1/alerts/silences/test-id", "viewer", 403, None, None),
            
            # operator 可以创建静默
            ("POST", "/api/v1/alerts/silences", "operator", 200, {
                "tenant_id": "yantian",
                "duration_minutes": 60,
                "reason": "RBAC test silence"
            }, None),
        ]
        
        # 执行测试
        for case in test_cases:
            method, path, role, expected, json_data, params = case
            result = await self.test_endpoint(method, path, role, expected, json_data, params)
            
            status_icon = "✓" if result.passed else "✗"
            print(f"  {status_icon} [{role:8}] {method:6} {path[:40]:40} "
                  f"expected={expected} actual={result.actual_status}")
            if not result.passed and result.detail:
                print(f"           └─ {result.detail[:60]}")
    
    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 60)
        print("测试摘要")
        print("=" * 60)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        
        print(f"总计: {total} | 通过: {passed} | 失败: {failed}")
        print(f"通过率: {passed/total*100:.1f}%")
        
        if failed > 0:
            print("\n失败的测试:")
            for r in self.results:
                if not r.passed:
                    print(f"  - [{r.role}] {r.method} {r.endpoint}")
                    print(f"    期望: {r.expected_status}, 实际: {r.actual_status}")
                    if r.detail:
                        print(f"    详情: {r.detail[:80]}")
        
        # 按角色统计
        print("\n按角色统计:")
        for role in ["admin", "operator", "viewer"]:
            role_results = [r for r in self.results if r.role == role]
            role_passed = sum(1 for r in role_results if r.passed)
            print(f"  {role:10}: {role_passed}/{len(role_results)} 通过")
        
        return failed == 0
    
    async def cleanup(self):
        """清理资源"""
        await self.client.aclose()


async def main():
    parser = argparse.ArgumentParser(description="RBAC 权限冒烟测试")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API 服务地址 (默认: http://localhost:8000)",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="跳过用户创建步骤",
    )
    args = parser.parse_args()
    
    tester = RBACTester(args.api_url)
    
    try:
        # 1. 创建测试用户
        if not args.skip_setup:
            print("\n1. 创建测试用户...")
            await tester.setup_users()
        
        # 2. 登录获取 token
        print("\n2. 登录测试用户...")
        await tester.login_users()
        
        # 检查是否所有用户都登录成功
        all_logged_in = all(u.token for u in tester.users.values())
        if not all_logged_in:
            print("\n警告: 部分用户登录失败，测试可能不完整")
        
        # 3. 运行测试
        print("\n3. 运行权限测试...")
        await tester.run_tests()
        
        # 4. 打印摘要
        success = tester.print_summary()
        
        return 0 if success else 1
        
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
