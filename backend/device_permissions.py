
"""Kiểm tra quyền truy cập thiết bị của người chăm sóc."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from models import Account, AccountDevice, Device


def get_authorized_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_account: Account = Depends(get_current_account),
) -> tuple[Device, AccountDevice]:
    """
    Kiểm tra quyền truy cập một thiết bị cụ thể.

    Quy trình:
    1. Xác định Account từ JWT hợp lệ.
    2. Tìm Device theo device_id.
    3. Kiểm tra liên kết AccountDevice.
    4. Trả về Device và liên kết nếu có quyền.

    Nếu Device không tồn tại thì trả HTTP 404.
    Nếu Account không theo dõi Device thì trả HTTP 403.
    """

    # Tìm thiết bị theo Primary Key.
    device = db.get(
        Device,
        device_id,
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thiết bị.",
        )

    # AccountDevice có Primary Key gồm hai trường.
    # Phải kiểm tra đúng cả Account ID và Device ID.
    account_device = db.get(
        AccountDevice,
        (
            current_account.account_id,
            device_id,
        ),
    )

    # Không có liên kết nghĩa là caregiver chưa có quyền.
    if account_device is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập thiết bị này.",
        )

    # Trả thông tin thiết bị và tên riêng của caregiver.
    return device, account_device
