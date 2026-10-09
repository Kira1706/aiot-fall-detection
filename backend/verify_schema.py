
from sqlalchemy import (
    inspect, Integer, String, Text, DateTime, Float
)

from database import Base, engine
import models


# 1. Schema mong đợi
# Mỗi cột: (kiểu dữ liệu, cho phép NULL, độ dài)

expected_columns = {
    "accounts": {
        "account_id": (Integer, False, None),
        "email": (String, False, 255),
        "password_hash": (String, False, 255),
        "display_name": (String, False, 100),
    },

    "devices": {
        "device_id": (String, False, 64),
        "status": (String, False, 20),
        "model_version": (String, True, 50),
    },

    "account_devices": {
        "account_id": (Integer, False, None),
        "device_id": (String, False, 64),
        "display_name": (String, True, 100),
    },

    "fall_events": {
        "event_id": (Integer, False, None),
        "device_id": (String, False, 64),
        "event_time": (DateTime, False, None),
        "event_type": (String, False, 20),
        "model_version": (String, False, 50),
        "confidence": (Float, True, None),
    },

    "model_versions": {
        "version": (String, False, 50),
        "file_path": (Text, False, None),
        "created_at": (DateTime, False, None),
    },
}


# 2. Primary Key mong đợi

expected_pks = {
    "accounts": {"account_id"},
    "devices": {"device_id"},
    "account_devices": {"account_id", "device_id"},
    "fall_events": {"event_id"},
    "model_versions": {"version"},
}


# 3. Foreign Key mong đợi

expected_fks = {
    "account_devices": {
        (("account_id",), "accounts", ("account_id",)),
        (("device_id",), "devices", ("device_id",)),
    },

    "fall_events": {
        (("device_id",), "devices", ("device_id",)),
    },
}


# 4. Kiểm tra danh sách bảng

inspector = inspect(engine)

expected_tables = set(expected_columns)
actual_tables = set(inspector.get_table_names())
orm_tables = set(Base.metadata.tables.keys())

assert actual_tables == expected_tables, (
    f"Database tables incorrect: {actual_tables}"
)

assert orm_tables == expected_tables, (
    f"ORM models incorrect: {orm_tables}"
)

print("[PASS] All 5 tables exist")


# 5. Kiểm tra cột, kiểu dữ liệu, NULL và PK

for table_name, columns_spec in expected_columns.items():

    actual_columns = {
        c["name"]: c
        for c in inspector.get_columns(table_name)
    }

    assert set(actual_columns) == set(columns_spec), (
        f"Incorrect columns in {table_name}"
    )

    for name, (data_type, nullable, length) in columns_spec.items():

        column = actual_columns[name]

        assert isinstance(column["type"], data_type), (
            f"{table_name}.{name}: incorrect data type"
        )

        assert column["nullable"] == nullable, (
            f"{table_name}.{name}: incorrect NULL constraint"
        )

        if length is not None:
            assert column["type"].length == length, (
                f"{table_name}.{name}: incorrect length"
            )

    actual_pk = set(
        inspector.get_pk_constraint(table_name)[
            "constrained_columns"
        ]
    )

    assert actual_pk == expected_pks[table_name], (
        f"{table_name}: incorrect Primary Key"
    )

    print(f"[PASS] {table_name}: columns, types, NULL, PK")


# 6. Kiểm tra Foreign Key

for table_name in expected_tables:

    actual_fks = {
        (
            tuple(fk["constrained_columns"]),
            fk["referred_table"],
            tuple(fk["referred_columns"]),
        )
        for fk in inspector.get_foreign_keys(table_name)
    }

    assert actual_fks == expected_fks.get(
        table_name, set()
    ), f"{table_name}: incorrect Foreign Keys"

print("[PASS] All Foreign Keys")


# 7. Kiểm tra UNIQUE của email

unique_constraints = inspector.get_unique_constraints(
    "accounts"
)

unique_indexes = inspector.get_indexes("accounts")

email_unique = any(
    item["column_names"] == ["email"]
    for item in unique_constraints
) or any(
    item["unique"] and item["column_names"] == ["email"]
    for item in unique_indexes
)

assert email_unique, "accounts.email must be UNIQUE"

print("[PASS] accounts.email is UNIQUE")


# 8. Kiểm tra SQLite Foreign Key enforcement

with engine.connect() as connection:
    enabled = connection.exec_driver_sql(
        "PRAGMA foreign_keys"
    ).scalar()

assert enabled == 1, "SQLite Foreign Keys are disabled"

print("[PASS] SQLite Foreign Key enforcement")


print("\nSCHEMA V1 VERIFICATION: PASS")
