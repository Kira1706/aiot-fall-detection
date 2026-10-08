from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = "sqlite:///./aiot.db"



engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def enable_foreign_keys(
    dbapi_connection,
    connection_record
):
    previous = getattr(
        dbapi_connection, "autocommit", None
    )

    if previous is not None:
        dbapi_connection.autocommit = True

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

    if previous is not None:
        dbapi_connection.autocommit = previous



SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()