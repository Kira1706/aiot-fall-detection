"""Kiểm tra bảng cảnh báo và các ràng buộc của PostgreSQL schema v3."""

from sqlalchemy import func, inspect, select, text

from database import engine
from models import AccountDevice, AlertNotification, FallEvent


def main():
    """Kiểm tra cấu trúc và revision Alembic mà không sửa dữ liệu."""

    if engine.dialect.name != "postgresql":
        raise RuntimeError("Đặt DB_BACKEND=postgresql trước khi kiểm tra schema v3.")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "accounts", "devices", "account_devices", "fall_events",
        "model_versions", "device_heartbeat_states", "alert_notifications",
    }
    assert expected.issubset(tables), f"Thiếu bảng: {expected - tables}"

    name = AlertNotification.__tablename__
    columns = {column["name"] for column in inspector.get_columns(name)}
    assert columns == {
        "notification_id", "account_id", "fall_event_id", "created_at", "read_at"
    }
    pk = set(inspector.get_pk_constraint(name)["constrained_columns"])
    assert pk == {"notification_id"}
    fks = {
        (fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0])
        for fk in inspector.get_foreign_keys(name)
    }
    assert ("account_id", "accounts", "account_id") in fks
    assert ("fall_event_id", "fall_events", "event_id") in fks
    uniques = [set(item["column_names"]) for item in inspector.get_unique_constraints(name)]
    assert {"account_id", "fall_event_id"} in uniques

    by_name = {column["name"]: column for column in inspector.get_columns(name)}
    assert getattr(by_name["created_at"]["type"], "timezone", False)
    assert getattr(by_name["read_at"]["type"], "timezone", False)

    with engine.connect() as connection:
        current = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert current == "0003_alert_notifications", f"Revision hiện tại: {current}"
        total = connection.scalar(select(func.count()).select_from(AlertNotification))
        print("Bản ghi cảnh báo hiện có:", total)

    print("POSTGRESQL SCHEMA V3: PASS")


if __name__ == "__main__":
    main()
