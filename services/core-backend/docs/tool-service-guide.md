# 工具服务指南

## 概述

工具服务提供类 MCP 的 HTTP Tool Server，将 core-backend 的业务能力以工具化接口暴露给 ai-orchestrator 调用。

**核心特性：**
- Schema 校验：所有输入输出通过 Pydantic v2 校验
- 鉴权上下文：强制携带 tenant_id, site_id, trace_id
- 结构化审计：所有调用写入 trace_ledger
- 全链路追踪：trace_id 贯穿整个调用链

## API 接口

### POST /tools/list

获取可用工具列表。

**请求头（必需）：**
```
X-Tenant-ID: yantian
X-Site-ID: yantian-main
X-Trace-ID: trace-xxx
```

**请求体：**
```json
{
  "category": null,
  "ai_callable_only": true
}
```

**响应：**
```json
{
  "tools": [
    {
      "name": "get_npc_profile",
      "version": "1.0.0",
      "description": "获取 NPC 人设配置",
      "category": "npc",
      "input_schema": {...},
      "output_schema": {...},
      "requires_auth": true,
      "ai_callable": true
    }
  ],
  "total": 6
}
```

### POST /tools/call

执行工具调用。

**请求头（必需）：**
```
X-Tenant-ID: yantian
X-Site-ID: yantian-main
X-Trace-ID: trace-xxx
```

**请求头（可选）：**
```
X-Span-ID: span-xxx
X-User-ID: user-xxx
X-Session-ID: session-xxx
X-NPC-ID: ancestor_yan
X-Internal-API-Key: your-internal-api-key
```

**请求体：**
```json
{
  "tool_name": "search_content",
  "input": {
    "query": "严氏家训",
    "limit": 10
  },
  "context": {
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "trace_id": "trace-xxx"
  }
}
```

**响应（成功）：**
```json
{
  "success": true,
  "output": {
    "items": [...],
    "total": 3,
    "query": "严氏家训"
  },
  "audit": {
    "trace_id": "trace-xxx",
    "tool_name": "search_content",
    "status": "success",
    "latency_ms": 45,
    "request_payload_hash": "a1b2c3d4"
  }
}
```

**响应（失败）：**
```json
{
  "success": false,
  "error": "NPC profile not found: unknown_npc",
  "error_type": "ValueError",
  "audit": {
    "trace_id": "trace-xxx",
    "tool_name": "get_npc_profile",
    "status": "error",
    "latency_ms": 12,
    "error_type": "ValueError",
    "error_message": "NPC profile not found: unknown_npc",
    "request_payload_hash": "e5f6g7h8"
  }
}
```

---

## 可用工具

### 1. get_npc_profile

获取 NPC 人设配置。

**输入：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| npc_id | string | ✓ | NPC ID |
| version | int | - | 指定版本号，不填则返回 active 版本 |

**输出：**
```json
{
  "npc_id": "ancestor_yan",
  "version": 1,
  "active": true,
  "name": "严氏先祖",
  "persona": {...},
  "knowledge_domains": ["严氏家族历史", "祖训家规"],
  "greeting_templates": ["后生来了？..."],
  "max_response_length": 500,
  "must_cite_sources": true
}
```

### 2. search_content

搜索内容/知识库。

**输入：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| query | string | ✓ | 搜索关键词 |
| content_type | string | - | 内容类型过滤 |
| tags | string[] | - | 标签过滤 |
| status | string | - | 状态过滤，默认 "published" |
| limit | int | - | 返回数量，默认 10，最大 50 |

**输出：**
```json
{
  "items": [
    {
      "id": "xxx",
      "content_type": "knowledge",
      "title": "严氏家训十则",
      "body": "...",
      "credibility_score": 0.98,
      "verified": true
    }
  ],
  "total": 1,
  "query": "严氏家训"
}
```

### 3. get_site_map

获取站点地图。

**输入：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| include_pois | bool | - | 是否包含兴趣点，默认 true |
| include_routes | bool | - | 是否包含路线，默认 false |

**输出：**
```json
{
  "site_id": "yantian-main",
  "site_name": "严田古村",
  "pois": [
    {"id": "xxx", "name": "严氏祠堂", "type": "heritage"}
  ],
  "routes": []
}
```

### 4. create_draft_content

创建草稿内容。

**输入：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| content_type | string | ✓ | 内容类型 |
| title | string | ✓ | 标题 |
| body | string | ✓ | 正文 |
| summary | string | - | 摘要 |
| tags | string[] | - | 标签 |
| domains | string[] | - | 知识领域 |
| source | string | - | 来源 |

