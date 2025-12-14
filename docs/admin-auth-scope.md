# Tenant/Site Scope 隔离机制

本文档描述 admin-console 和 core-backend 的多租户/多站点作用域隔离机制。

## 1. 概述

系统实现了基于 JWT claims 的 tenant/site 作用域隔离：

- **tenant_id**: 租户 ID，用于隔离不同租户的数据
- **site_ids**: 站点 ID 列表，用于限制用户可访问的站点

### 权限层级

| 角色 | tenant_id | site_ids | 访问范围 |
|------|-----------|----------|----------|
| super_admin | null | [] | 所有 tenant/site |
| tenant_admin | "yantian" | [] | 该 tenant 下所有 site |
| site_admin | "yantian" | ["site-a"] | 仅指定 site |
| operator | "yantian" | ["site-a"] | 仅指定 site |
| viewer | "yantian" | ["site-a", "site-b"] | 仅指定 sites |

## 2. JWT Claims 扩展

登录和 refresh 时，access_token 包含以下 claims：

```json
{
  "sub": "user-uuid",
  "username": "admin",
  "role": "operator",
  "tenant_id": "yantian",
  "site_ids": ["yantian-main"],
  "exp": 1702569600,
  "iat": 1702568700,
  "type": "access"
}
```

### Claims 说明

| Claim | 类型 | 说明 |
|-------|------|------|
| `tenant_id` | string \| null | 用户所属租户，null 表示 super_admin |
| `site_ids` | string[] | 用户可访问的站点列表，空数组表示可访问所有 |

## 3. Scope 校验依赖

### 校验流程

```
请求 → 提取 JWT claims → 提取 X-Tenant-ID/X-Site-ID header
                              ↓
                    校验 header 值是否在 claims 授权范围内
                              ↓
                    通过 → 继续处理
                    失败 → 返回 403
```

### 使用方式

```python
from app.core.scope import RequireTenantScope, verify_tenant_site_access

@router.get("/releases")
async def list_releases(
    tenant_id: str = Query(...),
    site_id: str = Query(...),
    scope: RequireTenantScope = None,
):
    # 校验用户是否有权访问该 tenant/site
    verify_tenant_site_access(scope, tenant_id, site_id)
    
    # 继续处理...
```

### 403 响应示例

**Tenant 不匹配**:

```json
{
  "detail": {
    "message": "无权访问该租户的资源",
    "error": "tenant_scope_mismatch",
    "requested_tenant": "other-tenant",
    "allowed_tenant": "yantian"
  }
}
```

**Site 不匹配**:

```json
{
  "detail": {
    "message": "无权访问该站点的资源",
    "error": "site_scope_mismatch",
    "requested_site": "site-b",
    "allowed_sites": ["site-a"]
  }
}
```

## 4. Admin Console 代理层注入

### 自动注入 Header

`auth-utils.ts` 中的 `getAuthHeaders()` 自动注入：

- `X-Tenant-ID`: 当前 tenant
- `X-Site-ID`: 当前 site

```typescript
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  const tenantId = await getTenantId();
  const siteId = await getSiteId();
  
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    'X-Tenant-ID': tenantId,
    'X-Site-ID': siteId,
  };
}
```

### Tenant/Site 来源

优先级：Cookie > 环境变量默认值

| 来源 | Cookie 名称 | 环境变量 | 默认值 |
|------|-------------|----------|--------|
| tenant_id | `yt_admin_tenant` | `DEFAULT_TENANT_ID` | "yantian" |
| site_id | `yt_admin_site` | `DEFAULT_SITE_ID` | "yantian-main" |

### 站点切换器（未来扩展）

灰度期使用固定的环境变量配置。后续可实现站点切换器 UI：

1. 用户登录后，根据 JWT claims 中的 `site_ids` 显示可选站点
2. 用户选择站点后，写入 `yt_admin_site` cookie
3. 所有 API 请求自动使用选中的站点

## 5. 已接入 Scope 校验的 API

### releases

| 端点 | 校验方式 |
|------|----------|
| `POST /releases` | 校验 request body 中的 tenant_id/site_id |
| `GET /releases` | 校验 query params 中的 tenant_id/site_id |
| `GET /releases/active` | 校验 query params |
| `GET /releases/{id}` | 获取后校验 release 的 tenant_id/site_id |
| `POST /releases/{id}/activate` | 获取后校验 |
| `POST /releases/{id}/rollback` | 获取后校验 |
| `GET /releases/{id}/validate` | 获取后校验 |
| `GET /releases/{id}/history` | 获取后校验 |

### 待接入（后续迭代）

- policies
- alerts (events/silences/evaluate)
- feedback (list/triage/status/stats)
- experiments (assign/ab-summary/active)
- runtime_config

## 6. 配置

### core-backend/.env

```env
# 默认 tenant/site（用于 seed 数据等）
DEFAULT_TENANT_ID=yantian
DEFAULT_SITE_ID=yantian-main
```

### admin-console/.env

```env
# 默认 tenant/site（灰度期固定值）
DEFAULT_TENANT_ID=yantian
DEFAULT_SITE_ID=yantian-main
```

## 7. 验收测试

```bash
# 运行 scope 校验冒烟测试
cd services/core-backend
python scripts/scope_smoke_test.py
```

### 手动测试

```bash
# 1. 登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')

# 2. 请求 releases（带正确的 scope header）
curl -X GET "http://localhost:8000/api/v1/releases?tenant_id=yantian&site_id=yantian-main" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"

# 3. 请求错误的 tenant（应返回 403）
curl -X GET "http://localhost:8000/api/v1/releases?tenant_id=other&site_id=other-site" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: other" \
  -H "X-Site-ID: other-site"
```

## 8. 风险点与下一步

1. **Header 篡改** - 当前依赖 JWT claims 校验，header 只是辅助。确保所有 API 都接入 scope 校验
2. **缓存一致性** - 如果用户权限变更，需要等 token 过期或强制重新登录
3. **站点切换器** - 灰度期使用固定值，后续需实现 UI
4. **批量操作** - 跨 site 的批量操作需要特殊处理
5. **审计日志** - 记录 scope 相关的访问日志，便于安全审计
