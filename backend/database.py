
"""Cấu hình kết nối SQLite hoặc PostgreSQL cho Backend."""

import os

from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# Đọc cấu hình tại đúng thư mục backend, không phụ thuộc Terminal.
BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


# Mặc định sử dụng SQLite như các milestone trước.
DB_BACKEND = os.getenv(
    "DB_BACKEND",
    "sqlite",
).strip().lower()


if DB_BACKEND == "sqlite":

    # Giữ dữ liệu SQLite trong file aiot.db hiện có.
    sqlite_path = (
        BASE_DIR / "aiot.db"
    ).resolve()

    DATABASE_URL = (
        f"sqlite:///{sqlite_path.as_posix()}"
    )

    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False
        },
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(
        dbapi_connection,
        connection_record,
    ):
        """Bật kiểm tra khóa ngoại cho mỗi kết nối SQLite."""

        previous_autocommit = getattr(
            dbapi_connection,
            "autocommit",
            None,
        )

        if previous_autocommit is not None:
            dbapi_connection.autocommit = True

        cursor = dbapi_connection.cursor()

        try:
            cursor.execute(
                "PRAGMA foreign_keys=ON"
            )

        finally:
            cursor.close()

            if previous_autocommit is not None:
                dbapi_connection.autocommit = (
                    previous_autocommit
                )


elif DB_BACKEND == "postgresql":

    # Bắt buộc cấu hình đủ biến để không kết nối nhầm.
    required = [
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
    ]

    missing = [
        name
        for name in required
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "Thiếu cấu hình PostgreSQL: "
            + ", ".join(missing)
        )

    try:
        pg_port = int(
            os.environ["PGPORT"]
        )

    except ValueError as error:
        raise RuntimeError(
            "PGPORT phải là số nguyên."
        ) from error

    # URL.create xử lý mật khẩu có ký tự đặc biệt
    # an toàn hơn việc nối chuỗi kết nối thủ công.
    DATABASE_URL = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        host=os.environ["PGHOST"],
        port=pg_port,
        database=os.environ["PGDATABASE"],
    )

    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )


else:
    raise RuntimeError(
        "DB_BACKEND chỉ được là sqlite hoặc postgresql."
    )


# Giữ nguyên giao diện sử dụng của những milestone trước.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Lớp cơ sở cho năm ORM Model trong schema v1."""

    pass


def get_db():
    """Cấp phát và đóng Session sau khi request hoàn thành."""

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
