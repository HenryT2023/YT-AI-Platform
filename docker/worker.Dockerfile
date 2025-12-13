# 严田 AI 文明引擎 - Worker Dockerfile

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY services/worker/pyproject.toml ./

# 安装依赖
RUN pip install .

# 复制源代码
COPY services/worker/app ./app

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
