"""Các cấu trúc dữ liệu dành cho Fall Event API."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class FallEventCreate(BaseModel):
    """Kiểm tra sự kiện ngã được gửi từ Edge Device."""

    # Không cho ESP32 gửi các trường ngoài hợp đồng API.
    model_config = ConfigDict(extra="forbid")

    event_time: datetime

    event_type: Literal["fall"]

    model_version: str = Field(
        min_length=1,
        max_length=50,
    )

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
    )

    @field_validator("event_time")
    @classmethod
    def validate_event_time(
        cls,
        value: datetime,
    ) -> datetime:
        """
        Yêu cầu sự kiện có múi giờ và chuẩn hóa về UTC.

        Không tự thay bằng giờ Server vì sự kiện có thể
        được gửi lại sau một khoảng thời gian mất mạng.
        """

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Thời điểm sự kiện phải có múi giờ."
            )

        return value.astimezone(timezone.utc)

    @field_validator("model_version", mode="before")
    @classmethod
    def normalize_model_version(cls, value):
        """Loại bỏ khoảng trắng thừa của phiên bản AI."""

        if isinstance(value, str):
            return value.strip()

        return value


class FallEventResponse(BaseModel):
    """Thông tin Fall Event được phép trả về cho caregiver."""

    event_id: int
    device_id: str
    event_time: datetime
    event_type: Literal["fall"]
    model_version: str
    confidence: float | None


class FallEventAcknowledgement(BaseModel):
    """Kết quả Backend ghi nhận sự kiện từ ESP32."""

    event_id: int

    status: Literal["recorded", "duplicate"]

    duplicate: bool