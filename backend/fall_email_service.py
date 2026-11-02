"""Đưa email vào hàng đợi và gửi lại khi SMTP tạm thời thất bại."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from fall_email_models import FallEmailDelivery
from models import Account, AccountDevice, AlertNotification, FallEvent
from fall_email_sender import send_fall_alert_email

load_dotenv(Path(__file__).resolve().parent / ".env")

MAX_ATTEMPTS = 5


def utc_now() -> datetime:
    """Tạo thời gian UTC hiện hành."""
    return datetime.now(timezone.utc)


def enabled() -> bool:
    """Bật gửi email chỉ khi người quản trị cấu hình rõ ràng."""
    return os.getenv("FALL_EMAIL_ENABLED", "false").strip().lower() == "true"


def enqueue_event_emails(db: Session, event_id: int) -> int:
    """Ghi công việc email cùng transaction với FallEvent và AlertNotification."""
    if not enabled():
        return 0
    event = db.get(FallEvent, event_id)
    if event is None or event.event_type != "fall":
        return 0
    if event.model_version == "demo_admin":
        if os.getenv("APP_ENV", "development").lower() not in ("development", "test"):
            return 0
        if os.getenv("FALL_EMAIL_INCLUDE_DEMO", "false").lower() != "true":
            return 0

    notices = db.scalars(
        select(AlertNotification).where(AlertNotification.fall_event_id == event_id)
    ).all()
    now = utc_now()
    db.add_all([
        FallEmailDelivery(
            notification_id=notice.notification_id,
            status="pending",
            attempts=0,
            created_at=now,
            next_attempt_at=now,
        )
        for notice in notices
    ])
    # Hàm gọi phải commit cùng giao dịch chứa FallEvent.
    return len(notices)


def claim_one(db: Session) -> int | None:
    """Nhận quyền xử lý một việc gửi; worker song song không lấy cùng bản ghi."""
    now = utc_now()
    due = or_(
        and_(FallEmailDelivery.status == "pending", FallEmailDelivery.next_attempt_at <= now),
        and_(FallEmailDelivery.status == "sending", FallEmailDelivery.locked_until <= now),
    )
    stmt = select(FallEmailDelivery).where(due).order_by(
        FallEmailDelivery.next_attempt_at, FallEmailDelivery.delivery_id
    ).limit(1)
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(of=FallEmailDelivery, skip_locked=True)
    job = db.scalar(stmt)
    if job is None:
        return None
    job.status = "sending"
    job.attempts += 1
    job.locked_until = now + timedelta(minutes=2)
    db.commit()
    return job.delivery_id


def _get_recipient_if_allowed(db: Session, job_id: int) -> tuple[str, dict] | None:
    """Kiểm tra quyền theo dõi và email đã xác minh ngay trước khi gửi."""
    row = db.execute(
        select(Account.email, Account.email_verified_at, FallEvent.device_id,
               FallEvent.event_time, FallEvent.confidence, FallEvent.model_version)
        .select_from(FallEmailDelivery)
        .join(AlertNotification, AlertNotification.notification_id == FallEmailDelivery.notification_id)
        .join(FallEvent, FallEvent.event_id == AlertNotification.fall_event_id)
        .join(Account, Account.account_id == AlertNotification.account_id)
        .join(AccountDevice, and_(
            AccountDevice.account_id == AlertNotification.account_id,
            AccountDevice.device_id == FallEvent.device_id,
        ))
        .where(FallEmailDelivery.delivery_id == job_id)
    ).first()
    if row is None or row.email_verified_at is None:
        return None
    return row.email, {
        "device_id": row.device_id,
        "event_time": row.event_time,
        "confidence": row.confidence,
        "model_version": row.model_version,
    }


def _finish(db: Session, job_id: int, status: str, error_type: str | None = None) -> None:
    """Ghi kết quả gửi, chỉ lưu loại lỗi để không làm rò rỉ thông tin SMTP."""
    job = db.get(FallEmailDelivery, job_id)
    if job is None:
        return
    if job.status != "sending":
        return
    job.locked_until = None
    job.last_error_type = error_type[:80] if error_type else None
    if status == "sent":
        job.status = "sent"
        job.sent_at = utc_now()
    elif status == "skipped":
        job.status = "skipped"
    else:
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
        else:
            job.status = "pending"
            # Tăng thời gian chờ để tránh liên tục gửi đến SMTP đang lỗi.
            job.next_attempt_at = utc_now() + timedelta(seconds=min(30 * (2 ** (job.attempts - 1)), 1800))
    db.commit()


def process_one(session_factory, send=send_fall_alert_email) -> str | None:
    """Xử lý tối đa một email; mỗi giai đoạn dùng transaction ngắn."""
    with session_factory() as db:
        job_id = claim_one(db)
    if job_id is None:
        return None

    with session_factory() as db:
        recipient = _get_recipient_if_allowed(db, job_id)

    if recipient is None:
        with session_factory() as db:
            _finish(db, job_id, "skipped")
        return "skipped"

    try:
        address, event = recipient
        send(address, event)
    except Exception as exc:
        # Không in lỗi SMTP đầy đủ: có thể chứa địa chỉ hoặc thông tin nhạy cảm.
        with session_factory() as db:
            _finish(db, job_id, "error", type(exc).__name__)
        return "error"
    with session_factory() as db:
        _finish(db, job_id, "sent")
    return "sent"
