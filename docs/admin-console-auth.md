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

## 风险点与下一步

1. **Token 刷新机制** - 当前 token 过期后需要重新登录，可考虑实现 refresh token
2. **密码策略** - 建议添加密码复杂度校验和登录失败锁定
3. **审计日志** - 记录管理员操作日志
4. **多租户隔离** - 当前 RBAC 未考虑租户边界
5. **HTTPS** - 生产环境必须启用 HTTPS 以保护 cookie 传输
