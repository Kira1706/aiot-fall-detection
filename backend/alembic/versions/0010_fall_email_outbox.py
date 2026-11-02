"""Schema v10: hàng đợi email cảnh báo theo từng AlertNotification."""

from alembic import op
import sqlalchemy as sa

revision = "0010_fall_email_outbox"
down_revision = "0009_alert_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Thêm bảng email mà không thay đổi bảng FallEvent và AlertNotification cũ."""
    op.create_table(
        "fall_email_deliveries",
        sa.Column("delivery_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("alert_notifications.notification_id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(80), nullable=True),
        sa.UniqueConstraint("notification_id", name="uq_fall_email_notification"),
        sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'skipped', 'failed')", name="ck_fall_email_status"),
    )
    op.create_index("ix_fall_email_due", "fall_email_deliveries", ["status", "next_attempt_at"])


def downgrade() -> None:
    """Không hạ schema tự động vì thao tác này sẽ làm mất lịch sử gửi email."""
    raise RuntimeError("Không downgrade v10 tự động: dữ liệu gửi email có thể bị mất.")
