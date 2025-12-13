# Release Gate 发布门禁

## 概述

Release Gate 是严田平台的发布治理系统，用于管理策略、Prompt、实验等配置的统一发布。每个 Release 是一个包含多种配置的发布包，支持：

- **版本化管理**：每个发布包有唯一 ID 和名称
- **状态流转**：draft → active → archived
- **一键激活**：切换当前生效的配置
- **快速回滚**：回退到历史版本
- **完整性校验**：激活前自动校验引用资源是否存在
- **审计追踪**：所有操作记录到审计日志

---

## Release Payload 结构

```json
{
  "evidence_gate_policy_version": "v1.0-strict",
  "feedback_routing_policy_version": null,
  "prompts_active_map": {
    "npc-laonong": "1",
    "npc-xiaohua": "2"
  },
  "experiment_id": "exp-abc123",
  "retrieval_defaults": {
    "strategy": "hybrid",
    "top_k": 5
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `evidence_gate_policy_version` | string | 否 | Evidence Gate Policy 版本号 |
| `feedback_routing_policy_version` | string | 否 | Feedback Routing Policy 版本号 |
| `prompts_active_map` | object | 否 | NPC Prompt 版本映射，格式 `{npc_id: version}` |
| `experiment_id` | string | 否 | 关联的 A/B 实验 ID |
| `retrieval_defaults` | object | 否 | 检索默认配置 |

### retrieval_defaults 子字段

| 字段 | 类型 | 范围 | 说明 |
|------|------|------|------|
| `strategy` | string | trgm, qdrant, hybrid, semantic | 检索策略 |
| `top_k` | integer | 1-50 | 返回结果数量 |

---

## 激活门禁（Integrity Check）

### 校验时机

- `POST /v1/releases/{id}/activate` - 激活前校验
- `POST /v1/releases/{id}/rollback` - 回滚前校验
- `GET /v1/releases/{id}/validate` - 预检（不修改数据）

### 校验项

| 校验项 | 错误码 | 说明 |
|--------|--------|------|
| Policy 存在性 | `missing_policy` | `evidence_gate_policy_version` 必须在 Policy 表中存在 |
| Prompt 存在性 | `missing_prompt` | `prompts_active_map` 中每个 `npc_id@version` 必须存在 |
| Experiment 存在性 | `missing_experiment` | `experiment_id` 若非空必须在 Experiment 表中存在 |
| Experiment 状态 | `invalid_experiment_status` | Experiment 必须为 draft 或 active 状态 |
| 检索策略 | `invalid_retrieval_strategy` | `strategy` 必须为允许的值 |
| Top K 范围 | `invalid_retrieval_top_k` | `top_k` 必须在 1-50 之间 |

### 校验结果格式

```json
{
  "ok": false,
  "errors": [
    {"code": "missing_prompt", "detail": "Prompt 'npc-laonong@v99' not found"},
    {"code": "missing_policy", "detail": "Policy version 'v1.0-strict' not found"}
  ]
}
```

---

## API 端点

### 创建 Release

```http
POST /v1/releases
Content-Type: application/json
X-Internal-API-Key: <key>

