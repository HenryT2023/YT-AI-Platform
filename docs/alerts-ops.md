# 告警系统运维指南

## 概述

严田平台告警系统提供：
- **告警评估**：基于配置化规则评估系统指标
- **告警去重**：同一告警在 firing 状态不重复通知
- **告警静默**：按 alert_code 或 severity 临时静默
- **事件存储**：告警事件历史记录，支持复盘
- **上下文记录**：记录 active_release_id、active_experiment_id
- **定时评估**：每 5 分钟自动评估

---

## 快速开始

### 手动评估告警

```bash
# 简单评估（不持久化）
curl "http://localhost:8000/api/v1/alerts/evaluate?tenant_id=yantian&range=15m"

# 评估并持久化（带去重、静默、事件写入）
curl -X POST "http://localhost:8000/api/v1/alerts/evaluate-persist?tenant_id=yantian&range=15m"
```

### 查看告警事件

```bash
# 列出所有事件
curl "http://localhost:8000/api/v1/alerts/events?tenant_id=yantian"

# 仅 firing 状态
curl "http://localhost:8000/api/v1/alerts/events?tenant_id=yantian&status=firing"

# 最近 24 小时
curl "http://localhost:8000/api/v1/alerts/events?tenant_id=yantian&since=2024-12-13T00:00:00"
```

### 创建静默

```bash
# 静默特定告警 1 小时
curl -X POST "http://localhost:8000/api/v1/alerts/silences" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "alert_code": "gate.conservative_rate_high",
    "duration_minutes": 60,
    "reason": "正在调整 Evidence Gate 阈值"
  }'

# 静默所有 medium 级别告警 2 小时
curl -X POST "http://localhost:8000/api/v1/alerts/silences" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "severity": "medium",
    "duration_minutes": 120,
    "reason": "灰度期间暂时忽略中等级别告警"
  }'
```

---

## 去重规则

### 去重键（dedup_key）

格式：`{tenant_id}|{site_id}|{alert_code}|{window}`

示例：`yantian|yantian-main|gate.conservative_rate_high|15m`

### 去重逻辑

1. **首次触发**：创建新的 AlertEvent，状态为 `firing`，发送 webhook
2. **重复触发**：更新 `last_seen_at`，**不发送 webhook**
3. **告警解决**：状态变为 `resolved`，记录 `resolved_at`
4. **再次触发**：创建新的 AlertEvent，发送 webhook

### 示例流程

```
T0: 告警触发 → 创建事件 ae-001 (firing) → 发送 webhook ✓
T5: 告警持续 → 更新 ae-001.last_seen_at → 不发送 webhook ✗
T10: 告警持续 → 更新 ae-001.last_seen_at → 不发送 webhook ✗
T15: 告警解决 → ae-001.status = resolved
T20: 告警再次触发 → 创建事件 ae-002 (firing) → 发送 webhook ✓
```

---

## 静默规则

### 匹配逻辑

静默规则按以下优先级匹配：

1. **精确匹配 alert_code**：仅静默指定告警
2. **匹配 severity**：静默该级别的所有告警
3. **全局静默**：alert_code 和 severity 都为空时，静默所有告警

### 静默 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/alerts/silences` | POST | 创建静默 |
| `/v1/alerts/silences` | GET | 列出静默 |
| `/v1/alerts/silences/{id}` | DELETE | 删除静默 |

### 静默请求参数

```json
{
  "tenant_id": "yantian",
  "site_id": "yantian-main",      // 可选，空表示全局
  "alert_code": "gate.xxx",       // 可选，空表示匹配所有
  "severity": "high",             // 可选，空表示匹配所有
  "duration_minutes": 60,         // 1-10080（最长 7 天）
  "reason": "静默原因",
  "created_by": "admin_console"
}
```

### 静默最佳实践

1. **明确原因**：创建静默时填写 reason，便于审计
2. **最小范围**：优先使用 alert_code 精确静默，避免全局静默
3. **合理时长**：根据处理时间设置，避免过长静默
4. **及时清理**：问题解决后删除静默规则

---

## 告警事件查询与复盘

### 事件结构

```json
{
  "id": "ae-xxx",
  "tenant_id": "yantian",
  "site_id": "yantian-main",
  "alert_code": "gate.conservative_rate_high",
  "severity": "high",
  "status": "firing",
  "window": "15m",
  "current_value": 35.5,
  "threshold": 30.0,
  "condition": ">",
  "unit": "%",
  "dedup_key": "yantian|yantian-main|gate.conservative_rate_high|15m",
  "first_seen_at": "2024-12-14T02:00:00Z",
  "last_seen_at": "2024-12-14T02:15:00Z",
  "resolved_at": null,
  "context": {
    "active_release_id": "rel-xxx",
    "active_release_name": "Release v1.0",
    "active_experiment_id": "exp-xxx",
    "active_experiment_name": "A/B Test",
    "recommended_actions": ["..."]
  },
  "webhook_sent": "sent",
  "webhook_sent_at": "2024-12-14T02:00:00Z"
}
```

### 复盘路径

1. **查询告警事件**
   ```bash
   curl "http://localhost:8000/api/v1/alerts/events?tenant_id=yantian&since=2024-12-13T00:00:00"
   ```

2. **查看事件上下文**
   - `active_release_id`：当时生效的 Release
   - `active_experiment_id`：当时运行的实验
   - `metrics_snapshot`：当时的指标快照

3. **关联 trace_ledger**
   ```bash
   curl "http://localhost:8000/api/v1/trace?release_id=rel-xxx&limit=50"
   ```

