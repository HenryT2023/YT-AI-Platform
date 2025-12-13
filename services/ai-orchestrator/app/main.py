"""
严田 AI 文明引擎 - AI Orchestrator 主入口

职责:
- NPC 对话编排
- 提示词模板管理
- RAG 检索增强生成
- 工具调用（Tool Calling）
- 文化准确性护栏
- 会话记忆管理
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.core.config import settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    setup_logging()
    yield


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="严田 AI 文明引擎 - AI Orchestrator",
        description="NPC 对话编排、RAG 检索、文化护栏",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    @app.get("/health")
    async def health_check() -> dict:
        """健康检查端点"""
        return {"status": "healthy", "service": "ai-orchestrator", "version": "0.1.0"}

    return app


app = create_app()
