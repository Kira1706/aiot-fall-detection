
from sqlalchemy import inspect

from database import Base, engine
import models


Base.metadata.create_all(bind=engine)

inspector = inspect(engine)

print("Database tables:")
print(inspector.get_table_names())

print("\nAccount columns:")

columns = inspector.get_columns("accounts")

for column in columns:
    print(
        column["name"],
        column["type"],
        "nullable =", column["nullable"]
    )
print(inspector.get_unique_constraints("accounts"))