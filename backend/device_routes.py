
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

from device_permissions import get_authorized_device

from device_schemas import (
    DeviceLinkRequest,
    DeviceNicknameRequest,
    FollowedDeviceResponse,
)

from models import Account, AccountDevice, Device


# Đọc cấu hình từ file .env trong thư mục backend.
# Không ghi đè các biến môi trường đã được thiết lập.
BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    dotenv_path=BASE_DIR / ".env"
)


# Tạo nhóm API thiết bị.
router = APIRouter(
    prefix="/devices",
    tags=["Devices"],
)


def require_demo_linking():
    """
    Chỉ cho phép liên kết bằng Device ID ở chế độ demo.

    Đây chưa phải cơ chế chứng minh quyền sở hữu thiết bị.
    Mặc định chức năng bị tắt để tránh cấp quyền tùy ý.
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
) -> FollowedDeviceResponse:
    """
    Tạo dữ liệu trả về từ Device và AccountDevice.

    Tên riêng được lấy theo đúng liên kết của caregiver.
    """

    return FollowedDeviceResponse(
        device_id=device.device_id,
        display_name=account_device.display_name,
        status=device.status,
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
):
    """
    Lấy danh sách thiết bị caregiver đang theo dõi.

    Chỉ sử dụng Account ID từ JWT đã được xác minh.
    """

    # Ghép Device với AccountDevice để lấy tên riêng.
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

    # Tạo danh sách response chỉ gồm các thiết bị có quyền.
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
    Trả thông tin thiết bị sau khi đã kiểm tra quyền.

    Dependency sẽ xác thực JWT và kiểm tra AccountDevice.
    """

    device, account_device = authorized_data

    return build_device_response(
        device,
        account_device,
    )


# =========================================================
# 3. LIÊN KẾT THIẾT BỊ
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
):
    """
    Tạo liên kết giữa caregiver và Device đã đăng ký.

    Chức năng này chỉ được bật trong môi trường demo.
    Chưa xác minh quyền sở hữu thiết bị ngoài Device ID.
    """

    # Chặn tạo liên kết khi chưa bật chế độ thử nghiệm.
    require_demo_linking()

    # Tìm Device đã được đăng ký trước trong Database.
    device = db.get(
        Device,
        payload.device_id,
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thiết bị.",
        )

    # Xác định khóa chính kép của liên kết.
    link_key = (
        current_account.account_id,
        device.device_id,
    )

    # Không cho cùng caregiver liên kết trùng Device.
    existing_link = db.get(
        AccountDevice,
        link_key,
    )

    if existing_link is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bạn đã liên kết thiết bị này.",
        )

    # Tạo liên kết với Account ID lấy từ JWT.
    # Không nhận Account ID do Client tự khai báo.
    account_device = AccountDevice(
        account_id=current_account.account_id,
        device_id=device.device_id,
        display_name=payload.display_name,
    )

    db.add(account_device)

    try:
        # Lưu liên kết vào Database.
        db.commit()

    except IntegrityError:
        # Phục hồi Session khi giao dịch thất bại.
        db.rollback()

        # Xử lý trường hợp hai request đồng thời
        # cùng tạo một liên kết AccountDevice.
        duplicate_link = db.get(
            AccountDevice,
            link_key,
        )

        if duplicate_link is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bạn đã liên kết thiết bị này.",
            )

        # Nếu lỗi do nguyên nhân khác thì chuyển tiếp.
        raise

    # Đọc lại liên kết vừa tạo.
    db.refresh(account_device)

    return build_device_response(
        device,
        account_device,
    )


# =========================================================
# 4. ĐỔI HOẶC XÓA TÊN RIÊNG CỦA THIẾT BỊ
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
):
    """
    Cập nhật tên riêng của Device đối với caregiver hiện tại.

    Chỉ sửa AccountDevice của caregiver đã xác thực.
    Không thay đổi Device ID hoặc tên của caregiver khác.
    """

    # Dependency đã xác minh caregiver có liên kết.
    device, account_device = authorized_data

    # Ghi tên mới hoặc None nếu caregiver muốn xóa tên.
    account_device.display_name = payload.display_name

    # Xác nhận thay đổi trong Database.
    db.commit()

    # Đọc lại giá trị sau khi cập nhật.
    db.refresh(account_device)

    return build_device_response(
        device,
        account_device,
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
    Hủy liên kết Device của caregiver hiện tại.

    Chỉ xóa một bản ghi trong AccountDevice.
    Không xóa Device, Account hoặc FallEvent.
    """

    # Lấy liên kết đã được xác minh quyền.
    device, account_device = authorized_data

    # Chỉ xóa liên kết của caregiver hiện tại.
    db.delete(account_device)

    # Xác nhận thao tác xóa liên kết.
    db.commit()

    # HTTP 204 không có nội dung response.
    return None
