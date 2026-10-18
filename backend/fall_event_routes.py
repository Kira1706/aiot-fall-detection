"""API gửi Fall Event với UUID và đọc lịch sử được phân quyền."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from device_auth import require_device_key
from device_permissions import get_authorized_device
from fall_event_schemas import FallEventAcknowledgement, FallEventCreate, FallEventResponse
from fall_event_service import (
    EventIdConflictError, build_fall_event_response,
    resolve_alert_recipient_account_ids, save_fall_event,
)
from models import Account, AccountDevice, Device, FallEvent

logger = logging.getLogger(__name__)
edge_router = APIRouter(prefix="/device-ingest", tags=["Device Ingest"])
device_history_router = APIRouter(prefix="/devices", tags=["Fall Events"])
history_router = APIRouter(prefix="/fall-events", tags=["Fall Events"])


@edge_router.post(
    "/{device_id}/fall-events",
    response_model=FallEventAcknowledgement,
    status_code=status.HTTP_201_CREATED,
)
def receive_fall_event(
    payload: FallEventCreate,
    response: Response,
    device_id: str = Depends(require_device_key),
    db: Session = Depends(get_db),
):
    """Ghi Fall Event đã vượt cửa sổ Cancel; UUID giữ nguyên khi retry."""

    if db.get(Device, device_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thiết bị.")

    try:
        event, duplicate = save_fall_event(db, device_id, payload)
    except EventIdConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if duplicate:
        response.status_code = status.HTTP_200_OK
        return FallEventAcknowledgement(
            event_id=event.event_id, status="duplicate", duplicate=True
        )

    recipient_ids = resolve_alert_recipient_account_ids(db, device_id)
    logger.info(
        "Đã lưu Fall Event %s từ %s; %s caregiver đang theo dõi.",
        event.event_id, device_id, len(recipient_ids),
    )
    # Chưa có cơ chế thông báo realtime; không báo là đã gửi cảnh báo.
    return FallEventAcknowledgement(
        event_id=event.event_id, status="recorded", duplicate=False
    )


@device_history_router.get(
    "/{device_id}/fall-events", response_model=list[FallEventResponse]
)
def get_device_fall_events(
    authorized_data: tuple[Device, AccountDevice] = Depends(get_authorized_device),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Lấy lịch sử một Device mà caregiver đang theo dõi."""

    device, _ = authorized_data
    events = db.scalars(
        select(FallEvent)
        .where(FallEvent.device_id == device.device_id)
        .order_by(FallEvent.event_time.desc(), FallEvent.event_id.desc())
        .limit(limit).offset(offset)
    ).all()
    return [build_fall_event_response(event) for event in events]


@history_router.get("", response_model=list[FallEventResponse])
def get_my_fall_events(
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Chỉ trả sự kiện của Device thuộc quyền theo dõi hiện tại."""

    events = db.scalars(
        select(FallEvent)
        .join(AccountDevice, AccountDevice.device_id == FallEvent.device_id)
        .where(AccountDevice.account_id == current_account.account_id)
        .order_by(FallEvent.event_time.desc(), FallEvent.event_id.desc())
        .limit(limit).offset(offset)
    ).all()
    return [build_fall_event_response(event) for event in events]
