"""Schema v6: xác minh email và mã khôi phục mật khẩu một lần."""

from alembic import op
import sqlalchemy as sa

revision = "0006_account_security"
down_revision = "0005_google_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Bổ sung dữ liệu bảo mật mà không thay đổi quyền truy cập cũ."""
    op.add_column(
        "accounts",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Tài khoản Google cũ đã được kiểm tra email_verified=True ở lúc tạo.
    # Tài khoản mật khẩu cũ không được tự đánh dấu đã xác minh.
    op.execute(
        "UPDATE accounts SET email_verified_at = CURRENT_TIMESTAMP "
        "WHERE google_sub IS NOT NULL"
    )
    op.create_table(
        "account_action_tokens",
        sa.Column("token_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.account_id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_account_action_tokens_hash"),
        sa.CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="ck_account_action_purpose"),
    )
    op.create_index("ix_account_action_tokens_account_purpose", "account_action_tokens", ["account_id", "purpose", "created_at"])


def downgrade() -> None:
    """Không tự động xóa dữ liệu bảo mật đã phát sinh."""
    raise RuntimeError("Không tự động downgrade schema v6; hãy dùng backup đã kiểm chứng.")
