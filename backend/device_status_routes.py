
"""API nhận heartbeat từ Edge và xem tình trạng kết nối thiết bị."""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.orm import Session

from database import get_db

from device_auth import require_device_key

from device_heartbeat_store import (
    HeartbeatStore,
    get_heartbeat_store,
)

from device_permissions import get_authorized_device

from device_status_schemas import (
    DeviceHeartbeatRequest,
    DeviceHeartbeatResponse,
    DeviceStatusResponse,
)

from models import AccountDevice, Device


# API dành riêng cho Edge Device.
edge_router = APIRouter(
    prefix="/device-ingest",
    tags=["Device Ingest"],
)


# API đọc trạng thái dành cho caregiver.
status_router = APIRouter(
    prefix="/devices",
    tags=["Devices"],
)


# =========================================================
# 1. ESP32 GỬI HEARTBEAT
# =========================================================

@edge_router.post(
    "/{device_id}/heartbeat",
    response_model=DeviceHeartbeatResponse,
    status_code=status.HTTP_200_OK,
)
def receive_heartbeat(
    payload: DeviceHeartbeatRequest,
    device_id: str = Depends(require_device_key),
    db: Session = Depends(get_db),
    store: HeartbeatStore = Depends(get_heartbeat_store),
):
    """
    Nhận heartbeat từ Device có khóa bí mật hợp lệ.

    Quy trình:
    1. Xác thực Device Key.
    2. Kiểm tra Device đã đăng ký trong Database.
    3. Cập nhật model_version nếu Device báo phiên bản mới.
    4. Ghi nhận thời điểm Server nhận heartbeat.
    5. Trả kết quả thành công.
    """

    # Chỉ nhận heartbeat từ Device đã đăng ký.
    device = db.get(
        Device,
        device_id,
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thiết bị.",
        )

    # Chỉ cập nhật model_version khi ESP32 có gửi giá trị mới.
    # Không thay đổi phiên bản nếu request không chứa thông tin.
    if (
        payload.model_version is not None
        and device.model_version != payload.model_version
    ):
        device.model_version = payload.model_version

        # Lưu phiên bản model đã được báo cáo vào SQLite.
        db.commit()

    # Chỉ ghi nhận heartbeat sau khi xử lý dữ liệu thành công.
    received_at = store.record(
        device_id
    )

    return DeviceHeartbeatResponse(
        device_id=device_id,
        status="online",
        received_at=received_at,
        timeout_seconds=store.timeout_seconds,
    )


# =========================================================
# 2. CAREGIVER XEM TRẠNG THÁI THIẾT BỊ
# =========================================================

@status_router.get(
    "/{device_id}/status",
    response_model=DeviceStatusResponse,
    status_code=status.HTTP_200_OK,
)
def get_device_status(
    authorized_data: tuple[Device, AccountDevice] = Depends(
        get_authorized_device
    ),
    store: HeartbeatStore = Depends(get_heartbeat_store),
):
    """
    Cho caregiver có quyền đọc tình trạng kết nối hiện tại.

    Trạng thái được tính từ heartbeat gần nhất.
    Không lấy trực tiếp giá trị status cũ trong SQLite.
    """

    # Dependency đã kiểm tra JWT và quyền theo dõi Device.
    device, account_device = authorized_data

    # Tính trạng thái tại thời điểm có request.
    result = store.snapshot(
        device.device_id
    )

    return DeviceStatusResponse(
        device_id=device.device_id,
        status=result.status,
        last_seen_at=result.last_seen_at,
        timeout_seconds=store.timeout_seconds,
    )
