# 反馈运营工作流 (Feedback Ops)

## 概述

P23 实现了反馈的工单化机制，将反馈从"列表"升级为"可分派、可跟踪、可统计"的运营工作流。

## 状态机

```
new/pending → triaged → in_progress → resolved → closed
```

| 状态 | 说明 | 触发条件 |
|------|------|----------|
| `new`/`pending` | 新建 | 用户提交反馈 |
| `triaged` | 已分派 | 调用 triage API |
| `in_progress` | 处理中 | 调用 status API |
| `resolved` | 已解决 | 调用 resolve API |
| `closed` | 已关闭 | 调用 close API |

## SLA 机制

### 自动计算

根据 `severity` 和 `feedback_type` 自动计算 SLA：

| 严重程度 | 默认 SLA |
|----------|----------|
| `critical` | 2 小时 |
| `high` | 4-8 小时 |
| `medium` | 24 小时 |
| `low` | 72 小时 |

### 逾期扫描

```bash
# Dry run
python scripts/scan_feedback_overdue.py --dry-run

# 执行扫描
python scripts/scan_feedback_overdue.py
```

扫描条件：
- `status` 不是 `resolved` 或 `closed`
- `sla_due_at < now()`
- `overdue_flag = false`

## 自动分派规则

配置文件：`data/policies/feedback_routing_policy_v0.1.json`

### 规则结构

```json
{
  "rules": [
    {
      "id": "critical_all",
      "conditions": {
        "severity": "critical"
      },
      "action": {
        "assignee": "duty_manager",
        "group": "escalation",
        "sla_hours": 2
      },
      "priority": 100
    }
  ]
}
```

### 条件字段

- `severity`: low/medium/high/critical
- `type`: correction/fact_error/missing_info/...
- `site_id`: 站点 ID
- `npc_id`: NPC ID

### 优先级

规则按 `priority` 降序匹配，第一个匹配的规则生效。

## API 接口

### POST /v1/feedback/{id}/triage

分派反馈，应用自动分派规则。

**请求**:
```json
{
  "auto_route": true,
  "assignee": null,
  "group": null,
  "sla_hours": null
}
```

**响应**:
```json
{
  "id": "...",
  "status": "triaged",
  "assignee": "duty_manager",
  "group": "escalation",
  "sla_due_at": "2025-12-14T03:00:00Z"
}
```

### POST /v1/feedback/{id}/status

更新反馈状态。

**请求**:
```json
{
  "status": "in_progress",
  "notes": "开始处理"
}
```

### GET /v1/feedback/stats

获取增强的反馈统计。

**响应**:
```json
{
  "total": 100,
  "overdue_count": 5,
  "resolution_rate": 0.85,
  "avg_resolution_time_hours": 12.5,
  "backlog_by_status": {
    "new": 10,
    "triaged": 15,
    "in_progress": 8
  },
  "resolution_rate_by_assignee": {
    "alice": 95.0,
    "bob": 88.5
  },
  "avg_time_to_resolve_by_severity": {
    "critical": 1.5,
    "high": 4.2,
    "medium": 18.3
  }
}
```

## 数据模型

### 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `assignee` | string | 处理人 |
| `group` | string | 处理组 |
| `sla_due_at` | datetime | SLA 截止时间 |
| `overdue_flag` | bool | 是否逾期 |
| `triaged_at` | datetime | 分派时间 |
| `in_progress_at` | datetime | 开始处理时间 |
| `closed_at` | datetime | 关闭时间 |

### 索引

- `ix_user_feedbacks_assignee`
- `ix_user_feedbacks_group`
- `ix_user_feedbacks_sla_due_at`
- `ix_user_feedbacks_overdue_flag`
- `ix_user_feedbacks_overdue_scan` (复合索引)

## 验收步骤

### 1. 提交高优先级反馈

```bash
curl -X POST http://localhost:8000/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "feedback_type": "fact_error",
    "severity": "high",
    "content": "严田村的历史描述有误",
    "tenant_id": "yantian",
    "site_id": "yantian-main"
  }'
```

### 2. 分派反馈

```bash
curl -X POST http://localhost:8000/v1/feedback/{id}/triage \
  -H "Content-Type: application/json" \
  -d '{"auto_route": true}'
```

验证：
- `status` = `triaged`
- `group` = `content_team`（根据规则）
- `sla_due_at` 已设置

### 3. 模拟逾期

```sql
UPDATE user_feedbacks 
SET sla_due_at = now() - interval '1 hour'
WHERE id = '{id}';
```

### 4. 运行逾期扫描

```bash
python scripts/scan_feedback_overdue.py
```

验证：`overdue_flag` = `true`

### 5. 查看统计

```bash
curl "http://localhost:8000/v1/feedback/stats?tenant_id=yantian"
```

验证：`overdue_count` > 0

## Cron 配置

```cron
# 每 15 分钟扫描逾期反馈
*/15 * * * * /path/to/python /path/to/scripts/scan_feedback_overdue.py
```

## 风险与建议

1. **分派规则复杂度** - 当前规则较简单，生产环境可能需要更复杂的条件组合
2. **assignee 验证** - 当前 assignee 是字符串，未验证是否为有效用户
3. **通知机制** - 逾期后应触发通知（邮件/钉钉），当前仅标记
4. **权限控制** - triage/status API 应增加权限校验
5. **审计日志** - 状态变更应记录到审计日志
