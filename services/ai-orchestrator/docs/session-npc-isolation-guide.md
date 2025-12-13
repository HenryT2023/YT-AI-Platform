# P14 Session × NPC 隔离与偏好记忆分层指南

## 概述

解决跨 NPC 混淆问题，将会话记忆分层为**短记忆**与**偏好记忆**，避免记忆污染事实输出。

## 核心设计

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Session                                  │
│                    (session-abc123)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              偏好记忆 (Preference Memory)                │    │
│  │              跨 NPC 共享                                 │    │
│  │  ┌─────────────────────────────────────────────────┐   │    │
│  │  │ verbosity: "detailed"                           │   │    │
│  │  │ tone: "respectful"                              │   │    │
│  │  │ interest_tags: ["家训", "祠堂", "农耕"]          │   │    │
│  │  │ language: "zh"                                  │   │    │
│  │  └─────────────────────────────────────────────────┘   │    │
│  │  Key: yantian:session:pref:{tenant}:{site}:{session}   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────┐             │
│  │  短记忆 (NPC A)       │  │  短记忆 (NPC B)       │             │
│  │  ancestor_yan        │  │  village_elder       │             │
│  │  ┌────────────────┐  │  │  ┌────────────────┐  │             │
│  │  │ User: 家训...  │  │  │  │ User: 祠堂...  │  │             │
│  │  │ NPC: 后生...   │  │  │  │ NPC: 这座...   │  │             │
│  │  │ User: 第一条.. │  │  │  │ User: 建于...  │  │             │
│  │  │ NPC: 孝悌...   │  │  │  │ NPC: 据记载... │  │             │
│  │  └────────────────┘  │  │  └────────────────┘  │             │
│  │  Key: ...:short:...  │  │  Key: ...:short:...  │             │
│  │       :ancestor_yan  │  │       :village_elder │             │
│  └──────────────────────┘  └──────────────────────┘             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 文件树变更清单

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/memory/redis_memory.py` | 添加 NPC 隔离 key、偏好记忆类 |
| `app/memory/__init__.py` | 导出新类和函数 |
| `app/agent/runtime.py` | 更新 memory 调用支持 NPC 隔离 |
| `app/api/v1/npc.py` | 更新会话 API 支持按 npc_id 操作 |
| `app/api/v1/trace.py` | 添加 persona_version 到 Trace 视图 |

## Redis Key 设计

### 短记忆（NPC 隔离）

```text
Key: yantian:session:short:{tenant_id}:{site_id}:{session_id}:{npc_id}
Type: List
TTL: 24 小时
```

示例：
```text
yantian:session:short:yantian:yantian-main:session-abc123:ancestor_yan
yantian:session:short:yantian:yantian-main:session-abc123:village_elder
```

### 偏好记忆（跨 NPC 共享）

```text
Key: yantian:session:pref:{tenant_id}:{site_id}:{session_id}
Type: Hash
TTL: 24 小时
```

字段：
| 字段 | 类型 | 说明 |
|------|------|------|
| verbosity | string | brief, normal, detailed |
| tone | string | casual, formal, respectful |
| interest_tags | json array | 兴趣标签列表 |
| language | string | 语言偏好 |
| updated_at | string | 更新时间 |

## API 接口

### GET /api/v1/npc/sessions/{session_id}

获取会话摘要（支持按 NPC 过滤）

```bash
# 获取整个 session 的摘要
curl "http://localhost:8001/api/v1/npc/sessions/session-abc123" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"

# 获取特定 NPC 的摘要
curl "http://localhost:8001/api/v1/npc/sessions/session-abc123?npc_id=ancestor_yan" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
```

响应：
```json
{
  "session_id": "session-abc123",
  "npc_id": "ancestor_yan",
  "message_count": 6,
  "recent_messages": [
    {"role": "user", "content": "请问严氏家训有哪些？", "timestamp": "..."},
    {"role": "assistant", "content": "后生问得好...", "timestamp": "..."}
  ],
  "first_message_at": "2024-12-13T10:00:00Z",
  "last_message_at": "2024-12-13T10:05:00Z",
  "preference": {
    "verbosity": "normal",
    "tone": "formal",
    "interest_tags": ["家训", "祠堂"],
    "language": "zh",
    "updated_at": "2024-12-13T10:00:00Z"
  }
}
```

### DELETE /api/v1/npc/sessions/{session_id}

清空会话记忆（支持按 NPC 清空）

```bash
# 清空整个 session
curl -X DELETE "http://localhost:8001/api/v1/npc/sessions/session-abc123" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"

