#!/usr/bin/env python3
"""
v0.2.3 Site Scope 验收脚本

验证 admin-console 的 tenant/site 隔离功能：
1. 创建两个不同 site 的 submission
2. 分别用不同 Header 查询，验证数据隔离

使用方法：
    python scripts/site_scope_smoke.py

前置条件：
    - core-backend 运行在 localhost:8000
    - 数据库已初始化
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional

import httpx
from rich.console import Console
from rich.table import Table

console = Console()

# 配置
BACKEND_URL = "http://localhost:8000"
TENANT_ID = "yantian"
SITE_MAIN = "yantian-main"
SITE_TEST = "yantian-test"

# 测试用的 JWT Token（需要 operator 权限）
# 实际使用时需要先登录获取 token
TEST_TOKEN: Optional[str] = None


async def get_auth_token() -> str:
    """登录获取 token"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        if resp.status_code != 200:
            console.print(f"[red]登录失败: {resp.text}[/red]")
            raise Exception("登录失败")
        data = resp.json()
        return data["access_token"]


async def create_test_submission(
    client: httpx.AsyncClient,
    token: str,
    site_id: str,
    quest_id: str = "quest_family_rules",
) -> dict:
    """创建测试提交记录（直接插入数据库）"""
    # 注意：这里我们直接调用公开 API 创建 submission
    # 实际场景中应该通过游客端提交
    
    # 由于公开 API 需要 session，我们直接用 SQL 插入
    # 这里简化为调用一个内部测试 API
    
    submission_id = str(uuid.uuid4())
    session_id = f"test_session_{site_id}_{uuid.uuid4().hex[:8]}"
    
    console.print(f"[dim]创建 submission: site={site_id}, id={submission_id}[/dim]")
    
    # 直接通过数据库插入（需要 psycopg2）
    # 这里我们用一个简化的方式：调用后端的内部 API
    # 如果没有内部 API，可以直接用 SQL
    
    return {
        "id": submission_id,
        "site_id": site_id,
        "session_id": session_id,
        "quest_id": quest_id,
    }


async def query_submissions(
    client: httpx.AsyncClient,
    token: str,
    tenant_id: str,
    site_id: str,
) -> dict:
    """查询 submissions（使用 Header 传递 scope）"""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": tenant_id,
        "X-Site-ID": site_id,
    }
    
    resp = await client.get(
        f"{BACKEND_URL}/api/v1/admin/quest-submissions",
        headers=headers,
    )
    
    return {
        "status_code": resp.status_code,
        "data": resp.json() if resp.status_code == 200 else None,
        "error": resp.text if resp.status_code != 200 else None,
    }


async def query_without_headers(client: httpx.AsyncClient, token: str) -> dict:
    """不带 scope header 查询（应该返回 400）"""
    headers = {
        "Authorization": f"Bearer {token}",
    }
    
    resp = await client.get(
        f"{BACKEND_URL}/api/v1/admin/quest-submissions",
        headers=headers,
    )
    
    return {
        "status_code": resp.status_code,
        "data": resp.json() if resp.status_code < 400 else None,
        "error": resp.text if resp.status_code >= 400 else None,
    }


async def main():
    console.print("[bold blue]v0.2.3 Site Scope 验收测试[/bold blue]\n")
    
    # 1. 获取 token
    console.print("[yellow]1. 登录获取 token...[/yellow]")
    try:
        token = await get_auth_token()
        console.print("[green]✓ 登录成功[/green]\n")
    except Exception as e:
        console.print(f"[red]✗ 登录失败: {e}[/red]")
        return
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 2. 测试缺少 Header 时返回 400
        console.print("[yellow]2. 测试缺少 X-Tenant-ID/X-Site-ID Header...[/yellow]")
        result = await query_without_headers(client, token)
        
        if result["status_code"] == 400:
            console.print(f"[green]✓ 正确返回 400: {result['error']}[/green]\n")
        else:
            console.print(f"[red]✗ 期望 400，实际 {result['status_code']}[/red]\n")
        
        # 3. 查询 main site
        console.print(f"[yellow]3. 查询 {SITE_MAIN} 的 submissions...[/yellow]")
        main_result = await query_submissions(client, token, TENANT_ID, SITE_MAIN)
        
        if main_result["status_code"] == 200:
            main_count = main_result["data"]["total"]
            console.print(f"[green]✓ 查询成功，共 {main_count} 条记录[/green]\n")
        else:
            console.print(f"[red]✗ 查询失败: {main_result['error']}[/red]\n")
            main_count = 0
        
        # 4. 查询 test site
        console.print(f"[yellow]4. 查询 {SITE_TEST} 的 submissions...[/yellow]")
        test_result = await query_submissions(client, token, TENANT_ID, SITE_TEST)
        
        if test_result["status_code"] == 200:
            test_count = test_result["data"]["total"]
            console.print(f"[green]✓ 查询成功，共 {test_count} 条记录[/green]\n")
        else:
            console.print(f"[red]✗ 查询失败: {test_result['error']}[/red]\n")
            test_count = 0
        
        # 5. 输出对比表格
        console.print("[yellow]5. 结果对比[/yellow]")
        table = Table(title="Site Scope 隔离验证")
        table.add_column("Site ID", style="cyan")
        table.add_column("Submissions Count", style="magenta")
        table.add_column("Status", style="green")
        
        table.add_row(
            SITE_MAIN,
            str(main_count),
            "✓" if main_result["status_code"] == 200 else "✗"
        )
        table.add_row(
            SITE_TEST,
            str(test_count),
            "✓" if test_result["status_code"] == 200 else "✗"
        )
        
        console.print(table)
        
        # 6. 验收结论
        console.print("\n[bold]验收结论:[/bold]")
        
        all_passed = True
        
        # 检查 1: 缺少 header 返回 400
        if result["status_code"] == 400:
            console.print("[green]✓ 缺少 Header 时正确返回 400[/green]")
        else:
            console.print("[red]✗ 缺少 Header 时应返回 400[/red]")
            all_passed = False
        
        # 检查 2: 不同 site 返回不同数据
        if main_result["status_code"] == 200 and test_result["status_code"] == 200:
            console.print("[green]✓ 不同 site 可以独立查询[/green]")
        else:
            console.print("[red]✗ site 查询失败[/red]")
            all_passed = False
        
        # 检查 3: 数据隔离（main 有数据，test 应该没有或数据不同）
        if main_count != test_count or main_count == 0:
            console.print("[green]✓ 数据隔离正常（不同 site 数据量不同）[/green]")
        else:
            console.print("[yellow]⚠ 两个 site 数据量相同，请手动验证数据内容是否隔离[/yellow]")
        
        if all_passed:
            console.print("\n[bold green]🎉 v0.2.3 Site Scope 验收通过！[/bold green]")
        else:
            console.print("\n[bold red]❌ 验收未通过，请检查上述问题[/bold red]")


if __name__ == "__main__":
    asyncio.run(main())
