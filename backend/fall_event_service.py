"""Xử lý lưu trữ Fall Event và tìm tài khoản nhận cảnh báo."""

from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from fall_event_schemas import (
    FallEventCreate,
    FallEventResponse,
)
from models import AccountDevice, FallEvent


# Tuần tự hóa các thao tác kiểm tra và ghi Fall Event
# trong phạm vi một tiến trình Backend.
# Khóa này không bảo vệ được nhiều worker hoặc nhiều Server.
fall_event_write_lock = Lock()


def normalize_database_datetime(
    value: datetime,
) -> datetime:
    """
    Chuẩn hóa thời gian lấy từ Database về UTC.

    SQLite có thể trả datetime không kèm múi giờ.
    Với dữ liệu do API này lưu, thời gian đó được hiểu là UTC.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def save_fall_event(
    db: Session,
    device_id: str,
    payload: FallEventCreate,
) -> tuple[FallEvent, bool]:
    """
    Lưu Fall Event hoặc tìm bản ghi có nội dung giống hệt.

    Một sự kiện thử nghiệm được nhận diện bằng:
    - Device ID.
    - Thời điểm sự kiện.
    - Loại sự kiện.
    - Phiên bản model.
    - Độ tin cậy.

    Trả về:
    - FallEvent được lưu hoặc đã tồn tại.
    - True nếu nhận diện là sự kiện gửi lại.

    Cơ chế này chỉ bảo đảm tuần tự hóa trong một tiến trình.
    """

    # Đảm bảo dữ liệu đã được chuẩn hóa về UTC.
    event_time = payload.event_time.astimezone(
        timezone.utc
    )

    with fall_event_write_lock:

        # Kiểm tra bản ghi có dữ liệu giống hệt.
        statement = (
            select(FallEvent)
            .where(
                FallEvent.device_id == device_id,
                FallEvent.event_time == event_time,
                FallEvent.event_type == payload.event_type,
                FallEvent.model_version == payload.model_version,
                FallEvent.confidence == payload.confidence,
            )
            .order_by(
                FallEvent.event_id
            )
            .limit(1)
        )

        existing_event = db.scalar(statement)

        if existing_event is not None:
            return existing_event, True

        # Tạo Fall Event mới theo ORM Model đã có.
        fall_event = FallEvent(
            device_id=device_id,
            event_time=event_time,
            event_type=payload.event_type,
            model_version=payload.model_version,
            confidence=payload.confidence,
        )

        db.add(fall_event)

        try:
            # Ghi sự kiện vào Database.
            db.commit()

        except Exception:
            # Khôi phục Session nếu thao tác lưu thất bại.
            db.rollback()
            raise

        # Lấy event_id do Database tự tạo.
        db.refresh(fall_event)

        return fall_event, False


def resolve_alert_recipient_account_ids(
    db: Session,
    device_id: str,
) -> list[int]:
    """
    Tìm tất cả Account đang theo dõi Device.

    Một Device có thể có nhiều caregiver.
    Chỉ trả Account ID nội bộ, không trả dữ liệu này cho ESP32.
    """

    statement = (
        select(AccountDevice.account_id)
        .where(
            AccountDevice.device_id == device_id
        )
        .order_by(
            AccountDevice.account_id
        )
    )

    return list(
        db.scalars(statement).all()
    )


def build_fall_event_response(
    fall_event: FallEvent,
) -> FallEventResponse:
    """
    Tạo dữ liệu Fall Event trả về cho caregiver.

    Thời gian được biểu diễn theo UTC.
    """

    return FallEventResponse(
        event_id=fall_event.event_id,
        device_id=fall_event.device_id,
        event_time=normalize_database_datetime(
            fall_event.event_time
        ),
        event_type=fall_event.event_type,
        model_version=fall_event.model_version,
        confidence=fall_event.confidence,
    )