"""
兴趣点模型

POI (Point of Interest) 代表场景中的具体兴趣点，如文物、碑刻、古树等
"""

from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditMixin, Base


class POI(Base, AuditMixin):
    """兴趣点实体"""

    __tablename__ = "pois"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    site_id: Mapped[str] = mapped_column(String(50), ForeignKey("sites.id"), nullable=False)
    scene_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scenes.id")
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    poi_type: Mapped[Optional[str]] = mapped_column(String(50))

    location_lat: Mapped[Optional[float]] = mapped_column()
    location_lng: Mapped[Optional[float]] = mapped_column()
    indoor_position: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    cover_asset_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))
    audio_guide_asset_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True))

    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(50)))
    metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")

    scene: Mapped[Optional["Scene"]] = relationship(back_populates="pois")

    def __repr__(self) -> str:
        return f"<POI(id={self.id}, name={self.name})>"


from app.domain.scene import Scene