4. **检查 Release 历史**
   ```bash
   curl "http://localhost:8000/api/v1/releases/{release_id}/history"
   ```

---

## 定时评估配置

### 脚本使用

```bash
# 直接运行
python scripts/run_alerts_cron.py

# 指定参数
python scripts/run_alerts_cron.py --tenant-id yantian --site-id yantian-main --range 15m

# Dry run（不持久化）
python scripts/run_alerts_cron.py --dry-run

# 不发送 webhook
python scripts/run_alerts_cron.py --no-webhook
```

### crontab 配置

```bash
# 每 5 分钟评估一次
*/5 * * * * cd /app && python scripts/run_alerts_cron.py >> /var/log/alerts_cron.log 2>&1
```

### Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: alerts-evaluator
  namespace: yantian
spec:
  schedule: "*/5 * * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: alerts-cron
            image: yantian/core-backend:latest
            command:
            - python
            - scripts/run_alerts_cron.py
            - --tenant-id
            - yantian
            - --site-id
            - yantian-main
            env:
            - name: CORE_BACKEND_URL
              value: "http://core-backend:8000"
            - name: ALERT_WEBHOOK_URL
              valueFrom:
                secretKeyRef:
                  name: alerts-config
                  key: webhook-url
          restartPolicy: OnFailure
```

### 灰度期默认配置

| 参数 | 值 | 说明 |
|------|-----|------|
| 评估间隔 | 5 分钟 | 平衡及时性和资源消耗 |
| 评估窗口 | 15m | 避免瞬时波动触发告警 |
| Webhook 通知 | 仅 critical/high | 避免告警疲劳 |
| 静默最长时间 | 7 天 | 防止遗忘 |

---

## API 参考

### 评估 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/alerts/evaluate` | GET | 评估告警（不持久化） |
| `/v1/alerts/evaluate-persist` | POST | 评估并持久化（带去重、静默） |
| `/v1/alerts/summary` | GET | 告警摘要 |
| `/v1/alerts/rules` | GET | 告警规则列表 |

### 事件 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/alerts/events` | GET | 列出告警事件 |
| `/v1/alerts/events/{id}` | GET | 获取事件详情 |

### 静默 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/alerts/silences` | POST | 创建静默 |
| `/v1/alerts/silences` | GET | 列出静默 |
| `/v1/alerts/silences/{id}` | DELETE | 删除静默 |

---

## 示例 JSON

### 告警事件

```json
{
  "id": "ae-abc123",
  "tenant_id": "yantian",
  "site_id": "yantian-main",
  "alert_code": "llm.success_rate_low",
  "severity": "critical",
  "status": "firing",
  "window": "15m",
  "current_value": 85.0,
  "threshold": 95.0,
  "condition": "<",
  "unit": "%",
  "dedup_key": "yantian|yantian-main|llm.success_rate_low|15m",
  "first_seen_at": "2024-12-14T02:00:00Z",
  "last_seen_at": "2024-12-14T02:15:00Z",
  "resolved_at": null,
  "context": {
    "active_release_id": "rel-v1.0",
    "active_release_name": "Release v1.0",
    "active_experiment_id": null,
    "recommended_actions": [
      "检查 LLM Provider 状态",
      "考虑切换到备用 Provider"
    ]
  },
  "webhook_sent": "sent",
  "webhook_sent_at": "2024-12-14T02:00:00Z"
}
```

### 静默规则

```json
{
  "id": "as-xyz789",
  "tenant_id": "yantian",
  "site_id": null,
  "alert_code": "gate.conservative_rate_high",
  "severity": null,
  "starts_at": "2024-12-14T02:00:00Z",
  "ends_at": "2024-12-14T03:00:00Z",
  "reason": "正在调整 Evidence Gate 阈值",
  "created_by": "admin_console",
  "created_at": "2024-12-14T02:00:00Z",
  "is_active": true
}
```

### Webhook 通知 payload

```json
{
  "timestamp": "2024-12-14T02:00:00Z",
  "tenant_id": "yantian",
  "site_id": "yantian-main",
  "alert_count": 1,
  "alerts": [
    {
      "code": "llm.success_rate_low",
      "severity": "critical",
      "current_value": 85.0,
      "threshold": 95.0,
      "condition": "<",
      "unit": "%",
      "first_seen_at": "2024-12-14T02:00:00Z"
    }
  ],
  "context": {
    "active_release_id": "rel-v1.0",
    "active_release_name": "Release v1.0",
    "active_experiment_id": null,
    "active_experiment_name": null
  }
}
```

---

## 故障排查

### 告警不触发

1. 检查告警规则是否加载
   ```bash
   curl "http://localhost:8000/api/v1/alerts/rules" | jq '.rule_count'
   ```

2. 检查指标是否正常收集
   ```bash
   curl "http://localhost:8000/api/v1/alerts/evaluate?tenant_id=yantian" | jq '.metrics_snapshot'
   ```

3. 检查是否被静默
   ```bash
   curl "http://localhost:8000/api/v1/alerts/silences?tenant_id=yantian"
   ```

### Webhook 不发送

1. 检查环境变量
   ```bash
   echo $ALERT_WEBHOOK_URL
   ```

2. 检查告警级别（仅 critical/high 发送）

3. 检查去重（同一告警不重复发送）
   ```bash
   curl "http://localhost:8000/api/v1/alerts/events?tenant_id=yantian&status=firing"
   ```

### 事件不写入

1. 确认使用 `/evaluate-persist` 而非 `/evaluate`

2. 检查数据库连接
   ```bash
   curl "http://localhost:8000/health"
   ```

3. 检查迁移是否执行
   ```bash
   alembic current
   ```
