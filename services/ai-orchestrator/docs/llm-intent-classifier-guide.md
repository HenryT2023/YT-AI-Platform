# P16 LLM 意图分类器指南

## 概述

用 LLM 意图分类替代规则分类器，提高判定准确率，同时保证稳定性（降级、缓存、限流）。

## 架构设计

```text
┌─────────────────────────────────────────────────────────────┐
│                     IntentClassifier                        │
│                      (抽象接口)                              │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────┐
│  RuleIntentClassifier   │     │   LLMIntentClassifier       │
│  (规则版，同步)          │     │   (LLM版，带缓存+降级)       │
└─────────────────────────┘     └─────────────────────────────┘
                                              │
                                              ▼
                                ┌─────────────────────────────┐
                                │  失败时降级到 Rule 分类器    │
                                └─────────────────────────────┘
```

## 文件树变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `app/guardrails/intent_classifier_v2.py` | 抽象接口 + 规则版 + LLM 版分类器 |
| `app/guardrails/evidence_gate_v2.py` | 证据闸门 v2，支持 LLM 分类器 |
| `tests/intent_cases.json` | 100+ 条意图分类测试用例 |
| `tests/test_intent_classifier_v2.py` | pytest 测试 |
| `docs/llm-intent-classifier-guide.md` | 本文档 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/core/config.py` | 添加 `INTENT_CLASSIFIER_USE_LLM` 和 `INTENT_CLASSIFIER_CACHE_TTL` 配置 |

## 核心接口

### IntentClassifier 抽象接口

```python
class IntentClassifier(ABC):
    @property
    @abstractmethod
    def classifier_type(self) -> str:
        """分类器类型: rule / llm"""
        pass

    @abstractmethod
    async def classify(
        self,
        query: str,
        context: Optional[IntentContext] = None,
    ) -> IntentResult:
        """分类查询意图"""
        pass
```

### IntentResult 数据结构

```python
@dataclass
class IntentResult:
    label: IntentLabel           # 意图标签
    confidence: float            # 置信度 0.0-1.0
    tags: List[str]              # 标签
    reason: str                  # 原因
    requires_evidence: bool      # 是否需要证据
    classifier_type: str         # 分类器类型
    latency_ms: int              # 延迟（毫秒）
    cached: bool                 # 是否命中缓存
```

### IntentLabel 意图标签

| 标签 | 说明 | 需要证据 |
|------|------|----------|
| `fact_seeking` | 事实性问题 | ✅ |
| `context_preference` | 上下文偏好 | ❌ |
| `greeting` | 问候 | ❌ |
| `clarification` | 澄清追问 | ❌ |
| `out_of_scope` | 超出范围 | ❌ |

## 配置说明

```bash
# .env

# 是否使用 LLM 意图分类器（默认 false，使用规则版）
INTENT_CLASSIFIER_USE_LLM=false

# 缓存 TTL（秒）
INTENT_CLASSIFIER_CACHE_TTL=300
```

## 缓存设计

### 缓存 Key 格式

```text
yantian:intent:{tenant_id}:{site_id}:{npc_id}:{query_hash}
```

### 缓存策略

- **TTL**: 5 分钟（300 秒）
- **Key 组成**: tenant_id + site_id + npc_id + query MD5 前 16 位
- **缓存内容**: label, confidence, tags, reason, requires_evidence

## 降级机制

```text
LLM 分类请求
    │
    ▼
┌─────────────────┐
│  检查缓存       │ ──命中──▶ 返回缓存结果
└─────────────────┘
    │ 未命中
    ▼
┌─────────────────┐
│  调用 LLM       │ ──成功──▶ 写入缓存，返回结果
└─────────────────┘
    │ 失败
    ▼
┌─────────────────┐
│  降级到规则版   │ ──────▶ 返回规则分类结果
└─────────────────┘
```

### 降级触发条件

1. LLM Provider 未配置
2. LLM 调用超时
3. LLM 返回格式错误
4. LLM 返回无法解析的 JSON

## 使用示例

### 基本使用

```python
from app.guardrails.intent_classifier_v2 import (
    RuleIntentClassifier,
    LLMIntentClassifier,
    IntentContext,
)

