
"""Các API đọc và quản lý liên kết thiết bị của caregiver."""

import os

from pathlib import Path

from dotenv import load_dotenv

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db

from device_heartbeat_store import (
    HeartbeatStore,
    get_heartbeat_store,
)

from device_permissions import get_authorized_device

from device_schemas import (
    DeviceLinkRequest,
    DeviceNicknameRequest,
    FollowedDeviceResponse,
)

from models import Account, AccountDevice, Device


# Đọc cấu hình phát triển của Backend.
BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    dotenv_path=BASE_DIR / ".env"
)


router = APIRouter(
    prefix="/devices",
    tags=["Devices"],
)


def require_demo_linking():
    """
    Chỉ cho phép liên kết bằng Device ID ở môi trường demo.

    Chế độ này chưa chứng minh quyền sở hữu thiết bị.
    """

    demo_mode = os.getenv(
        "DEVICE_LINK_DEMO_MODE",
        "false",
    ).lower()

    if demo_mode != "true":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Chức năng liên kết thử nghiệm "
                "chưa được bật."
            ),
        )


def build_device_response(
    device: Device,
    account_device: AccountDevice,
    store: HeartbeatStore,
) -> FollowedDeviceResponse:
    """
    Tạo dữ liệu Device dành riêng cho caregiver.

    Trạng thái online/offline lấy từ bộ nhớ heartbeat.
    Tên hiển thị lấy từ liên kết AccountDevice.
    """

    # Không sử dụng device.status để xác định kết nối thật.
    liveness = store.snapshot(
        device.device_id
    )

    return FollowedDeviceResponse(
        device_id=device.device_id,
        display_name=account_device.display_name,
        status=liveness.status,
        model_version=device.model_version,
    )


# =========================================================
# 1. LẤY DANH SÁCH THIẾT BỊ ĐANG THEO DÕI
# =========================================================

@router.get(
    "",
    response_model=list[FollowedDeviceResponse],
    status_code=status.HTTP_200_OK,
)
def get_my_devices(
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
    store: HeartbeatStore = Depends(get_heartbeat_store),
):
    """
    Lấy danh sách Device mà caregiver được phép theo dõi.

    Trạng thái được tính từ heartbeat của từng thiết bị.
    """

    statement = (
        select(
            Device,
            AccountDevice.display_name,
        )
        .join(
            AccountDevice,
            AccountDevice.device_id == Device.device_id,
        )
        .where(
            AccountDevice.account_id
            == current_account.account_id
        )
        .order_by(
            Device.device_id
        )
    )

    rows = db.execute(statement).all()

    result = []

    for device, display_name in rows:

        # Tính trạng thái từ heartbeat mới nhất.
        liveness = store.snapshot(
            device.device_id
        )

        result.append(
            FollowedDeviceResponse(
                device_id=device.device_id,
                display_name=display_name,
                status=liveness.status,
                model_version=device.model_version,
            )
        )

    return result


# =========================================================
# 2. XEM CHI TIẾT MỘT THIẾT BỊ
# =========================================================

@router.get(
    "/{device_id}",
    response_model=FollowedDeviceResponse,
    status_code=status.HTTP_200_OK,
)
def get_device_detail(
    authorized_data: tuple[Device, AccountDevice] = Depends(
        get_authorized_device
    ),
    store: HeartbeatStore = Depends(get_heartbeat_store),
):
    """
    Lấy chi tiết Device sau khi xác minh quyền caregiver.

    Trạng thái kết nối được tính từ heartbeat.
    """

    device, account_device = authorized_data

    return build_device_response(
        device,
        account_device,
        store,
    )


# =========================================================
# 3. LIÊN KẾT THIẾT BỊ TRONG CHẾ ĐỘ DEMO
# =========================================================

@router.post(
    "/link",
    response_model=FollowedDeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
def link_device(
    payload: DeviceLinkRequest,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
    store: HeartbeatStore = Depends(get_heartbeat_store),
):
    """
    Tạo liên kết caregiver với Device đã đăng ký.

    Chỉ cho phép khi chế độ liên kết demo được bật.
    """

    # Không mở liên kết chỉ bằng ID nếu chưa bật demo.
    require_demo_linking()

    device = db.get(
        Device,
        payload.device_id,
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thiết bị.",
        )

    # Khóa chính kép xác định một liên kết duy nhất.
    link_key = (
        current_account.account_id,
        device.device_id,
    )

    existing_link = db.get(
        AccountDevice,
        link_key,
    )

    if existing_link is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bạn đã liên kết thiết bị này.",
        )

    account_device = AccountDevice(
        account_id=current_account.account_id,
        device_id=device.device_id,
        display_name=payload.display_name,
    )

    db.add(account_device)

    try:
        db.commit()

    except IntegrityError:
        # Phục hồi Session trước khi kiểm tra lỗi trùng.
        db.rollback()

        duplicate_link = db.get(
            AccountDevice,
            link_key,
        )

        if duplicate_link is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bạn đã liên kết thiết bị này.",
            )

        raise

    db.refresh(account_device)

    return build_device_response(
        device,
        account_device,
        store,
    )


# =========================================================
# 4. ĐỔI HOẶC XÓA TÊN RIÊNG
# =========================================================

@router.patch(
    "/{device_id}/nickname",
    response_model=FollowedDeviceResponse,
    status_code=status.HTTP_200_OK,
)
def update_device_nickname(
    payload: DeviceNicknameRequest,
    authorized_data: tuple[Device, AccountDevice] = Depends(
        get_authorized_device
    ),
    db: Session = Depends(get_db),
    store: HeartbeatStore = Depends(get_heartbeat_store),
):
    """
    Cập nhật tên riêng của Device cho caregiver hiện tại.

    Không thay đổi Device hoặc liên kết của caregiver khác.
    """

    device, account_device = authorized_data

    # None có nghĩa là xóa tên riêng nhưng vẫn giữ liên kết.
    account_device.display_name = payload.display_name

    db.commit()
    db.refresh(account_device)

    return build_device_response(
        device,
        account_device,
        store,
    )


# =========================================================
# 5. HỦY LIÊN KẾT THIẾT BỊ
# =========================================================

@router.delete(
    "/{device_id}/link",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unlink_device(
    authorized_data: tuple[Device, AccountDevice] = Depends(
        get_authorized_device
    ),
    db: Session = Depends(get_db),
):
    """
    Hủy liên kết của caregiver với một Device.

    Không xóa Device hoặc dữ liệu FallEvent.
    """

    device, account_device = authorized_data

    # Chỉ xóa liên kết của caregiver đang đăng nhập.
    db.delete(account_device)

    db.commit()

    # HTTP 204 không trả nội dung response.
    return None
