# P12 端到端联调与可观测性指南

## 概述

本指南提供端到端联调脚本与指标聚合接口，使系统进入"可监控可迭代"的状态。

## 文件树变更清单

### 新增文件

```text
/
├── docker-compose.dev.yml           # 最小化开发环境
├── scripts/
│   └── e2e_chat_test.py             # 端到端对话测试脚本
└── services/ai-orchestrator/
    ├── app/api/v1/
    │   ├── observability.py         # 健康检查 + 指标聚合
    │   └── trace.py                 # Trace 统一视图
    └── docs/
        └── e2e-guide.md             # 本文档
```

### 修改文件

| 文件 | 变更 |
|------|------|
| `Makefile` | 添加 dev-up, dev-down, dev-logs, dev-healthz, e2e-chat targets |
| `app/api/__init__.py` | 注册 observability 和 trace 路由 |

## 运行步骤

### 1. 一键启动开发环境

```bash
# 启动最小化开发环境（Postgres + Redis + core-backend + ai-orchestrator）
make dev-up

# 查看日志
make dev-logs

# 检查健康状态
make dev-healthz

# 停止
make dev-down
```

### 2. 手动启动（不使用 Docker）

```bash
# 终端 1: 启动基础设施
make infra-up

# 终端 2: 启动 core-backend
make dev-backend

# 终端 3: 启动 ai-orchestrator
make dev-orchestrator

# 终端 4: 运行 e2e 测试
make e2e-chat
```

### 3. 运行端到端测试

```bash
# 使用默认配置
python scripts/e2e_chat_test.py

# 指定参数
python scripts/e2e_chat_test.py \
  --base-url http://localhost:8001 \
  --tenant-id yantian \
  --site-id yantian-main \
  --npc-id ancestor_yan
```

## API 接口

### GET /api/v1/healthz

深度健康检查，检查所有依赖组件。

```bash
curl http://localhost:8001/api/v1/healthz | jq .
```

响应示例：

```json
{
  "status": "healthy",
  "service": "ai-orchestrator",
  "version": "0.2.0",
  "timestamp": "2024-12-13T09:00:00Z",
  "components": [
    {"name": "redis", "status": "healthy", "latency_ms": 2},
    {"name": "tool_server", "status": "healthy", "latency_ms": 15},
    {"name": "llm_provider", "status": "healthy", "latency_ms": 5},
    {"name": "session_memory", "status": "healthy", "latency_ms": 3}
  ],
  "uptime_seconds": 3600
}
```

### GET /api/v1/metrics/summary

指标聚合，返回最近 N 分钟的关键指标。

```bash
curl "http://localhost:8001/api/v1/metrics/summary?minutes=5" | jq .
```

响应示例：

```json
{
  "time_range_minutes": 5,
  "total_requests": 100,
  "success_count": 95,
  "error_count": 5,
  "success_rate": 0.95,
  "latency_p50_ms": 200,
  "latency_p95_ms": 500,
  "latency_p99_ms": 800,
  "cache_hit_ratio": 0.6,
  "policy_distribution": {
    "normal": 80,
    "conservative": 15,
    "refuse": 5
  },
  "top_tool_failures": [
    {"tool_name": "retrieve_evidence", "failure_count": 3, "last_error": "timeout"}
  ],
  "llm_stats": {
    "provider": "baidu",
    "sandbox_mode": true
  }
}
```

### GET /api/v1/traces/{trace_id}/unified

Trace 统一视图，整合 tool_calls + llm_audit + prompt_version + citations。

```bash
curl "http://localhost:8001/api/v1/traces/trace-abc123/unified?include_session=true" \
  -H "X-Tenant-ID: yantian" \
  -H "X-Site-ID: yantian-main" | jq .
```

响应示例：

```json
{
  "trace_id": "trace-abc123",
  "tenant_id": "yantian",
  "site_id": "yantian-main",
  "request_type": "npc_chat",
  "status": "success",
  "query": "请问严氏家训有哪些？",
  "npc_id": "ancestor_yan",
  "policy_mode": "normal",
  "answer_text": "后生问得好...",
  "latency_ms": 350,
  "prompt": {
    "version": 1,
    "source": "prompt_registry",
    "npc_id": "ancestor_yan"
  },
  "tool_calls": [
    {"name": "get_npc_profile", "status": "success", "latency_ms": 20, "cache_hit": true},
    {"name": "get_prompt_active", "status": "success", "latency_ms": 15},
    {"name": "retrieve_evidence", "status": "success", "latency_ms": 100}
  ],
  "llm_audit": {
    "provider": "baidu",
    "model": "ernie-4.0-8k",
    "tokens_input": 500,
    "tokens_output": 200,
    "latency_ms": 200,
    "fallback": false
  },
  "citations": [
    {"evidence_id": "ev-001", "title": "严氏家训", "confidence": 0.95}
  ],
  "session": {
    "session_id": "session-def456",
    "message_count": 6,
    "recent_messages": [
      {"role": "user", "content": "请问严氏家训有哪些？"},
      {"role": "assistant", "content": "后生问得好..."}
    ]
  }
}
```

## 端到端测试示例

### 测试输出示例

