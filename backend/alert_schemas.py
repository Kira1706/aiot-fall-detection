"""Dữ liệu thông báo ngã trả về cho caregiver."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AlertResponse(BaseModel):
    """Thông báo một Fall Event dành cho một tài khoản có quyền."""

    notification_id: int
    event_id: int
    device_id: str
    device_name: str
    event_time: datetime
    model_version: str
    confidence: float | None
    created_at: datetime
    read_at: datetime | None


class AlertReadResponse(BaseModel):
    """Xác nhận caregiver đã đánh dấu thông báo là đã xem."""

    notification_id: int
    status: Literal["read"] = "read"
    read_at: datetime
