
"""Đối chiếu từng bản ghi SQLite với PostgreSQL sau khi chuyển dữ liệu."""

import argparse

from datetime import datetime, timezone

from sqlalchemy import select

from database import engine, BASE_DIR

from migrate_sqlite_to_postgres import (
    MODELS,
    read_source_rows,
)


def normalize_row(row: dict) -> dict:
    """Chuẩn hóa datetime về UTC để đối chiếu hai Database."""

    result = dict(row)

    for name, value in result.items():

        if isinstance(value, datetime):

            if (
                value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise RuntimeError(
                    f"Dữ liệu PostgreSQL thiếu timezone "
                    f"ở cột {name}."
                )

            result[name] = value.astimezone(
                timezone.utc
            )

    return result


def index_rows(
    rows: list[dict],
    pk_names: tuple[str, ...],
) -> dict:
    """Đánh chỉ mục bản ghi theo khóa chính."""

    indexed = {}

    for row in rows:

        key = tuple(
            row[name]
            for name in pk_names
        )

        if key in indexed:
            raise AssertionError(
                "Phát hiện khóa chính trùng "
                "trong dữ liệu đối chiếu."
            )

        indexed[key] = normalize_row(row)

    return indexed


def main():
    """
    Kiểm tra tất cả cột của năm bảng.

    Không in password_hash hoặc dữ liệu bí mật.
    """

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Chỉ chạy khi DB_BACKEND=postgresql."
        )

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--assume-naive-utc",
        action="store_true",
    )

    args = parser.parse_args()

    sqlite_path = (
        BASE_DIR / "aiot.db"
    ).resolve()

    source_data, naive_count = read_source_rows(
        sqlite_path
    )

    # Không tự ý diễn giải timestamp thiếu timezone.
    if naive_count and not args.assume_naive_utc:
        raise RuntimeError(
            "Dữ liệu nguồn có timestamp thiếu timezone. "
            "Chỉ chạy lại với --assume-naive-utc "
            "sau khi đã xác nhận UTC."
        )

    print(
        "Timestamp SQLite thiếu timezone:",
        naive_count,
    )

    with engine.connect() as conn:

        for model in MODELS:

            table = model.__table__

            pk_names = tuple(
                column.name
                for column in table.primary_key.columns
            )

            # Đánh chỉ mục dữ liệu SQLite theo Primary Key.
            source_rows = index_rows(
                source_data[table.name],
                pk_names,
            )

            # Đọc dữ liệu PostgreSQL.
            postgres_rows = [
                dict(row._mapping)
                for row in conn.execute(
                    select(table)
                )
            ]

            target_rows = index_rows(
                postgres_rows,
                pk_names,
            )


# Nếu phát hiện dữ liệu không khớp, in ra sự khác biệt.
            if source_rows != target_rows:

                # Chỉ hiển thị thông tin thiết bị.
                # Không in mật khẩu hoặc mã băm của Account.
                if table.name == "devices":

                    all_keys = sorted(
                        set(source_rows) | set(target_rows)
                    )

                    for key in all_keys:

                        sqlite_row = source_rows.get(key)
                        postgres_row = target_rows.get(key)

                        # Bỏ qua các thiết bị có dữ liệu giống nhau.
                        if sqlite_row == postgres_row:
                            continue

                        print(f"\n[CHÊNH LỆCH] Device ID: {key[0]}")

                        for column in [
                            "device_id",
                            "status",
                            "model_version",
                        ]:

                            sqlite_value = (
                                sqlite_row.get(column)
                                if sqlite_row is not None
                                else None
                            )

                            postgres_value = (
                                postgres_row.get(column)
                                if postgres_row is not None
                                else None
                            )

                            if sqlite_value != postgres_value:
                                print(f"  Cột: {column}")
                                print(f"  SQLite: {sqlite_value!r}")
                                print(f"  PostgreSQL: {postgres_value!r}")

                raise AssertionError(
                    f"Dữ liệu {table.name} KHÔNG khớp "
                    "giữa SQLite và PostgreSQL."
                )


            print(
                f"[PASS] {table.name}: "
                f"{len(source_rows)} bản ghi khớp"
            )

    print(
        "POSTGRESQL DATA VERIFICATION: PASS"
    )


if __name__ == "__main__":
    main()
