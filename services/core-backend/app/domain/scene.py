"""
场景模型

Scene 代表物理空间场景，如建筑、庭院、道路等
"""

from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditMixin, Base


class Scene(Base, AuditMixin):
    """场景实体"""

    __tablename__ = "scenes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id: Mapped[str] = mapped_column(String(50), ForeignKey("sites.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    scene_type: Mapped[Optional[str]] = mapped_column(String(50))

    location_lat: Mapped[Optional[float]] = mapped_column()
    location_lng: Mapped[Optional[float]] = mapped_column()
    boundary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    floor_plan_asset_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))

    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    parent_scene_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scenes.id")
    )

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")

    site: Mapped["Site"] = relationship(back_populates="scenes")
    parent_scene: Mapped[Optional["Scene"]] = relationship(
        remote_side=[id], back_populates="child_scenes"
    )
    child_scenes: Mapped[list["Scene"]] = relationship(back_populates="parent_scene")
    pois: Mapped[list["POI"]] = relationship(back_populates="scene", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Scene(id={self.id}, name={self.name})>"


from app.domain.site import Site
from app.domain.poi import POI
