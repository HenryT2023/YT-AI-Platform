# Admin Console 认证系统 v2

## 概述

实现了基于 JWT 的管理员认证系统，包括：
- core-backend: 管理员登录 API + RBAC 权限控制
- admin-console: 登录页面 + middleware 路由保护 + HttpOnly cookie

## 文件变更清单

### core-backend

```
services/core-backend/
├── app/
│   ├── api/v1/auth.py          # 扩展: 添加 /login, /me 端点
│   └── core/
│       └── rbac.py             # 新增: RBAC 权限依赖
└── scripts/
    └── create_admin_user.py    # 新增: 创建管理员用户脚本
```

### admin-console

```
apps/admin-console/
├── src/
│   ├── app/
│   │   ├── login/page.tsx              # 新增: 登录页面
│   │   ├── admin/
│   │   │   ├── dashboard/page.tsx      # 新增: 管理后台首页
│   │   │   ├── npcs/page.tsx           # 迁移自 /npcs
│   │   │   ├── scenes/page.tsx         # 迁移自 /scenes
│   │   │   ├── quests/page.tsx         # 迁移自 /quests
│   │   │   ├── visitors/page.tsx       # 迁移自 /visitors
│   │   │   └── settings/page.tsx       # 迁移自 /settings
│   │   ├── api/auth/
│   │   │   ├── login/route.ts          # 新增: 登录代理
│   │   │   ├── logout/route.ts         # 新增: 登出
│   │   │   └── me/route.ts             # 新增: 获取当前用户
│   │   └── [旧路径]/page.tsx           # 重定向到 /admin/*
│   ├── lib/
│   │   └── auth-utils.ts               # 新增: 认证工具函数
│   ├── middleware.ts                   # 新增: 路由保护
│   └── components/layout/
│       └── dashboard-layout.tsx        # 更新: 导航链接
```

## 运行与验收步骤

### 1. 创建管理员用户

```bash
cd services/core-backend

# 方式一：使用环境变量
ADMIN_USERNAME=admin ADMIN_PASSWORD=admin123 python scripts/create_admin_user.py

# 方式二：使用命令行参数
python scripts/create_admin_user.py --username admin --password admin123 --role super_admin
```

### 2. 启动服务

```bash
# 启动 core-backend
cd services/core-backend
uvicorn app.main:app --reload --port 8000

# 启动 admin-console
cd apps/admin-console
npm run dev
```

### 3. 验证登录流程

```bash
# 测试登录 API
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# 预期响应
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "...",
    "username": "admin",
    "display_name": "admin",
    "role": "super_admin"
  }
}
```

### 4. 验证路由保护

```bash
# 未登录访问 /admin/dashboard → 重定向到 /login
curl -I http://localhost:3000/admin/dashboard
# 预期: 302 Location: /login

# 登录后访问
# 1. 打开浏览器访问 http://localhost:3000/login
# 2. 输入 admin / admin123
# 3. 登录成功后自动跳转到 /admin/dashboard
```

### 5. 验证 Cookie 设置

登录成功后，检查浏览器 DevTools → Application → Cookies：
- Name: `yt_admin_token`
- HttpOnly: ✓
- SameSite: Lax

## 角色权限测试

### 创建不同角色用户

```bash
# 创建 viewer
python scripts/create_admin_user.py -u viewer -p viewer123 -r viewer

# 创建 operator
python scripts/create_admin_user.py -u operator -p operator123 -r operator

# 创建 admin
python scripts/create_admin_user.py -u admin -p admin123 -r super_admin
```

### 权限差异

| 角色 | 读取数据 | 创建/编辑 | 删除 | 发布版本 | 系统设置 |
|------|----------|-----------|------|----------|----------|
| viewer | ✓ | ✗ | ✗ | ✗ | ✗ |
| operator | ✓ | ✓ | ✓ | ✗ | ✗ |
| admin | ✓ | ✓ | ✓ | ✓ | ✓ |

## API 权限保护示例

在 core-backend 的路由中使用 RBAC：

```python
from app.core.rbac import AdminOnly, OperatorOrAbove, CurrentAdminUser

@router.post("/releases/{release_id}/activate")
async def activate_release(
    release_id: str,
    user: AdminOnly,  # 仅 admin 角色可访问
):
    ...

@router.post("/alerts/silences")
async def create_silence(
    data: SilenceCreate,
    user: OperatorOrAbove,  # operator 或更高权限
):
    ...

@router.get("/npcs")
async def list_npcs(
    user: CurrentAdminUser,  # 任何已登录用户
):
    ...
```

## RBAC 权限矩阵

### 角色定义

| 角色 | 说明 |
|------|------|
| `super_admin` | 超级管理员，全部权限 |
| `tenant_admin` | 租户管理员 |
| `site_admin` | 站点管理员 |
| `operator` | 运营人员，可执行大部分操作 |
| `viewer` | 只读用户，仅查看权限 |
| `visitor` | 游客，**不允许登录后台** |

### API 权限矩阵

| API 端点 | Admin | Operator | Viewer |
|----------|-------|----------|--------|
| **Releases** |
| `GET /releases` | ✓ | ✓ | ✓ |
| `GET /releases/{id}` | ✓ | ✓ | ✓ |
| `POST /releases` (创建) | ✓ | ✗ | ✗ |
| `POST /releases/{id}/activate` | ✓ | ✗ | ✗ |
| `POST /releases/{id}/rollback` | ✓ | ✗ | ✗ |
| **Policies** |
| `GET /policies/evidence-gate/*` | ✓ | ✓ | ✓ |
| `POST /policies/evidence-gate` | ✓ | ✗ | ✗ |
| `POST /policies/evidence-gate/rollback/*` | ✓ | ✗ | ✗ |
| **Feedback** |
| `GET /feedback` | ✓ | ✓ | ✓ |
| `GET /feedback/stats` | ✓ | ✓ | ✓ |
| `POST /feedback/{id}/triage` | ✓ | ✓ | ✗ |
| `POST /feedback/{id}/status` | ✓ | ✓ | ✗ |
| **Alerts** |
| `GET /alerts/*` | ✓ | ✓ | ✓ |
| `POST /alerts/silences` | ✓ | ✓ | ✗ |
| `DELETE /alerts/silences/{id}` | ✓ | ✓ | ✗ |

