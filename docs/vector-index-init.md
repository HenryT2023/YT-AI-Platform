# 向量索引初始化与一致性校验

## 概述

本文档描述如何初始化和维护 Qdrant 向量索引，确保向量数据的完整性和一致性。

## 验收标准

```
向量索引初始化验收标准：
- coverage_ratio ≥ 98%
- stale_vectors = 0（或 ≤ 可接受阈值）
- 同步任务可重复执行，不产生重复向量
```

## 快速开始

### 1. 运行数据库迁移

```bash
cd services/core-backend
alembic upgrade head
```

### 2. 启动 Qdrant 服务

```bash
docker-compose -f docker-compose.dev.yml up -d qdrant
```

### 3. 执行全量同步

```bash
# 正式同步
python scripts/sync_vectors.py --tenant-id yantian

# 仅统计（不写入）
python scripts/sync_vectors.py --tenant-id yantian --dry-run

# 指定站点
python scripts/sync_vectors.py --tenant-id yantian --site-id yantian-main
```

### 4. 验证覆盖率

```bash
curl "http://localhost:8000/api/v1/retrieval/vector-coverage?tenant_id=yantian"
```

## API 参考

### GET /v1/retrieval/vector-coverage

获取向量覆盖率统计。

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| tenant_id | string | 是 | 租户 ID |
| site_id | string | 否 | 站点 ID |

**响应示例:**

```json
{
  "tenant_id": "yantian",
  "site_id": "yantian-main",
  "total_evidences": 1243,
  "vectorized_evidences": 1219,
  "coverage_ratio": 0.9807,
  "stale_vectors": 17,
  "never_vectorized": 7,
  "last_sync_at": "2025-12-13T10:31:12Z",
  "last_sync_status": "success",
  "last_sync_job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### GET /v1/retrieval/stale-evidences

获取过期/未向量化的 evidence 列表。

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| tenant_id | string | 是 | 租户 ID |
| site_id | string | 否 | 站点 ID |
| limit | int | 否 | 返回数量限制（默认 100） |

**响应示例:**

```json
{
  "tenant_id": "yantian",
  "site_id": null,
  "total": 24,
  "stale_count": 17,
  "never_vectorized_count": 7,
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "title": "严氏宗祠历史",
      "updated_at": "2025-12-13T09:00:00Z",
      "vector_updated_at": "2025-12-10T08:00:00Z",
      "reason": "stale"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "title": "新增证据",
      "updated_at": "2025-12-13T10:00:00Z",
      "vector_updated_at": null,
      "reason": "never_vectorized"
    }
  ]
}
```

### GET /v1/retrieval/sync-jobs

获取同步任务列表。

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| tenant_id | string | 是 | 租户 ID |
| site_id | string | 否 | 站点 ID |
| limit | int | 否 | 返回数量限制（默认 20） |

**响应示例:**

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "tenant_id": "yantian",
      "site_id": null,
      "job_type": "full_sync",
      "status": "success",
      "started_at": "2025-12-13T10:30:00Z",
      "finished_at": "2025-12-13T10:31:12Z",
      "total_items": 1243,
      "success_count": 1219,
      "skip_count": 17,
      "failure_count": 7,
      "progress_percent": 100.0,
      "duration_seconds": 72.5
    }
  ],
  "total": 5
}
```

## CLI 参考

### sync_vectors.py

```bash
python scripts/sync_vectors.py [OPTIONS]

Options:
  --tenant-id TEXT      租户 ID（必填）
  --site-id TEXT        站点 ID（可选）
  --dry-run             只统计，不写入 Qdrant
  --batch-size INT      批次大小（默认 50）
  --openai-key TEXT     OpenAI API Key
  --baidu-key TEXT      Baidu API Key
  --baidu-secret TEXT   Baidu Secret Key
```

**输出示例:**

```
🚀 开始向量同步...
   Tenant: yantian
   Site:   all
   Mode:   LIVE

============================================================
📊 向量同步结果
============================================================
  Job ID:       550e8400-e29b-41d4-a716-446655440000
  Tenant:       yantian
  Site:         all
  Dry Run:      False
------------------------------------------------------------
  总 Evidence:  1243
  成功向量化:   1219
  跳过(重复):   17
  失败:         7
------------------------------------------------------------
  覆盖率:       99.4%
  耗时:         72.50s
============================================================
```

## 数据模型

### Evidence 扩展字段

| 字段 | 类型 | 说明 |
|------|------|------|
| vector_updated_at | datetime | 最近向量化时间 |
| vector_hash | string(64) | 内容 hash（用于去重） |

### VectorSyncJob 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | 任务 ID |
| tenant_id | string | 租户 ID |
| site_id | string | 站点 ID |
| job_type | string | 任务类型：full_sync/incremental/repair |
| status | string | 状态：pending/running/success/partial_failed/failed |
| started_at | datetime | 开始时间 |
| finished_at | datetime | 结束时间 |
| total_items | int | 总条目数 |
| success_count | int | 成功数 |
| skip_count | int | 跳过数 |
| failure_count | int | 失败数 |
| progress_percent | float | 进度百分比 |
| error_summary | json | 错误摘要 |

## Stale 向量检测规则

1. **stale（过期）**: `evidence.updated_at > evidence.vector_updated_at`
   - 表示 evidence 内容已更新，但向量未同步

2. **never_vectorized（从未向量化）**: `evidence.vector_updated_at IS NULL`
   - 表示 evidence 从未被向量化

## 一致性保障

### 自动触发

当 evidence 创建或更新时，worker 会自动触发 `vectorize_evidence` 任务：

```python
from app.tasks.vectorize import vectorize_evidence

vectorize_evidence.delay(
    evidence_id=evidence.id,
    tenant_id=evidence.tenant_id,
    site_id=evidence.site_id,
    source_type=evidence.source_type,
    source_ref=evidence.source_ref,
    title=evidence.title,
    excerpt=evidence.excerpt,
    confidence=evidence.confidence,
    verified=evidence.verified,
    tags=evidence.tags,
    domains=evidence.domains,
)
```

### 定期检查

建议设置定时任务，定期检查覆盖率：

```bash
# crontab 示例：每天凌晨 2 点检查
0 2 * * * curl -s "http://localhost:8000/api/v1/retrieval/vector-coverage?tenant_id=yantian" | jq '.coverage_ratio'
```

### 修复脚本

当发现 stale 向量时，重新运行同步：

```bash
python scripts/sync_vectors.py --tenant-id yantian
```

## 故障排查

### 覆盖率低于 98%

1. 检查 embedding API 配置
2. 查看同步任务错误日志
3. 检查 Qdrant 服务状态

### 同步任务失败

1. 检查 `error_summary` 字段
2. 查看 worker 日志
3. 验证 Qdrant 连接

### Qdrant 连接失败

```bash
# 检查 Qdrant 状态
curl http://localhost:6333/collections

# 重启 Qdrant
docker-compose -f docker-compose.dev.yml restart qdrant
```

## 监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| coverage_ratio | 向量覆盖率 | < 0.98 |
| stale_vectors | 过期向量数 | > 0 |
| sync_job_failure_rate | 同步失败率 | > 0.05 |
| sync_job_duration | 同步耗时 | > 300s |

## 下一步

1. 集成到 CI/CD 流程
2. 添加 Prometheus 指标导出
3. 实现增量同步
4. 添加 Admin Console UI
