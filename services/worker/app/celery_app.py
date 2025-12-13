"""
Celery 应用配置

异步任务处理：
- 文档向量化
- 媒体文件处理
- 批量数据导入
- 定时任务
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "yantian_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.vectorize",
        "app.tasks.media",
        "app.tasks.import_data",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 小时
    task_soft_time_limit=3000,  # 50 分钟
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

celery_app.conf.beat_schedule = {
    "cleanup-expired-sessions": {
        "task": "app.tasks.cleanup.cleanup_expired_sessions",
        "schedule": 3600.0,  # 每小时
    },
    "sync-solar-terms": {
        "task": "app.tasks.solar_term.sync_solar_terms",
        "schedule": 86400.0,  # 每天
    },
}
