"""API quản lý Dashboard: bộ lọc an toàn, phân trang và lời mời đang chờ."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from models import (
    Account, AccountDevice, AlertNotification, DeviceHeartbeatState,
    DeviceOwnership, DeviceShareInvitation, FallEvent,
)
from pairing_service import as_utc, commit_or_conflict, lock_device, owner_for
from alert_schemas import AlertResponse
from fall_event_schemas import FallEventResponse
from fall_event_service import build_fall_event_response

router = APIRouter(prefix="/management", tags=["Dashboard Management"])


class FallEventPage(BaseModel):
    """Trang lịch sử sự kiện theo quyền caregiver."""
    items: list[FallEventResponse]
    total: int
    limit: int
    offset: int
    has_next: bool


class AlertHistoryPage(BaseModel):
    """Trang lịch sử thông báo, bao gồm đã xem và chưa xem."""
    items: list[AlertResponse]
    total: int
    limit: int
    offset: int
    has_next: bool


class DashboardSummary(BaseModel):
    """Thống kê chỉ tính dữ liệu caregiver đang có quyền."""
    devices_total: int
    devices_online: int
    falls_last_30_days: int
    unread_alerts: int
    pending_invitations: int


class InvitationPublic(BaseModel):
    """Thông tin lời mời cho chủ sở hữu; không tiết lộ mã băm hoặc mã gốc."""
    invitation_id: int
    device_id: str
    invitee_email: str
    created_at: datetime
    expires_at: datetime


def require_range(from_at: datetime | None, to_at: datetime | None) -> None:
    """Chỉ chấp nhận thời điểm kèm timezone và khoảng thời gian hợp lệ."""
    for value in (from_at, to_at):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(status_code=422, detail="Thời gian lọc phải có múi giờ.")
    if from_at is not None and to_at is not None and from_at >= to_at:
        raise HTTPException(status_code=422, detail="Thời điểm bắt đầu phải nhỏ hơn thời điểm kết thúc.")


def require_device_link(db: Session, account_id: int, device_id: str | None) -> None:
    """Từ chối truy vấn Device chưa liên kết thay vì tiết lộ dữ liệu lịch sử."""
    if device_id is not None and db.get(AccountDevice, (account_id, device_id)) is None:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập thiết bị này.")


def page_info(total: int, limit: int, offset: int) -> dict:
    """Tạo thông tin phân trang thống nhất cho API."""
    return {"total": total, "limit": limit, "offset": offset, "has_next": offset + limit < total}


def search_filter(query: str | None):
    """Tìm bằng ID hoặc tên riêng Device đã cấp quyền."""
    if not query:
        return None
    # Escape các ký tự wildcard để ô tìm kiếm được hiểu là văn bản thông thường.
    escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return or_(AccountDevice.device_id.ilike(pattern, escape="\\"),
               AccountDevice.display_name.ilike(pattern, escape="\\"))


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Đếm dữ liệu trong phạm vi liên kết và vai trò hiện tại."""
    account_id = account.account_id
    now = datetime.now(timezone.utc)
    links = list(db.scalars(select(AccountDevice.device_id).where(AccountDevice.account_id == account_id)))
    online = 0
    if links:
        states = db.scalars(select(DeviceHeartbeatState).where(DeviceHeartbeatState.device_id.in_(links))).all()
        online = sum(1 for state in states if 0 <= (now - as_utc(state.last_seen_at)).total_seconds() <= 45)
    falls = db.scalar(
        select(func.count(FallEvent.event_id))
        .join(AccountDevice, AccountDevice.device_id == FallEvent.device_id)
        .where(AccountDevice.account_id == account_id, FallEvent.event_time >= now - timedelta(days=30))
    ) or 0
    alerts = db.scalar(
        select(func.count(AlertNotification.notification_id))
        .join(FallEvent, FallEvent.event_id == AlertNotification.fall_event_id)
        .join(AccountDevice, and_(AccountDevice.device_id == FallEvent.device_id,
                                  AccountDevice.account_id == AlertNotification.account_id))
        .where(AlertNotification.account_id == account_id, AlertNotification.read_at.is_(None))
    ) or 0
    invitations = db.scalar(
        select(func.count(DeviceShareInvitation.invitation_id))
        .join(DeviceOwnership, DeviceOwnership.device_id == DeviceShareInvitation.device_id)
        .where(DeviceOwnership.account_id == account_id,
               DeviceShareInvitation.accepted_at.is_(None),
               DeviceShareInvitation.revoked_at.is_(None),
               DeviceShareInvitation.expires_at > now)
    ) or 0
    return DashboardSummary(devices_total=len(links), devices_online=online,
                            falls_last_30_days=falls, unread_alerts=alerts,
                            pending_invitations=invitations)


