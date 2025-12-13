# P17 Evidence Gate 参数化与分角色策略指南

## 概述

将 Evidence Gate 从"硬编码规则"升级为"可配置策略"：不同 NPC/不同站点的 evidence 阈值、保守模板、允许的软断言范围都可配置。

## 架构设计

```text
┌─────────────────────────────────────────────────────────────┐
│                  data/policies/                             │
│           evidence_gate_policy_v0.1.json                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  defaults                                           │    │
│  │  ├── min_citations: 1                               │    │
│  │  ├── min_score: 0.3                                 │    │
│  │  ├── allowed_soft_claims: [据说, 相传, ...]         │    │
│  │  └── fallback_templates: {...}                      │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  sites                                              │    │
│  │  └── yantian-main                                   │    │
│  │      └── npcs                                       │    │
│  │          ├── ancestor_yan (严格: min=2, score=0.5)  │    │
│  │          ├── farmer_li (宽松: min=0, score=0.2)     │    │
│  │          └── craftsman_wang (中等)                  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     PolicyLoader                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  - 从 JSON 加载策略                                 │    │
│  │  - 缓存 + TTL（默认 60 秒）                         │    │
│  │  - 文件修改检测（热更新）                           │    │
│  │  - get_policy_for_context(site_id, npc_id)          │    │
│  │  - get_applied_rule() -> AppliedRule (审计)         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   EvidenceGateV3                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  check_before_llm(query, citations, site_id, npc_id)│    │
│  │  ├── 加载策略                                       │    │
│  │  ├── 分类意图                                       │    │
│  │  ├── 应用 per-npc 阈值                              │    │
│  │  └── 返回 EvidenceGateResult (含审计字段)           │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 文件树变更清单

### 新增文件

| 路径 | 说明 |
|------|------|
| `data/policies/evidence_gate_policy_v0.1.json` | 策略配置文件 |
| `app/guardrails/policy_loader.py` | 策略加载器（缓存 + TTL） |
| `app/guardrails/evidence_gate_v3.py` | 证据闸门 v3（策略驱动） |
| `tests/test_evidence_gate_policy.py` | 回归测试 |
| `docs/evidence-gate-policy-guide.md` | 本文档 |

### 修改文件

| 路径 | 变更 |
|------|------|
| `app/guardrails/__init__.py` | 导出 v3 模块 |

---

## 策略配置结构

### 完整示例

```json
{
  "version": "0.1.0",
  "updated_at": "2024-12-13T21:55:00Z",

  "defaults": {
    "min_citations": 1,
    "min_score": 0.3,
    "max_soft_claims": 2,
    "allowed_soft_claims": ["据说", "相传", "传说"],
    "fallback_templates": {
      "fact_seeking": "...",
      "out_of_scope": "...",
      "default": "..."
    },
    "strict_mode": false
  },

  "sites": {
    "yantian-main": {
      "npcs": {
        "ancestor_yan": {
          "min_citations": 2,
          "min_score": 0.5,
          "strict_mode": true,
          "allowed_soft_claims": ["据族谱记载"],
          "fallback_templates": {...}
        },
        "farmer_li": {
          "min_citations": 0,
          "min_score": 0.2,
          "max_soft_claims": 5,
          "strict_mode": false
        }
      }
    }
  },

  "intent_overrides": {
    "greeting": { "requires_evidence": false },
    "context_preference": { "requires_filtering": true }
  },

  "audit": {
    "log_policy_version": true,
    "log_applied_rule": true
  }
}
```

### 配置优先级

```text
NPC 配置 > Site 配置 > Defaults
```

---

## NPC 策略对比

| NPC | min_citations | min_score | max_soft_claims | strict_mode | 说明 |
|-----|---------------|-----------|-----------------|-------------|------|
| **ancestor_yan** | 2 | 0.5 | 1 | ✅ | 族谱权威，要求严格 |
| **farmer_li** | 0 | 0.2 | 5 | ❌ | 农耕知识，可以宽松 |
| **craftsman_wang** | 1 | 0.35 | 2 | ❌ | 建筑工艺，中等严格 |

---

## 软断言机制

### 什么是软断言

软断言是一种模糊表述，用于在没有确凿证据时表达不确定性：

- ✅ 允许：`据说`、`相传`、`老辈人讲`
- ❌ 禁止：`公元1368年`、`第5代祖先`

### 软断言配置

```json
{
  "allowed_soft_claims": ["据说", "相传", "老辈人讲"],
  "max_soft_claims": 2
}
```

### 严格模式 vs 宽松模式

| 模式 | 行为 |
|------|------|
| **strict_mode: true** | 检测到禁止断言直接拒绝 |
| **strict_mode: false** | 如果使用了软断言，可以通过 |

---

## 审计日志

### EvidenceGateResult 审计字段

```python
@dataclass
class EvidenceGateResult:
    # ... 其他字段 ...
    policy_version: str          # 策略版本
    policy_hash: str             # 策略 hash
    applied_rule: Dict[str, Any] # 应用的规则
