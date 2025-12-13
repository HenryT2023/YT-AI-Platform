"""
健康检查 API
"""

from fastapi import APIRouter

from app.database.health import check_db_health

router = APIRouter()


@router.get("")
async def health_check():
    """
    健康检查

    返回服务和数据库状态
    """
    db_status = await check_db_health()

    return {
        "status": "healthy" if db_status.healthy else "unhealthy",
        "service": "core-backend",
        "version": "0.1.0",
        "database": db_status.to_dict(),
    }


@router.get("/ready")
async def readiness_check():
    """
    就绪检查

    用于 Kubernetes readiness probe
    """
    db_status = await check_db_health()

    if not db_status.healthy:
        return {"ready": False, "reason": "database_unavailable"}

    return {"ready": True}


@router.get("/live")
async def liveness_check():
    """
    存活检查

    用于 Kubernetes liveness probe
    """
    return {"alive": True}
