# Embedding Usage 审计与成本监控

## 概述

本文档描述 embedding 调用的审计、去重、成本估算和限流治理机制。

## 核心概念

### 状态定义

| 状态 | 说明 | 是否调用 API |
|------|------|-------------|
| `success` | 成功获取向量 | ✅ 是 |
| `failed` | API 调用失败 | ✅ 是 |
| `rate_limited` | 触发限流 | ✅ 是 |
| `dedup_hit` | Hash 去重命中 | ❌ 否 |

### 指标口径

| 指标 | 计算公式 | 说明 |
|------|----------|------|
| `total_records` | COUNT(*) | 所有审计记录数 |
| `total_embedding_calls` | success + failed + rate_limited | 真实 API 调用数 |
| `api_call_success_rate` | success / total_embedding_calls | 真实 API 调用成功率 |
| `dedup_hit_rate` | dedup_hit / total_records | 去重命中率 |
| `avg_latency_ms` | AVG(latency_ms) WHERE status != 'dedup_hit' | 平均延迟（仅真实调用） |
| `p95_latency_ms` | PERCENTILE_CONT(0.95) WHERE status != 'dedup_hit' | P95 延迟 |

## API 接口

### GET /v1/embedding/usage/summary

获取 embedding 使用统计汇总。

**参数**:
- `range`: 时间范围，如 `24h`, `7d`, `30d`
- `tenant_id`: 租户 ID（可选）
- `site_id`: 站点 ID（可选）

**响应示例**:
```json
{
  "time_range": "24h",
  "start_time": "2025-12-13T00:00:00Z",
  "end_time": "2025-12-14T00:00:00Z",
  "total_records": 100,
  "total_embedding_calls": 20,
  "total_success": 18,
  "total_failed": 1,
  "total_rate_limited": 1,
  "total_dedup_hit": 80,
  "total_chars": 50000,
  "total_tokens_estimate": 25000,
  "total_cost_estimate": 0.0025,
  "api_call_success_rate": 90.0,
  "dedup_hit_rate": 80.0,
  "avg_latency_ms": 450.5,
  "p95_latency_ms": 890.2,
  "by_provider_model": [
    {
      "provider": "baidu",
      "model": "bge-large-zh",
      "calls": 20,
      "success_count": 18,
      "success_rate": 90.0
    }
  ]
}
```

### GET /v1/embedding/usage/recent

获取最近的 embedding 使用记录。

## 去重机制

### Hash 计算

```python
content_hash = sha256(text.encode()).hexdigest()
```

### 去重判断

1. 计算当前内容的 `content_hash`
2. 与已有的 `vector_hash` 比较
3. 如果相同，记录 `dedup_hit` 并跳过 embedding 调用
4. 如果不同，调用 embedding API 并更新 `vector_hash`

## 限流重试

### 策略

- 最大重试次数: 3
- 退避算法: 指数退避 (10s, 20s, 40s)
- 状态码 429 触发限流处理

### 审计记录

限流时记录:
- `status`: `rate_limited`
- `backoff_seconds`: 实际等待秒数
- `retry_count`: 重试次数

## 成本估算

### 定价配置

```python
EMBEDDING_PRICING = {
    "openai": {
        "text-embedding-3-small": 0.00002,  # USD per 1K tokens
        "text-embedding-3-large": 0.00013,
    },
    "baidu": {
        "bge-large-zh": 0.0001,
        "embedding-v1": 0.0001,
    },
}
```

### Token 估算

```python
estimated_tokens = len(text) // 2  # 粗略估算
```

## 维度一致性校验

### 规则

在首次调用 Qdrant 前，校验:
- 配置的 `VECTOR_DIM` (1024)
- Qdrant collection 的 `vector_size`

如果不一致，**立即失败**并记录审计。

### 错误处理

```python
if qdrant_dim != VECTOR_DIM:
    raise RuntimeError(f"embedding_dim mismatch: expected {VECTOR_DIM}, Qdrant has {qdrant_dim}")
```

## 数据保留策略

### 清理脚本

```bash
# Dry run
python scripts/cleanup_embedding_usage.py --days 30 --dry-run

# 执行清理
python scripts/cleanup_embedding_usage.py --days 30
```

### 建议配置

- 生产环境: 保留 30 天
- 开发环境: 保留 7 天

### Cron 配置

```cron
# 每天凌晨 3 点清理 30 天前的数据
0 3 * * * /path/to/python /path/to/scripts/cleanup_embedding_usage.py --days 30
```

---

## 生产纪律

### 1. embedding_dim 不一致 = 阻断上线

这是最常见的隐性事故源。维度不一致会导致:
- 向量检索结果完全错误
- 静默失败，难以排查

**检查清单**:
- [ ] 确认 embedding 模型输出维度
- [ ] 确认 Qdrant collection 配置维度
- [ ] 确认 `VECTOR_DIM` 配置一致

### 2. 成功率指标必须区分"真实调用成功率"与"去重命中率"

混淆这两个指标会误导运营决策:
- 高去重率 + 低 API 成功率 = 需要关注 API 稳定性
- 低去重率 + 高 API 成功率 = 需要优化去重逻辑
- 高去重率 + 高 API 成功率 = 理想状态

**监控告警建议**:
- `api_call_success_rate < 95%` → P1 告警
- `dedup_hit_rate < 50%` → 检查是否有大量重复导入
- `p95_latency_ms > 2000` → 检查网络或 API 状态
