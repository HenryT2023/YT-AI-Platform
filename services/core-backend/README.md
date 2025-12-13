# Core Backend

严田 AI 文明引擎 - 主后端服务

## 功能

- 用户认证与授权 (JWT)
- 站点、场景、POI 管理
- NPC 管理与对话入口
- 研学任务系统
- 游客档案管理

## 开发

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e ".[dev]"

# 运行数据库迁移
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --port 8000
```

## API 文档

启动后访问：http://localhost:8000/docs
