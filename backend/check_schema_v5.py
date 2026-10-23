"""Kiểm tra schema v5 đã hỗ trợ hai phương thức đăng nhập."""

from sqlalchemy import inspect
from database import engine


def main():
    """Xác minh bảng accounts, khóa Google và khả năng NULL password_hash."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Hãy đặt DB_BACKEND=postgresql trước khi kiểm tra.")

    inspector = inspect(engine)
    columns = {row["name"]: row for row in inspector.get_columns("accounts")}
    assert "google_sub" in columns, "Chưa có cột accounts.google_sub."
    assert columns["google_sub"]["nullable"], "Google sub phải cho phép NULL."
    assert columns["password_hash"]["nullable"], "password_hash phải cho phép NULL."

    constraints = inspector.get_unique_constraints("accounts")
    assert any(set(item["column_names"]) == {"google_sub"} for item in constraints), (
        "Thiếu UNIQUE(accounts.google_sub)."
    )
    checks = inspector.get_check_constraints("accounts")
    assert any(item["name"] == "ck_accounts_has_auth_method" for item in checks), (
        "Thiếu CHECK bảo đảm Account có cách xác thực."
    )
    print("POSTGRESQL SCHEMA V5: PASS")


if __name__ == "__main__":
    main()
