# YT-AI-Platform 开发心得与避坑指南

> 严田 AI 文明引擎项目从 v0.1.0 到 v0.2.2 的完整开发历程总结。
> 记录架构决策、踩过的坑、解决方案，供后续 Spec 设计参考。

---

## 一、项目架构决策

### 1.1 Monorepo 结构选择

**决策**：采用 Monorepo 管理多个应用和服务。

```
YT-AI-Platform/
├── apps/
│   ├── admin-console/    # 管理后台 (Next.js)
│   └── visitor-h5/       # 游客端 H5 (Next.js)
├── services/
│   └── core-backend/     # 核心后端 (FastAPI)
├── packages/             # 共享包（预留）
└── infra/               # 基础设施配置
```

**心得**：
- ✅ 代码共享方便，统一版本管理
- ✅ 跨项目重构容易
- ⚠️ 需要注意各子项目的依赖隔离

**避坑**：
- 各子项目保持独立的 `package.json` / `pyproject.toml`
- 不要在根目录安装依赖，避免版本冲突

---

### 1.2 技术栈选择

| 层级 | 技术 | 选择理由 |
|------|------|----------|
| 后端框架 | FastAPI | 异步支持好、类型提示、自动文档 |
| 前端框架 | Next.js 14 | SSR/SSG、App Router、React 生态 |
| 数据库 | PostgreSQL | 成熟稳定、JSON 支持、全文搜索 |
| 缓存 | Redis | Session 存储、限流、缓存 |
| 向量库 | Qdrant | NPC 记忆检索、语义搜索 |
| ORM | SQLAlchemy 2.0 | 异步支持、类型安全 |
| 迁移 | Alembic | SQLAlchemy 官方迁移工具 |

**心得**：
- FastAPI + SQLAlchemy 2.0 异步组合很香，但学习曲线陡峭
- Next.js App Router 比 Pages Router 更现代，但文档和社区资源较少

---

## 二、认证与权限系统 (v0.1.0)

### 2.1 双轨认证设计

**设计**：管理端用户认证 + 游客端会话认证，两套独立体系。

```
管理端：JWT Token + RBAC 角色
游客端：Session ID + Redis 存储
```

**踩坑记录**：

1. **JWT 过期处理**
   - 问题：Token 过期后前端没有统一处理
   - 解决：前端封装 `proxyRequest`，统一检测 401 并跳转登录

2. **RBAC 角色层级**
   - 问题：最初只有 admin/user 两级，不够灵活
   - 解决：设计 5 级角色体系
   ```python
   ROLE_HIERARCHY = {
       "super_admin": 100,
       "admin": 80,
       "operator": 60,
       "editor": 40,
       "viewer": 20,
   }
   ```

3. **权限依赖注入**
   - 问题：每个 API 都要写权限检查代码
   - 解决：封装 `ViewerOrAbove`, `OperatorOrAbove` 等依赖
   ```python
   # 使用方式
   @router.get("/submissions")
   async def list_submissions(current_user: ViewerOrAbove):
       pass
   ```

**Spec 建议**：
- 认证和权限在 v0.1 就要设计好，后期改动成本高
- 角色层级要预留扩展空间

---

### 2.2 游客会话管理

**设计**：匿名游客通过 Session ID 识别，存储在 Redis。

**踩坑记录**：

1. **Session 生成时机**
   - 问题：最初在首页就生成 Session，导致大量无效 Session
   - 解决：延迟到用户首次交互（扫码、对话）时生成

2. **Session 与用户绑定**
   - 问题：游客扫码后如何关联微信身份
   - 解决：Session 表增加 `wx_openid` 字段，扫码时更新

3. **Session 过期策略**
   - 设计：默认 24 小时过期，活跃时自动续期
   - Redis Key：`session:{session_id}` → JSON 数据

---

## 三、多租户与多站点设计 (v0.1.0)

### 3.1 数据隔离模型

**设计**：`tenant_id` + `site_id` 双层隔离。

```
tenant (租户) → site (站点) → 业务数据
   严田集团  →  严田古村    →  NPC、场景、任务...
             →  其他景区    →  ...
```

**踩坑记录**：

1. **硬编码问题**
   - 问题：早期为快速开发，`tenant_id` 和 `site_id` 硬编码
   - 现状：v0.2.3 计划去除硬编码
   - 教训：即使是 MVP，也要预留配置化入口

2. **查询时忘记过滤**
   - 问题：部分 API 忘记加 `tenant_id` 过滤，导致数据泄露风险
   - 解决：封装 `get_tenant_filter()` 工具函数
   ```python
   def get_tenant_filter(tenant_id: str, site_id: str):
       return and_(
           Model.tenant_id == tenant_id,
           Model.site_id == site_id
       )
   ```

