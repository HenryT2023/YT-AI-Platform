# Worker

严田 AI 文明引擎 - 异步任务服务

## 功能

- 文档向量化
- 媒体文件处理
- 批量数据导入

## 开发

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .

# 启动 Celery Worker
celery -A app.celery_app worker --loglevel=info
```
