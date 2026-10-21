"""Kiểm thử cảnh báo realtime, lưu bền vững, JWT và phân quyền."""

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from models import AccountDevice, AlertNotification, Device, FallEvent


def register_and_login(client: TestClient, email: str) -> tuple[int, str]:
    """Tạo caregiver bằng API thật và nhận JWT."""

    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "DemoPass@2026!",
            "display_name": email,
        },
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["account_id"]
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "DemoPass@2026!"},
    )
    assert response.status_code == 200, response.text
    return account_id, response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    """Tạo Bearer header cho caregiver."""

    return {"Authorization": f"Bearer {token}"}


def run_tests():
    """Kiểm thử các trường hợp ghi cảnh báo và nhận qua WebSocket."""

    # SQLite trên file tạm cho phép nhiều kết nối khi WebSocket và HTTP chạy đồng thời.
    with TemporaryDirectory() as temp_dir:
        sqlite_path = Path(temp_dir) / "realtime-test.db"
        test_engine = create_engine(
            f"sqlite:///{sqlite_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(test_engine, "connect")
        def enable_foreign_keys(connection, record):
            """Bật kiểm tra khóa ngoại trên SQLite kiểm thử."""

            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False)

        def override_get_db():
            """Đưa mọi HTTP API và WebSocket vào Database thử nghiệm."""

            with TestSessionLocal() as db:
                yield db

        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db
        key_1 = secrets.token_urlsafe(32)
        key_2 = secrets.token_urlsafe(32)
        device_keys = {"DEV-001": key_1, "DEV-002": key_2}

        try:
            with patch.dict(os.environ, {"DEVICE_KEYS_JSON": json.dumps(device_keys)}):
                with TestClient(app) as client:
                    id_a, token_a = register_and_login(client, "alert-a@example.com")
                    id_b, token_b = register_and_login(client, "alert-b@example.com")
                    _, token_c = register_and_login(client, "alert-c@example.com")
                    with TestSessionLocal() as db:
                        db.add_all([
                            Device(device_id="DEV-001", status="offline", model_version="model_v1"),
                            Device(device_id="DEV-002", status="offline", model_version="model_v1"),
                        ])
                        db.commit()
                        db.add_all([
                            AccountDevice(account_id=id_a, device_id="DEV-001", display_name="Bố"),
                            AccountDevice(account_id=id_b, device_id="DEV-001", display_name="Ông"),
                            AccountDevice(account_id=id_b, device_id="DEV-002", display_name="Thiết bị thứ hai"),
                        ])
                        db.commit()
                    print("[PASS] Có 3 caregiver, 2 Device và phân quyền riêng")

                    for url in ("/alerts",):
                        assert client.get(url).status_code == 401
                    assert client.get("/alerts", headers=auth(token_c)).json() == []
                    print("[PASS] REST yêu cầu JWT, caregiver không liên kết không có cảnh báo")

                    payload = {
                        "edge_event_id": str(uuid4()),
                        "event_time": datetime.now(timezone.utc).isoformat(),
                        "event_type": "fall",
                        "model_version": "model_v1",
                        "confidence": 0.95,
                    }
                    url = "/device-ingest/DEV-001/fall-events"
                    response = client.post(url, json=payload, headers={"X-Device-Key": key_1})
                    assert response.status_code == 201, response.text
                    event_id = response.json()["event_id"]
                    with TestSessionLocal() as db:
                        assert db.scalar(select(func.count()).select_from(FallEvent)) == 1
                        assert db.scalar(select(func.count()).select_from(AlertNotification)) == 2
                    print("[PASS] FallEvent và hai thông báo cùng được lưu Database")

                    # Giả lập lỗi ghi thông báo, đảm bảo FallEvent rollback cùng giao dịch.
                    failed_payload = {**payload, "edge_event_id": str(uuid4())}

                    def simulate_alert_write_failure(connection, cursor, statement, params, context, many):
                        """Chủ động gây lỗi khi ghi bản ghi thông báo thử nghiệm."""

                        if "insert into alert_notifications" in statement.lower():
                            raise RuntimeError("Lỗi ghi thông báo được giả lập")

                    event.listen(test_engine, "before_cursor_execute", simulate_alert_write_failure)
                    try:
                        try:
                            client.post(url, json=failed_payload, headers={"X-Device-Key": key_1})
                            raise AssertionError("Sự kiện lỗi vẫn được lưu thành công.")
                        except RuntimeError as error:
                            assert "Lỗi ghi thông báo được giả lập" in str(error)
                    finally:
                        event.remove(test_engine, "before_cursor_execute", simulate_alert_write_failure)

                    with TestSessionLocal() as db:
                        assert db.scalar(select(func.count()).select_from(FallEvent)) == 1
                        assert db.scalar(select(func.count()).select_from(AlertNotification)) == 2
                    print("[PASS] Lỗi ghi thông báo rollback cả FallEvent")

                    response = client.post(url, json=payload, headers={"X-Device-Key": key_1})
                    assert response.status_code == 200 and response.json()["duplicate"] is True
                    with TestSessionLocal() as db:
                        assert db.scalar(select(func.count()).select_from(AlertNotification)) == 2
                    print("[PASS] Retry cùng UUID không tạo lại thông báo")

                    changed = {**payload, "confidence": 0.75}
                    assert client.post(url, json=changed, headers={"X-Device-Key": key_1}).status_code == 409
                    assert client.post(url, json=payload, headers={"X-Device-Key": key_2}).status_code == 401
                    print("[PASS] Sai nội dung UUID trả 409 và Device Key sai bị chặn")

                    alerts_a = client.get("/alerts", headers=auth(token_a))
                    alerts_b = client.get("/alerts", headers=auth(token_b))
                    assert alerts_a.status_code == alerts_b.status_code == 200
                    assert len(alerts_a.json()) == len(alerts_b.json()) == 1
                    assert alerts_a.json()[0]["device_name"] == "Bố"
                    assert alerts_b.json()[0]["device_name"] == "Ông"
                    alert_id_a = alerts_a.json()[0]["notification_id"]
                    alert_id_b = alerts_b.json()[0]["notification_id"]
                    assert alerts_a.json()[0]["event_id"] == event_id
                    print("[PASS] Thông báo đúng account và tên thiết bị riêng")

                    # Không chấp nhận kết nối WebSocket có Origin của website khác.
                    from starlette.websockets import WebSocketDisconnect
                    try:
                        with client.websocket_connect(
                            "/ws/alerts", headers={"origin": "https://evil.example"}
                        ):
                            raise AssertionError("Origin khác nguồn không bị chặn.")
                    except WebSocketDisconnect as error:
                        assert error.code == 1008
                    print("[PASS] WebSocket chặn Origin khác nguồn")

                    # Socket không dùng JWT trên URL; Client gửi JWT trong bản tin đầu.
                    with client.websocket_connect("/ws/alerts") as websocket:
                        websocket.send_json({"type": "auth", "token": token_a})
                        assert websocket.receive_json()["type"] == "authenticated"
                        pushed = websocket.receive_json()
                        assert pushed["type"] == "fall_alert"
                        assert pushed["data"]["notification_id"] == alert_id_a
                        print("[PASS] WebSocket xác thực và đẩy cảnh báo chưa xem")

                    # Kiểm tra việc đẩy sự kiện mới khi WebSocket đang mở.
                    with client.websocket_connect("/ws/alerts") as websocket:
                        websocket.send_json({"type": "auth", "token": token_a})
                        assert websocket.receive_json()["type"] == "authenticated"
                        assert websocket.receive_json()["data"]["notification_id"] == alert_id_a
                        live_payload = {**payload, "edge_event_id": str(uuid4())}
                        assert client.post(
                            url, json=live_payload, headers={"X-Device-Key": key_1}
                        ).status_code == 201
                        live_alert = websocket.receive_json()
                        assert live_alert["type"] == "fall_alert"
                        assert live_alert["data"]["event_id"] != event_id
                    print("[PASS] WebSocket đẩy sự kiện mới khi đang kết nối")

                    # WebSocket từ chối JWT không hợp lệ bằng mã đóng 4401.
                    try:
                        with client.websocket_connect("/ws/alerts") as websocket:
                            websocket.send_json({"type": "auth", "token": "jwt-khong-hop-le"})
                            websocket.receive_json()
                            raise AssertionError("JWT không hợp lệ vẫn kết nối được.")
                    except WebSocketDisconnect as error:
                        assert error.code == 4401
                    print("[PASS] WebSocket từ chối JWT không hợp lệ")

                    # Tài khoản C không được xem hoặc đánh dấu đã xem cảnh báo của A.
                    assert client.post(f"/alerts/{alert_id_a}/read", headers=auth(token_c)).status_code == 404
                    assert client.get("/alerts", headers=auth(token_c)).json() == []
                    print("[PASS] Không lộ cảnh báo cho caregiver khác")

                    response = client.post(f"/alerts/{alert_id_a}/read", headers=auth(token_a))
                    assert response.status_code == 200 and response.json()["status"] == "read"
                    assert client.post(f"/alerts/{alert_id_a}/read", headers=auth(token_a)).status_code == 200
                    unread_a = client.get("/alerts", headers=auth(token_a)).json()
                    assert len(unread_a) == 1
                    assert unread_a[0]["notification_id"] != alert_id_a
                    assert len(client.get("/alerts", headers=auth(token_b)).json()) == 2
                    assert len(client.get("/alerts?unread_only=false", headers=auth(token_a)).json()) == 2
                    print("[PASS] Đã xem idempotent cho A, không ảnh hưởng B")

                    # Một sự kiện mới khi A đang offline phải xuất hiện qua REST khi đăng nhập lại.
                    payload_2 = {**payload, "edge_event_id": str(uuid4())}
                    assert client.post(url, json=payload_2, headers={"X-Device-Key": key_1}).status_code == 201
                    with client.websocket_connect("/ws/alerts") as websocket:
                        websocket.send_json({"type": "auth", "token": token_a})
                        assert websocket.receive_json()["type"] == "authenticated"
                        pushed = websocket.receive_json()
                        assert pushed["data"]["event_id"] != event_id
                    print("[PASS] Cảnh báo chưa xem được nhận lại khi kết nối lại")

                    # A không còn được xem cảnh báo sau khi hủy liên kết.
                    assert client.delete("/devices/DEV-001/link", headers=auth(token_a)).status_code == 204
                    assert client.get("/alerts", headers=auth(token_a)).json() == []
                    assert len(client.get("/alerts", headers=auth(token_b)).json()) == 3
                    print("[PASS] Hủy liên kết thu hồi quyền xem cảnh báo")

                    # Legacy FallEvent không có thông báo v3, lịch sử cũ không bị xóa.
                    with TestSessionLocal() as db:
                        assert db.scalar(select(func.count()).select_from(FallEvent)) == 3
                        assert db.scalar(select(func.count()).select_from(AlertNotification)) == 6
                    print("[PASS] Dữ liệu FallEvent được giữ nguyên")

            print("\nREALTIME ALERTS TEST: PASS")
        finally:
            app.dependency_overrides.pop(get_db, None)
            test_engine.dispose()


if __name__ == "__main__":
    run_tests()
