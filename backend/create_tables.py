
from sqlalchemy import inspect

from database import Base, engine
import models


# Tạo những bảng chưa tồn tại
Base.metadata.create_all(bind=engine)

# Kiểm tra database
inspector = inspect(engine)

tables = inspector.get_table_names()

print("Database tables:", tables)

for table_name in tables:
    print(f"\nTable: {table_name}")

    columns = inspector.get_columns(table_name)

    for column in columns:
        print(
            column["name"],
            column["type"],
            "nullable =", column["nullable"]
        )

    primary_key = inspector.get_pk_constraint(
        table_name
    )

    print(
        "Primary Key:",
        primary_key["constrained_columns"]
    )


print("\nAccountDevice Foreign Keys:")

foreign_keys = inspector.get_foreign_keys(
    "account_devices"
)

for fk in foreign_keys:
    print(
        fk["constrained_columns"],
        "->",
        fk["referred_table"],
        fk["referred_columns"]
    )


with engine.connect() as connection:
    enabled = connection.exec_driver_sql(
        "PRAGMA foreign_keys"
    ).scalar()

    print("\nForeign Key enforcement:", enabled)