**Spec 建议**：
- 所有业务表必须有 `tenant_id` 和 `site_id`
- API 层强制要求这两个参数
- 查询时使用统一的过滤函数

---

## 四、NPC 对话系统 (v0.1.0 - v0.2.0)

### 4.1 NPC 数据模型

**设计**：NPC 配置与对话分离。

```
npcs (NPC 配置)
├── id, name, avatar
├── system_prompt (人设)
├── greeting (开场白)
└── knowledge_base_id (知识库)

npc_conversations (对话记录)
├── session_id
├── npc_id
└── messages (JSON Array)
```

**踩坑记录**：

1. **System Prompt 过长**
   - 问题：NPC 人设写太长，Token 消耗大
   - 解决：精简到 500 字以内，关键信息用结构化格式

2. **对话历史管理**
   - 问题：长对话导致 Context 超限
   - 解决：滑动窗口，只保留最近 N 轮对话
   ```python
   MAX_HISTORY_TURNS = 10
   messages = conversation.messages[-MAX_HISTORY_TURNS:]
   ```

3. **流式响应**
   - 问题：LLM 响应慢，用户体验差
   - 解决：SSE 流式输出
   ```python
   async def chat_stream():
       async for chunk in llm.stream(messages):
           yield f"data: {chunk}\n\n"
   ```

---

### 4.2 NPC 记忆系统

**设计**：使用 Qdrant 向量库存储 NPC 记忆。

**踩坑记录**：

1. **记忆检索相关性**
   - 问题：检索结果不够相关
   - 解决：调整 Embedding 模型，增加 metadata 过滤

2. **记忆更新时机**
   - 问题：每轮对话都更新记忆，性能差
   - 解决：对话结束时批量更新，或异步队列处理

---

## 五、研学任务系统 (v0.2.0 - v0.2.2)

### 5.1 任务数据模型

**设计**：任务配置 + 提交记录 + 审核流程。

```
quests (任务配置)
├── id, title, description
├── proof_type (text/image/location)
├── steps (JSON Array)
└── rewards

quest_submissions (提交记录)
├── session_id, quest_id
├── proof_payload (JSON)
├── status (submitted)
├── review_status (pending/approved/rejected)  # v0.2.2 新增
└── review_comment, reviewed_at, reviewed_by   # v0.2.2 新增
```

**踩坑记录**：

1. **状态字段语义混乱**
   - 问题：`status` 既表示提交状态又表示审核状态
   - 解决：v0.2.2 拆分为 `status`（提交状态）和 `review_status`（审核状态）
   - 教训：状态字段命名要明确语义

2. **完成判定逻辑**
   - 问题：最初 `status=submitted` 就算完成，没有审核
   - 解决：v0.2.2 改为 `review_status=approved` 才算完成

3. **重复提交处理**
   - 问题：用户可以无限重复提交
   - 解决：被驳回后才能重新提交，已通过则不能再提交

---

### 5.2 审核流程 (v0.2.2)

**设计**：管理员审核 → 通过/驳回 → 游客看到结果。

**踩坑记录**：

1. **API 请求体解析**
   - 问题：FastAPI `Body(default=None)` 在空 body 时返回 422
   - 解决：改用 Query 参数
   ```python
   # ❌ 有问题
   comment: Optional[str] = Body(default=None)
   
   # ✅ 推荐
   comment: Optional[str] = Query(default=None)
   ```

2. **审核时间一致性**
   - 问题：应用层时间可能与数据库不同步
   - 解决：使用数据库 `now()` 函数
   ```python
   await db.execute(
       text("UPDATE ... SET reviewed_at = now() WHERE id = :id"),
       {"id": submission_id}
   )
   ```

---

## 六、FastAPI 后端通用问题

### 6.1 异步数据库操作

**踩坑记录**：

1. **Session 生命周期**
   - 问题：在异步函数中 Session 提前关闭
   - 解决：使用 `async with` 或依赖注入管理
   ```python
   async def get_db():
       async with AsyncSession(engine) as session:
           yield session
   ```

2. **N+1 查询问题**
   - 问题：循环中查询关联数据
   - 解决：使用 `selectinload` 预加载
   ```python
   query = select(Quest).options(selectinload(Quest.submissions))
   ```

---

### 6.2 错误处理

**设计**：统一错误响应格式。

```python
# 统一格式
{"detail": "错误信息"}

# 验证错误
{"detail": [{"loc": ["body", "field"], "msg": "...", "type": "..."}]}
```

**踩坑记录**：
- 前端要同时处理 `detail` 字符串和数组两种格式
- 自定义异常要继承 `HTTPException`

---

## 七、Next.js 前端通用问题

### 7.1 App Router 特性

**踩坑记录**：

1. **动态路由参数**
   - 问题：Next.js 15 中 `params` 变成 Promise
   - 解决：
   ```typescript
   // Next.js 14
   { params }: { params: { id: string } }
   
   // Next.js 15
   { params }: { params: Promise<{ id: string }> }
   const { id } = await params;
   ```

