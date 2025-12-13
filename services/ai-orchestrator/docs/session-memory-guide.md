# 多轮对话记忆指南

## 概述

多轮对话记忆实现"上下文保持"，让 NPC 能够记住与用户的近期对话。

**核心约束：**
- 记忆仅作为"上下文与偏好"，**不作为史实来源**
- 史实必须来自 evidence
- 若用户追问史实，仍必须 retrieve_evidence

## 文件树变更清单

### 新增文件

```text
services/ai-orchestrator/
├── app/memory/
│   ├── __init__.py           # Memory 模块导出
│   └── redis_memory.py       # Redis 会话记忆实现
└── docs/
    └── session-memory-guide.md  # 本文档
```

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/core/config.py` | 添加 MEMORY_MAX_MESSAGES, MEMORY_MAX_CHARS, MEMORY_ENABLED |
| `app/agent/schemas.py` | ChatResponse 添加 session_id 字段 |
| `app/agent/runtime.py` | 集成会话记忆：获取、拼接、保存 |
| `app/api/v1/npc.py` | 添加会话管理接口 |

## 存储设计

### Redis Key 格式

```text
yantian:session:{tenant_id}:{site_id}:{session_id}
```

### 数据结构

使用 Redis List 存储消息：

```json
[
  {"role": "user", "content": "严氏家训有哪些？", "timestamp": "...", "npc_id": "ancestor_yan"},
  {"role": "assistant", "content": "后生问得好...", "timestamp": "...", "npc_id": "ancestor_yan"},
  ...
]
```

### 裁剪策略

| 策略 | 默认值 | 说明 |
|------|--------|------|
| 按条数 | 10 条 | 保留最近 N 条消息 |
| 按字符 | 4000 字符 | 超过上限时从最早消息开始删除 |
| TTL | 24 小时 | 会话自动过期 |

## API 接口

### POST /v1/npc/chat

对话请求（支持 session_id）

```bash
# 第一次对话（不传 session_id，自动生成）
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问严氏家训有哪些？"
  }'

# 响应
{
  "trace_id": "trace-abc123",
  "session_id": "session-def456",  # 返回的 session_id
  "policy_mode": "normal",
  "answer_text": "后生问得好..."
}

# 后续对话（传入 session_id 保持上下文）
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "session_id": "session-def456",
    "query": "第一条是什么？"
  }'
```

### GET /v1/npc/sessions/{session_id}

获取会话摘要

```bash
curl http://localhost:8001/api/v1/npc/sessions/session-def456 \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"

# 响应
{
  "session_id": "session-def456",
  "message_count": 6,
  "recent_messages": [
    {"role": "user", "content": "请问严氏家训有哪些？", "timestamp": "..."},
    {"role": "assistant", "content": "后生问得好...", "timestamp": "..."}
  ],
  "first_message_at": "2024-12-13T08:00:00Z",
  "last_message_at": "2024-12-13T08:05:00Z"
}
```

### DELETE /v1/npc/sessions/{session_id}

清空会话记忆

```bash
curl -X DELETE http://localhost:8001/api/v1/npc/sessions/session-def456 \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"

# 响应
{"success": true, "session_id": "session-def456"}
```

### GET /v1/npc/traces/{trace_id}?include_session=true

追踪回放（包含会话摘要）

```bash
curl "http://localhost:8001/api/v1/npc/traces/trace-abc123?include_session=true" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"

# 响应
{
  "trace_id": "trace-abc123",
  "session_id": "session-def456",
  "request_input": {...},
  "tool_calls": [...],
  "session_summary": {
    "session_id": "session-def456",
    "message_count": 6,
    "recent_messages": [...]
  }
}
```

## 三轮连续对话示例

### 场景：用户询问严氏家训

```bash
# 第一轮：询问家训
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问严氏家训有哪些？"
  }'

# 响应
{
  "session_id": "session-abc123",
  "answer_text": "后生问得好。老夫当年定下家训十则：一曰孝悌为本，二曰耕读传家..."
}

# 第二轮：追问第一条（使用 session_id）
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "session_id": "session-abc123",
    "query": "第一条孝悌为本是什么意思？"
  }'

# 响应（NPC 记得之前聊过家训）
{
  "session_id": "session-abc123",
  "answer_text": "孝悌为本，乃是说孝顺父母、敬爱兄长是做人的根本..."
}

# 第三轮：继续追问
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "session_id": "session-abc123",
    "query": "有什么具体的故事吗？"
  }'

# 响应（NPC 理解"具体故事"是关于孝悌的）
{
  "session_id": "session-abc123",
  "answer_text": "说起孝悌，老夫想起一个故事..."
}
```

### Prompt 中的上下文格式

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

## 配置说明

### 环境变量

```bash
# 记忆配置
MEMORY_ENABLED=true          # 是否启用会话记忆
MEMORY_MAX_MESSAGES=10       # 最大消息条数
MEMORY_MAX_CHARS=4000        # 最大字符数
MEMORY_TTL_SECONDS=86400     # 会话 TTL（24 小时）

# Redis 配置
REDIS_URL=redis://localhost:6379/0
```

## 风险点与下一步

### 风险点

| 风险点 | 说明 |
|--------|------|
| **记忆当史实** | Prompt 中明确标注"仅供上下文"，但 LLM 可能仍会引用 |
| **Redis 不可用** | 优雅降级，不阻塞主流程 |
| **上下文过长** | 裁剪策略可能丢失重要信息 |
| **跨 NPC 混淆** | 同一 session 切换 NPC 可能导致上下文混乱 |
| **隐私泄露** | 会话内容存储在 Redis，需注意数据安全 |

### 下一步

1. **v0.2.0** - 添加会话摘要生成（LLM 总结长对话）
2. **v0.2.1** - 支持跨 NPC 会话隔离
3. **v0.2.2** - 添加会话导出功能
4. **v0.3.0** - 支持长期记忆（用户偏好持久化）
5. **v0.3.1** - 添加会话分析（热门话题统计）
