# AI Orchestrator

严田 AI 文明引擎 - AI 编排服务

## 功能

- NPC 对话编排
- LLM 抽象层 (OpenAI/Qwen)
- 知识库 RAG 检索
- 会话记忆管理
- 文化准确性护栏

## 开发

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e ".[dev]"

# 启动开发服务器
uvicorn app.main:app --reload --port 8001
```

## API 文档

启动后访问：http://localhost:8001/docs
