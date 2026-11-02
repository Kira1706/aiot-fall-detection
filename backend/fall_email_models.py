"""Lưu hàng đợi email cảnh báo để gửi lại an toàn sau khi Backend khởi động lại."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class FallEmailDelivery(Base):
    """Một thông báo của caregiver tương ứng tối đa một công việc gửi email."""

    __tablename__ = "fall_email_deliveries"
    __table_args__ = (
        UniqueConstraint("notification_id", name="uq_fall_email_notification"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'skipped', 'failed')",
            name="ck_fall_email_status",
        ),
        Index("ix_fall_email_due", "status", "next_attempt_at"),
    )

    delivery_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("alert_notifications.notification_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
