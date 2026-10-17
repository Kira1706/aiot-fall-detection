"""API tiếp nhận sự kiện ngã và truy vấn lịch sử Fall Event."""

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)

from sqlalchemy import select
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from device_auth import require_device_key
from device_permissions import get_authorized_device

from fall_event_schemas import (
    FallEventAcknowledgement,
    FallEventCreate,
    FallEventResponse,
)

from fall_event_service import (
    build_fall_event_response,
    resolve_alert_recipient_account_ids,
    save_fall_event,
)

from models import (
    Account,
    AccountDevice,
    Device,
    FallEvent,
)


# Sử dụng bộ ghi log của Python.
logger = logging.getLogger(__name__)


# API dành cho ESP32 gửi sự kiện lên Backend.
edge_router = APIRouter(
    prefix="/device-ingest",
    tags=["Device Ingest"],
)


# API đọc lịch sử theo từng Device.
device_history_router = APIRouter(
    prefix="/devices",
    tags=["Fall Events"],
)


# API đọc lịch sử tổng hợp của caregiver.
history_router = APIRouter(
    prefix="/fall-events",
    tags=["Fall Events"],
)


# =========================================================
# 1. ESP32 GỬI FALL EVENT
# =========================================================

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
    """
    Tiếp nhận Fall Event đã được Edge xác nhận.

    ESP32 chỉ gửi sự kiện sau khi hết cửa sổ Cancel.
    Backend xác thực Device Key, lưu sự kiện và xác định
    các caregiver đang theo dõi thiết bị.

    Việc phát cảnh báo realtime được làm ở milestone sau.
    """

    # Chỉ cho phép Device đã đăng ký gửi sự kiện.
    device = db.get(
        Device,
        device_id,
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thiết bị.",
        )

    # Kiểm tra dữ liệu trùng và lưu Fall Event mới nếu cần.
    fall_event, is_duplicate = save_fall_event(
        db=db,
        device_id=device_id,
        payload=payload,
    )

    if is_duplicate:
        # Sự kiện cũ được xác nhận lại mà không tạo bản ghi mới.
        # Không thực hiện lại bước xác định người nhận cảnh báo.
        response.status_code = status.HTTP_200_OK

        return FallEventAcknowledgement(
            event_id=fall_event.event_id,
            status="duplicate",
            duplicate=True,
        )

    # Tìm Account đang theo dõi Device tại thời điểm xử lý.
    # Danh sách này chỉ phục vụ luồng xử lý nội bộ.
    recipient_ids = resolve_alert_recipient_account_ids(
        db,
        device_id,
    )

    # Chỉ ghi số lượng người nhận, không in khóa hoặc JWT.
    # Chưa có chức năng gửi thông báo thực tế.
    logger.info(
        "Đã lưu Fall Event %s từ %s; có %s caregiver cần cảnh báo.",
        fall_event.event_id,
        device_id,
        len(recipient_ids),
    )

    return FallEventAcknowledgement(
        event_id=fall_event.event_id,
        status="recorded",
        duplicate=False,
    )


# =========================================================
# 2. CAREGIVER XEM LỊCH SỬ MỘT DEVICE
# =========================================================

@device_history_router.get(
    "/{device_id}/fall-events",
    response_model=list[FallEventResponse],
    status_code=status.HTTP_200_OK,
)
def get_device_fall_events(
    authorized_data: tuple[Device, AccountDevice] = Depends(
        get_authorized_device
    ),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Lấy lịch sử té ngã của một Device.

    Chỉ caregiver đang theo dõi Device mới được truy cập.
    Trả các sự kiện mới nhất trước và hỗ trợ phân trang.
    """

    # Device đã được xác thực quyền ở dependency.
    device, account_device = authorized_data

    statement = (
        select(FallEvent)
        .where(
            FallEvent.device_id == device.device_id
        )
        .order_by(
            FallEvent.event_time.desc(),
            FallEvent.event_id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    events = db.scalars(statement).all()

    return [
        build_fall_event_response(event)
        for event in events
    ]


# =========================================================
# 3. CAREGIVER XEM LỊCH SỬ CỦA MỌI DEVICE ĐANG THEO DÕI
# =========================================================

@history_router.get(
    "",
    response_model=list[FallEventResponse],
    status_code=status.HTTP_200_OK,
)
def get_my_fall_events(
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Lấy lịch sử Fall Event của các Device caregiver đang theo dõi.

    Không nhận Account ID từ Client.
    Chỉ trả sự kiện thuộc các liên kết AccountDevice hiện tại.
    """

    # Ghép FallEvent với AccountDevice qua Device ID.
    # Điều kiện Account ID được lấy từ JWT đã xác minh.
    statement = (
        select(FallEvent)
        .join(
            AccountDevice,
            AccountDevice.device_id == FallEvent.device_id,
        )
        .where(
            AccountDevice.account_id
            == current_account.account_id
        )
        .order_by(
            FallEvent.event_time.desc(),
            FallEvent.event_id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    events = db.scalars(statement).all()

    return [
        build_fall_event_response(event)
        for event in events
    ]