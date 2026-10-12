
"""Các API đọc thông tin thiết bị của người chăm sóc."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from device_permissions import get_authorized_device
from device_schemas import FollowedDeviceResponse
from models import Account, AccountDevice, Device


# Nhóm các API thiết bị dưới đường dẫn /devices.
router = APIRouter(
    prefix="/devices",
    tags=["Devices"],
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
):
    """
    Lấy danh sách Device mà caregiver đang theo dõi.

    Chỉ sử dụng Account ID lấy từ JWT đã xác minh.
    Không cho Client tự chọn Account ID cần truy vấn.
    """

    # Ghép Device với AccountDevice để lấy tên riêng
    # và chỉ chọn các thiết bị mà Account đang theo dõi.
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
        .order_by(Device.device_id)
    )

    # Mỗi kết quả gồm một Device và tên hiển thị riêng.
    rows = db.execute(statement).all()

    # Chuyển dữ liệu thành Response Schema.
    # Không trả thông tin Account của người khác.
    result = []

    for device, display_name in rows:
        result.append(
            FollowedDeviceResponse(
                device_id=device.device_id,
                display_name=display_name,
                status=device.status,
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
):
    """
    Trả thông tin một thiết bị nếu caregiver có quyền.

    Việc xác thực JWT và kiểm tra AccountDevice
    được thực hiện trước bởi các dependency.
    """

    # Lấy hai object đã được Authorization kiểm tra.
    device, account_device = authorized_data

    # Trả thông tin Device và tên riêng của caregiver.
    return FollowedDeviceResponse(
        device_id=device.device_id,
        display_name=account_device.display_name,
        status=device.status,
        model_version=device.model_version,
    )
