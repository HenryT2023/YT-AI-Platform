# LLM Provider 集成指南

## 概述

LLM Provider 模块提供统一的 LLM 服务抽象，支持多种后端：

- **百度 ERNIE Bot**（已实现）
- OpenAI（预留）
- Qwen（预留）
- Ollama（预留）

**核心特性：**

- 统一接口，切换后端不改主流程
- 超时控制 + 指数退避重试
- 错误分类（auth/network/timeout/rate_limit/server）
- 降级处理（LLM 不可用时自动切 conservative 模式）
- 审计记录（与 trace_id 关联）

## 文件树变更清单

### 新增文件

```text
services/ai-orchestrator/
├── app/providers/
│   ├── __init__.py               # Providers 模块导出
│   └── llm/
│       ├── __init__.py           # LLM Provider 模块导出
│       ├── base.py               # 统一抽象接口
│       ├── baidu_ernie.py        # 百度 ERNIE Bot 实现
│       └── factory.py            # Provider 工厂
├── .env.example                  # 环境变量示例
└── tests/
    └── test_llm_provider.py      # 集成测试
```

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/core/config.py` | 添加 LLM 超时、重试、降级配置 |
| `app/agent/runtime.py` | 注入 LLMProvider，支持降级 |

## 配置说明

### 环境变量

```bash
# LLM Provider 选择
LLM_PROVIDER=baidu  # baidu / openai / qwen / ollama

# 降级配置
LLM_FALLBACK_ENABLED=true   # LLM 不可用时自动降级
LLM_SANDBOX_MODE=false      # 开启后使用模拟响应（开发测试用）

# 百度 ERNIE Bot 配置
BAIDU_API_KEY=your-api-key
BAIDU_SECRET_KEY=your-secret-key
BAIDU_MODEL=ernie-bot-4
BAIDU_TIMEOUT_SECONDS=60.0
BAIDU_MAX_RETRIES=3
```

### 获取百度 API Key

1. 访问 [百度智能云控制台](https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application)
2. 创建应用，获取 API Key 和 Secret Key
3. 开通文心一言模型服务

### 支持的模型

| 模型 | 说明 |
|------|------|
| `ernie-bot-4` | ERNIE 4.0，推荐 |
| `ernie-4.0-8k` | ERNIE 4.0 8K 上下文 |
| `ernie-bot-turbo` | ERNIE 3.5 Turbo，更快 |
| `ernie-bot` | ERNIE 3.5 |
| `ernie-3.5-8k` | ERNIE 3.5 8K 上下文 |

## 运行与联调步骤

### 1. 配置环境变量

```bash
cd services/ai-orchestrator
cp .env.example .env
# 编辑 .env，填入百度 API Key
```

### 2. 启动服务

```bash
# 启动 core-backend
cd services/core-backend
uvicorn app.main:app --reload --port 8000

# 启动 ai-orchestrator
cd services/ai-orchestrator
uvicorn app.main:app --reload --port 8001
```

### 3. 运行测试

```bash
cd services/ai-orchestrator

# 运行 Sandbox 模式测试（不需要 API Key）
pytest tests/test_llm_provider.py -v

# 运行真实 API 测试（需要配置 API Key）
# 修改 test_llm_provider.py 中 @pytest.mark.skipif 为 False
pytest tests/test_llm_provider.py::TestBaiduERNIERealAPI -v
```

## curl 示例

### 成功调用（真实 API）

```bash
# 确保已配置 BAIDU_API_KEY 和 BAIDU_SECRET_KEY
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问严氏家训有哪些？"
  }'
```

预期响应：

```json
{
  "trace_id": "trace-xxx",
  "policy_mode": "normal",
  "answer_text": "后生问得好。老夫当年定下家训十则...",
  "citations": [
    {"evidence_id": "...", "title": "严氏家训十则", "source_ref": "..."}
  ],
  "followup_questions": ["能给我讲讲严氏家族历史吗？"]
}
```

### 降级调用（LLM 不可用）

```bash
# 模拟 LLM 不可用：设置错误的 API Key
# 或设置 LLM_SANDBOX_MODE=true

curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问严氏家训有哪些？"
  }'
```

预期响应（降级模式）：

```json
{
  "trace_id": "trace-xxx",
  "policy_mode": "conservative",
  "answer_text": "此事我不甚了了，后生可去祠堂查阅族谱，或询问村中耆老。",
  "citations": [],
  "followup_questions": []
}
```

### Sandbox 模式测试

```bash
# 设置 LLM_SANDBOX_MODE=true
curl -X POST http://localhost:8001/api/v1/npc/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "yantian",
    "site_id": "yantian-main",
    "npc_id": "ancestor_yan",
    "query": "请问严氏家训有哪些？"
  }'
```

## 错误分类

| 错误类型 | 说明 | 是否重试 |
|----------|------|----------|
| `auth` | 认证错误（API Key 无效） | 否 |
| `network` | 网络错误 | 是 |
| `timeout` | 超时 | 是 |
| `rate_limit` | 限流 | 是 |
| `server` | 服务端错误 | 是 |
| `invalid_request` | 请求参数错误 | 否 |
| `content_filter` | 内容过滤 | 否 |

## 审计记录

每次 LLM 调用都会记录到 trace_ledger：

```json
{
  "tool_calls": [
    {
      "name": "llm_generate",
      "status": "success",
      "provider": "baidu",
      "model": "ernie-bot-4",
      "tokens_input": 150,
      "tokens_output": 200,
      "latency_ms": 1500
    }
  ]
}
```

## 风险点与下一步

### 风险点

| 风险点 | 说明 |
|--------|------|
| **Token 计费** | 百度 API 按 token 计费，需监控用量 |
| **限流** | 高并发可能触发限流，需实现队列 |
| **Token 过期** | Access Token 30 天过期，需自动刷新 |
| **内容过滤** | 百度有内容审核，可能拒绝某些请求 |
| **延迟** | 真实 API 延迟 1-3 秒，需考虑用户体验 |

### 下一步

1. **v0.2.0** - 实现 OpenAI Provider
2. **v0.2.1** - 实现 Qwen Provider
3. **v0.2.2** - 添加 Redis 缓存（相同问题复用响应）
4. **v0.3.0** - 支持流式响应
5. **v0.3.1** - 添加 Token 用量监控和告警
