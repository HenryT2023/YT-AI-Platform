# 严田平台运维手册 (Ops Runbook)

## 概述

本手册提供灰度上线期间的运维指南，包括：
- 告警诊断与处置
- 日常巡检清单
- 紧急回滚流程
- 常见问题排查

---

## 快速参考

### 告警评估 API

```bash
# 评估当前告警（15分钟窗口）
curl "http://localhost:8000/api/v1/alerts/evaluate?tenant_id=yantian&range=15m"

# 获取告警摘要
curl "http://localhost:8000/api/v1/alerts/summary?tenant_id=yantian"

# 查看告警规则
curl "http://localhost:8000/api/v1/alerts/rules"
```

### 关键 API 端点

| 用途 | 端点 |
|------|------|
| 健康检查 | `GET /health` |
| 告警评估 | `GET /v1/alerts/evaluate` |
| 向量覆盖率 | `GET /v1/retrieval/vector-coverage` |
| Embedding 统计 | `GET /v1/embedding/usage/summary` |
| 反馈统计 | `GET /v1/feedback/stats` |
| Release 状态 | `GET /v1/releases/active` |
| Trace 列表 | `GET /v1/trace` |

---

## 灰度每日巡检 3 分钟清单

### 第 1 分钟：健康检查

```bash
# 1. 服务健康
curl -s http://localhost:8000/health | jq '.status'
# 期望: "healthy"

# 2. 告警摘要
curl -s "http://localhost:8000/api/v1/alerts/summary?tenant_id=yantian" | jq '{has_alerts, alert_count, critical_codes}'
# 期望: has_alerts=false 或无 critical
```

### 第 2 分钟：核心指标

```bash
# 3. 向量覆盖率
curl -s "http://localhost:8000/api/v1/retrieval/vector-coverage?tenant_id=yantian" | jq '{coverage_ratio, stale_vectors}'
# 期望: coverage_ratio > 0.9, stale_vectors < 50

# 4. Embedding 成本
curl -s "http://localhost:8000/api/v1/embedding/usage/summary?range=24h&tenant_id=yantian" | jq '{total_cost_estimate, api_call_success_rate}'
# 期望: success_rate > 95%, cost < 预算
```

### 第 3 分钟：业务指标

```bash
# 5. 反馈积压
curl -s "http://localhost:8000/api/v1/feedback/stats?tenant_id=yantian" | jq '.by_status'
# 关注: pending 和 overdue 数量

# 6. 当前 Release
curl -s "http://localhost:8000/api/v1/releases/active?tenant_id=yantian&site_id=yantian-main" | jq '{name, status, activated_at}'
# 确认: 当前激活的 release 是否正确
```

---

## 告警诊断与处置

### Health 类告警

#### health.core_backend_down (Critical)

**症状：** Core Backend 服务不可用，API 无响应

**诊断步骤：**
1. 检查服务状态
   ```bash
   # Docker
   docker ps | grep core-backend
   docker logs core-backend --tail=100
   
   # Kubernetes
   kubectl get pods -l app=core-backend
   kubectl logs -l app=core-backend --tail=100
   ```

2. 检查数据库连接
   ```bash
   curl http://localhost:8000/health
   ```

3. 检查资源使用
   ```bash
   docker stats core-backend
   ```

**处置动作：**
1. 如果容器崩溃，重启服务
2. 如果数据库连接失败，检查 PostgreSQL 状态
3. 如果资源不足，扩容或优化

---

#### health.qdrant_down (Critical)

**症状：** Qdrant 向量数据库不可用

**诊断步骤：**
1. 检查 Qdrant 服务
   ```bash
   curl http://localhost:6333/health
   docker logs qdrant --tail=100
   ```

2. 检查网络连通性
   ```bash
   nc -zv localhost 6333
   ```

**处置动作：**
1. 重启 Qdrant 服务
2. 系统会自动降级到 trgm 检索（PostgreSQL 全文搜索）
3. 恢复后触发向量同步

---

#### health.redis_down (High)

**症状：** Redis 缓存不可用

**诊断步骤：**
```bash
redis-cli ping
docker logs redis --tail=100
```

**处置动作：**
1. 重启 Redis 服务
2. 系统可降级运行，但会话缓存和限流将失效
3. 监控内存使用

---

### LLM 类告警