{
  "tenant_id": "yantian",
  "site_id": "yantian-main",
  "name": "Release v1.0",
  "description": "首次发布",
  "payload": {
    "evidence_gate_policy_version": "v1.0-strict",
    "prompts_active_map": {"npc-laonong": "1"}
  }
}
```

### 预检 Release

```http
GET /v1/releases/{release_id}/validate
```

**响应示例（校验通过）：**
```json
{
  "ok": true,
  "errors": []
}
```

**响应示例（校验失败）：**
```json
{
  "ok": false,
  "errors": [
    {"code": "missing_prompt", "detail": "Prompt 'npc-laonong@v99' not found"}
  ]
}
```

### 激活 Release

```http
POST /v1/releases/{release_id}/activate
X-Internal-API-Key: <key>
```

**成功响应：** HTTP 200 + Release 详情

**失败响应（校验不通过）：** HTTP 400
```json
{
  "detail": {
    "ok": false,
    "errors": [
      {"code": "missing_policy", "detail": "Policy version 'v1.0-strict' not found"}
    ]
  }
}
```

### 回滚 Release

```http
POST /v1/releases/{release_id}/rollback
X-Internal-API-Key: <key>
```

回滚前同样会进行完整性校验。

---

## 常见失败原因与处理

### 1. missing_policy

**原因：** `evidence_gate_policy_version` 引用的 Policy 版本不存在

**处理步骤：**
1. 检查 Policy 表中是否存在该版本
2. 若不存在，先创建 Policy 版本
3. 或修改 Release payload 使用已存在的版本

### 2. missing_prompt

**原因：** `prompts_active_map` 中的 NPC Prompt 版本不存在

**处理步骤：**
1. 检查 `npc_prompts` 表中是否存在该 `npc_id` + `version` 组合
2. 注意 tenant_id 和 site_id 维度
3. 若不存在，先创建 Prompt 版本
4. 或修改 Release payload 使用已存在的版本

### 3. missing_experiment

**原因：** `experiment_id` 引用的实验不存在

**处理步骤：**
1. 检查 `experiments` 表中是否存在该实验
2. 若不存在，先创建实验
3. 或将 `experiment_id` 设为 null

### 4. invalid_experiment_status

**原因：** 实验存在但状态不允许（如 completed 或 paused）

**处理步骤：**
1. 将实验状态改为 draft 或 active
2. 或将 `experiment_id` 设为 null

### 5. invalid_retrieval_strategy

**原因：** `retrieval_defaults.strategy` 不是允许的值

**处理步骤：**
1. 修改为允许的值：trgm, qdrant, hybrid, semantic
2. 或移除 `retrieval_defaults` 字段

---

## 审计日志

所有激活/回滚操作都会记录到 `admin_audit_log` 表：

| action | 说明 |
|--------|------|
| `release.create` | 创建 Release |
| `release.activate_success` | 激活成功 |
| `release.activate_failed` | 激活失败（校验不通过） |
| `release.rollback_success` | 回滚成功 |
| `release.rollback_failed` | 回滚失败（校验不通过） |

**失败日志 payload 示例：**
```json
{
  "name": "Release v1.0",
  "errors": [
    {"code": "missing_prompt", "detail": "Prompt 'npc-laonong@v99' not found"}
  ]
}
```

---

## 最佳实践

1. **先预检再激活**：在 Admin Console 中点击激活前，先调用 `/validate` 接口预检
2. **保持资源同步**：确保 Release 引用的 Policy、Prompt、Experiment 都已创建
3. **渐进式发布**：先在测试环境验证，再发布到生产环境
4. **保留历史版本**：不要删除已使用的 Policy/Prompt 版本，以便回滚
5. **监控审计日志**：定期检查 `activate_failed` 日志，发现配置问题

---

## 示例流程

### 成功激活流程

```bash
# 1. 创建 Release
curl -X POST http://localhost:8000/api/v1/releases \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: test-key" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "name": "Release v1.0",
    "payload": {
      "evidence_gate_policy_version": "v1.0",
      "prompts_active_map": {"npc-laonong": "1"}
    }
  }'

# 2. 预检
curl http://localhost:8000/api/v1/releases/{release_id}/validate
# 返回: {"ok": true, "errors": []}

# 3. 激活
curl -X POST http://localhost:8000/api/v1/releases/{release_id}/activate \
  -H "X-Internal-API-Key: test-key"
# 返回: Release 详情，status: "active"
```

### 失败激活流程

```bash
# 1. 创建引用不存在资源的 Release
curl -X POST http://localhost:8000/api/v1/releases \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: test-key" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "name": "Release v2.0",
    "payload": {
      "evidence_gate_policy_version": "v99-not-exist",
      "prompts_active_map": {"npc-laonong": "999"}
    }
  }'

# 2. 预检
curl http://localhost:8000/api/v1/releases/{release_id}/validate
# 返回:
# {
#   "ok": false,
#   "errors": [
#     {"code": "missing_policy", "detail": "Policy version 'v99-not-exist' not found"},
#     {"code": "missing_prompt", "detail": "Prompt 'npc-laonong@v999' not found"}
#   ]
# }

# 3. 尝试激活（会失败）
curl -X POST http://localhost:8000/api/v1/releases/{release_id}/activate \
  -H "X-Internal-API-Key: test-key"
# 返回: HTTP 400
# {
#   "detail": {
#     "ok": false,
#     "errors": [...]
#   }
# }
```
