"""Schema v3: lưu thông báo cảnh báo cho từng caregiver.

Revision ID: 0003_alert_notifications
Revises: 0002_schema_v2
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_alert_notifications"
down_revision = "0002_schema_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Bổ sung bảng thông báo mà không thay đổi dữ liệu Fall Event v2."""

    op.create_table(
        "alert_notifications",
        sa.Column("notification_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("fall_event_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"]),
        sa.ForeignKeyConstraint(["fall_event_id"], ["fall_events.event_id"]),
        sa.UniqueConstraint(
            "account_id", "fall_event_id",
            name="uq_alert_notifications_account_event",
        ),
    )
    op.create_index(
        "ix_alert_notifications_account_notification",
        "alert_notifications", ["account_id", "notification_id"],
    )


def downgrade() -> None:
    """Chặn tự xóa dữ liệu thông báo đã ghi nhận."""

    raise RuntimeError(
        "Không hạ schema v3 tự động vì sẽ làm mất các thông báo cảnh báo."
    )
