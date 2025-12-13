# P13 证据闸门 Evidence-Gated Generation 指南

## 概述

证据闸门将"文化准确性"从提示词约束升级为机制：**事实性问题必须证据先行，否则强制保守**。

## 核心逻辑

```text
┌─────────────────────────────────────────────────────────────┐
│                     用户查询                                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              意图分类器 (Intent Classifier)                  │
│  ┌─────────────────────┐  ┌─────────────────────┐          │
│  │   fact_seeking      │  │ context_preference  │          │
│  │   事实性问题        │  │ 上下文偏好问题      │          │
│  └──────────┬──────────┘  └──────────┬──────────┘          │
└─────────────┼────────────────────────┼──────────────────────┘
              │                        │
              ▼                        ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│    检索证据              │  │    检索证据              │
│    retrieve_evidence    │  │    retrieve_evidence    │
└──────────┬──────────────┘  └──────────┬──────────────┘
           │                            │
           ▼                            ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│  证据闸门检查            │  │  证据闸门检查            │
│  citations >= 1?        │  │  允许使用会话记忆        │
│  ┌───────┐ ┌───────┐   │  │  但禁止史实断言          │
│  │ YES   │ │ NO    │   │  └─────────────────────────┘
│  │ ↓     │ │ ↓     │   │
│  │NORMAL │ │CONSER │   │
│  │       │ │VATIVE │   │
│  └───────┘ └───────┘   │
└─────────────────────────┘
```

## 文件树变更清单

### 新增文件

```text
services/ai-orchestrator/
├── app/guardrails/
│   ├── intent_classifier.py    # 意图分类器
│   └── evidence_gate.py        # 证据闸门
├── tests/
│   ├── redteam_cases.json      # 红队测试用例 (25 条)
│   └── test_redteam.py         # 红队测试
└── docs/
    └── evidence-gate-guide.md  # 本文档
```

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/guardrails/__init__.py` | 导出意图分类器和证据闸门 |
| `app/agent/runtime.py` | 集成证据闸门检查 |

## 意图分类规则

### fact_seeking（事实性问题）

需要证据支撑的问题类型：

| 类别 | 关键词示例 |
|------|-----------|
| 时间相关 | 哪一年、什么时候、何时、年代、朝代 |
| 人物相关 | 谁是、是谁、祖先、先祖、族谱、第几代 |
| 事件相关 | 发生了什么、历史事件、战争、迁移 |
| 地点相关 | 在哪里、从哪里来、迁自 |
| 数量相关 | 多少人、几个、多少代 |
| 验证相关 | 是真的吗、史实、记载、文献 |

### context_preference（上下文偏好问题）

可使用会话记忆的问题类型：

| 类别 | 关键词示例 |
|------|-----------|
| 偏好相关 | 喜欢、感兴趣、想了解、想听 |
| 建议相关 | 推荐、建议、应该、怎么办 |
| 情感相关 | 感觉、觉得、认为、看法 |
| 闲聊相关 | 你好、谢谢、再见、聊聊 |
| 追问相关 | 刚才、之前、继续、还有吗 |

## 禁止的史实断言

以下模式在无证据时会被检测并过滤：

```text
公元\d+年          → "很久以前"
\d{3,4}年          → "多年前"
距今\d+年          → "很多年前"
第\d+代            → "某一代"
康熙/乾隆/...年间  → "清朝某个时期"
洪武/永乐/...年间  → "明朝某个时期"
```

## 红队测试用例

共 25 条测试用例，覆盖以下场景：

| 类别 | 数量 | 说明 |
|------|------|------|
| fact_seeking_no_evidence | 3 | 询问具体年代/人名/年数 |
| memory_as_fact | 2 | 试图用对话记忆追问史实 |
| fabricate_genealogy | 2 | 诱导编造族谱 |
| fabricate_history | 3 | 诱导编造历史事件 |
| specific_date | 2 | 询问具体公元年份 |
| migration_history | 2 | 询问迁徙路线/原因 |
| population_data | 2 | 询问人口数据 |
| famous_ancestors | 2 | 询问历史名人 |
| document_reference | 2 | 引用族谱/县志询问 |
| context_preference_valid | 3 | 合法的上下文偏好问题 |
| mixed_intent | 1 | 混合意图问题 |
| indirect_fabrication | 1 | 假设性问题诱导编造 |

## 运行测试

```bash
# 运行红队测试
cd services/ai-orchestrator
pytest tests/test_redteam.py -v

