
"""Dữ liệu heartbeat gửi lên và trạng thái trả về cho Client."""

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class DeviceHeartbeatRequest(BaseModel):
    """Dữ liệu ESP32 gửi định kỳ cùng heartbeat."""

    model_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    @field_validator("model_version", mode="before")
    @classmethod
    def normalize_model_version(cls, value):
        """Loại bỏ khoảng trắng thừa của phiên bản model."""

        if isinstance(value, str):
            return value.strip()

        return value


class DeviceHeartbeatResponse(BaseModel):
    """Kết quả nhận heartbeat của Backend."""

    device_id: str
    status: Literal["online"]
    received_at: datetime
    timeout_seconds: int


class DeviceStatusResponse(BaseModel):
    """Trạng thái Device trả cho caregiver có quyền theo dõi."""

    device_id: str
    status: Literal["online", "offline"]
    last_seen_at: datetime | None
    timeout_seconds: int