# 规则分类器
rule_classifier = RuleIntentClassifier()
result = await rule_classifier.classify("严氏是什么时候迁来的？")
print(result.label)  # IntentLabel.FACT_SEEKING

# LLM 分类器（带降级）
llm_classifier = LLMIntentClassifier(
    llm_provider=llm_provider,
    cache_client=redis_client,
)
result = await llm_classifier.classify("严氏是什么时候迁来的？")
```

### 在 Evidence Gate 中使用

```python
from app.guardrails.evidence_gate_v2 import EvidenceGateV2

# 创建证据闸门（自动根据配置选择分类器）
gate = EvidenceGateV2(
    use_llm_classifier=True,  # 或从 settings.INTENT_CLASSIFIER_USE_LLM 读取
    llm_provider=llm_provider,
    cache_client=redis_client,
)

# LLM 调用前检查
result = await gate.check_before_llm(
    query="严氏是什么时候迁来的？",
    citations=citations,
    context=IntentContext(
        tenant_id="yantian",
        site_id="yantian-main",
        npc_id="ancestor_yan",
    ),
)

if not result.passed:
    # 使用保守响应
    response = gate.get_conservative_response(result.intent, query)
```

## 测试命令

```bash
cd services/ai-orchestrator

# 运行所有意图分类器测试
pytest tests/test_intent_classifier_v2.py -v

# 运行特定测试类
pytest tests/test_intent_classifier_v2.py::TestRuleIntentClassifier -v
pytest tests/test_intent_classifier_v2.py::TestLLMIntentClassifier -v
pytest tests/test_intent_classifier_v2.py::TestIntentCases -v

# 查看测试覆盖率
pytest tests/test_intent_classifier_v2.py --cov=app/guardrails --cov-report=term-missing
```

## 测试用例分布

| 类别 | 数量 | 说明 |
|------|------|------|
| fact_seeking | 40 | 事实性问题 |
| context_preference | 30 | 上下文偏好 |
| greeting | 10 | 问候 |
| clarification | 5 | 澄清追问 |
| out_of_scope | 10 | 超出范围 |
| mixed | 5 | 混合问题 |
| **总计** | **100** | |

## LLM Prompt 设计

```text
你是一个意图分类器。请分析用户的查询，判断其意图类型。

## 意图类型

1. **fact_seeking** - 事实性问题
   - 询问具体的历史事实、时间、人物、事件
   - 需要证据支撑的问题

2. **context_preference** - 上下文偏好问题
   - 询问建议、偏好、感受
   - 依赖上下文的追问

3. **greeting** - 问候

4. **clarification** - 澄清追问

5. **out_of_scope** - 超出范围

## 输出格式

请以 JSON 格式输出：
{
  "label": "fact_seeking",
  "confidence": 0.85,
  "tags": ["历史", "时间"],
  "reason": "用户询问具体的迁徙时间"
}
```

## 风险点与缓解

| 风险点 | 说明 | 缓解措施 |
|--------|------|----------|
| **LLM 延迟** | LLM 调用增加延迟 | 缓存 + 低温度 + 限制 max_tokens |
| **LLM 成本** | 每次分类消耗 token | 缓存复用 + 规则预过滤 |
| **LLM 不稳定** | 可能返回格式错误 | 降级到规则分类器 |
| **缓存穿透** | 大量不同查询 | 限流 + 规则预过滤 |
| **分类不一致** | LLM 可能给出不同结果 | 低温度 (0.1) + 缓存 |

## 下一步

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | **规则预过滤** | 明显的问候/事实性问题直接规则判定 |
| P2 | **批量分类** | 支持批量查询分类 |
| P3 | **分类反馈** | 收集用户反馈优化分类 |
| P4 | **A/B 测试** | 对比规则版和 LLM 版效果 |
| P5 | **Fine-tune** | 基于反馈微调分类模型 |

## 监控指标

| 指标 | 说明 |
|------|------|
| `intent_classifier_latency_ms` | 分类延迟 |
| `intent_classifier_cache_hit_rate` | 缓存命中率 |
| `intent_classifier_fallback_rate` | 降级率 |
| `intent_classifier_label_distribution` | 意图标签分布 |
