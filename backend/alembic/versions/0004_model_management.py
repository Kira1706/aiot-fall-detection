"""Schema v4: metadata kiểm tra file model và phiên bản phát hành.

Revision ID: 0004_model_management
Revises: 0003_alert_notifications
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_model_management"
down_revision = "0003_alert_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Giữ model cũ và thêm thông tin xác thực file cho model mới."""
    # NULL giúp giữ các bản ghi ModelVersion cũ vốn chưa có SHA-256.
    op.add_column("model_versions", sa.Column("sha256", sa.String(64), nullable=True))
    op.add_column("model_versions", sa.Column("size_bytes", sa.BigInteger(), nullable=True))

    # Một dòng có release_id=1 đại diện phiên bản đang phát hành.
    op.create_table(
        "model_releases",
        sa.Column("release_id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version"], ["model_versions.version"], ondelete="RESTRICT"
        ),
    )


def downgrade() -> None:
    """Không tự động hạ schema vì có thể mất trạng thái phát hành."""
    raise RuntimeError("Không downgrade schema v4 tự động; hãy dùng bản backup đã kiểm tra.")
