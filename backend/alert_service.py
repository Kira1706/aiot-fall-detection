"""Tra cứu thông báo đã lưu, có kiểm tra liên kết Device hiện tại."""

from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from alert_schemas import AlertResponse
from models import AccountDevice, AlertNotification, FallEvent


def utc_datetime(value: datetime) -> datetime:
    """Bảo đảm thời điểm trả về API có múi giờ UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def alert_query(account_id: int):
    """Tạo truy vấn chỉ lấy cảnh báo từ các Device còn được theo dõi."""

    return (
        select(AlertNotification, FallEvent, AccountDevice.display_name)
        .join(FallEvent, FallEvent.event_id == AlertNotification.fall_event_id)
        .join(
            AccountDevice,
            and_(
                AccountDevice.account_id == AlertNotification.account_id,
                AccountDevice.device_id == FallEvent.device_id,
            ),
        )
        .where(AlertNotification.account_id == account_id)
    )


def list_alerts(
    db: Session,
    account_id: int,
    *,
    after_id: int = 0,
    unread_only: bool = True,
    limit: int = 100,
) -> list[AlertResponse]:
    """Trả các thông báo theo thứ tự ID tăng để có thể nhận lại khi mất mạng."""

    query = alert_query(account_id).where(
        AlertNotification.notification_id > after_id
    )
    if unread_only:
        query = query.where(AlertNotification.read_at.is_(None))
    query = query.order_by(AlertNotification.notification_id.asc()).limit(limit)
    rows = db.execute(query).all()
    result = []
    for alert, event, display_name in rows:
        result.append(
            AlertResponse(
                notification_id=alert.notification_id,
                event_id=event.event_id,
                device_id=event.device_id,
                device_name=display_name or event.device_id,
                event_time=utc_datetime(event.event_time),
                model_version=event.model_version,
                confidence=event.confidence,
                created_at=utc_datetime(alert.created_at),
                read_at=(utc_datetime(alert.read_at) if alert.read_at else None),
            )
        )
    return result


def mark_alert_read(db: Session, account_id: int, notification_id: int):
    """Chỉ đánh dấu đã xem khi liên kết AccountDevice còn hiệu lực."""

    row = db.execute(
        alert_query(account_id).where(
            AlertNotification.notification_id == notification_id
        )
    ).first()
    if row is None:
        return None
    alert = row[0]
    if alert.read_at is None:
        alert.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(alert)
    return utc_datetime(alert.read_at)
