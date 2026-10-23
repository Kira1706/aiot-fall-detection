"""Kiểm tra schema v6 trên PostgreSQL mà không sửa dữ liệu."""

from sqlalchemy import inspect
from database import engine


def main() -> None:
    """Kiểm tra các cột và ràng buộc mới sau migration."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Kiểm tra này yêu cầu DB_BACKEND=postgresql.")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"accounts", "account_action_tokens"}.issubset(tables)
    account_columns = {c["name"] for c in inspector.get_columns("accounts")}
    assert {"google_sub", "password_hash", "email_verified_at"}.issubset(account_columns)
    token_columns = {c["name"] for c in inspector.get_columns("account_action_tokens")}
    assert {"token_id", "account_id", "purpose", "token_hash", "created_at", "expires_at", "consumed_at"}.issubset(token_columns)
    unique = [set(c["column_names"]) for c in inspector.get_unique_constraints("account_action_tokens")]
    assert {"token_hash"} in unique
    foreign_keys = inspector.get_foreign_keys("account_action_tokens")
    assert any(fk["referred_table"] == "accounts" for fk in foreign_keys)
    print("POSTGRESQL SCHEMA V6: PASS")


if __name__ == "__main__":
    main()