**输出：**
```json
{
  "content_id": "xxx",
  "status": "draft",
  "created_at": "2024-12-13T12:00:00Z"
}
```

### 5. log_user_event

记录用户事件。

**输入：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| event_type | string | ✓ | 事件类型 |
| event_data | object | - | 事件数据 |
| user_id | string | - | 用户 ID |
| session_id | string | - | 会话 ID |

**输出：**
```json
{
  "event_id": "xxx",
  "logged_at": "2024-12-13T12:00:00Z"
}
```

### 6. get_prompt_active

获取 NPC 当前激活的 Prompt（为 P8 预留）。

**输入：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| npc_id | string | ✓ | NPC ID |
| prompt_type | string | - | Prompt 类型：system/greeting/fallback |

**输出：**
```json
{
  "npc_id": "ancestor_yan",
  "prompt_type": "system",
  "prompt_text": "你是严氏先祖...",
  "version": 1,
  "metadata": {
    "name": "严氏先祖",
    "knowledge_domains": ["严氏家族历史"]
  }
}
```

---

## curl 示例

### 1. 获取工具列表

```bash
curl -X POST http://localhost:8000/api/tools/list \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -H "X-Trace-ID: trace-$(date +%s)" \
  -d '{"ai_callable_only": true}'
```

### 2. 搜索内容

```bash
curl -X POST http://localhost:8000/api/tools/call \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -H "X-Trace-ID: trace-$(date +%s)" \
  -d '{
    "tool_name": "search_content",
    "input": {
      "query": "严氏家训",
      "limit": 5
    },
    "context": {
      "tenant_id": "yantian",
      "site_id": "yantian-main",
      "trace_id": "trace-001"
    }
  }'
```

### 3. 获取 NPC 人设

```bash
curl -X POST http://localhost:8000/api/tools/call \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -H "X-Trace-ID: trace-$(date +%s)" \
  -d '{
    "tool_name": "get_npc_profile",
    "input": {
      "npc_id": "ancestor_yan"
    },
    "context": {
      "tenant_id": "yantian",
      "site_id": "yantian-main",
      "trace_id": "trace-002"
    }
  }'
```

### 4. 创建草稿内容

```bash
curl -X POST http://localhost:8000/api/tools/call \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -H "X-Trace-ID: trace-$(date +%s)" \
  -d '{
    "tool_name": "create_draft_content",
    "input": {
      "content_type": "knowledge",
      "title": "严田村古井传说",
      "body": "村中心的古井相传有千年历史...",
      "tags": ["传说", "古井"]
    },
    "context": {
      "tenant_id": "yantian",
      "site_id": "yantian-main",
      "trace_id": "trace-003"
    }
  }'
```

### 5. 获取 Prompt

```bash
curl -X POST http://localhost:8000/api/tools/call \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" \
  -H "X-Trace-ID: trace-$(date +%s)" \
  -d '{
    "tool_name": "get_prompt_active",
    "input": {
      "npc_id": "ancestor_yan",
      "prompt_type": "system"
    },
    "context": {
      "tenant_id": "yantian",
      "site_id": "yantian-main",
      "trace_id": "trace-004"
    }
  }'
```

---

## 审计与观测

### 审计记录

所有工具调用自动写入 `trace_ledger` 表：

| 字段 | 说明 |
|------|------|
| trace_id | 追踪 ID |
| tool_calls | 工具调用详情（JSONB） |
| latency_ms | 延迟（毫秒） |
| status | 状态（success/error） |
| error | 错误信息 |

### 结构化日志

日志格式为 JSON，包含：

```json
{
  "event": "tool_call_success",
  "trace_id": "trace-xxx",
  "tool_name": "search_content",
  "tenant_id": "yantian",
  "site_id": "yantian-main",
  "latency_ms": 45,
  "timestamp": "2024-12-13T12:00:00Z"
}
```

---

## 运行测试

```bash
cd services/core-backend

# 运行集成测试
pytest tests/test_tools_integration.py -v

# 运行所有测试
pytest tests/ -v
```

---

## 风险点与下一步

### 风险点

1. **鉴权机制** - 当前仅支持 X-Internal-API-Key，生产环境需要更完善的服务间鉴权
2. **限流** - 未实现工具调用限流，高并发下可能影响性能
3. **重试机制** - 工具调用失败后无自动重试
4. **超时控制** - 未实现工具执行超时控制

### 下一步

1. **v0.1.1** - 添加工具调用限流
2. **v0.1.2** - 实现服务间 JWT 鉴权
3. **v0.2.0** - 支持工具执行超时和重试
4. **v0.3.0** - 接入 MCP 官方协议
