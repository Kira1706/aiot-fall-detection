"""Schema v8: thu hồi phiên, giới hạn lượt gọi và lưu nhật ký bảo mật."""

from alembic import op
import sqlalchemy as sa

revision = "0008_security_hardening"
down_revision = "0007_secure_device_pairing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Giữ dữ liệu v7 và thêm cấu trúc bảo mật mới."""
    op.add_column(
        "accounts",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint("ck_accounts_session_version_positive", "accounts", "session_version >= 1")

    op.create_table(
        "security_revoked_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.account_id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revoked_tokens_expires_at", "security_revoked_tokens", ["expires_at"])

    op.create_table(
        "security_rate_buckets",
        sa.Column("bucket_key", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_rate_expires_at", "security_rate_buckets", ["expires_at"])

    op.create_table(
        "security_audit_logs",
        sa.Column("audit_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_account_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("result", sa.String(24), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("client_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_security_audit_created", "security_audit_logs", ["created_at"])
    op.create_index("ix_security_audit_actor", "security_audit_logs", ["actor_account_id"])


def downgrade() -> None:
    """Chặn hạ schema tự động vì sẽ mất lịch sử bảo mật."""
    raise RuntimeError("Không tự động downgrade v8 vì có dữ liệu thu hồi phiên và audit.")
