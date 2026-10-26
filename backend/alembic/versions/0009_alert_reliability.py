"""Schema v9: trạng thái xử lý sự cố được lưu bền vững."""
from alembic import op
import sqlalchemy as sa

revision = "0009_alert_reliability"
down_revision = "0008_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Bổ sung trạng thái xử lý riêng, không sửa cờ đã xem của caregiver."""
    op.create_table(
        "fall_incident_resolutions",
        sa.Column("fall_event_id", sa.Integer(), sa.ForeignKey("fall_events.event_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("updated_by_account_id", sa.Integer(), sa.ForeignKey("accounts.account_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.CheckConstraint("status IN ('acknowledged', 'resolved')", name="ck_incident_resolution_status"),
    )
    op.create_index("ix_incident_resolution_updated", "fall_incident_resolutions", ["updated_at"])


def downgrade() -> None:
    """Không tự xóa lịch sử xử lý sự cố trong quá trình hạ phiên bản."""
    raise RuntimeError("Không tự downgrade schema v9 vì có thể mất dữ liệu xử lý sự cố.")
