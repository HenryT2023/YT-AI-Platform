# 严田 AI 文明引擎 - Backend Dockerfile
# 支持 core-backend 和 ai-orchestrator

ARG SERVICE_PATH=services/core-backend

# ===== 基础镜像 =====
FROM python:3.11-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ===== 开发阶段 =====
FROM base as development

ARG SERVICE_PATH

# 复制依赖文件和 README
COPY ${SERVICE_PATH}/pyproject.toml ${SERVICE_PATH}/README.md ./

# 安装依赖
RUN pip install -e ".[dev]" || pip install .

# 复制源代码
COPY ${SERVICE_PATH}/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ===== 生产阶段 =====
FROM base as production

ARG SERVICE_PATH

# 复制依赖文件和 README
COPY ${SERVICE_PATH}/pyproject.toml ${SERVICE_PATH}/README.md ./

# 安装生产依赖
RUN pip install .

# 复制源代码
COPY ${SERVICE_PATH}/app ./app

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
