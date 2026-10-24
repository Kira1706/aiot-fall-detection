"""Kiểm tra cấu trúc bảo mật schema v8 sau migration."""

from sqlalchemy import inspect, text
from database import engine


def main():
    """Kiểm tra cột phiên và các bảng bảo mật trên PostgreSQL."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Phải đặt DB_BACKEND=postgresql để nghiệm thu schema v8.")
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    expected = {"security_revoked_tokens", "security_rate_buckets", "security_audit_logs"}
    assert expected.issubset(names), f"Thiếu bảng: {sorted(expected - names)}"
    columns = {x["name"] for x in inspector.get_columns("accounts")}
    assert "session_version" in columns
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM accounts WHERE session_version < 1")) == 0
    print("POSTGRESQL SCHEMA V8: PASS")


if __name__ == "__main__":
    main()
