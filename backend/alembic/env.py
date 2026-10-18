"""Kết nối Alembic đến PostgreSQL bằng cấu hình Backend hiện có."""

from logging.config import fileConfig

from alembic import context
from database import Base, engine
import models  # Nạp đủ mô tả sáu bảng trước khi so sánh metadata.


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Chỉ thực hiện migration khi kết nối PostgreSQL được xác nhận."""

    if engine.dialect.name != "postgresql":
        raise RuntimeError("Migration chính thức chỉ chạy với DB_BACKEND=postgresql.")

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Bản hướng dẫn này không hỗ trợ Alembic offline mode.")
else:
    run_migrations_online()
