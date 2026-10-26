"""API nhận lại cảnh báo, xử lý sự cố và theo dõi độ sẵn sàng."""
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from auth_dependencies import get_current_account
from models import Account, AccountDevice, AlertNotification, DeviceHeartbeatState, FallEvent
from incident_models import FallIncidentResolution
from alert_service import list_alerts

router = APIRouter(tags=["Alert Reliability"])


class IncidentUpdate(BaseModel):
    """Thông tin caregiver cập nhật khi xác nhận hoặc xử lý sự cố."""
    status: Literal["acknowledged", "resolved"]
    note: str | None = Field(default=None, max_length=500)


def _current_access(db: Session, account_id: int, event_id: int):
    """Chỉ cho phép truy cập sự cố từ thiết bị caregiver đang được theo dõi."""
    return db.scalar(select(FallEvent).join(AccountDevice, AccountDevice.device_id == FallEvent.device_id)
        .where(and_(FallEvent.event_id == event_id, AccountDevice.account_id == account_id)))


@router.get("/reliability/alerts/replay")
def replay_alerts(
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Nhận lại thông báo theo ID tăng dần, gồm cả cảnh báo đã xem."""
    records = list_alerts(db, account.account_id, after_id=after_id, unread_only=False, limit=limit)
    return {"items": [x.model_dump(mode="json") for x in records],
            "next_cursor": records[-1].notification_id if records else after_id,
            "has_more": len(records) == limit}


@router.get("/reliability/incidents/{event_id}")
def get_incident(event_id: int, account: Account = Depends(get_current_account), db: Session = Depends(get_db)):
    """Đọc trạng thái xử lý của sự cố nếu caregiver còn quyền."""
    event = _current_access(db, account.account_id, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự cố hoặc không có quyền.")
    row = db.get(FallIncidentResolution, event_id)
    return {"event_id": event_id, "status": row.status if row else "open",
            "updated_at": row.updated_at if row else None,
            "updated_by_account_id": row.updated_by_account_id if row else None,
            "note": row.note if row else None}


@router.put("/reliability/incidents/{event_id}")
def update_incident(event_id: int, body: IncidentUpdate, account: Account = Depends(get_current_account), db: Session = Depends(get_db)):
    """Ghi trạng thái xử lý bền vững và tránh trạng thái bị lùi về trước."""
    # Khóa hàng FallEvent để tuần tự hóa các cập nhật cạnh tranh trên PostgreSQL.
    event = db.scalar(select(FallEvent).where(FallEvent.event_id == event_id).with_for_update())
    if event is None or _current_access(db, account.account_id, event_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự cố hoặc không có quyền.")
    row = db.get(FallIncidentResolution, event_id)
    if row is not None and row.status == "resolved" and body.status != "resolved":
        raise HTTPException(status_code=409, detail="Sự cố đã được đánh dấu xử lý xong.")
    if row is None:
        row = FallIncidentResolution(fall_event_id=event_id, status=body.status,
                                    updated_by_account_id=account.account_id,
                                    updated_at=datetime.now(timezone.utc), note=body.note)
        db.add(row)
    elif row.status != body.status or row.note != body.note:
        row.status = body.status
        row.note = body.note
        row.updated_at = datetime.now(timezone.utc)
        row.updated_by_account_id = account.account_id
    db.commit()
    return {"event_id": event_id, "status": row.status, "updated_at": row.updated_at,
            "updated_by_account_id": row.updated_by_account_id, "note": row.note}


@router.get("/reliability/overview")
def reliability_overview(account: Account = Depends(get_current_account), db: Session = Depends(get_db)):
    """Đếm số cảnh báo và thiết bị có quyền, không để lộ dữ liệu caregiver khác."""
    ids = select(AccountDevice.device_id).where(AccountDevice.account_id == account.account_id)
    now = datetime.now(timezone.utc)
    online_cutoff = now - timedelta(seconds=45)
    device_count = db.scalar(select(func.count()).select_from(AccountDevice)
                             .where(AccountDevice.account_id == account.account_id)) or 0
    offline_count = db.scalar(select(func.count()).select_from(AccountDevice)
        .outerjoin(DeviceHeartbeatState, AccountDevice.device_id == DeviceHeartbeatState.device_id)
        .where(AccountDevice.account_id == account.account_id)
        .where((DeviceHeartbeatState.last_seen_at.is_(None)) | (DeviceHeartbeatState.last_seen_at < online_cutoff))) or 0
    unread = db.scalar(select(func.count()).select_from(AlertNotification)
        .join(FallEvent, FallEvent.event_id == AlertNotification.fall_event_id)
        .where(and_(AlertNotification.account_id == account.account_id,
                    AlertNotification.read_at.is_(None), FallEvent.device_id.in_(ids)))) or 0
    open_incidents = db.scalar(select(func.count()).select_from(FallEvent)
        .where(FallEvent.device_id.in_(ids))
        .outerjoin(FallIncidentResolution, FallIncidentResolution.fall_event_id == FallEvent.event_id)
        .where(FallIncidentResolution.fall_event_id.is_(None))) or 0
    return {"devices_total": device_count, "devices_offline": offline_count,
            "unread_notifications": unread, "incidents_without_action": open_incidents,
            "checked_at": now}


@router.get("/reliability/ready", include_in_schema=False)
def reliability_ready(response: Response, db: Session = Depends(get_db)):
    """Dùng cho health check; không công bố thông tin bí mật của hệ thống."""
    try:
        db.execute(text("SELECT 1"))
        db.execute(text("SELECT 1 FROM fall_incident_resolutions LIMIT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "not_ready"}
    return {"status": "ready"}
