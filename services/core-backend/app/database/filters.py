"""
多租户查询过滤器

确保所有查询都带有 tenant_id 和 site_id 过滤
"""

from dataclasses import dataclass
from typing import Any, Optional, Type, TypeVar

from sqlalchemy import Select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Query

from app.database.base import Base, TenantMixin

T = TypeVar("T", bound=Base)


@dataclass
class TenantFilter:
    """
    租户过滤器上下文

    用于在查询中自动注入 tenant_id 和 site_id 过滤条件
    """

    tenant_id: str
    site_id: str
    user_id: Optional[str] = None

    def apply(self, stmt: Select[tuple[T]]) -> Select[tuple[T]]:
        """
        应用租户过滤到查询语句

        Args:
            stmt: SQLAlchemy Select 语句

        Returns:
            添加了租户过滤的语句
        """
        # 获取查询的主表
        from_clause = stmt.froms[0] if stmt.froms else None
        if from_clause is None:
            return stmt

        # 检查表是否有 tenant_id 和 site_id 列
        columns = from_clause.c
        conditions = []

        if hasattr(columns, "tenant_id"):
            conditions.append(columns.tenant_id == self.tenant_id)

        if hasattr(columns, "site_id"):
            conditions.append(columns.site_id == self.site_id)

        if conditions:
            return stmt.where(and_(*conditions))

        return stmt


def with_tenant_filter(
    stmt: Select[tuple[T]],
    tenant_id: str,
    site_id: str,
) -> Select[tuple[T]]:
    """
    便捷函数：为查询添加租户过滤

    Args:
        stmt: SQLAlchemy Select 语句
        tenant_id: 租户 ID
        site_id: 站点 ID

    Returns:
        添加了租户过滤的语句

    Example:
        stmt = select(Content).where(Content.status == "published")
        stmt = with_tenant_filter(stmt, tenant_id="yantian", site_id="yantian-main")
    """
    filter_ctx = TenantFilter(tenant_id=tenant_id, site_id=site_id)
    return filter_ctx.apply(stmt)


class TenantBoundSession:
    """
    租户绑定的会话包装器

    自动为所有查询添加租户过滤
    自动为所有新建对象设置 tenant_id 和 site_id
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: str,
        site_id: str,
    ):
        self._session = session
        self.tenant_id = tenant_id
        self.site_id = site_id

    @property
    def session(self) -> AsyncSession:
        return self._session

    def add(self, instance: Any) -> None:
        """
        添加对象到会话

        自动设置 tenant_id 和 site_id
        """
        if hasattr(instance, "tenant_id") and not instance.tenant_id:
            instance.tenant_id = self.tenant_id
        if hasattr(instance, "site_id") and not instance.site_id:
            instance.site_id = self.site_id

        self._session.add(instance)

    async def execute(self, stmt: Select[tuple[T]]) -> Any:
        """
        执行查询

        自动添加租户过滤
        """
        filtered_stmt = with_tenant_filter(stmt, self.tenant_id, self.site_id)
        return await self._session.execute(filtered_stmt)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, instance: Any) -> None:
        await self._session.refresh(instance)
