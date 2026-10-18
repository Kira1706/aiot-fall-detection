"""Định nghĩa sáu bảng dữ liệu của hệ thống AIoT ở schema v2."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Account(Base):
    """Tài khoản người chăm sóc."""

    __tablename__ = "accounts"

    account_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)


class Device(Base):
    """Thiết bị đã được cấp phát trước trong hệ thống."""

    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)


class AccountDevice(Base):
    """Liên kết theo dõi thiết bị của từng người chăm sóc."""

    __tablename__ = "account_devices"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id"), primary_key=True
    )
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)


class FallEvent(Base):
    """Sự kiện ngã; bản ghi cũ có thể chưa có edge_event_id."""

    __tablename__ = "fall_events"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "edge_event_id", name="uq_fall_events_device_edge_event_id"
        ),
    )

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id"), nullable=False
    )
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    edge_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ModelVersion(Base):
    """Phiên bản AI model đã được đăng ký."""

    __tablename__ = "model_versions"

    version: Mapped[str] = mapped_column(String(50), primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeviceHeartbeatState(Base):
    """Chỉ lưu heartbeat mới nhất; không phải nhật ký đầy đủ."""

    __tablename__ = "device_heartbeat_states"

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
