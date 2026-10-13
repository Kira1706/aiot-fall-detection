
"""Kiểm tra dữ liệu đầu vào và đầu ra của các API thiết bị."""

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


def normalize_display_name(value):
    """
    Chuẩn hóa tên riêng của thiết bị.

    - Nếu là None, giữ nguyên để biểu thị không có tên riêng.
    - Nếu là chuỗi, loại bỏ khoảng trắng đầu và cuối.
    - Không chấp nhận chuỗi rỗng hoặc chỉ có khoảng trắng.
    """

    if value is None:
        return None

    if isinstance(value, str):
        cleaned_name = value.strip()

        if not cleaned_name:
            raise ValueError(
                "Tên thiết bị không được chỉ chứa khoảng trắng."
            )

        return cleaned_name

    return value


class FollowedDeviceResponse(BaseModel):
    """
    Thông tin Device được phép trả về cho caregiver.

    display_name là tên riêng do caregiver đặt.
    """

    device_id: str
    display_name: str | None = None
    status: str
    model_version: str | None = None


class DeviceLinkRequest(BaseModel):
    """
    Dữ liệu caregiver gửi khi yêu cầu liên kết Device.

    Device phải tồn tại trong bảng devices.
    Tên hiển thị có thể không được cung cấp.
    """

    device_id: str = Field(
        min_length=1,
        max_length=64,
    )

    display_name: str | None = Field(
        default=None,
        max_length=100,
    )

    @field_validator("device_id", mode="before")
    @classmethod
    def normalize_device_id(cls, value):
        """Loại bỏ khoảng trắng thừa ở hai đầu Device ID."""

        if isinstance(value, str):
            return value.strip()

        return value

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value):
        """Chuẩn hóa tên riêng trước khi kiểm tra độ dài."""

        return normalize_display_name(value)


class DeviceNicknameRequest(BaseModel):
    """
    Dữ liệu cập nhật tên riêng của thiết bị.

    Bắt buộc gửi trường display_name.
    Gửi null nếu muốn xóa tên riêng.
    """

    display_name: str | None = Field(
        ...,
        max_length=100,
    )

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value):
        """Chuẩn hóa tên riêng trước khi lưu."""

        return normalize_display_name(value)
