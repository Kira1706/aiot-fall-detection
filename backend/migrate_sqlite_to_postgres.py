
"""Sao chép dữ liệu schema v1 từ SQLite sang PostgreSQL mới."""

import argparse

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    create_engine,
    func,
    select,
    text,
)

from database import BASE_DIR, engine

from models import (
    Account,
    Device,
    ModelVersion,
    AccountDevice,
    FallEvent,
)


# Thứ tự chèn bảo đảm bảng cha có dữ liệu trước bảng con.
MODELS = [
    Account,
    Device,
    ModelVersion,
    AccountDevice,
    FallEvent,
]


DATETIME_COLUMNS = {
    "model_versions": "created_at",
    "fall_events": "event_time",
}


def read_source_rows(sqlite_path: Path):
    """
    Đọc dữ liệu từ SQLite mà không chỉnh sửa Database nguồn.

    Trả toàn bộ bản ghi và số timestamp thiếu timezone.
    Phù hợp với lượng dữ liệu nhỏ trong prototype hiện tại.
    """

    if not sqlite_path.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy nguồn SQLite: {sqlite_path}"
        )

    source_url = (
        f"sqlite:///{sqlite_path.as_posix()}"
    )

    source_engine = create_engine(
        source_url
    )

    data = {}
    naive_count = 0

    try:
        with source_engine.connect() as conn:

            for model in MODELS:

                table = model.__table__

                rows = [
                    dict(row._mapping)
                    for row in conn.execute(
                        select(table)
                    )
                ]

                datetime_column = DATETIME_COLUMNS.get(
                    table.name
                )

                if datetime_column:

                    for row in rows:

                        value = row[datetime_column]

                        if not isinstance(value, datetime):
                            raise RuntimeError(
                                f"Thời gian {table.name}."
                                f"{datetime_column} không hợp lệ."
                            )

                        if (
                            value.tzinfo is None
                            or value.utcoffset() is None
                        ):

                            naive_count += 1

                            # Chỉ áp dụng quy ước UTC sau khi
                            # người dùng xác nhận dữ liệu nguồn.
                            row[datetime_column] = (
                                value.replace(
                                    tzinfo=timezone.utc
                                )
                            )

                        else:

                            row[datetime_column] = (
                                value.astimezone(
                                    timezone.utc
                                )
                            )

                data[table.name] = rows

    finally:
        source_engine.dispose()

    return data, naive_count


def require_empty_target():
    """
    Từ chối sao chép nếu PostgreSQL đã có dữ liệu.

    Không thực hiện hành vi ghi đè hay xóa bản ghi.
    """

    with engine.connect() as conn:

        for model in MODELS:

            total = conn.scalar(
                select(func.count()).select_from(
                    model.__table__
                )
            )

            if total != 0:
                raise RuntimeError(
                    f"PostgreSQL có dữ liệu trong "
                    f"{model.__tablename__}. "
                    "Không sao chép đè lên Database đang dùng."
                )


def migrate():
    """
    Kiểm tra nguồn và đích trước khi sao chép.

    Mặc định chỉ kiểm tra.
    Chỉ ghi dữ liệu khi có --execute.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Chuyển dữ liệu từ aiot.db "
            "sang PostgreSQL trống."
        )
    )

    parser.add_argument(
        "--execute",
        action="store_true",
    )

    parser.add_argument(
        "--assume-naive-utc",
        action="store_true",
    )

    args = parser.parse_args()

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Đích phải là PostgreSQL: "
            "đặt DB_BACKEND=postgresql."
        )

    sqlite_path = (
        BASE_DIR / "aiot.db"
    ).resolve()

    # Đọc dữ liệu nguồn và thống kê timestamp.
    data, naive_count = read_source_rows(
        sqlite_path
    )

    # Kiểm tra các bảng đích chưa có bản ghi.
    require_empty_target()

    print(
        "Nguồn SQLite:",
        sqlite_path,
    )

    for model in MODELS:
        print(
            f"{model.__tablename__}: "
            f"{len(data[model.__tablename__])} bản ghi"
        )

    print(
        "Mốc thời gian thiếu timezone:",
        naive_count,
    )

    # Nếu không có --execute, chỉ in kết quả kiểm tra.
    if not args.execute:
        print(
            "DRY RUN: PASS — chưa ghi bất kỳ bản ghi nào."
        )
        return

    # Từ chối tự diễn giải thời gian nếu chưa xác nhận.
    if naive_count and not args.assume_naive_utc:
        raise RuntimeError(
            "Có timestamp SQLite không kèm timezone. "
            "Hãy đối chiếu rằng dữ liệu cũ dùng UTC, "
            "sau đó chạy lại với "
            "--execute --assume-naive-utc."
        )

    # Sao chép dữ liệu trong một transaction.
    # Nếu phát sinh lỗi, các INSERT sẽ được rollback.
    with engine.begin() as conn:

        # Kiểm tra lại đích ngay trước khi ghi.
        for model in MODELS:

            total = conn.scalar(
                select(func.count()).select_from(
                    model.__table__
                )
            )

            if total:
                raise RuntimeError(
                    "Đích đã có dữ liệu, dừng migration."
                )

        # Sao chép lần lượt theo thứ tự khóa ngoại.
        for model in MODELS:

            table = model.__table__

            rows = data[table.name]

            if rows:
                conn.execute(
                    table.insert(),
                    rows,
                )

        # Dữ liệu sao chép có ID cũ.
        # Điều chỉnh sequence để bản ghi mới không trùng ID.
        # Tên bảng và tên cột đều là hằng số nội bộ.
        for table_name, column_name in [
            ("accounts", "account_id"),
            ("fall_events", "event_id"),
        ]:

            conn.execute(
                text(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence(
                            '{table_name}',
                            '{column_name}'
                        ),
                        COALESCE(
                            (
                                SELECT MAX({column_name})
                                FROM {table_name}
                            ),
                            1
                        ),
                        EXISTS(
                            SELECT 1 FROM {table_name}
                        )
                    )
                    """
                )
            )

    # Kiểm tra số lượng bản ghi sau khi commit.
    with engine.connect() as conn:

        for model in MODELS:

            actual = conn.scalar(
                select(func.count()).select_from(
                    model.__table__
                )
            )

            expected = len(
                data[model.__tablename__]
            )

            assert actual == expected, (
                f"Số bản ghi {model.__tablename__} "
                f"không khớp: {actual}/{expected}"
            )

    print(
        "SQLITE TO POSTGRESQL MIGRATION: PASS"
    )


if __name__ == "__main__":
    migrate()
