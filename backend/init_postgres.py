
"""Khởi tạo schema v1 trên PostgreSQL mới và kiểm tra an toàn."""

from sqlalchemy import inspect

from database import Base, engine

# Import đủ năm model để SQLAlchemy biết tất cả bảng.
from models import (
    Account,
    Device,
    AccountDevice,
    FallEvent,
    ModelVersion,
)


EXPECTED_TABLES = {
    "accounts",
    "devices",
    "account_devices",
    "fall_events",
    "model_versions",
}


def main():
    """Chỉ tạo bảng trên Database PostgreSQL trống."""

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Hãy đặt DB_BACKEND=postgresql trước khi khởi tạo."
        )

    existing_tables = set(
        inspect(engine).get_table_names()
    )

    if existing_tables:
        raise RuntimeError(
            "Database không trống; không tự ý tạo hoặc sửa bảng. "
            "Các bảng đang tồn tại: "
            + ", ".join(sorted(existing_tables))
        )

    # Chỉ dùng create_all cho lần khởi tạo schema v1 trên DB mới.
    # Không dùng create_all thay thế migration khi thay đổi schema.
    Base.metadata.create_all(
        bind=engine
    )

    actual_tables = set(
        inspect(engine).get_table_names()
    )

    assert actual_tables == EXPECTED_TABLES, (
        f"Schema không khớp: {sorted(actual_tables)}"
    )

    print("POSTGRESQL SCHEMA INIT: PASS")


if __name__ == "__main__":
    main()
