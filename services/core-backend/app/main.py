"""
严田 AI 文明引擎 - Core Backend 主入口

职责:
- 用户认证与授权
- 站点、场景、POI 管理
- NPC 配置管理
- 研学任务管理
- 游客档案管理
- 事件日志记录
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    setup_logging()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="严田 AI 文明引擎 - Core Backend",
        description="祖宗智慧 × AI × 农耕节律 × 场景触发 × 游客行为学习",
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
        return {"status": "healthy", "service": "core-backend", "version": "0.1.0"}

    return app


app = create_app()
