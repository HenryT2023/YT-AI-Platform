# Admin Console 认证安全机制

本文档描述 admin-console 和 core-backend 的认证安全机制。

## 1. 登录失败锁定

### 机制

使用 Redis 计数实现登录失败锁定，防止暴力破解：

- **Key 格式**: `login_fail:{username}:{ip}`
- **计数规则**: 每次登录失败 +1，登录成功清零
- **锁定触发**: 失败次数达到阈值后锁定
- **自动解锁**: TTL 过期后自动解锁

### 配置项

在 `services/core-backend/.env` 中配置：

```env
# 最大登录失败次数（默认 5）
AUTH_MAX_LOGIN_FAILS=5

# 锁定时间（分钟，默认 10）
AUTH_LOCKOUT_MINUTES=10
```

### 错误响应

**锁定时的响应 (HTTP 429)**:

```json
{
  "detail": {
    "message": "登录失败次数过多，请在 600 秒后重试",
    "remaining_seconds": 600,
    "locked": true
  }
}
```

**达到锁定阈值时的响应 (HTTP 429)**:

```json
{
  "detail": {
    "message": "登录失败次数过多，账户已锁定 10 分钟",
    "remaining_seconds": 600,
    "locked": true
  }
}
```

### 日志示例

```
login_blocked_by_rate_limit username=admin ip=192.168.1.100 remaining_seconds=542
login_failed username=admin ip=192.168.1.100 reason=invalid_password fail_count=3 remaining_attempts=2
login_success username=admin ip=192.168.1.100 user_id=xxx role=super_admin
```

### Redis 不可用时的行为

如果 Redis 不可用，登录功能仍然正常工作，但不会进行失败计数和锁定。会记录警告日志：

```
redis_unavailable_for_rate_limit error="Connection refused"
```

## 2. Cookie 安全属性

### 环境化配置

Cookie 安全属性根据运行环境自动调整：

| 属性 | Development | Production |
|------|-------------|------------|
| `httpOnly` | `true` | `true` |
| `secure` | `false` | `true` |
| `sameSite` | `lax` | `strict` |
| `path` | `/` | `/` |

### 为什么 Production 使用 `sameSite='strict'`

- **防止 CSRF 攻击**: Cookie 不会在跨站请求中发送
- **内部管理系统**: admin-console 是内部系统，不需要跨站访问
- **最高安全级别**: `strict` 比 `lax` 更安全

如果需要支持 OAuth 回调等跨站场景，可以在 `cookie-config.ts` 中改为 `lax`。

### Cookie 列表

| Cookie 名称 | 内容 | 有效期 | 用途 |
|------------|------|--------|------|
| `yt_admin_access` | JWT access_token | 15 分钟 | API 认证 |
| `yt_admin_refresh` | 随机串 refresh_token | 7 天 | 刷新 access_token |

### 配置文件

Cookie 配置集中在 `apps/admin-console/src/lib/cookie-config.ts`：

```typescript
export function getCookieSecurityOptions(): CookieSecurityOptions {
  return {
    httpOnly: true,
    secure: isProduction,
    sameSite: isProduction ? 'strict' : 'lax',
    path: '/',
  };
}
```

## 3. Refresh Token 并发互斥

### 问题

多标签页同时触发 401 时，如果每个标签页都发起 refresh 请求：

1. 第一个 refresh 成功，旧 refresh_token 被 rotate 作废
2. 后续 refresh 使用已作废的 token，失败
3. 导致用户被强制登出

### 解决方案

在 `auth-utils.ts` 中实现全局互斥锁：

```typescript
let refreshPromise: Promise<boolean> | null = null;
let refreshLockTime: number = 0;
const REFRESH_LOCK_TIMEOUT = 10000; // 10 秒超时

async function refreshTokenWithMutex(): Promise<boolean> {
  const now = Date.now();
  
  // 检查是否有正在进行的 refresh 请求
  if (refreshPromise && (now - refreshLockTime) < REFRESH_LOCK_TIMEOUT) {
    // 等待现有的 refresh 完成
    return refreshPromise;
  }
  
  // 获取锁并执行 refresh
  refreshLockTime = now;
  refreshPromise = doRefreshToken();
  
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}
```

### 行为

1. 第一个 401 触发 refresh，获取锁
2. 后续 401 等待同一个 promise 结果
3. refresh 完成后，所有等待者获得相同结果
4. 超时保护：10 秒后锁自动释放

### 日志示例

```
[auth-utils] Got 401 for GET /api/v1/releases, attempting refresh...
[auth-utils] Executing refresh token request...
[auth-utils] Refresh successful
[auth-utils] Retrying GET /api/v1/releases with new token...

# 并发请求时
[auth-utils] Got 401 for GET /api/v1/feedback, attempting refresh...
[auth-utils] Waiting for existing refresh request...
```

## 4. 验收测试

### 4.1 登录失败锁定测试

```bash
# 1. 确保 Redis 运行
redis-cli ping

# 2. 启动 core-backend
cd services/core-backend
uvicorn app.main:app --reload --port 8000

# 3. 连续输错密码 5 次
for i in {1..5}; do
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"wrong"}'
  echo ""
done

# 4. 第 6 次应该返回 429
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"wrong"}'

# 预期输出：
# {"detail":{"message":"登录失败次数过多，请在 xxx 秒后重试","remaining_seconds":xxx,"locked":true}}

# 5. 检查 Redis 中的 key
redis-cli keys "login_fail:*"
redis-cli get "login_fail:admin:127.0.0.1"
redis-cli ttl "login_fail:admin:127.0.0.1"

# 6. 等待锁定时间过期后，正确密码应该能登录
```

### 4.2 Cookie 安全属性测试

```bash
# 1. 启动 admin-console (development)
cd apps/admin-console
npm run dev

# 2. 登录后检查 cookies
# 打开 DevTools > Application > Cookies
# 检查 yt_admin_access 和 yt_admin_refresh：
# - httpOnly: true
# - secure: false (development)
# - sameSite: lax (development)

# 3. 构建并启动 production 模式
npm run build
NODE_ENV=production npm start

# 4. 登录后检查 cookies
# - secure: true (production)
# - sameSite: strict (production)
```

### 4.3 Refresh 并发互斥测试

```bash
# 1. 登录获取 token
# 2. 将 JWT_ACCESS_TOKEN_EXPIRE_MINUTES 设为 1 分钟
# 3. 等待 access token 过期
# 4. 同时打开多个标签页访问 /admin/dashboard
# 5. 观察 admin-console 日志：
#    - 应该只有一个 "Executing refresh token request..."
#    - 其他请求显示 "Waiting for existing refresh request..."
# 6. 所有标签页都应该正常加载，不会被强制登出
```

## 5. 配置汇总

### core-backend/.env

```env
# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# 登录安全
AUTH_MAX_LOGIN_FAILS=5
AUTH_LOCKOUT_MINUTES=10
```

### admin-console/.env

```env
CORE_BACKEND_URL=http://localhost:8000
NODE_ENV=development  # 或 production
```

## 6. 风险点与下一步

1. **IP 欺骗** - 攻击者可能伪造 X-Forwarded-For 绕过 IP 限制，建议在反向代理层验证
2. **分布式锁** - 当前 refresh 互斥锁是进程内的，多实例部署时需要 Redis 分布式锁
3. **账户枚举** - 当前登录失败消息统一为"用户名或密码错误"，已防止账户枚举
4. **密码策略** - 建议添加密码复杂度校验
5. **审计日志持久化** - 当前登录日志在 stdout，建议持久化到数据库或日志系统
