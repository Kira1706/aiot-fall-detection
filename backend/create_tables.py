
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
