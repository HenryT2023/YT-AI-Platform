# 可靠性工程指南

## 概述

本模块将 ai-orchestrator 从"能跑"提升到"可稳定运行"：

- **Redis 缓存**：安全读工具结果缓存
- **Per-tool 超时**：防止长尾延迟拖垮系统
- **指数退避重试**：应对瞬时故障
- **降级策略**：关键工具失败时优雅降级

## 文件树变更清单

### 新增文件

```text
services/ai-orchestrator/
├── app/cache/
│   ├── __init__.py           # Cache 模块导出
│   ├── client.py             # Redis 缓存客户端
│   └── keys.py               # Key 命名规范 + TTL 配置
├── app/tools/
│   └── resilient_client.py   # 弹性工具客户端
└── tests/
    └── test_cache_performance.py  # 性能验证测试
```

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/core/config.py` | 添加 CACHE_ENABLED, CACHE_DEFAULT_TTL |
| `app/tools/__init__.py` | 导出 ResilientToolClient |
| `app/agent/runtime.py` | 使用 ResilientToolClient，合并审计记录 |

## 缓存 Key 规范

### Key 格式

```text
{prefix}:{tenant_id}:{site_id}:{resource_type}:{resource_id}
```

### 示例

| 资源类型 | Key 示例 |
|----------|----------|
| NPC Profile | `yantian:tenant1:site1:npc_profile:ancestor_yan` |
| Prompt Active | `yantian:tenant1:site1:prompt:ancestor_yan:active` |
| Site Map | `yantian:tenant1:site1:site_map:default` |
| Evidence | `yantian:tenant1:site1:evidence:a1b2c3d4` (query hash) |

## TTL 配置表

| 工具名称 | 超时(ms) | 重试次数 | TTL(s) | 可缓存 | 优先级 |
|----------|----------|----------|--------|--------|--------|
| `get_prompt_active` | 200 | 2 | 300 | ✅ | CRITICAL |
| `get_npc_profile` | 300 | 2 | 300 | ✅ | CRITICAL |
| `get_site_map` | 300 | 1 | 600 | ✅ | OPTIONAL |
| `retrieve_evidence` | 800 | 1 | 60 | ✅ | IMPORTANT |
| `search_content` | 500 | 1 | - | ❌ | IMPORTANT |
| `log_user_event` | 150 | 0 | - | ❌ | OPTIONAL |
| `create_trace` | 300 | 1 | - | ❌ | IMPORTANT |

### 超时配置理由

- **get_prompt_active (200ms)**：关键路径，必须快速返回，有缓存兜底
- **get_npc_profile (300ms)**：关键路径，数据量小，有缓存兜底
- **get_site_map (300ms)**：非关键，可跳过
- **retrieve_evidence (800ms)**：涉及搜索，允许较长时间
- **log_user_event (150ms)**：非关键，异步化，失败静默

## 降级策略

### 优先级定义

| 优先级 | 说明 | 失败处理 |
|--------|------|----------|
| CRITICAL | 关键工具 | 整体失败 |
| IMPORTANT | 重要工具 | 降级处理 |
| OPTIONAL | 可选工具 | 跳过 |

### 降级流程

```text
工具调用
    ↓
检查缓存 → 命中 → 返回缓存结果
    ↓ 未命中
调用工具（带超时）
    ↓ 超时/失败
重试（指数退避）
    ↓ 重试失败
根据优先级处理：
  - CRITICAL: 抛出异常
  - IMPORTANT: 返回空/默认值，切换 conservative 模式
  - OPTIONAL: 静默跳过
```

## 运行与联调步骤

### 1. 启动 Redis

```bash
# Docker
docker run -d --name redis -p 6379:6379 redis:7

# 或本地安装
brew install redis
redis-server
```

### 2. 配置环境变量

```bash
# .env
REDIS_URL=redis://localhost:6379/0
CACHE_ENABLED=true
CACHE_DEFAULT_TTL=300
```

### 3. 运行测试

```bash
cd services/ai-orchestrator

# 运行缓存测试
pytest tests/test_cache_performance.py -v

# 输出 TTL 表
pytest tests/test_cache_performance.py::TestPerformanceVerification::test_ttl_table -v -s
```

## 最小性能验证

### 场景：同一 NPC 连续对话 5 次

```bash
# 启动服务
uvicorn app.main:app --reload --port 8001

# 连续调用 5 次
for i in {1..5}; do
  echo "=== Call $i ==="
  curl -s -X POST http://localhost:8001/api/v1/npc/chat \
    -H "Content-Type: application/json" \
    -d '{
      "tenant_id": "yantian",
      "site_id": "yantian-main",
      "npc_id": "ancestor_yan",
      "query": "请问严氏家训有哪些？"
    }' | jq '.trace_id'
  sleep 0.5
done
```

### 预期结果

| 调用次数 | 实际工具调用 | 缓存命中 |
|----------|--------------|----------|
| 第 1 次 | 3 (profile + prompt + evidence) | 0 |
| 第 2-5 次 | 0 | 3 |

### 验证方式

查看日志输出：

```text
# 第 1 次调用
tool_call_success tool_name=get_npc_profile latency_ms=50
tool_call_success tool_name=get_prompt_active latency_ms=30
tool_call_success tool_name=retrieve_evidence latency_ms=200

# 第 2 次调用
tool_cache_hit tool_name=get_npc_profile latency_ms=1
tool_cache_hit tool_name=get_prompt_active latency_ms=1
tool_cache_hit tool_name=retrieve_evidence latency_ms=1
```

### 统计输出

```python
# 获取缓存统计
from app.cache import get_cache

cache = await get_cache()
stats = cache.get_stats()
print(stats)
# {
#   "hits": 12,
#   "misses": 3,
#   "errors": 0,
#   "hit_rate": "80.00%",
#   "connected": true
# }
```

## 审计记录格式

每次工具调用都会记录到 trace_ledger 的 tool_calls：

```json
{
  "tool_calls": [
    {
      "name": "get_npc_profile",
      "status": "cache_hit",
      "latency_ms": 1,
      "retries": 0,
      "cache_hit": true
    },
    {
      "name": "get_prompt_active",
      "status": "success",
      "latency_ms": 45,
      "retries": 0,
      "cache_hit": false
    },
    {
      "name": "retrieve_evidence",
      "status": "error",
      "latency_ms": 800,
      "retries": 1,
      "cache_hit": false,
      "error": "Timeout after 800ms"
    }
  ]
}
```

## 风险点与下一步

### 风险点

| 风险点 | 说明 |
|--------|------|
| **Redis 不可用** | 缓存模块优雅降级，不阻塞主流程 |
| **缓存穿透** | 短 TTL 的 evidence 可能频繁穿透 |
| **缓存一致性** | Prompt/Profile 更新后需手动失效 |
| **超时过短** | 网络抖动可能导致频繁超时 |
| **重试风暴** | 高并发下重试可能加剧压力 |

### 下一步

1. **v0.2.0** - 添加缓存失效 Webhook（Prompt/Profile 更新时）
2. **v0.2.1** - 添加熔断器（Circuit Breaker）
3. **v0.2.2** - 添加缓存预热机制
4. **v0.3.0** - 添加分布式限流
5. **v0.3.1** - 添加 Prometheus 指标导出
