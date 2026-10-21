"""Ghi Fall Event và hàng đợi thông báo trong cùng một giao dịch."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from fall_event_schemas import FallEventCreate, FallEventResponse
from models import AccountDevice, AlertNotification, FallEvent


class EventIdConflictError(Exception):
    """UUID đã tồn tại nhưng nội dung sự kiện gửi lại không trùng khớp."""


def utc_datetime(value: datetime) -> datetime:
    """Chuẩn hóa thời điểm lấy từ Database về UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_alert_recipient_account_ids(db: Session, device_id: str) -> list[int]:
    """Tìm caregiver đang theo dõi Device tại thời điểm tạo sự kiện."""

    return list(
        db.scalars(
            select(AccountDevice.account_id)
            .where(AccountDevice.device_id == device_id)
            .order_by(AccountDevice.account_id)
        ).all()
    )


def save_fall_event(
    db: Session, device_id: str, payload: FallEventCreate
) -> tuple[FallEvent, bool]:
    """
    Ghi nguyên tử Fall Event và các thông báo cho caregiver.

    Nếu một thao tác thất bại, giao dịch được rollback toàn bộ.
    Nếu UUID trùng, không tạo lại bất cứ thông báo nào.
    """

    values = {
        "device_id": device_id,
        "edge_event_id": str(payload.edge_event_id),
        "event_time": payload.event_time,
        "event_type": payload.event_type,
        "model_version": payload.model_version,
        "confidence": payload.confidence,
    }

    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = pg_insert(FallEvent).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(FallEvent).values(**values)
    else:
        raise RuntimeError("Chỉ hỗ trợ PostgreSQL và SQLite.")

    statement = statement.on_conflict_do_nothing(
        index_elements=["device_id", "edge_event_id"]
    ).returning(FallEvent.event_id)

    try:
        new_id = db.scalar(statement)
        if new_id is not None:
            # Đọc người theo dõi ngay trong cùng transaction tạo Fall Event.
            recipient_ids = resolve_alert_recipient_account_ids(db, device_id)
            created_at = datetime.now(timezone.utc)
            db.add_all(
                [
                    AlertNotification(
                        account_id=account_id,
                        fall_event_id=new_id,
                        created_at=created_at,
                        read_at=None,
                    )
                    for account_id in recipient_ids
                ]
            )
            # Chỉ xác nhận HTTP 201 sau khi cả sự kiện và thông báo được commit.
            db.commit()
            return db.get(FallEvent, new_id), False

        event = db.scalar(
            select(FallEvent).where(
                FallEvent.device_id == device_id,
                FallEvent.edge_event_id == values["edge_event_id"],
            )
        )
        if event is None:
            raise RuntimeError("Không tìm thấy sự kiện sau khi trùng UUID.")

        same_data = (
            utc_datetime(event.event_time) == payload.event_time
            and event.event_type == payload.event_type
            and event.model_version == payload.model_version
            and event.confidence == payload.confidence
        )
        if not same_data:
            raise EventIdConflictError(
                "Mã sự kiện đã tồn tại nhưng nội dung không trùng khớp."
            )
        return event, True
    except Exception:
        db.rollback()
        raise


def build_fall_event_response(event: FallEvent) -> FallEventResponse:
    """Chuyển bản ghi Fall Event về response theo schema v2."""

    return FallEventResponse(
        event_id=event.event_id,
        device_id=event.device_id,
        edge_event_id=event.edge_event_id,
        event_time=utc_datetime(event.event_time),
        event_type=event.event_type,
        model_version=event.model_version,
        confidence=event.confidence,
    )
