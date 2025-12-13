"""
数据库健康检查
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import async_session_maker


@dataclass
class DBHealthStatus:
    """数据库健康状态"""

    healthy: bool
    latency_ms: float
    version: Optional[str] = None
    error: Optional[str] = None
    checked_at: datetime = None

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "version": self.version,
            "error": self.error,
            "checked_at": self.checked_at.isoformat(),
        }


async def check_db_health() -> DBHealthStatus:
    """
    检查数据库健康状态

    Returns:
        DBHealthStatus: 健康状态对象
    """
    import time

    start = time.perf_counter()

    try:
        async with async_session_maker() as session:
            # 执行简单查询测试连接
            result = await session.execute(text("SELECT version()"))
            version = result.scalar()

            latency_ms = (time.perf_counter() - start) * 1000

            return DBHealthStatus(
                healthy=True,
                latency_ms=round(latency_ms, 2),
                version=version,
            )

    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000

        return DBHealthStatus(
            healthy=False,
            latency_ms=round(latency_ms, 2),
            error=str(e),
        )
