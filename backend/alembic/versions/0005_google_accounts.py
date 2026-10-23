"""Schema v5: hỗ trợ tài khoản Google OIDC bên cạnh tài khoản mật khẩu."""

from alembic import op
import sqlalchemy as sa

revision = "0005_google_accounts"
down_revision = "0004_model_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Giữ tài khoản cũ, cho phép tài khoản Google không có mật khẩu."""
    op.alter_column(
        "accounts", "password_hash",
        existing_type=sa.String(255),
        existing_nullable=False,
        nullable=True,
    )
    op.add_column(
        "accounts",
        sa.Column("google_sub", sa.String(255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_accounts_google_sub", "accounts", ["google_sub"]
    )
    # Một tài khoản hợp lệ phải có mật khẩu hoặc Google sub.
    op.create_check_constraint(
        "ck_accounts_has_auth_method",
        "accounts",
        "password_hash IS NOT NULL OR google_sub IS NOT NULL",
    )


def downgrade() -> None:
    """Chặn downgrade vì có thể mất quyền đăng nhập của tài khoản Google."""
    raise RuntimeError(
        "Không downgrade schema v5 tự động; khôi phục bằng bản backup đã kiểm tra."
    )