```

### AppliedRule 结构

```python
@dataclass
class AppliedRule:
    policy_version: str
    policy_hash: str
    site_id: str
    npc_id: Optional[str]
    min_citations: int
    min_score: float
    max_soft_claims: int
    strict_mode: bool
    intent_override: Optional[str]
    applied_at: str  # ISO 时间戳
```

### 在 trace_ledger 中记录

```python
# 在 Agent Runtime 中
result = await evidence_gate.check_before_llm(...)

# 记录到 trace_ledger
trace_data = {
    "policy_version": result.policy_version,
    "policy_hash": result.policy_hash,
    "applied_rule": result.applied_rule,
    "passed": result.passed,
    "reason": result.reason,
}
```

---

## 热更新机制

### 缓存策略

```python
PolicyLoader(
    policy_path="data/policies/evidence_gate_policy_v0.1.json",
    cache_ttl_seconds=60,  # 60 秒 TTL
)
```

### 热更新触发条件

1. **TTL 过期**：缓存超过 60 秒
2. **文件修改**：检测到文件 mtime 变化

### 强制重新加载

```python
loader = get_policy_loader()
loader.reload()  # 强制重新加载
```

---

## 使用示例

### 基本使用

```python
from app.guardrails import EvidenceGateV3, get_policy_loader

# 创建证据闸门
gate = EvidenceGateV3()

# LLM 调用前检查
result = await gate.check_before_llm(
    query="严氏是什么时候迁来的？",
    citations=citations,
    site_id="yantian-main",
    npc_id="ancestor_yan",
)

if not result.passed:
    # 使用保守响应
    response = gate.get_conservative_response(
        intent=result.intent,
        query=query,
        npc_name="先祖",
        site_id="yantian-main",
        npc_id="ancestor_yan",
    )
```

### 审计日志

```python
# 记录到 trace_ledger
await trace_ledger.log({
    "event": "evidence_gate_check",
    "policy_version": result.policy_version,
    "applied_rule": result.applied_rule,
    "passed": result.passed,
})
```

---

## 测试命令

```bash
cd services/ai-orchestrator

# 运行策略测试
pytest tests/test_evidence_gate_policy.py -v

# 运行特定测试类
pytest tests/test_evidence_gate_policy.py::TestPolicyLoader -v
pytest tests/test_evidence_gate_policy.py::TestEvidenceGateV3 -v
pytest tests/test_evidence_gate_policy.py::TestDifferentNPCThresholds -v
pytest tests/test_evidence_gate_policy.py::TestSoftClaims -v
```

---

## 风险与下一步

| # | 风险/下一步 | 说明 |
|---|-------------|------|
| 1 | **策略版本管理** | 支持多版本策略，A/B 测试 |
| 2 | **策略 UI** | Admin Console 可视化编辑策略 |
| 3 | **策略验证** | JSON Schema 校验策略格式 |
| 4 | **策略继承** | 支持站点继承默认，NPC 继承站点 |
| 5 | **策略回滚** | 支持快速回滚到上一版本 |
