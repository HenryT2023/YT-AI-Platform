"""
站点 API 测试
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """测试健康检查端点"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "core-backend"


@pytest.mark.asyncio
async def test_create_site(client: AsyncClient):
    """测试创建站点"""
    # 先获取 token
    login_response = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "admin"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # 创建站点
    site_data = {
        "id": "test-site",
        "name": "测试站点",
        "display_name": "测试站点展示名",
        "description": "这是一个测试站点",
        "config": {"features": {"ai_guide": True}},
    }

    response = await client.post(
        "/api/v1/sites",
        json=site_data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "test-site"
    assert data["name"] == "测试站点"


@pytest.mark.asyncio
async def test_list_sites(client: AsyncClient):
    """测试获取站点列表"""
    login_response = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "admin"},
    )
    token = login_response.json()["access_token"]

    response = await client.get(
        "/api/v1/sites",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
