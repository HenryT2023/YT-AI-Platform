# Agent Runtime 指南

## 概述

Agent Runtime 实现 NPC 对话闭环：

```
输入对话 → 调工具取证据 → 生成回答 → 输出校验 → 写入证据链账本 → 返回客户端
```

**核心特性：**

- 通过 Tool Server 获取所有数据（不直接连数据库）
- 输出符合 Agent Output Protocol
- 无证据时进入 conservative 模式
- 所有调用写入 trace_ledger

## 文件树变更清单

### ai-orchestrator 新增文件

```text
services/ai-orchestrator/app/
├── tools/                          # Tool Client 模块
│   ├── __init__.py
│   ├── schemas.py                  # Schema 定义
│   └── client.py                   # Tool Server 客户端
├── llm/                            # LLM Adapter 模块
│   ├── __init__.py
│   ├── base.py                     # 基类
│   ├── baidu.py                    # 百度 LLM Adapter（占位）
│   └── factory.py                  # 工厂
├── agent/                          # Agent Runtime 模块
│   ├── __init__.py
│   ├── schemas.py                  # 请求/响应 Schema
│   ├── validator.py                # 输出校验器
│   └── runtime.py                  # Agent Runtime 实现
└── api/v1/
    └── npc.py                      # NPC 对话 API
```

### ai-orchestrator 修改文件

| 文件 | 变更 |
|------|------|
| `app/core/config.py` | 添加 TOOLS_BASE_URL、百度 LLM 配置 |
| `app/api/__init__.py` | 注册 NPC 路由 |

### core-backend 修改文件

| 文件 | 变更 |
|------|------|
| `app/tools/schemas.py` | 添加 retrieve_evidence Schema |
| `app/tools/registry.py` | 注册 retrieve_evidence 工具 |
| `app/tools/executor.py` | 实现 retrieve_evidence 处理器 |

## 本地运行步骤

### 1. 启动基础设施

```bash
cd /Users/hal/YT-AI-Platform
make infra-up
```

### 2. 启动 core-backend

```bash
cd services/core-backend

# 运行迁移
alembic upgrade head

# 导入种子数据
python scripts/seed_db.py

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### 3. 启动 ai-orchestrator

```bash
cd services/ai-orchestrator

# 安装依赖
pip install -e ".[dev]"

# 启动服务
uvicorn app.main:app --reload --port 8001
```

### 4. 使用 docker-compose（可选）

```bash
cd /Users/hal/YT-AI-Platform
docker-compose up -d
```

## API 接口

### POST /v1/npc/chat

NPC 对话闭环。

**请求体：**

```json
{
  "tenant_id": "yantian",
  "site_id": "yantian-main",
  "npc_id": "ancestor_yan",
  "query": "请问严氏家训有哪些？",
  "user_id": "user-001",
  "session_id": "session-001"
}
```

**响应（Agent Output Protocol）：**

```json
{
  "trace_id": "trace-abc123",
  "policy_mode": "normal",
  "answer_text": "严氏家训共有十则...",
  "citations": [
    {
      "evidence_id": "evidence-001",
      "title": "严氏家训十则",
      "source_ref": "《严氏族谱》",
      "excerpt": "一曰孝悌...",
      "confidence": 0.95
    }
  ],
  "followup_questions": [
    "能给我讲讲严氏家族历史吗？",
    "关于严氏家训十则，还有什么有趣的故事吗？"
  ],
  "npc_name": "严氏先祖",
  "latency_ms": 450,
  "timestamp": "2024-12-13T12:00:00Z"
}
```

### GET /v1/npc/traces/{trace_id}

追踪回放接口。

**请求头：**

```text
X-Tenant-ID: yantian
X-Site-ID: yantian-main
```

**响应：**

```json
{
  "trace_id": "trace-abc123",
  "request_type": "npc_chat",
  "request_input": {"query": "请问严氏家训有哪些？"},
  "tool_calls": [
    {"name": "get_npc_profile", "status": "success"},
    {"name": "get_prompt_active", "status": "success"},
    {"name": "retrieve_evidence", "status": "success", "count": 3}
  ],
  "evidence_ids": ["evidence-001", "evidence-002"],
  "policy_mode": "normal",
  "latency_ms": 450,
  "status": "success"
}
```

## curl 示例

### 1. NPC 对话

```bash
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -H "X-Trace-ID: trace-$(date +%s)" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问严氏家训有哪些？",
    "session_id": "session-001"
  }'
```

### 2. 追踪回放

```bash
curl http://localhost:8001/api/v1/npc/traces/trace-abc123 \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main"
```

### 3. 测试保守模式（无证据）

```bash
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问外星人存在吗？"
  }'
```

预期响应：

```json
{
  "policy_mode": "conservative",
  "answer_text": "这个问题我不太清楚，建议您询问村中其他长辈。"
}
```

## 策略模式说明

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| `normal` | 有足够证据（≥1 条，置信度 ≥0.5） | 正常回答，返回引用 |
| `conservative` | 证据不足 | 使用保守模板，不返回引用 |
| `refuse` | 敏感话题或禁止话题 | 拒绝回答 |

## 风险点与下一步

### 风险点

1. **LLM 占位实现** - 当前 BaiduLLMAdapter 返回模拟响应，需接入真实 API
2. **Tool Server 依赖** - orchestrator 完全依赖 core-backend，需确保高可用
3. **超时控制** - 未实现工具调用超时，长时间调用可能阻塞
4. **会话记忆** - 当前未实现多轮对话记忆
5. **向量检索** - retrieve_evidence 使用 LIKE 模糊匹配，效果有限

### 下一步

1. **v0.1.1** - 接入百度 ERNIE Bot API
2. **v0.1.2** - 添加会话记忆（Redis）
3. **v0.2.0** - 接入 Qdrant 向量检索
4. **v0.2.1** - 添加工具调用超时和重试
5. **v0.3.0** - 支持流式响应
