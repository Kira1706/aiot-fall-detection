"""API nhận heartbeat và cung cấp trạng thái kết nối từ Database."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from device_auth import require_device_key
from device_heartbeat_service import (
    HEARTBEAT_TIMEOUT_SECONDS,
    get_device_liveness,
    record_device_heartbeat,
)
from device_permissions import get_authorized_device
from device_status_schemas import (
    DeviceHeartbeatRequest, DeviceHeartbeatResponse, DeviceStatusResponse
)
from models import AccountDevice, Device

edge_router = APIRouter(prefix="/device-ingest", tags=["Device Ingest"])
status_router = APIRouter(prefix="/devices", tags=["Devices"])


@edge_router.post(
    "/{device_id}/heartbeat",
    response_model=DeviceHeartbeatResponse,
    status_code=status.HTTP_200_OK,
)
def receive_heartbeat(
    payload: DeviceHeartbeatRequest,
    device_id: str = Depends(require_device_key),
    db: Session = Depends(get_db),
):
    """Xác thực ESP32 rồi ghi heartbeat bền vững vào Database."""

    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thiết bị.")

    received_at = record_device_heartbeat(
        db=db, device=device, model_version=payload.model_version
    )
    return DeviceHeartbeatResponse(
        device_id=device_id,
        status="online",
        received_at=received_at,
        timeout_seconds=HEARTBEAT_TIMEOUT_SECONDS,
    )


@status_router.get(
    "/{device_id}/status",
    response_model=DeviceStatusResponse,
    status_code=status.HTTP_200_OK,
)
def get_device_status(
    authorized_data: tuple[Device, AccountDevice] = Depends(get_authorized_device),
    db: Session = Depends(get_db),
):
    """Chỉ caregiver có quyền mới xem được trạng thái thiết bị."""

    device, _ = authorized_data
    state, last_seen_at = get_device_liveness(db, device.device_id)
    return DeviceStatusResponse(
        device_id=device.device_id,
        status=state,
        last_seen_at=last_seen_at,
        timeout_seconds=HEARTBEAT_TIMEOUT_SECONDS,
    )
