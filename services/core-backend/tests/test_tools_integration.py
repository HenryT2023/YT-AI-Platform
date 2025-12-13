"""
工具服务集成测试

测试 /tools/list 和 /tools/call 接口
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.database.engine import async_session_maker
from app.database.models import TraceLedger, NPCProfile, Content


@pytest.fixture
def trace_id():
    """生成测试用 trace_id"""
    import uuid
    return f"test-trace-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def headers(trace_id):
    """请求头"""
    return {
        "X-Tenant-ID": "yantian",
        "X-Site-ID": "yantian-main",
        "X-Trace-ID": trace_id,
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_tools_list(headers):
    """测试获取工具列表"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/tools/list",
            json={"ai_callable_only": True},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()

    assert "tools" in data
    assert "total" in data
    assert data["total"] >= 6

    # 验证必需的工具存在
    tool_names = [t["name"] for t in data["tools"]]
    assert "get_npc_profile" in tool_names
    assert "search_content" in tool_names
    assert "get_site_map" in tool_names
    assert "create_draft_content" in tool_names
    assert "log_user_event" in tool_names
    assert "get_prompt_active" in tool_names


@pytest.mark.asyncio
async def test_tools_call_search_content(headers, trace_id):
    """测试调用 search_content 工具"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/tools/call",
            json={
                "tool_name": "search_content",
                "input": {
                    "query": "严氏",
                    "limit": 5,
                },
                "context": {
                    "tenant_id": "yantian",
                    "site_id": "yantian-main",
                    "trace_id": trace_id,
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "output" in data
    assert "audit" in data
    assert data["audit"]["status"] == "success"
    assert data["audit"]["trace_id"] == trace_id

    # 验证审计记录已写入
    async with async_session_maker() as session:
        stmt = select(TraceLedger).where(TraceLedger.trace_id == trace_id)
        result = await session.execute(stmt)
        trace = result.scalar_one_or_none()

        assert trace is not None
        assert trace.request_type == "tool_call"
        assert trace.status == "success"


@pytest.mark.asyncio
async def test_tools_call_get_npc_profile(headers, trace_id):
    """测试调用 get_npc_profile 工具"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/tools/call",
            json={
                "tool_name": "get_npc_profile",
                "input": {
                    "npc_id": "ancestor_yan",
                },
                "context": {
                    "tenant_id": "yantian",
                    "site_id": "yantian-main",
                    "trace_id": trace_id,
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()

    # 如果 NPC 存在则验证输出
    if data["success"]:
        assert "output" in data
        assert data["output"]["npc_id"] == "ancestor_yan"
        assert "persona" in data["output"]
    else:
        # NPC 不存在时应返回错误
        assert "error" in data


@pytest.mark.asyncio
async def test_tools_call_create_draft_content(headers, trace_id):
    """测试调用 create_draft_content 工具"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/tools/call",
            json={
                "tool_name": "create_draft_content",
                "input": {
                    "content_type": "knowledge",
                    "title": "测试内容标题",
                    "body": "这是测试内容正文。",
                    "tags": ["测试"],
                },
                "context": {
                    "tenant_id": "yantian",
                    "site_id": "yantian-main",
                    "trace_id": trace_id,
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "output" in data
    assert "content_id" in data["output"]
    assert data["output"]["status"] == "draft"


@pytest.mark.asyncio
async def test_tools_call_unknown_tool(headers, trace_id):
    """测试调用不存在的工具"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/tools/call",
            json={
                "tool_name": "unknown_tool",
                "input": {},
                "context": {
                    "tenant_id": "yantian",
                    "site_id": "yantian-main",
                    "trace_id": trace_id,
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is False
    assert "error" in data
    assert "Unknown tool" in data["error"]


@pytest.mark.asyncio
async def test_tools_call_audit_recorded(headers, trace_id):
    """测试工具调用审计记录"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/tools/call",
            json={
                "tool_name": "get_site_map",
                "input": {
                    "include_pois": True,
                    "include_routes": False,
                },
                "context": {
                    "tenant_id": "yantian",
                    "site_id": "yantian-main",
                    "trace_id": trace_id,
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()

    # 验证审计信息
    audit = data["audit"]
    assert audit["trace_id"] == trace_id
    assert audit["tool_name"] == "get_site_map"
    assert "latency_ms" in audit
    assert "request_payload_hash" in audit

    # 验证数据库记录
    async with async_session_maker() as session:
        stmt = select(TraceLedger).where(TraceLedger.trace_id == trace_id)
        result = await session.execute(stmt)
        trace = result.scalar_one_or_none()

        assert trace is not None
        assert trace.latency_ms is not None
        assert trace.tool_calls is not None
        assert len(trace.tool_calls) > 0
