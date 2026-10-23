"""Định nghĩa các bảng AIoT, bổ sung thông báo bền vững ở schema v3."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Account(Base):
    """Tài khoản người chăm sóc."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("google_sub", name="uq_accounts_google_sub"),
        CheckConstraint(
            "password_hash IS NOT NULL OR google_sub IS NOT NULL",
            name="ck_accounts_has_auth_method",
        ),
    )

    account_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Tài khoản Google không bắt buộc có mật khẩu nội bộ.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Google sub cố định là định danh đăng nhập, không dùng email làm khóa.
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # NULL đối với email chưa được người dùng xác minh.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ModelRelease(Base):
    """Phiên bản model được phát hành chung cho các thiết bị Edge."""

    __tablename__ = "model_releases"

    release_id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(
        String(50), ForeignKey("model_versions.version", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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


class AlertNotification(Base):
    """Thông báo té ngã dành riêng cho một caregiver tại thời điểm ghi sự kiện."""

    __tablename__ = "alert_notifications"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "fall_event_id", name="uq_alert_notifications_account_event"
        ),
        Index("ix_alert_notifications_account_notification", "account_id", "notification_id"),
    )

    notification_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id"), nullable=False
    )
    fall_event_id: Mapped[int] = mapped_column(
        ForeignKey("fall_events.event_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AccountActionToken(Base):
    """Lưu SHA-256 của token xác minh/khôi phục, không lưu token gốc."""

    __tablename__ = "account_action_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_account_action_tokens_hash"),
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name="ck_account_action_purpose",
        ),
        Index("ix_account_action_tokens_account_purpose", "account_id", "purpose", "created_at"),
    )

    token_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceOwnership(Base):
    """Một Device chỉ có một caregiver giữ quyền chủ sở hữu."""

    __tablename__ = "device_ownerships"

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DevicePairingToken(Base):
    """Lưu mã ghép nối dạng băm, một mã đang có hiệu lực trên mỗi Device."""

    __tablename__ = "device_pairing_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_device_pairing_token_hash"),)

    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), primary_key=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceShareInvitation(Base):
    """Mã mời một lần chỉ cho tài khoản được chỉ định."""

    __tablename__ = "device_share_invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_device_share_invitation_hash"),
        Index("ix_device_invitations_target", "device_id", "invited_account_id"),
    )

    invitation_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False
    )
    invited_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="CASCADE"), nullable=False
    )
    invited_by_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