### 错误响应示例

**401 Unauthorized** - 未登录或 token 无效：

```json
{
  "detail": "未登录或登录已过期，请重新登录"
}
```

**403 Forbidden** - 角色权限不足：

```json
{
  "detail": "权限不足：当前角色 [viewer] 无权执行此操作，需要角色: [super_admin, tenant_admin, site_admin]"
}
```

**403 Forbidden** - 账户被禁用：

```json
{
  "detail": "账户已被禁用，请联系管理员"
}
```

### RBAC 测试脚本

```bash
cd services/core-backend

# 运行权限冒烟测试
python scripts/rbac_smoke_test.py

# 指定 API 地址
python scripts/rbac_smoke_test.py --api-url http://localhost:8000

# 跳过用户创建（如果测试用户已存在）
python scripts/rbac_smoke_test.py --skip-setup
```

测试脚本会：
1. 创建三个测试用户（admin/operator/viewer）
2. 登录获取 token
3. 测试各端点的权限控制
4. 输出测试结果表格

## Refresh Token 机制

### 概述

系统实现了完整的 refresh token 机制，提供生产级的登录体验和安全性：

- **access_token**: JWT，短有效期（默认 15 分钟）
- **refresh_token**: 随机串，长有效期（默认 7 天），落库可撤销

### Cookie 存储

两个 token 都存储在 HttpOnly cookie 中，JS 无法访问：

| Cookie 名称 | 内容 | 有效期 | 用途 |
|------------|------|--------|------|
| `yt_admin_access` | access_token | 15 分钟 | API 认证 |
| `yt_admin_refresh` | refresh_token | 7 天 | 刷新 access_token |

### Token 轮换 (Rotate)

每次调用 `/refresh` 时：
1. 验证旧 refresh_token 是否有效
2. 生成新的 access_token 和 refresh_token
3. **撤销旧 refresh_token**（设置 `revoked_at`）
4. 建立链接（`replaced_by_id` 指向新 token）
5. 返回新的 tokens

这确保了即使 refresh_token 被窃取，攻击者只能使用一次。

### 数据库模型

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    token_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 hash
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,  -- 撤销时间
    replaced_by_id UUID REFERENCES refresh_tokens(id),  -- 轮换链
    user_agent VARCHAR(500),
    ip_address VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

### API 端点

**POST /api/v1/auth/login**
```json
// Request
{ "username": "admin", "password": "xxx" }

// Response
{
  "access_token": "eyJ...",
  "refresh_token": "a1b2c3...",
  "token_type": "bearer",
  "access_expires_in": 900,
  "refresh_expires_in": 604800,
  "user": { "id": "...", "username": "admin", "role": "super_admin" }
}
```

**POST /api/v1/auth/refresh**
```json
// Request
{ "refresh_token": "a1b2c3..." }

// Response
{
  "access_token": "eyJ...",
  "refresh_token": "d4e5f6...",  // 新的 refresh_token
  "token_type": "bearer",
  "access_expires_in": 900,
  "refresh_expires_in": 604800
}
```

**POST /api/v1/auth/logout**
```json
// Request
{ "refresh_token": "a1b2c3..." }

// Response
{ "ok": true, "message": "登出成功" }
```

### 前端自动刷新

代理层 (`auth-utils.ts`) 实现了 401 自动重试：

1. 发起 API 请求
2. 如果返回 401，调用 `/api/auth/refresh`
3. 如果刷新成功，用新 token 重试原请求
4. 如果刷新失败，返回 401，前端跳转登录页

### 验收测试

```bash
# 1. 运行数据库迁移
cd services/core-backend
alembic upgrade head

# 2. 启动 core-backend
uvicorn app.main:app --reload --port 8000

# 3. 启动 admin-console
cd apps/admin-console
npm run dev

# 4. 测试登录
# 访问 http://localhost:3000/login
# 登录后检查 cookies（DevTools > Application > Cookies）
# 应该看到 yt_admin_access 和 yt_admin_refresh

# 5. 测试 refresh（可选：将 access token 有效期改为 1 分钟测试）
# 等待 access token 过期后访问 /admin/dashboard
# 应该自动 refresh 并继续可用

# 6. 测试 logout
# 点击退出登录
# 检查 cookies 已清除
# 访问 /admin/* 应重定向到 /login
```

### 配置项

在 `services/core-backend/.env` 中：

```env
# Access token 有效期（分钟）
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15

# Refresh token 有效期（天）
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

## 风险点与下一步

1. ~~**Token 刷新机制**~~ ✅ 已实现 refresh token + rotate
2. **密码策略** - 建议添加密码复杂度校验和登录失败锁定
3. **多租户隔离** - 当前 RBAC 未考虑租户边界，需要在数据层面增加隔离
4. **HTTPS** - 生产环境必须启用 HTTPS 以保护 cookie 传输
5. **审计日志查询** - 提供审计日志查询 API 供管理员审查操作历史
6. **Refresh Token 清理** - 定期清理过期/已撤销的 refresh token 记录