```text
============================================================
  严田 AI 文明引擎 - 端到端测试
============================================================
  Base URL: http://localhost:8001
  Tenant: yantian
  Site: yantian-main
  NPC: ancestor_yan

============================================================
  1. 健康检查
============================================================
基本健康: ✅ healthy
深度健康: ✅ healthy
  redis: ✅ healthy (2ms)
  tool_server: ✅ healthy (15ms)
  llm_provider: ✅ healthy (5ms)
  session_memory: ✅ healthy (3ms)

============================================================
  2. 多轮对话测试
============================================================

--- 第 1 轮 ---
问题: 请问严氏家训有哪些？
状态: ✅ 成功 (350ms)
trace_id: trace-abc123
session_id: session-def456
policy_mode: normal
回答: 后生问得好。老夫当年定下家训十则：一曰孝悌为本，二曰耕读传家...

--- 第 2 轮 ---
问题: 第一条孝悌为本是什么意思？
状态: ✅ 成功 (280ms)
trace_id: trace-abc124
session_id: session-def456
policy_mode: normal
回答: 孝悌为本，乃是说孝顺父母、敬爱兄长是做人的根本...

--- 第 3 轮 ---
问题: 有什么具体的故事吗？
状态: ✅ 成功 (320ms)
trace_id: trace-abc125
session_id: session-def456
policy_mode: normal
回答: 说起孝悌，老夫想起一个故事...

============================================================
  3. 会话状态检查
============================================================
状态: ✅ 成功
session_id: session-def456
消息数: 6
最近消息:
  user: 请问严氏家训有哪些？
  assistant: 后生问得好。老夫当年定下家训十则...
  user: 第一条孝悌为本是什么意思？
  assistant: 孝悌为本，乃是说孝顺父母、敬爱兄长是做人的根本...

============================================================
  4. Trace 统一视图
============================================================
状态: ✅ 成功
trace_id: trace-abc125
request_type: npc_chat
policy_mode: normal
latency_ms: 320
prompt_version: 1
prompt_source: prompt_registry
llm_provider: baidu
llm_model: ernie-4.0-8k
tokens: in=500, out=200
工具调用: 4 个
  get_npc_profile: ✅ success
  get_prompt_active: ✅ success
  get_session_memory: ✅ success
  retrieve_evidence: ✅ success

============================================================
  5. 指标摘要
============================================================
状态: ✅ 成功
总请求数: 3
成功率: 100.0%
P95 延迟: 350ms
缓存命中率: 33.3%
策略分布: normal=3, conservative=0, refuse=0

============================================================
  测试摘要
============================================================
对话轮数: 3
session_id: session-def456
trace_ids:
    - trace-abc123
    - trace-abc124
    - trace-abc125

✅ 端到端测试通过
```

## 架构图

```text
┌─────────────────────────────────────────────────────────────────┐
│                        docker-compose.dev.yml                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Postgres   │    │    Redis     │    │   Qdrant     │       │
│  │    :5432     │    │    :6379     │    │   (可选)     │       │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘       │
│         │                   │                                    │
│         │                   │                                    │
│  ┌──────▼───────────────────▼───────┐                           │
│  │         core-backend :8000        │                           │
│  │  ┌─────────────────────────────┐ │                           │
│  │  │ /tools/call                 │ │                           │
│  │  │ /health                     │ │                           │
│  │  │ trace_ledger                │ │                           │
│  │  └─────────────────────────────┘ │                           │
│  └──────────────┬───────────────────┘                           │
│                 │                                                │
│                 │ HTTP                                           │
│                 │                                                │
│  ┌──────────────▼───────────────────┐                           │
│  │      ai-orchestrator :8001       │                           │
│  │  ┌─────────────────────────────┐ │                           │
│  │  │ /api/v1/npc/chat            │ │  ← 对话入口               │
│  │  │ /api/v1/healthz             │ │  ← 深度健康检查           │
│  │  │ /api/v1/metrics/summary     │ │  ← 指标聚合               │
│  │  │ /api/v1/traces/{id}/unified │ │  ← Trace 统一视图         │
│  │  └─────────────────────────────┘ │                           │
│  │                                   │                           │
│  │  ┌─────────────────────────────┐ │                           │
│  │  │ AgentRuntime                │ │                           │
│  │  │ LLMProvider (Baidu/OpenAI)  │ │                           │
│  │  │ SessionMemory (Redis)       │ │                           │
│  │  │ ResilientToolClient         │ │                           │
│  │  └─────────────────────────────┘ │                           │
│  └──────────────────────────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 风险点与下一步

### 风险点

| 风险点 | 说明 | 缓解措施 |
|--------|------|----------|
| **指标存储内存** | 当前指标存储在内存中，重启丢失 | 生产环境使用 Prometheus/Redis |
| **Dockerfile 缺失** | docker/backend.Dockerfile 可能不存在 | 需要创建或使用本地启动 |
| **数据库迁移** | 首次启动需要迁移 | docker-compose.dev.yml 自动执行 |
| **LLM Sandbox** | 默认 Sandbox 模式，返回模拟数据 | 配置真实 API Key 关闭 Sandbox |
| **NPC 数据缺失** | 需要种子数据 | 运行 `make seed-data` |

### 下一步

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | **创建 Dockerfile** | 补充 docker/backend.Dockerfile |
| P1 | **种子数据脚本** | 创建 NPC、Prompt 种子数据 |
| P2 | **Prometheus 集成** | 替换内存指标存储 |
| P3 | **Grafana Dashboard** | 可视化监控面板 |
| P4 | **告警规则** | 成功率、延迟告警 |

## 快速验证命令

```bash
# 1. 启动开发环境
make dev-up

# 2. 等待服务就绪（约 30 秒）
sleep 30

# 3. 检查健康状态
make dev-healthz

# 4. 运行端到端测试
make e2e-chat

# 5. 查看指标
curl http://localhost:8001/api/v1/metrics/summary | jq .

# 6. 停止环境
make dev-down
```