#### llm.success_rate_low (Critical)

**症状：** LLM API 调用成功率低于 95%

**诊断步骤：**
1. 查看错误分布
   ```bash
   curl "http://localhost:8000/api/v1/trace?status=error&limit=20" | jq '.[].error'
   ```

2. 检查 LLM Provider 状态
   - 阿里云 DashScope 控制台
   - OpenAI 状态页面

3. 检查 API 配额
   ```bash
   # 查看最近调用
   curl "http://localhost:8000/api/v1/trace?limit=50" | jq 'group_by(.status) | map({status: .[0].status, count: length})'
   ```

**处置动作：**
1. 如果是 Provider 故障，切换到备用 Provider
   ```bash
   # 修改环境变量
   export LLM_PROVIDER=openai  # 或 dashscope
   ```

2. 如果是配额问题，联系云服务商增加配额

3. 紧急情况启用 fallback 模式
   ```bash
   export LLM_FALLBACK_ENABLED=true
   ```

---

#### llm.fallback_rate_high (High)

**症状：** LLM 降级比例超过 10%

**诊断步骤：**
```bash
# 查看 fallback 原因
curl "http://localhost:8000/api/v1/trace?limit=100" | jq '[.[] | select(.status == "error")] | group_by(.error) | map({error: .[0].error, count: length})'
```

**处置动作：**
1. 检查主 LLM Provider 是否正常
2. 调整超时配置
3. 考虑增加重试次数

---

#### llm.p95_latency_high (Medium)

**症状：** LLM P95 延迟超过 5000ms

**诊断步骤：**
```bash
# 查看延迟分布
curl "http://localhost:8000/api/v1/trace?limit=100" | jq '[.[].latency_ms] | sort | .[95]'
```

**处置动作：**
1. 检查 prompt 长度，考虑精简
2. 切换到更快的模型
3. 检查网络延迟

---

### Gate 类告警

#### gate.conservative_rate_high (High)

**症状：** Evidence Gate 保守模式触发比例超过 30%

**诊断步骤：**
1. 检查 evidence 覆盖率
   ```bash
   curl "http://localhost:8000/api/v1/retrieval/vector-coverage?tenant_id=yantian"
   ```

2. 查看保守模式触发原因
   ```bash
   curl "http://localhost:8000/api/v1/trace?policy_mode=conservative&limit=20" | jq '.[].policy_reason'
   ```

**处置动作：**
1. 如果覆盖率低，触发向量同步
2. 检查检索策略配置
3. 考虑放宽 Evidence Gate 阈值
4. 回滚到之前的 Release（如果是配置问题）
   ```bash
   curl -X POST "http://localhost:8000/api/v1/releases/{previous_release_id}/rollback" \
     -H "X-Internal-API-Key: your-key"
   ```

---

#### gate.refuse_rate_high (Medium)

**症状：** 系统拒绝回答比例超过 5%

**诊断步骤：**
```bash
curl "http://localhost:8000/api/v1/trace?policy_mode=refuse&limit=20" | jq '.[].request_input.query'
```

**处置动作：**
1. 检查敏感词过滤规则
2. 调整 Evidence Gate Policy
3. 查看是否有恶意请求

---

#### gate.citations_rate_low (Medium)

**症状：** 回答中包含引用的比例低于 70%

**诊断步骤：**
```bash
# 查看无引用的 trace
curl "http://localhost:8000/api/v1/trace?limit=50" | jq '[.[] | select(.evidence_ids == null or (.evidence_ids | length) == 0)]'
```

**处置动作：**
1. 检查 evidence 检索是否正常
2. 检查 prompt 是否要求引用
3. 检查向量索引健康状态

---

### Vector 类告警

#### vector.coverage_low (High)

**症状：** Evidence 向量化覆盖率低于 90%

**诊断步骤：**
```bash
# 查看未向量化的 evidence
curl "http://localhost:8000/api/v1/retrieval/stale-evidences?tenant_id=yantian&limit=50"

# 查看同步任务状态
curl "http://localhost:8000/api/v1/retrieval/sync-jobs?tenant_id=yantian"
```

**处置动作：**
1. 手动触发向量同步
   ```bash
   # 通过 worker 触发
   celery -A app.worker call tasks.sync_vectors --args='["yantian", "yantian-main"]'
   ```

