# ===========================
# 严田 AI 文明引擎 Makefile
# ===========================

.PHONY: help install dev-backend dev-admin dev-all test lint format \
        db-init db-migrate db-upgrade db-downgrade \
        infra-up infra-down docker-build docker-up docker-down \
        clean seed-data build-vectors

# 默认目标
.DEFAULT_GOAL := help

# -----------------
# 帮助信息
# -----------------
help:
	@echo "严田 AI 文明引擎 - 开发命令"
	@echo ""
	@echo "开发环境:"
	@echo "  make install        安装所有依赖"
	@echo "  make dev-backend    启动后端开发服务器"
	@echo "  make dev-admin      启动 Admin 后台开发服务器"
	@echo "  make dev-all        启动所有开发服务器"
	@echo ""
	@echo "数据库:"
	@echo "  make db-init        初始化数据库"
	@echo "  make db-migrate     生成迁移文件"
	@echo "  make db-upgrade     执行迁移"
	@echo "  make db-downgrade   回滚迁移"
	@echo "  make seed-data      导入种子数据"
	@echo ""
	@echo "基础设施:"
	@echo "  make infra-up       启动本地基础设施（PostgreSQL, Redis, Qdrant）"
	@echo "  make infra-down     停止本地基础设施"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build   构建所有 Docker 镜像"
	@echo "  make docker-up      启动所有服务（Docker Compose）"
	@echo "  make docker-down    停止所有服务"
	@echo ""
	@echo "测试 & 质量:"
	@echo "  make test           运行所有测试"
	@echo "  make lint           代码检查"
	@echo "  make format         代码格式化"
	@echo ""
	@echo "其他:"
	@echo "  make build-vectors  构建向量索引"
	@echo "  make clean          清理临时文件"

# -----------------
# 环境变量
# -----------------
export PYTHONPATH := $(shell pwd)/services/core-backend:$(shell pwd)/services/ai-orchestrator:$(shell pwd)/services/worker

# -----------------
# 安装依赖
# -----------------
install:
	@echo "📦 安装 Python 依赖..."
	cd services/core-backend && pip install -e ".[dev]"
	cd services/ai-orchestrator && pip install -e ".[dev]"
	cd services/worker && pip install -e ".[dev]"
	@echo "📦 安装 Node.js 依赖..."
	cd apps/admin-console && npm install
	@echo "✅ 依赖安装完成"

install-backend:
	cd services/core-backend && pip install -e ".[dev]"
	cd services/ai-orchestrator && pip install -e ".[dev]"
	cd services/worker && pip install -e ".[dev]"

install-admin:
	cd apps/admin-console && npm install

# -----------------
# 开发服务器
# -----------------
dev-backend:
	@echo "🚀 启动 Core Backend..."
	cd services/core-backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-orchestrator:
	@echo "🚀 启动 AI Orchestrator..."
	cd services/ai-orchestrator && uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

dev-worker:
	@echo "🚀 启动 Celery Worker..."
	cd services/worker && celery -A app.celery_app worker --loglevel=info

dev-admin:
	@echo "🚀 启动 Admin Console..."
	cd apps/admin-console && npm run dev

dev-all:
	@echo "🚀 启动所有开发服务器（使用 honcho 或手动在多个终端运行）"
	@echo "请在不同终端分别运行:"
	@echo "  make dev-backend"
	@echo "  make dev-orchestrator"
	@echo "  make dev-worker"
	@echo "  make dev-admin"

# -----------------
# 数据库操作
# -----------------
db-init:
	@echo "🗄️ 初始化数据库..."
	cd services/core-backend && alembic upgrade head
	@echo "✅ 数据库初始化完成"

db-migrate:
	@echo "📝 生成迁移文件..."
	@read -p "迁移描述: " msg; \
	cd services/core-backend && alembic revision --autogenerate -m "$$msg"

db-upgrade:
	@echo "⬆️ 执行数据库迁移..."
	cd services/core-backend && alembic upgrade head

db-downgrade:
	@echo "⬇️ 回滚数据库迁移..."
	cd services/core-backend && alembic downgrade -1

seed-data:
	@echo "🌱 导入种子数据..."
	python scripts/dev_seed_site.py
	@echo "✅ 种子数据导入完成"

# -----------------
# 基础设施
# -----------------
infra-up:
	@echo "🐳 启动本地基础设施..."
	docker-compose -f docker-compose.yml up -d postgres redis qdrant
	@echo "⏳ 等待服务就绪..."
	sleep 5
	@echo "✅ 基础设施已启动"

infra-down:
	@echo "🛑 停止本地基础设施..."
	docker-compose -f docker-compose.yml down
	@echo "✅ 基础设施已停止"

# -----------------
# Docker
# -----------------
docker-build:
	@echo "🔨 构建 Docker 镜像..."
	docker-compose build

docker-up:
	@echo "🐳 启动所有服务..."
	docker-compose up -d
	@echo "✅ 所有服务已启动"

docker-down:
	@echo "🛑 停止所有服务..."
	docker-compose down
	@echo "✅ 所有服务已停止"

docker-logs:
	docker-compose logs -f

# -----------------
# 测试
# -----------------
test:
	@echo "🧪 运行所有测试..."
	cd services/core-backend && pytest -v
	cd services/ai-orchestrator && pytest -v
	cd services/worker && pytest -v
	@echo "✅ 测试完成"

test-backend:
	cd services/core-backend && pytest -v

test-orchestrator:
	cd services/ai-orchestrator && pytest -v

test-integration:
	@echo "🧪 运行集成测试..."
	pytest tests/integration -v

test-e2e:
	@echo "🧪 运行端到端测试..."
	pytest tests/e2e -v

# -----------------
# 代码质量
# -----------------
lint:
	@echo "🔍 代码检查..."
	ruff check services/
	cd apps/admin-console && npm run lint
	@echo "✅ 检查完成"

format:
	@echo "✨ 代码格式化..."
	ruff format services/
	cd apps/admin-console && npm run format
	@echo "✅ 格式化完成"

typecheck:
	@echo "🔍 类型检查..."
	cd services/core-backend && mypy app/
	cd services/ai-orchestrator && mypy app/

# -----------------
# 向量索引
# -----------------
build-vectors:
	@echo "🔢 构建向量索引..."
	python scripts/build_vector_index.py
	@echo "✅ 向量索引构建完成"

import-knowledge:
	@echo "📚 导入知识库..."
	python scripts/import_knowledge.py
	@echo "✅ 知识库导入完成"

# -----------------
# 清理
# -----------------
clean:
	@echo "🧹 清理临时文件..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ 清理完成"
