"""Schema v2: định danh Fall Event và heartbeat bền vững.

Revision ID: 0002_schema_v2
Revises: 0001_schema_v1
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_schema_v2"
down_revision = "0001_schema_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Bổ sung cột và bảng mà không đụng tới dữ liệu v1."""

    # NULL giữ nguyên tính hợp lệ của những Fall Event lịch sử.
    op.add_column(
        "fall_events",
        sa.Column("edge_event_id", sa.String(36), nullable=True),
    )
    # PostgreSQL cho phép nhiều NULL trong UNIQUE thông thường.
    op.create_unique_constraint(
        "uq_fall_events_device_edge_event_id",
        "fall_events",
        ["device_id", "edge_event_id"],
    )
    op.create_table(
        "device_heartbeat_states",
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("device_id"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    """Chặn tự xóa cột UUID và trạng thái heartbeat đã có dữ liệu."""

    raise RuntimeError("Không hạ v2 tự động: thao tác sẽ xóa dữ liệu mới.")