# 运行特定测试
pytest tests/test_redteam.py::test_redteam_case -v

# 运行意图分类测试
pytest tests/test_redteam.py::TestQueryIntentClassifier -v

# 运行证据闸门测试
pytest tests/test_redteam.py::TestEvidenceGate -v
```

## API 行为变化

### 事实性问题无证据时

```bash
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "严氏始祖是哪一年迁到严田的？"
  }'

# 响应（无证据时）
{
  "trace_id": "trace-xxx",
  "session_id": "session-xxx",
  "policy_mode": "conservative",
  "answer_text": "这个问题涉及具体的历史事实，严氏先祖需要查阅族谱或文献才能准确回答。建议您询问村中管理族谱的长辈，或查阅相关史料记载。",
  "citations": []
}
```

### 事实性问题有证据时

```bash
# 假设知识库中有相关证据
{
  "trace_id": "trace-xxx",
  "session_id": "session-xxx",
  "policy_mode": "normal",
  "answer_text": "根据族谱记载，严氏始祖于明朝洪武年间迁入严田...",
  "citations": [
    {"evidence_id": "ev-001", "title": "严氏族谱", "confidence": 0.95}
  ]
}
```

### 上下文偏好问题

```bash
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "你觉得严氏家训对现代人有什么启发？"
  }'

# 响应（允许无证据回答）
{
  "trace_id": "trace-xxx",
  "session_id": "session-xxx",
  "policy_mode": "normal",
  "answer_text": "老夫认为，家训中的孝悌为本、耕读传家等理念，对现代人仍有重要启发...",
  "citations": []
}
```

## Trace 中的证据闸门记录

```json
{
  "tool_calls": [
    {"name": "get_npc_profile", "status": "success"},
    {"name": "get_prompt_active", "status": "success"},
    {"name": "retrieve_evidence", "status": "success", "count": 0},
    {
      "name": "evidence_gate",
      "status": "blocked",
      "intent": "fact_seeking",
      "citations_count": 0,
      "reason": "事实性问题，证据不足（需要 1，实际 0）"
    }
  ]
}
```

## 风险点与下一步

### 风险点

| 风险点 | 说明 | 缓解措施 |
|--------|------|----------|
| **误判意图** | 规则版分类器可能误判 | 后续升级为 LLM 分类 |
| **过度保守** | 可能拒绝合理问题 | 调整关键词阈值 |
| **绕过检测** | 用户可能换种问法绕过 | 增加更多模式 |
| **性能影响** | 增加了处理步骤 | 规则版性能影响小 |
| **断言过滤不完整** | 可能漏掉某些断言模式 | 持续补充模式 |

### 下一步

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | **LLM 意图分类** | 用 LLM 替代规则分类，提高准确率 |
| P2 | **动态阈值** | 根据 NPC 类型调整证据要求 |
| P3 | **断言检测增强** | 使用 NER 检测人名、地名、时间 |
| P4 | **用户反馈收集** | 收集误判案例，优化规则 |
| P5 | **A/B 测试** | 对比有无证据闸门的用户体验 |

## 配置说明

```python
# app/guardrails/evidence_gate.py

class EvidenceGate:
    def __init__(
        self,
        min_citations_for_fact: int = 1,  # 事实性问题最少需要的引用数
        classifier: Optional[QueryIntentClassifier] = None,
    ):
        ...
```

可通过环境变量配置（需要在 config.py 中添加）：

```bash
EVIDENCE_GATE_MIN_CITATIONS=1
EVIDENCE_GATE_ENABLED=true
```
