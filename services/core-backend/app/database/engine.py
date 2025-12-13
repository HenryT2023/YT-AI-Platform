"""
数据库引擎与会话管理

使用 SQLAlchemy 2.0 异步引擎 + asyncpg

连接池配置说明：
- pool_size: 连接池中保持的连接数（默认 5）
- max_overflow: 超出 pool_size 后允许的额外连接数（默认 10）
- pool_timeout: 获取连接的超时时间（秒）
- pool_recycle: 连接回收时间（秒），防止数据库断开空闲连接
- pool_pre_ping: 每次获取连接前检测连接是否有效
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core.config import settings


def _build_database_url() -> str:
    """构建异步数据库连接 URL"""
    return (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def _get_pool_config() -> dict:
    """
    获取连接池配置

    根据环境返回不同的连接池配置：
    - test: 使用 NullPool（无连接池），每次请求创建新连接
    - development: 较小的连接池
    - production: 较大的连接池
    """
    if settings.ENV == "test":
        return {"poolclass": NullPool}

    # 从配置读取连接池参数
    pool_size = settings.DB_POOL_SIZE
    max_overflow = settings.DB_MAX_OVERFLOW
    pool_timeout = settings.DB_POOL_TIMEOUT
    pool_recycle = settings.DB_POOL_RECYCLE

    return {
        "poolclass": AsyncAdaptedQueuePool,
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_timeout": pool_timeout,
        "pool_recycle": pool_recycle,
    }


# 创建异步引擎（带连接池）
engine: AsyncEngine = create_async_engine(
    _build_database_url(),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    **_get_pool_config(),
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话依赖

    用于 FastAPI 路由的依赖注入
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    初始化数据库连接

    在应用启动时调用
    """
    async with engine.begin() as conn:
        # 测试连接
        await conn.execute("SELECT 1")


async def close_db() -> None:
    """
    关闭数据库连接

    在应用关闭时调用
    """
    await engine.dispose()
