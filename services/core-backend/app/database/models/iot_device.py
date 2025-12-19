"""
IoT 设备数据模型
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DeviceType:
    """设备类型常量"""
    LIGHT = "light"        # 灯光
    SPEAKER = "speaker"    # 音响
    SENSOR = "sensor"      # 传感器
    CAMERA = "camera"      # 摄像头
    DISPLAY = "display"    # 显示屏
    OTHER = "other"        # 其他


class DeviceStatus:
    """设备状态常量"""
    ONLINE = "online"      # 在线
    OFFLINE = "offline"    # 离线
    ERROR = "error"        # 故障


class IoTDevice(Base):
    """IoT 设备表"""

    __tablename__ = "iot_devices"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    
    # 设备标识
    device_code: Mapped[str] = mapped_column(String(100), comment="设备编码")
    name: Mapped[str] = mapped_column(String(200), comment="设备名称")
    
    # 设备类型
    device_type: Mapped[str] = mapped_column(
        String(50), default=DeviceType.OTHER, comment="设备类型"
    )
    
    # 位置信息
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="位置描述")
    scene_id: Mapped[Optional[UUID]] = mapped_column(nullable=True, index=True, comment="关联场景")
    poi_id: Mapped[Optional[UUID]] = mapped_column(nullable=True, index=True, comment="关联兴趣点")
    
    # 配置
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="设备配置")
    
    # 状态
    status: Mapped[str] = mapped_column(
        String(50), default=DeviceStatus.OFFLINE, comment="设备状态"
    )
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后心跳时间"
    )
    
    # 扩展数据
    device_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="扩展元数据")
    
    # 启用状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    logs: Mapped[list["IoTDeviceLog"]] = relationship(
        "IoTDeviceLog", back_populates="device", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_iot_devices_tenant_site", "tenant_id", "site_id"),
        Index("ix_iot_devices_code", "tenant_id", "site_id", "device_code", unique=True),
        Index("ix_iot_devices_type", "device_type"),
        Index("ix_iot_devices_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<IoTDevice(id={self.id}, code={self.device_code}, name={self.name})>"


class EventType:
    """事件类型常量"""
    STATUS_CHANGE = "status_change"  # 状态变化
    COMMAND = "command"              # 控制命令
    ERROR = "error"                  # 错误
    HEARTBEAT = "heartbeat"          # 心跳


class IoTDeviceLog(Base):
    """IoT 设备日志表"""

    __tablename__ = "iot_device_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    site_id: Mapped[str] = mapped_column(String(50), index=True)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("iot_devices.id"), index=True)
    
    # 事件信息
    event_type: Mapped[str] = mapped_column(String(50), comment="事件类型")
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="事件数据")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 关系
    device: Mapped["IoTDevice"] = relationship("IoTDevice", back_populates="logs")

    __table_args__ = (
        Index("ix_iot_device_logs_tenant_site", "tenant_id", "site_id"),
        Index("ix_iot_device_logs_device", "device_id"),
        Index("ix_iot_device_logs_type", "event_type"),
        Index("ix_iot_device_logs_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<IoTDeviceLog(id={self.id}, device_id={self.device_id}, event_type={self.event_type})>"
