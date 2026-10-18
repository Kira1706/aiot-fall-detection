"""Kiểm tra dữ liệu Fall Event theo hợp đồng API schema v2."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, UUID4, field_validator


class FallEventCreate(BaseModel):
    """Một lần ngã có UUID riêng do ESP32 tạo và giữ nguyên khi gửi lại."""

    model_config = ConfigDict(extra="forbid")

    edge_event_id: UUID4
    event_time: datetime
    event_type: Literal["fall"]
    model_version: str = Field(min_length=1, max_length=50)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        """Bắt buộc thời gian có timezone và chuẩn hóa về UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Thời điểm sự kiện phải có múi giờ.")
        return value.astimezone(timezone.utc)

    @field_validator("model_version", mode="before")
    @classmethod
    def normalize_model_version(cls, value):
        """Loại bỏ khoảng trắng trước khi kiểm tra độ dài."""

        return value.strip() if isinstance(value, str) else value


class FallEventResponse(BaseModel):
    """Thông tin sự kiện được phép cung cấp cho caregiver."""

    event_id: int
    device_id: str
    edge_event_id: UUID | None
    event_time: datetime
    event_type: str
    model_version: str
    confidence: float | None


class FallEventAcknowledgement(BaseModel):
    """Xác nhận ghi sự kiện dành cho ESP32."""

    event_id: int
    status: Literal["recorded", "duplicate"]
    duplicate: bool
