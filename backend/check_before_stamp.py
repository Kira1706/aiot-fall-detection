"""Kiểm tra PostgreSQL đang đúng schema v1 trước khi Alembic stamp."""

from sqlalchemy import inspect
from database import engine


EXPECTED = {
    "accounts": {"account_id", "email", "password_hash", "display_name"},
    "devices": {"device_id", "status", "model_version"},
    "account_devices": {"account_id", "device_id", "display_name"},
    "fall_events": {
        "event_id", "device_id", "event_time", "event_type",
        "model_version", "confidence",
    },
    "model_versions": {"version", "file_path", "created_at"},
}


def main():
    """Ngăn việc đánh dấu v1 sai trên DB rỗng hoặc đã thay đổi."""

    if engine.dialect.name != "postgresql":
        raise RuntimeError("Chỉ kiểm tra PostgreSQL hiện có.")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if tables != set(EXPECTED):
        raise RuntimeError(
            "Các bảng không đúng schema v1. "
            f"Đang có: {sorted(tables)}"
        )

    for table, columns in EXPECTED.items():
        current = {item["name"] for item in inspector.get_columns(table)}
        if current != columns:
            raise RuntimeError(
                f"Cột bảng {table} không khớp v1: {sorted(current)}"
            )

    print("POSTGRESQL BEFORE ALEMBIC STAMP: PASS")
    print("Có thể stamp revision 0001_schema_v1 sau khi sao lưu và đối chiếu FK/UNIQUE.")


if __name__ == "__main__":
    main()
