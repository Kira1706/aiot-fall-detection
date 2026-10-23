"""Schema v7: chủ sở hữu, mã ghép nối và lời mời chia sẻ bảo mật."""

from alembic import op
import sqlalchemy as sa

revision = "0007_secure_device_pairing"
down_revision = "0006_account_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Tạo ba bảng mới, không tự gán chủ sở hữu cho dữ liệu cũ."""
    op.create_table(
        "device_ownerships",
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("device_id"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.account_id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "device_pairing_tokens",
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("device_id"),
        sa.UniqueConstraint("token_hash", name="uq_device_pairing_token_hash"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"], ondelete="CASCADE"),
    )
    op.create_table(
        "device_share_invitations",
        sa.Column("invitation_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("invited_account_id", sa.Integer(), nullable=False),
        sa.Column("invited_by_account_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_device_share_invitation_hash"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_account_id"], ["accounts.account_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_account_id"], ["accounts.account_id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_device_invitations_target", "device_share_invitations", ["device_id", "invited_account_id"]
    )


def downgrade() -> None:
    """Chặn hạ schema tự động vì thao tác sẽ xóa dữ liệu cấp quyền."""
    raise RuntimeError("Không downgrade v7 tự động; phải sao lưu và phục hồi có kiểm soát.")