2. 检查 embedding API 是否正常
3. 检查 worker 服务状态

---

#### vector.stale_count_high (Medium)

**症状：** 过期向量数超过 50 个

**诊断步骤：**
```bash
curl "http://localhost:8000/api/v1/retrieval/stale-evidences?tenant_id=yantian" | jq '.items | length'
```

**处置动作：**
1. 触发增量向量同步
2. 检查 worker 是否正常运行
3. 检查是否有大量内容更新

---

### Embedding 类告警

#### embedding.daily_cost_high (Medium)

**症状：** Embedding 日成本超过 $10

**诊断步骤：**
```bash
curl "http://localhost:8000/api/v1/embedding/usage/summary?range=24h&tenant_id=yantian" | jq '{total_cost_estimate, total_embedding_calls, dedup_hit_rate}'
```

**处置动作：**
1. 检查是否有异常批量调用
2. 检查去重缓存是否生效
3. 考虑降低调用频率

---

#### embedding.rate_limited_high (High)

**症状：** Embedding API 被限流比例超过 5%

**诊断步骤：**
```bash
curl "http://localhost:8000/api/v1/embedding/usage/recent?status=rate_limited&limit=20"
```

**处置动作：**
1. 联系 embedding provider 增加配额
2. 启用请求队列和限流
3. 切换到备用 embedding provider

---

### Feedback 类告警

#### feedback.overdue_count_high (High)

**症状：** 逾期反馈数超过 10 个

**诊断步骤：**
```bash
curl "http://localhost:8000/api/v1/feedback?overdue=true&status=pending" | jq 'length'
```

**处置动作：**
1. 优先处理 critical/high 级别反馈
2. 考虑增加运营人员
3. 检查反馈分配规则

---

#### feedback.backlog_high (Medium)

**症状：** 待处理反馈总数超过 50 个

**处置动作：**
1. 批量处理低优先级反馈
2. 考虑自动化处理部分反馈

---

## 紧急回滚流程

### Release 回滚

```bash
# 1. 查看历史 release
curl "http://localhost:8000/api/v1/releases?tenant_id=yantian&site_id=yantian-main&status=archived"

# 2. 预检目标 release
curl "http://localhost:8000/api/v1/releases/{release_id}/validate"

# 3. 执行回滚
curl -X POST "http://localhost:8000/api/v1/releases/{release_id}/rollback" \
  -H "X-Internal-API-Key: your-key"

# 4. 验证回滚成功
curl "http://localhost:8000/api/v1/releases/active?tenant_id=yantian&site_id=yantian-main"
```

### 实验暂停

```bash
# 暂停实验
curl -X PATCH "http://localhost:8000/api/v1/experiments/{experiment_id}/status" \
  -H "Content-Type: application/json" \
  -d '{"status": "paused"}'
```

### 检索策略切换

```bash
# 修改 retrieval_defaults
# 通过新建 release 并激活
curl -X POST "http://localhost:8000/api/v1/releases" \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: your-key" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "name": "Emergency - Switch to trgm",
    "payload": {
      "retrieval_defaults": {"strategy": "trgm", "top_k": 5}
    }
  }'

# 然后激活
curl -X POST "http://localhost:8000/api/v1/releases/{new_release_id}/activate" \
  -H "X-Internal-API-Key: your-key"
```

---

## 联系方式

| 角色 | 联系方式 | 职责 |
|------|----------|------|
| 平台 SRE | sre@example.com | 基础设施、告警响应 |
| 后端开发 | backend@example.com | 代码问题、API 故障 |
| AI 工程师 | ai@example.com | LLM、向量检索问题 |
| 运营 | ops@example.com | 反馈处理、内容问题 |

---

## 附录

### 环境变量参考

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ALERT_WEBHOOK_URL` | 告警 webhook 地址 | 无 |
| `LLM_PROVIDER` | LLM 提供商 | dashscope |
| `LLM_FALLBACK_ENABLED` | 是否启用 fallback | false |
| `EMBEDDING_PROVIDER` | Embedding 提供商 | dashscope |

### 日志查看

```bash
# 结构化日志查询
docker logs core-backend 2>&1 | grep "error" | jq '.'

# 按 trace_id 查询
docker logs core-backend 2>&1 | grep "trace_id=tr-xxx" | jq '.'
```
