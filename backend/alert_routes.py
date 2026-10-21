"""API đọc và đánh dấu đã xem thông báo té ngã."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from alert_schemas import AlertReadResponse, AlertResponse
from alert_service import list_alerts, mark_alert_read
from auth_dependencies import get_current_account
from database import get_db
from models import Account

router = APIRouter(prefix="/alerts", tags=["Realtime Alerts"])


@router.get("", response_model=list[AlertResponse])
def get_my_alerts(
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
    after_id: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=100),
):
    """Lấy cảnh báo theo quyền hiện tại, hỗ trợ nhận lại sau khi offline."""

    return list_alerts(
        db, current_account.account_id,
        after_id=after_id, unread_only=unread_only, limit=limit,
    )


@router.post("/{notification_id}/read", response_model=AlertReadResponse)
def read_alert(
    notification_id: int,
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Đánh dấu đã xem, không đồng nghĩa đã xử lý tình huống ngã."""

    read_at = mark_alert_read(db, current_account.account_id, notification_id)
    if read_at is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo có quyền xem.")
    return AlertReadResponse(notification_id=notification_id, read_at=read_at)
