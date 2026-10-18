"""Schema v1: năm bảng ban đầu của dự án.

Revision ID: 0001_schema_v1
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_schema_v1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Tạo schema v1 trên Database trống; không dùng với DB đã chuyển dữ liệu."""

    op.create_table(
        "accounts",
        sa.Column("account_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.UniqueConstraint("email", name="uq_accounts_email"),
    )
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
    )
    op.create_table(
        "model_versions",
        sa.Column("version", sa.String(50), primary_key=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "account_devices",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint("account_id", "device_id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
    )
    op.create_table(
        "fall_events",
        sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"]),
    )


def downgrade() -> None:
    """Không cho phép xóa nhầm năm bảng chứa dữ liệu dự án."""

    raise RuntimeError("Không tự động hạ schema v1; hãy dùng bản sao lưu đã xác minh.")
