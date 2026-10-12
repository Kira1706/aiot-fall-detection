
"""Định nghĩa dữ liệu trả về của các API thiết bị."""

from pydantic import BaseModel, Field


class FollowedDeviceResponse(BaseModel):
    """
    Thông tin thiết bị mà caregiver được phép theo dõi.

    Tên hiển thị được lấy từ bảng AccountDevice,
    vì mỗi caregiver có thể đặt tên riêng cho cùng thiết bị.
    """

    device_id: str

    display_name: str | None = None

    status: str

    model_version: str | None = None
