
"""Ghi Fall Event theo UUID và xử lý sự kiện gửi lại."""

from datetime import datetime, timezone

from sqlalchemy import select

from sqlalchemy.dialects.postgresql import (
    insert as pg_insert,
)

from sqlalchemy.dialects.sqlite import (
    insert as sqlite_insert,
)

from sqlalchemy.orm import Session

from fall_event_schemas import (
    FallEventCreate,
    FallEventResponse,
)

from models import AccountDevice, FallEvent


class EventIdConflictError(Exception):
    """UUID đã tồn tại nhưng nội dung sự kiện bị thay đổi."""


def utc_datetime(value: datetime) -> datetime:
    """Chuẩn hóa thời gian lấy từ Database về UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def save_fall_event(
    db: Session,
    device_id: str,
    payload: FallEventCreate,
) -> tuple[FallEvent, bool]:
    """
    Lưu Fall Event bằng khóa duy nhất của Database.

    Nếu cùng UUID và cùng nội dung:
        Trả sự kiện cũ, đánh dấu duplicate.

    Nếu cùng UUID nhưng đổi nội dung:
        Phát sinh lỗi để API trả HTTP 409.
    """

    values = {
        "device_id": device_id,
        "edge_event_id": str(payload.edge_event_id),
        "event_time": payload.event_time,
        "event_type": payload.event_type,
        "model_version": payload.model_version,
        "confidence": payload.confidence,
    }

    # Chọn cú pháp INSERT tương ứng Database.
    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        statement = pg_insert(FallEvent).values(**values)

    elif dialect == "sqlite":
        statement = sqlite_insert(FallEvent).values(**values)

    else:
        raise RuntimeError(
            "Backend chỉ hỗ trợ PostgreSQL hoặc SQLite."
        )

    # Database kiểm tra UUID trùng theo cặp Device + Event.
    statement = statement.on_conflict_do_nothing(
        index_elements=[
            "device_id",
            "edge_event_id",
        ]
    ).returning(FallEvent.event_id)

    try:
        new_id = db.scalar(statement)

        if new_id is not None:
            # Đây là Fall Event mới.
            db.commit()

            event = db.get(FallEvent, new_id)

            return event, False

        # Không chèn được vì khóa sự kiện đã tồn tại.
        event = db.scalar(
            select(FallEvent).where(
                FallEvent.device_id == device_id,
                FallEvent.edge_event_id
                == values["edge_event_id"],
            )
        )

        if event is None:
            raise RuntimeError(
                "Không tìm thấy bản ghi sau xung đột UUID."
            )

        # Xác nhận payload gửi lại giống sự kiện gốc.
        same_data = (
            utc_datetime(event.event_time)
            == payload.event_time
            and event.event_type == payload.event_type
            and event.model_version == payload.model_version
            and event.confidence == payload.confidence
        )

        if not same_data:
            raise EventIdConflictError(
                "Mã sự kiện đã tồn tại "
                "nhưng nội dung không trùng khớp."
            )

        return event, True

    except Exception:
        # Khôi phục giao dịch khi có lỗi.
        db.rollback()
        raise


def resolve_alert_recipient_account_ids(
    db: Session,
    device_id: str,
) -> list[int]:
    """Lấy tất cả caregiver đang theo dõi thiết bị."""

    return list(
        db.scalars(
            select(AccountDevice.account_id)
            .where(
                AccountDevice.device_id == device_id
            )
            .order_by(
                AccountDevice.account_id
            )
        ).all()
    )


def build_fall_event_response(
    event: FallEvent,
) -> FallEventResponse:
    """Chuyển FallEvent thành dữ liệu trả về cho caregiver."""

    return FallEventResponse(
        event_id=event.event_id,
        device_id=event.device_id,
        edge_event_id=event.edge_event_id,
        event_time=utc_datetime(event.event_time),
        event_type=event.event_type,
        model_version=event.model_version,
        confidence=event.confidence,
    )
