# Prompt Registry 指南

## 概述

Prompt Registry 将 NPC Prompt 从"写死在代码里"升级为"可版本化、可审计、可回滚、可运营"的资产体系。

**真源（Source of Truth）：数据库**

- 运营后台通过 API 管理 Prompt 版本
- `data/prompts/` 作为初始化种子和备份
- 导入脚本：`scripts/import_prompts.py`

## 文件树变更清单

### 新增文件

```text
data/prompts/
├── README.md                 # 目录说明
├── _template.yaml            # 模板文件
├── ancestor_yan.yaml         # 严氏先祖 Prompt
├── craftsman_wang.yaml       # 王家匠人 Prompt
└── farmer_li.yaml            # 李家农夫 Prompt

services/core-backend/
├── app/database/models/npc_prompt.py     # NPCPrompt 模型
├── app/api/v1/prompts.py                 # Prompt CRUD API
├── alembic/versions/003_add_npc_prompts.py  # 迁移脚本
└── scripts/import_prompts.py             # 导入脚本
```

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/database/models/__init__.py` | 导出 NPCPrompt |
| `app/api/__init__.py` | 注册 prompts 路由 |
| `app/tools/executor.py` | get_prompt_active 优先从 registry 加载 |

### ai-orchestrator 修改文件

| 文件 | 变更 |
|------|------|
| `app/agent/runtime.py` | 记录 prompt_version 到 trace_ledger |

## 迁移与导入步骤

### 1. 运行数据库迁移

```bash
cd services/core-backend
alembic upgrade head
```

### 2. 导入 Prompt 种子数据

```bash
# 导入所有 Prompt
python scripts/import_prompts.py

# 导入指定文件
python scripts/import_prompts.py --file ancestor_yan.yaml

# 强制覆盖已存在版本
python scripts/import_prompts.py --force

# 指定租户和站点
python scripts/import_prompts.py --tenant-id yantian --site-id yantian-main
```

## API 接口

### POST /v1/prompts

创建新 Prompt（自动递增版本号）

```bash
curl -X POST http://localhost:8000/api/v1/prompts \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -d '{
    "npc_id": "ancestor_yan",
    "content": "你是严氏先祖...",
    "meta": {"name": "严氏先祖 v2", "author": "admin"},
    "policy": {"require_citations": true, "max_response_length": 500},
    "description": "优化了说话风格",
    "set_active": true
  }'
```

### GET /v1/prompts/{npc_id}

获取激活版本

```bash
curl http://localhost:8000/api/v1/prompts/ancestor_yan \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
```

获取指定版本

```bash
curl "http://localhost:8000/api/v1/prompts/ancestor_yan?version=1" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
```

### GET /v1/prompts/{npc_id}/versions

列出所有版本

```bash
curl http://localhost:8000/api/v1/prompts/ancestor_yan/versions \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
```

响应：

```json
{
  "npc_id": "ancestor_yan",
  "versions": [
    {"id": "...", "version": 2, "active": true, "author": "admin", "created_at": "..."},
    {"id": "...", "version": 1, "active": false, "author": "system", "created_at": "..."}
  ],
  "total": 2,
  "active_version": 2
}
```

### POST /v1/prompts/{npc_id}/set-active

设置激活版本（支持回滚）

```bash
curl -X POST http://localhost:8000/api/v1/prompts/ancestor_yan/set-active \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -d '{"version": 1}'
```

响应：

```json
{
  "npc_id": "ancestor_yan",
  "previous_version": 2,
  "current_version": 1,
  "message": "Successfully activated version 1 (was v2)"
}
```

### DELETE /v1/prompts/{npc_id}/versions/{version}

删除指定版本（软删除，不能删除激活版本）

```bash
curl -X DELETE http://localhost:8000/api/v1/prompts/ancestor_yan/versions/1 \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
```

## 最小联调用例

### 场景：切换 active 版本 + npc/chat 生效

```bash
# 1. 导入 Prompt
cd services/core-backend
python scripts/import_prompts.py

# 2. 验证激活版本
curl http://localhost:8000/api/v1/prompts/ancestor_yan \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
# 返回 version: 1, active: true

# 3. 创建新版本
curl -X POST http://localhost:8000/api/v1/prompts \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -d '{
    "npc_id": "ancestor_yan",
    "content": "你是严氏先祖（v2 优化版）...",
    "meta": {"name": "严氏先祖 v2"},
    "set_active": true
  }'
# 返回 version: 2, active: true

# 4. 调用 NPC 对话（使用 v2）
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问严氏家训有哪些？"
  }'
# 响应中 trace_ledger 记录 prompt_version: 2

# 5. 回滚到 v1
curl -X POST http://localhost:8000/api/v1/prompts/ancestor_yan/set-active \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -d '{"version": 1}'

# 6. 再次调用 NPC 对话（使用 v1）
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问严氏家训有哪些？"
  }'
# 响应中 trace_ledger 记录 prompt_version: 1
```

## Prompt 文件格式

```yaml
meta:
  npc_id: ancestor_yan        # NPC ID（必需）
  version: 1                  # 版本号（必需）
  name: 严氏先祖系统提示词    # 显示名称
  author: system              # 作者
  created_at: "2024-12-13"    # 创建时间
  description: 初始版本       # 版本描述

policy:
  require_citations: true     # 是否要求引用
  min_confidence: 0.6         # 最低置信度
  must_cite_verified: true    # 是否必须引用已验证证据
  forbidden_topics:           # 禁止话题
    - 政治敏感
    - 宗教争议
  max_response_length: 500    # 最大回复长度
  conservative_template: "此事我不甚了了..."  # 保守模式模板

prompt: |
  # 身份设定
  你是严氏先祖...
```

## 风险点与下一步

### 风险点

1. **回退兼容** - 如果 Prompt Registry 无数据，会回退到 NPC Profile，需确保两边数据一致
2. **版本膨胀** - 频繁修改可能导致版本过多，需定期清理
3. **缓存** - 当前每次请求都查询数据库，高并发下可能需要缓存
4. **审计完整性** - operator_id 可空，生产环境应强制要求
5. **导入幂等性** - 导入脚本默认不覆盖，需手动 --force

### 下一步

1. **v0.1.1** - 添加 Prompt 缓存（Redis）
2. **v0.1.2** - Admin Console 集成 Prompt 管理界面
3. **v0.2.0** - 支持 Prompt 模板变量替换
4. **v0.2.1** - 添加 Prompt A/B 测试能力
5. **v0.3.0** - 支持 Prompt 审批流程
