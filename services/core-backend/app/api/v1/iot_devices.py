"""
IoT 设备管理 API
"""

from datetime import datetime, timedelta
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import ViewerOrAbove, OperatorOrAbove
from app.core.tenant_scope import RequiredScope
from app.db import get_db
from app.database.models import IoTDevice, IoTDeviceLog, DeviceType, DeviceStatus, EventType

router = APIRouter()


# ============ Schemas ============

class IoTDeviceCreate(BaseModel):
    device_code: str = Field(..., max_length=100, description="设备编码")
    name: str = Field(..., max_length=200, description="设备名称")
    device_type: str = Field(DeviceType.OTHER, description="设备类型")
    location: Optional[str] = Field(None, max_length=500, description="位置描述")
    scene_id: Optional[UUID] = Field(None, description="关联场景")
    poi_id: Optional[UUID] = Field(None, description="关联兴趣点")
    config: Optional[dict] = Field(None, description="设备配置")
    device_metadata: Optional[dict] = Field(None, description="扩展元数据")
    is_active: bool = Field(True, description="是否启用")


class IoTDeviceUpdate(BaseModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    location: Optional[str] = None
    scene_id: Optional[UUID] = None
    poi_id: Optional[UUID] = None
    config: Optional[dict] = None
    device_metadata: Optional[dict] = None
    is_active: Optional[bool] = None


class IoTDeviceResponse(BaseModel):
    id: UUID
    tenant_id: str
    site_id: str
    device_code: str
    name: str
    device_type: str
    location: Optional[str] = None
    scene_id: Optional[UUID] = None
    poi_id: Optional[UUID] = None
    config: Optional[dict] = None
    status: str
    last_heartbeat: Optional[datetime] = None
    device_metadata: Optional[dict] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IoTDeviceListResponse(BaseModel):
    items: List[IoTDeviceResponse]
    total: int


class DeviceCommandRequest(BaseModel):
    command: str = Field(..., description="命令类型")
    params: Optional[dict] = Field(None, description="命令参数")


class DeviceCommandResponse(BaseModel):
    device_id: UUID
    command: str
    status: str
    message: str


class IoTDeviceLogResponse(BaseModel):
    id: UUID
    device_id: UUID
    event_type: str
    event_data: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceStats(BaseModel):
    total: int
    online: int
    offline: int
    error: int
    by_type: dict


# ============ Device API ============

@router.get("/iot-devices", response_model=IoTDeviceListResponse, tags=["iot-devices"])
async def list_iot_devices(
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    device_type: Optional[str] = Query(None, description="按类型筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    is_active: Optional[bool] = Query(None, description="按启用状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """获取 IoT 设备列表"""
    conditions = [
        IoTDevice.tenant_id == scope.tenant_id,
        IoTDevice.site_id == scope.site_id,
    ]
    
    if device_type:
        conditions.append(IoTDevice.device_type == device_type)
    if status:
        conditions.append(IoTDevice.status == status)
    if is_active is not None:
        conditions.append(IoTDevice.is_active == is_active)
    
    # 统计总数
    count_result = await db.execute(
        select(func.count(IoTDevice.id)).where(*conditions)
    )
    total = count_result.scalar() or 0
    
    # 分页查询
    result = await db.execute(
        select(IoTDevice)
        .where(*conditions)
        .order_by(IoTDevice.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    
    return IoTDeviceListResponse(items=items, total=total)


@router.get("/iot-devices/stats", response_model=DeviceStats, tags=["iot-devices"])
async def get_device_stats(
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取设备统计"""
    base_conditions = [
        IoTDevice.tenant_id == scope.tenant_id,
        IoTDevice.site_id == scope.site_id,
    ]
    
    # 总数
    total_result = await db.execute(
        select(func.count(IoTDevice.id)).where(*base_conditions)
    )
    total = total_result.scalar() or 0
    
    # 按状态统计
    status_result = await db.execute(
        select(IoTDevice.status, func.count(IoTDevice.id))
        .where(*base_conditions)
        .group_by(IoTDevice.status)
    )
    status_counts = {row[0]: row[1] for row in status_result.all()}
    
    # 按类型统计
    type_result = await db.execute(
        select(IoTDevice.device_type, func.count(IoTDevice.id))
        .where(*base_conditions)
        .group_by(IoTDevice.device_type)
    )
    by_type = {row[0]: row[1] for row in type_result.all()}
    
    return DeviceStats(
        total=total,
        online=status_counts.get(DeviceStatus.ONLINE, 0),
        offline=status_counts.get(DeviceStatus.OFFLINE, 0),
        error=status_counts.get(DeviceStatus.ERROR, 0),
        by_type=by_type,
    )


@router.post("/iot-devices", response_model=IoTDeviceResponse, status_code=201, tags=["iot-devices"])
async def create_iot_device(
    data: IoTDeviceCreate,
    current_user: OperatorOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """注册 IoT 设备"""
    # 检查设备编码是否已存在
    existing = await db.execute(
        select(IoTDevice).where(
            IoTDevice.tenant_id == scope.tenant_id,
            IoTDevice.site_id == scope.site_id,
            IoTDevice.device_code == data.device_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="设备编码已存在")
    
    device = IoTDevice(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        status=DeviceStatus.OFFLINE,
        **data.model_dump()
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.get("/iot-devices/{device_id}", response_model=IoTDeviceResponse, tags=["iot-devices"])
async def get_iot_device(
    device_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取设备详情"""
    result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == scope.tenant_id,
            IoTDevice.site_id == scope.site_id,
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    return device


@router.patch("/iot-devices/{device_id}", response_model=IoTDeviceResponse, tags=["iot-devices"])
async def update_iot_device(
    device_id: UUID,
    data: IoTDeviceUpdate,
    current_user: OperatorOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新设备信息"""
    result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == scope.tenant_id,
            IoTDevice.site_id == scope.site_id,
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)
    
    await db.commit()
    await db.refresh(device)
    return device


@router.delete("/iot-devices/{device_id}", status_code=204, tags=["iot-devices"])
async def delete_iot_device(
    device_id: UUID,
    current_user: OperatorOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """删除设备"""
    result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == scope.tenant_id,
            IoTDevice.site_id == scope.site_id,
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    await db.delete(device)
    await db.commit()


@router.post("/iot-devices/{device_id}/command", response_model=DeviceCommandResponse, tags=["iot-devices"])
async def send_device_command(
    device_id: UUID,
    command: DeviceCommandRequest,
    current_user: OperatorOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """发送设备控制命令（预留接口）"""
    result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == scope.tenant_id,
            IoTDevice.site_id == scope.site_id,
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    if not device.is_active:
        raise HTTPException(status_code=400, detail="设备已禁用")
    
    if device.status != DeviceStatus.ONLINE:
        raise HTTPException(status_code=400, detail="设备不在线")
    
    # 记录命令日志
    log = IoTDeviceLog(
        tenant_id=scope.tenant_id,
        site_id=scope.site_id,
        device_id=device_id,
        event_type=EventType.COMMAND,
        event_data={"command": command.command, "params": command.params},
    )
    db.add(log)
    await db.commit()
    
    # TODO: 实际发送命令到设备（v0.4.0 实现）
    return DeviceCommandResponse(
        device_id=device_id,
        command=command.command,
        status="queued",
        message="命令已加入队列，等待设备执行",
    )


@router.post("/iot-devices/{device_id}/heartbeat", response_model=IoTDeviceResponse, tags=["iot-devices"])
async def device_heartbeat(
    device_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_data: Optional[dict] = None,
):
    """设备心跳（设备端调用）"""
    result = await db.execute(
        select(IoTDevice).where(IoTDevice.id == device_id)
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    # 更新心跳时间和状态
    device.last_heartbeat = datetime.utcnow()
    device.status = DeviceStatus.ONLINE
    
    # 记录心跳日志
    log = IoTDeviceLog(
        tenant_id=device.tenant_id,
        site_id=device.site_id,
        device_id=device_id,
        event_type=EventType.HEARTBEAT,
        event_data=status_data,
    )
    db.add(log)
    await db.commit()
    await db.refresh(device)
    
    return device


@router.get("/iot-devices/{device_id}/logs", response_model=List[IoTDeviceLogResponse], tags=["iot-devices"])
async def get_device_logs(
    device_id: UUID,
    current_user: ViewerOrAbove,
    scope: RequiredScope,
    db: Annotated[AsyncSession, Depends(get_db)],
    event_type: Optional[str] = Query(None, description="按事件类型筛选"),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
):
    """获取设备日志"""
    # 验证设备归属
    device_result = await db.execute(
        select(IoTDevice).where(
            IoTDevice.id == device_id,
            IoTDevice.tenant_id == scope.tenant_id,
            IoTDevice.site_id == scope.site_id,
        )
    )
    if not device_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="设备不存在")
    
    conditions = [IoTDeviceLog.device_id == device_id]
    if event_type:
        conditions.append(IoTDeviceLog.event_type == event_type)
    
    result = await db.execute(
        select(IoTDeviceLog)
        .where(*conditions)
        .order_by(IoTDeviceLog.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
