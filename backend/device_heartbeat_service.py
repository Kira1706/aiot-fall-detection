
"""Lưu heartbeat vào Database và tính trạng thái kết nối."""

from datetime import datetime, timezone

from sqlalchemy import func

from sqlalchemy.dialects.postgresql import (
    insert as pg_insert,
)

from sqlalchemy.dialects.sqlite import (
    insert as sqlite_insert,
)

from sqlalchemy.orm import Session

from models import Device, DeviceHeartbeatState


# ESP32 gửi heartbeat sau mỗi 15 giây.
HEARTBEAT_INTERVAL_SECONDS = 15

# Quá 45 giây không có heartbeat thì offline.
HEARTBEAT_TIMEOUT_SECONDS = 45


def utc_datetime(value: datetime) -> datetime:
    """Chuẩn hóa thời gian từ Database về UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def get_device_liveness(
    db: Session,
    device_id: str,
    now: datetime | None = None,
) -> tuple[str, datetime | None]:
    """
    Tính online/offline từ heartbeat mới nhất.

    Nếu chưa có bản ghi thì Device được xem là offline.
    """

    current_time = utc_datetime(
        now or datetime.now(timezone.utc)
    )

    row = db.get(
        DeviceHeartbeatState,
        device_id,
    )

    if row is None:
        return "offline", None

    last_seen_at = utc_datetime(
        row.last_seen_at
    )

    elapsed = (
        current_time - last_seen_at
    ).total_seconds()

    # Tại đúng ngưỡng 45 giây vẫn xem là online.
    online = (
        0 <= elapsed <= HEARTBEAT_TIMEOUT_SECONDS
    )

    return (
        "online" if online else "offline",
        last_seen_at,
    )


def record_device_heartbeat(
    db: Session,
    device: Device,
    model_version: str | None = None,
    now: datetime | None = None,
) -> datetime:
    """
    Ghi heartbeat mới nhất của một Device.

    Nếu Device đã có heartbeat, cập nhật bản ghi.
    Không tạo thêm bản ghi lịch sử cho mỗi lần gửi.
    """

    received_at = utc_datetime(
        now or datetime.now(timezone.utc)
    )

    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":

        statement = pg_insert(
            DeviceHeartbeatState
        ).values(
            device_id=device.device_id,
            last_seen_at=received_at,
        )

        # Chỉ giữ thời điểm mới hơn.
        statement = statement.on_conflict_do_update(
            index_elements=["device_id"],
            set_={
                "last_seen_at": func.greatest(
                    DeviceHeartbeatState.last_seen_at,
                    statement.excluded.last_seen_at,
                )
            },
        )

    elif dialect == "sqlite":

        statement = sqlite_insert(
            DeviceHeartbeatState
        ).values(
            device_id=device.device_id,
            last_seen_at=received_at,
        )

        statement = statement.on_conflict_do_update(
            index_elements=["device_id"],
            set_={
                "last_seen_at": func.max(
                    DeviceHeartbeatState.last_seen_at,
                    statement.excluded.last_seen_at,
                )
            },
        )

    else:
        raise RuntimeError(
            "Backend chỉ hỗ trợ PostgreSQL hoặc SQLite."
        )

    try:
        # Ghi hoặc cập nhật heartbeat trong Database.
        db.execute(statement)

        # Cập nhật phiên bản AI do Edge báo cáo nếu có.
        if model_version is not None:
            device.model_version = model_version

        # Lưu heartbeat và model_version trong một giao dịch.
        db.commit()

    except Exception:
        db.rollback()
        raise

    return received_at
