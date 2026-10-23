"""Kiểm tra các bảng và ràng buộc của schema v7 trong PostgreSQL."""

from sqlalchemy import inspect, text
from database import engine


def main():
    """Đối chiếu bảng, ràng buộc và revision đang chạy."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Kiểm tra này chỉ áp dụng cho PostgreSQL.")
    inspector = inspect(engine)
    required = {
        "device_ownerships": {"device_id", "account_id", "created_at"},
        "device_pairing_tokens": {"device_id", "token_hash", "created_at", "expires_at", "used_at"},
        "device_share_invitations": {"invitation_id", "device_id", "invited_account_id", "invited_by_account_id", "token_hash", "created_at", "expires_at", "accepted_at", "revoked_at"},
    }
    for name, columns in required.items():
        assert name in inspector.get_table_names(), f"Thiếu bảng {name}"
        actual = {column["name"] for column in inspector.get_columns(name)}
        assert columns == actual, f"Cột {name} không khớp"
        assert inspector.get_foreign_keys(name), f"Thiếu FK của {name}"
    for name in ("device_pairing_tokens", "device_share_invitations"):
        unique_cols = [set(item["column_names"]) for item in inspector.get_unique_constraints(name)]
        assert {"token_hash"} in unique_cols, f"Thiếu UNIQUE token_hash: {name}"
    assert set(inspector.get_pk_constraint("device_ownerships")["constrained_columns"]) == {"device_id"}
    with engine.connect() as conn:
        revision = conn.scalar(text("SELECT version_num FROM alembic_version"))
    assert revision == "0007_secure_device_pairing", f"Revision hiện tại: {revision}"
    print("POSTGRESQL SCHEMA V7: PASS")


if __name__ == "__main__":
    main()
