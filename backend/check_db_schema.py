
"""Kiểm tra schema v1 và số lượng dữ liệu trên SQLite/PostgreSQL."""

from sqlalchemy import (
    func,
    inspect,
    select,
    text,
)

from database import engine

from models import (
    Account,
    Device,
    AccountDevice,
    FallEvent,
    ModelVersion,
)


MODELS = [
    Account,
    Device,
    ModelVersion,
    AccountDevice,
    FallEvent,
]


EXPECTED_PK = {
    "accounts": {
        "account_id"
    },
    "devices": {
        "device_id"
    },
    "model_versions": {
        "version"
    },
    "account_devices": {
        "account_id",
        "device_id",
    },
    "fall_events": {
        "event_id"
    },
}


EXPECTED_FK = {
    "account_devices": {
        (
            "account_id",
            "accounts",
            "account_id",
        ),
        (
            "device_id",
            "devices",
            "device_id",
        ),
    },
    "fall_events": {
        (
            "device_id",
            "devices",
            "device_id",
        ),
    },
}


def check_schema():
    """
    Đối chiếu bảng, cột, khóa chính, khóa ngoại
    và kiểu dữ liệu thời gian.
    """

    inspector = inspect(engine)

    actual_tables = set(
        inspector.get_table_names()
    )

    expected_tables = set(
        EXPECTED_PK
    )

    assert expected_tables.issubset(
        actual_tables
    ), (
        f"Thiếu bảng: "
        f"{sorted(expected_tables - actual_tables)}"
    )

    # Kiểm tra tên cột và khóa chính của từng bảng.
    for model in MODELS:

        name = model.__tablename__

        expected_columns = {
            column.name
            for column in model.__table__.columns
        }

        actual_columns = {
            column["name"]
            for column in inspector.get_columns(name)
        }

        assert expected_columns == actual_columns, (
            f"Cột trong {name} không khớp: "
            f"{sorted(actual_columns)}"
        )

        actual_pk = set(
            inspector.get_pk_constraint(name)[
                "constrained_columns"
            ]
        )

        assert actual_pk == EXPECTED_PK[name], (
            f"Khóa chính {name} không khớp."
        )

    # Kiểm tra các liên kết khóa ngoại.
    for name, required in EXPECTED_FK.items():

        actual_fk = set()

        for fk in inspector.get_foreign_keys(name):

            for local_column, remote_column in zip(
                fk["constrained_columns"],
                fk["referred_columns"],
            ):
                actual_fk.add(
                    (
                        local_column,
                        fk["referred_table"],
                        remote_column,
                    )
                )

        assert required.issubset(actual_fk), (
            f"Khóa ngoại {name} không khớp."
        )

    # Kiểm tra ràng buộc UNIQUE của Account.email.
    unique_sets = [
        set(item["column_names"])
        for item in inspector.get_unique_constraints(
            "accounts"
        )
    ]

    unique_sets += [
        set(item["column_names"])
        for item in inspector.get_indexes(
            "accounts"
        )
        if item.get("unique")
    ]

    assert {"email"} in unique_sets, (
        "Thiếu UNIQUE accounts.email."
    )

    if engine.dialect.name == "postgresql":

        # PostgreSQL phải lưu thời gian có timezone.
        for table_name, column_name in [
            (
                "fall_events",
                "event_time",
            ),
            (
                "model_versions",
                "created_at",
            ),
        ]:

            column = next(
                item
                for item in inspector.get_columns(table_name)
                if item["name"] == column_name
            )

            assert getattr(
                column["type"],
                "timezone",
                False,
            ), (
                f"{table_name}.{column_name} "
                "phải là TIMESTAMPTZ."
            )

    print("DATABASE SCHEMA V1: PASS")
    print(
        "Hệ quản trị:",
        engine.dialect.name,
    )

    # Chỉ in số bản ghi, không in mật khẩu hoặc dữ liệu bí mật.
    with engine.connect() as conn:

        if engine.dialect.name == "postgresql":

            dbname = conn.scalar(
                text("SELECT current_database()")
            )

            print(
                "Database:",
                dbname,
            )

        for model in MODELS:

            total = conn.scalar(
                select(func.count()).select_from(
                    model.__table__
                )
            )

            print(
                f"{model.__tablename__}: {total}"
            )


if __name__ == "__main__":
    check_schema()
