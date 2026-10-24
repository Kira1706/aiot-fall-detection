"""WebSocket cảnh báo ngã có xác thực JWT và đọc hàng đợi từ Database."""

import asyncio
import time


from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from alert_service import list_alerts
from database import get_db
from security_tokens import authenticate_secure_token
from fastapi import HTTPException
from models import Account


router = APIRouter(tags=["Realtime Alerts"])

# Mỗi lần đọc tối đa 50 cảnh báo chưa xem để hạn chế một lần gửi quá lớn.
POLL_SECONDS = 1.0
BATCH_SIZE = 50


def same_origin_allowed(websocket: WebSocket) -> bool:
    """Chặn Origin khác Host khi kết nối từ trình duyệt."""

    origin = websocket.headers.get("origin")
    if origin is None:
        # Client không phải trình duyệt có thể không gửi Origin.
        return True
    parsed = urlparse(origin)
    # Với reverse proxy phải chuyển tiếp Host đúng từ phía proxy.
    return parsed.scheme in {"http", "https"} and parsed.netloc == websocket.headers.get("host")


@router.websocket("/ws/alerts")
async def alerts_socket(
    websocket: WebSocket,
    db: Session = Depends(get_db),
):
    """
    Cảnh báo ngã cho caregiver đã xác thực qua thông điệp đầu tiên.

    Không đặt JWT vào URL hoặc log truy cập; token chỉ gửi trong WS frame.
    Mỗi tiến trình tự đọc PostgreSQL nên dùng được nhiều worker.
    """

    if not same_origin_allowed(websocket):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        if not isinstance(auth, dict) or auth.get("type") != "auth":
            await websocket.close(code=4401)
            return
        token = auth.get("token")
        if not isinstance(token, str) or not token:
            await websocket.close(code=4401)
            return
        try:
            account, payload = authenticate_secure_token(token, db)
        except HTTPException:
            await websocket.close(code=4401)
            return
        account_id = account.account_id

        expiry = int(payload["exp"])
        await websocket.send_json({"type": "authenticated"})
        cursor = 0

        while True:
            if time.time() >= expiry:
                await websocket.close(code=4401)
                return

            # Chấm dứt transaction trước vòng thăm dò quyền mới.
            db.rollback()
            # Token có thể bị thu hồi khi WebSocket vẫn đang mở.
            try:
                authenticate_secure_token(token, db)
            except HTTPException:
                await websocket.close(code=4401)
                return
            # list_alerts tiếp tục lọc AccountDevice hiện hành sau khi thu hồi quyền.
            alerts = list_alerts(
                db, account_id, after_id=cursor,
                unread_only=True, limit=BATCH_SIZE,
            )
            for alert in alerts:
                await websocket.send_json({
                    "type": "fall_alert",
                    "data": alert.model_dump(mode="json"),
                })
                cursor = alert.notification_id

            # Nhận ping/đóng socket; timeout chỉ dùng để thăm dò DB định kỳ.
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(), timeout=POLL_SECONDS
                )
                if message == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                return

    except (WebSocketDisconnect, asyncio.TimeoutError):
        # Client ngắt trước khi hoàn tất bước xác thực hoặc hết thời gian chờ.
        return
