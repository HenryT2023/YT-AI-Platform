"""
数据库模块

提供 SQLAlchemy 2.0 异步数据库支持
"""

from app.database.engine import (
    engine,
    async_session_maker,
    get_db,
    init_db,
    close_db,
)
from app.database.base import (
    Base,
    TimestampMixin,
    SoftDeleteMixin,
    AuditMixin,
    TenantMixin,
    UUIDPrimaryKeyMixin,
)
from app.database.filters import (
    TenantFilter,
    with_tenant_filter,
    TenantBoundSession,
)
from app.database.health import (
    DBHealthStatus,
    check_db_health,
)
from app.database.search import (
    search_contents,
    search_contents_hybrid,
)

__all__ = [
    # Engine
    "engine",
    "async_session_maker",
    "get_db",
    "init_db",
    "close_db",
    # Base
    "Base",
    "TimestampMixin",
    "SoftDeleteMixin",
    "AuditMixin",
    "TenantMixin",
    "UUIDPrimaryKeyMixin",
    # Filters
    "TenantFilter",
    "with_tenant_filter",
    "TenantBoundSession",
    # Health
    "DBHealthStatus",
    "check_db_health",
    # Search
    "search_contents",
    "search_contents_hybrid",
]