2. **Server Component vs Client Component**
   - 问题：在 Server Component 中使用 hooks 报错
   - 解决：需要交互的组件加 `'use client'`

3. **API Route 代理**
   - 问题：Next.js API Route 代理后端时参数丢失
   - 解决：显式传递 Query 参数和 Headers
   ```typescript
   const comment = req.nextUrl.searchParams.get('comment');
   const url = comment ? `/api/xxx?comment=${encodeURIComponent(comment)}` : `/api/xxx`;
   ```

---

### 7.2 状态管理

**设计**：简单场景用 `useState`，复杂场景用 Context。

**踩坑记录**：
- 游客端状态简单，不需要 Redux
- 管理端考虑用 Zustand 或 Jotai

---

## 八、数据库与迁移

### 8.1 Alembic 迁移

**踩坑记录**：

1. **自动生成包含无关变更**
   - 问题：`alembic revision --autogenerate` 生成大量无关 SQL
   - 解决：手动审核并删除无关内容
   - 教训：每次迁移只包含一个功能的变更

2. **迁移顺序冲突**
   - 问题：多人开发时迁移文件冲突
   - 解决：合并前先 `alembic upgrade head`，再生成新迁移

3. **新字段默认值**
   - 问题：新增非空字段，已有数据报错
   - 解决：设置 `server_default`
   ```python
   op.add_column('table',
       sa.Column('field', sa.String(), server_default='default_value'))
   ```

---

## 九、前后端联调

### 9.1 API 代理架构

**设计**：Next.js API Route 代理后端，避免 CORS。

```
Browser → Next.js API Route → FastAPI Backend
         /api/admin/xxx     → /api/v1/admin/xxx
```

**踩坑记录**：

1. **Token 传递**
   - 问题：代理时忘记传递 Authorization Header
   - 解决：封装 `proxyRequest` 自动附加 Token

2. **错误信息丢失**
   - 问题：代理层吞掉了后端的错误详情
   - 解决：完整转发响应体
   ```typescript
   const data = await response.json();
   return NextResponse.json(data, { status: response.status });
   ```

---

### 9.2 类型同步

**踩坑记录**：
- 后端 Schema 变更后，前端 TypeScript 类型要同步更新
- 考虑使用 OpenAPI 自动生成类型

---

## 十、本地开发环境

### 10.1 服务启动

**推荐顺序**：

```bash
# 1. 基础设施
docker-compose up -d postgres redis qdrant

# 2. 后端
cd services/core-backend
uvicorn app.main:app --reload --port 8000

# 3. 前端（可并行）
cd apps/admin-console && npm run dev  # :3000
cd apps/visitor-h5 && npm run dev     # :3001
```

**踩坑记录**：

1. **Next.js 首次启动慢**
   - 问题：首次 `npm run dev` 需要 1-2 分钟
   - 解决：先 `npm run build` 一次

2. **端口冲突**
   - 问题：多个 Next.js 应用默认都用 3000
   - 解决：在 `package.json` 中指定端口
   ```json
   "dev": "next dev -p 3001"
   ```

3. **Docker Desktop 性能**
   - 问题：macOS 上 Docker 文件系统慢
   - 解决：开发时 Next.js 不进 Docker，只跑基础设施

---

## 十一、总结 Checklist

### 新功能开发前

- [ ] 写 Spec 明确 Goal / Non-Goal / Scope
- [ ] 确认数据模型变更
- [ ] 确认 API 接口设计
- [ ] 确认权限要求

### 数据库变更时

- [ ] 更新 SQLAlchemy Model
- [ ] 创建 Alembic 迁移
- [ ] 审核迁移文件，删除无关变更
- [ ] 新字段设置合理的默认值
- [ ] 测试 upgrade 和 downgrade

### API 开发时

- [ ] 定义请求/响应 Schema
- [ ] 可选参数优先用 Query
- [ ] 添加 RBAC 权限控制
- [ ] 统一错误响应格式
- [ ] 更新 API 文档

### 前端对接时

- [ ] 更新 TypeScript 类型
- [ ] API 代理正确传递参数
- [ ] 统一错误处理
- [ ] 处理加载和错误状态 UI

### 提交前

- [ ] 本地测试完整流程
- [ ] TypeScript 类型检查通过
- [ ] 代码格式化

---

## 版本历史

| 版本 | 主要功能 | 踩坑数 |
|------|----------|--------|
| v0.1.0 | 基础架构、认证、NPC 对话 | 多 |
| v0.2.0 | 研学任务、游客档案 | 中 |
| v0.2.1 | 任务提交看板 | 少 |
| v0.2.2 | 任务审核流程 | 中（API 请求体问题） |

---

*最后更新：2024-12-18*