@router.get("/fall-events", response_model=FallEventPage)
def management_fall_events(
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
    device_id: str | None = Query(default=None, min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=100),
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
):
    """Lọc FallEvent trên Server; không nhận account_id từ trình duyệt."""
    require_range(from_at, to_at)
    require_device_link(db, account.account_id, device_id)
    query = (select(FallEvent)
             .join(AccountDevice, AccountDevice.device_id == FallEvent.device_id)
             .where(AccountDevice.account_id == account.account_id))
    if device_id is not None:
        query = query.where(FallEvent.device_id == device_id)
    condition = search_filter(q)
    if condition is not None:
        query = query.where(condition)
    if from_at is not None:
        query = query.where(FallEvent.event_time >= from_at)
    if to_at is not None:
        query = query.where(FallEvent.event_time < to_at)
    if min_confidence is not None:
        query = query.where(FallEvent.confidence >= min_confidence)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.order_by(FallEvent.event_time.desc(), FallEvent.event_id.desc())
                      .offset(offset).limit(limit)).all()
    return FallEventPage(items=[build_fall_event_response(item) for item in rows],
                         **page_info(total, limit, offset))


@router.get("/alerts", response_model=AlertHistoryPage)
def management_alerts(
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
    device_id: str | None = Query(default=None, min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=100),
    read_state: Literal["all", "read", "unread"] = "all",
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
):
    """Đọc lịch sử cảnh báo có quyền, kể cả thông báo đã xem."""
    require_range(from_at, to_at)
    require_device_link(db, account.account_id, device_id)
    query = (
        select(AlertNotification, FallEvent, AccountDevice.display_name)
        .join(FallEvent, FallEvent.event_id == AlertNotification.fall_event_id)
        .join(AccountDevice, and_(AccountDevice.device_id == FallEvent.device_id,
                                  AccountDevice.account_id == AlertNotification.account_id))
        .where(AlertNotification.account_id == account.account_id)
    )
    if device_id is not None:
        query = query.where(FallEvent.device_id == device_id)
    condition = search_filter(q)
    if condition is not None:
        query = query.where(condition)
    if read_state == "read":
        query = query.where(AlertNotification.read_at.is_not(None))
    elif read_state == "unread":
        query = query.where(AlertNotification.read_at.is_(None))
    if from_at is not None:
        query = query.where(AlertNotification.created_at >= from_at)
    if to_at is not None:
        query = query.where(AlertNotification.created_at < to_at)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.execute(query.order_by(AlertNotification.notification_id.desc())
                      .offset(offset).limit(limit)).all()
    items = [AlertResponse(
        notification_id=notification.notification_id, event_id=event.event_id,
        device_id=event.device_id, device_name=name or event.device_id,
        event_time=as_utc(event.event_time), model_version=event.model_version,
        confidence=event.confidence, created_at=as_utc(notification.created_at),
        read_at=as_utc(notification.read_at) if notification.read_at else None,
    ) for notification, event, name in rows]
    return AlertHistoryPage(items=items, **page_info(total, limit, offset))


@router.get("/devices/{device_id}/invitations", response_model=list[InvitationPublic])
def management_invitations(
    device_id: str,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Chủ sở hữu xem lời mời chưa hết hạn; không có cách lấy lại token gốc."""
    owner_for(db, device_id, account.account_id)
    now = datetime.now(timezone.utc)
    query = (
        select(DeviceShareInvitation, Account.email)
        .join(Account, Account.account_id == DeviceShareInvitation.invited_account_id)
        .where(DeviceShareInvitation.device_id == device_id,
               DeviceShareInvitation.accepted_at.is_(None),
               DeviceShareInvitation.revoked_at.is_(None),
               DeviceShareInvitation.expires_at > now)
        .order_by(DeviceShareInvitation.invitation_id.desc())
    )
    return [InvitationPublic(invitation_id=item.invitation_id,
                             device_id=device_id, invitee_email=email,
                             created_at=as_utc(item.created_at),
                             expires_at=as_utc(item.expires_at))
            for item, email in db.execute(query).all()]


@router.delete("/devices/{device_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    device_id: str,
    invitation_id: int,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Chủ sở hữu vô hiệu hóa mã mời trước khi người nhận chấp nhận."""
    lock_device(db, device_id)
    owner_for(db, device_id, account.account_id)
    invitation = db.get(DeviceShareInvitation, invitation_id)
    if invitation is None or invitation.device_id != device_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy lời mời của thiết bị này.")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Lời mời đã được chấp nhận; cần thu hồi quyền theo dõi.")
    if invitation.revoked_at is not None or as_utc(invitation.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Lời mời không còn hiệu lực.")
    invitation.revoked_at = datetime.now(timezone.utc)
    commit_or_conflict(db)
    return None
