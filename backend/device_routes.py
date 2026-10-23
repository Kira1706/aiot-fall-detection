"""Quản lý Device và liên kết caregiver; trạng thái đọc từ Database."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from device_heartbeat_service import get_device_liveness
from device_permissions import get_authorized_device
from device_schemas import DeviceLinkRequest, DeviceNicknameRequest, FollowedDeviceResponse
from models import Account, AccountDevice, Device

router = APIRouter(prefix="/devices", tags=["Devices"])

def build_device_response(
    device: Device, link: AccountDevice, db: Session
) -> FollowedDeviceResponse:
    """Trả tên riêng caregiver và trạng thái heartbeat được lưu trong DB."""

    liveness, _ = get_device_liveness(db, device.device_id)
    return FollowedDeviceResponse(
        device_id=device.device_id,
        display_name=link.display_name,
        status=liveness,
        model_version=device.model_version,
    )


@router.get("", response_model=list[FollowedDeviceResponse])
def get_my_devices(
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Chỉ lấy danh sách Device của Account đã được xác thực."""

    rows = db.execute(
        select(Device, AccountDevice)
        .join(AccountDevice, AccountDevice.device_id == Device.device_id)
        .where(AccountDevice.account_id == current_account.account_id)
        .order_by(Device.device_id)
    ).all()
    return [build_device_response(device, link, db) for device, link in rows]


@router.get("/{device_id}", response_model=FollowedDeviceResponse)
def get_device_detail(
    authorized_data: tuple[Device, AccountDevice] = Depends(get_authorized_device),
    db: Session = Depends(get_db),
):
    """Trả Device sau khi đã kiểm tra AccountDevice."""

    device, link = authorized_data
    return build_device_response(device, link, db)


@router.post(
    "/link", response_model=FollowedDeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
def link_device(
    payload: DeviceLinkRequest,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Đóng API demo cũ để không ai tự nhận quyền chỉ bằng Device ID."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Liên kết bằng Device ID đã đóng. Hãy sử dụng mã ghép nối an toàn.",
    )


@router.patch("/{device_id}/nickname", response_model=FollowedDeviceResponse)
def update_device_nickname(
    payload: DeviceNicknameRequest,
    authorized_data: tuple[Device, AccountDevice] = Depends(get_authorized_device),
    db: Session = Depends(get_db),
):
    """Chỉ thay tên liên kết của caregiver hiện tại."""

    device, link = authorized_data
    link.display_name = payload.display_name
    db.commit()
    db.refresh(link)
    return build_device_response(device, link, db)


@router.delete("/{device_id}/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink_device(
    authorized_data: tuple[Device, AccountDevice] = Depends(get_authorized_device),
    db: Session = Depends(get_db),
):
    """Chỉ xóa liên kết, không xóa Device hoặc FallEvent."""

    _, link = authorized_data
    from models import DeviceOwnership
    owner = db.get(DeviceOwnership, link.device_id)
    if owner is not None and owner.account_id == link.account_id:
        raise HTTPException(
            status_code=409,
            detail="Chủ sở hữu không thể tự hủy theo dõi. Hãy thực hiện quy trình chuyển quyền sau.",
        )
    db.delete(link)
    db.commit()
    return None