# 只清空特定 NPC 的记忆
curl -X DELETE "http://localhost:8001/api/v1/npc/sessions/session-abc123?npc_id=ancestor_yan" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
```

### PUT /api/v1/npc/sessions/{session_id}/preference

更新用户偏好

```bash
curl -X PUT "http://localhost:8001/api/v1/npc/sessions/session-abc123/preference?verbosity=detailed&tone=respectful&interest_tag=农耕" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
```

响应：
```json
{
  "success": true,
  "preference": {
    "verbosity": "detailed",
    "tone": "respectful",
    "interest_tags": ["农耕"],
    "language": "zh",
    "updated_at": "2024-12-13T10:10:00Z"
  }
}
```

## Prompt 注入格式

### 偏好记忆

```text
【用户偏好 - 仅供参考】
- 用户偏好详细回答
- 用户偏好恭敬的语气
- 用户感兴趣的话题：家训、祠堂、农耕
【用户偏好结束】
```

### 短记忆

```text
【对话历史 - 仅供上下文参考，不作为事实依据】
以下是与用户的近期对话，帮助你理解用户的兴趣和问题背景。
注意：任何历史事实、人物、事件的信息必须从证据库中检索验证，不能仅凭对话历史回答。

用户: 请问严氏家训有哪些？
严氏先祖: 后生问得好。老夫当年定下家训十则...
用户: 第一条孝悌为本是什么意思？
严氏先祖: 孝悌为本，乃是说孝顺父母、敬爱兄长是做人的根本...

【对话历史结束】
```

## Trace 记录增强

trace_ledger 现在记录：

```json
{
  "trace_id": "trace-xxx",
  "request_input": {
    "query": "请问严氏家训有哪些？",
    "npc_id": "ancestor_yan",
    "session_id": "session-abc123",
    "prompt_version": 1,
    "prompt_source": "prompt_registry",
    "persona_version": 2
  },
  "tool_calls": [
    {"name": "get_session_memory", "status": "success", "npc_id": "ancestor_yan"},
    ...
  ]
}
```

## 使用示例

### 跨 NPC 对话场景

```bash
# 1. 与 ancestor_yan 对话
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "session_id": "session-abc123",
    "query": "请问严氏家训有哪些？"
  }'

# 2. 切换到 village_elder 对话（同一 session）
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "village_elder",
    "session_id": "session-abc123",
    "query": "祠堂是什么时候建的？"
  }'

# 3. 切换回 ancestor_yan（记忆保持隔离）
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "session_id": "session-abc123",
    "query": "第一条是什么意思？"
  }'
# ancestor_yan 能记住之前关于家训的对话
# 但不会混淆与 village_elder 的祠堂对话
```

## 风险点与下一步

### 风险点

| 风险点 | 说明 | 缓解措施 |
|--------|------|----------|
| **Key 数量增加** | 每个 NPC 一个 key | TTL 自动过期 |
| **偏好推断不准** | 需要用户主动设置或 LLM 推断 | 后续增加自动推断 |
| **迁移兼容性** | 旧 key 格式不兼容 | 旧数据自动过期 |
| **Redis 内存** | 更多 key 占用更多内存 | 监控 + 合理 TTL |

### 下一步

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | **偏好自动推断** | 从对话中推断用户偏好 |
| P2 | **NPC 关系图** | 支持 NPC 之间的信息共享 |
| P3 | **长期记忆** | 跨 session 的用户画像 |
| P4 | **记忆压缩** | 对长对话进行摘要压缩 |
| P5 | **记忆可视化** | Admin Console 中查看记忆 |

## 配置说明

```python
# app/core/config.py

# 记忆配置
MEMORY_TTL_SECONDS: int = 86400  # 24 小时
MEMORY_MAX_MESSAGES: int = 10    # 最大消息条数
MEMORY_MAX_CHARS: int = 4000     # 最大字符数
MEMORY_ENABLED: bool = True      # 是否启用会话记忆
```
