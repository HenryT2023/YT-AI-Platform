"""
数据库会话管理（兼容层）

提供与 app.db.session 相同的接口
"""

from app.db.session import get_db, engine, async_session_maker

# 别名
get_session = get_db

__all__ = ["get_db", "get_session", "engine", "async_session_maker"]
