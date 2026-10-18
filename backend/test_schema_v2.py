"""Kiểm thử schema v2 từ Register, Login đến heartbeat và Fall Event."""

import json
import os
import secrets

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from device_heartbeat_service import get_device_liveness
from models import (
    AccountDevice, Device, DeviceHeartbeatState, FallEvent
)


# Bộ nhớ SQLite chỉ dành riêng cho bài kiểm thử.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def enable_test_foreign_keys(dbapi_connection, connection_record):
    """Bật kiểm tra FK cho SQLite thử nghiệm."""

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False)


def override_get_db():
    """Thay Database thật bằng Database thử nghiệm trong request."""

    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


def register_and_login(client: TestClient, email: str) -> tuple[int, str]:
    """Đăng ký rồi đăng nhập qua API thực tế của dự án."""

    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "DemoPass@2026!",
            "display_name": "Người chăm sóc kiểm thử",
        },
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["account_id"]

    r = client.post(
        "/auth/login",
        json={"email": email, "password": "DemoPass@2026!"},
    )
    assert r.status_code == 200, r.text
    return account_id, r.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    """Tạo header JWT caregiver."""

    return {"Authorization": f"Bearer {token}"}


def device_key(key: str) -> dict[str, str]:
    """Tạo header xác thực của thiết bị."""

    return {"X-Device-Key": key}


def count_events(db) -> int:
    """Đếm số Fall Event được lưu để phát hiện ghi trùng."""

    return db.scalar(select(func.count(FallEvent.event_id)))


def run_tests():
    """Thực hiện kiểm tra độc lập bằng SQLite trong bộ nhớ."""

    Base.metadata.create_all(test_engine)
    app.dependency_overrides[get_db] = override_get_db
    key_1 = secrets.token_urlsafe(32)
    key_2 = secrets.token_urlsafe(32)

    try:
        with patch.dict(os.environ, {
            "DEVICE_KEYS_JSON": json.dumps({"DEV-001": key_1, "DEV-002": key_2})
        }):
            with TestClient(app) as client:
                a_id, a_token = register_and_login(client, "m66-a@example.com")
                b_id, b_token = register_and_login(client, "m66-b@example.com")
                a, b = bearer(a_token), bearer(b_token)

                with TestSessionLocal() as db:
                    db.add_all([
                        Device(device_id="DEV-001", status="offline", model_version=None),
                        Device(device_id="DEV-002", status="offline", model_version=None),
                    ])
                    db.commit()
                    db.add_all([
                        AccountDevice(account_id=a_id, device_id="DEV-001", display_name="Bố"),
                        AccountDevice(account_id=b_id, device_id="DEV-002", display_name="Mẹ"),
                    ])
                    db.commit()

                # Kiểm tra trường hợp chưa nhận heartbeat.
                r = client.get("/devices/DEV-001/status", headers=a)
                assert r.status_code == 200 and r.json()["status"] == "offline"
                assert r.json()["last_seen_at"] is None
                print("[PASS] Chưa có heartbeat -> offline")

                # Không cho ESP32 giả mạo bằng khóa thiết bị khác.
                r = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    headers=device_key(key_2), json={},
                )
                assert r.status_code == 401
                print("[PASS] Sai Device Key bị từ chối")

                r = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    headers=device_key(key_1), json={"model_version": "model_v1"},
                )
                assert r.status_code == 200
                r = client.get("/devices/DEV-001/status", headers=a)
                assert r.status_code == 200 and r.json()["status"] == "online"
                assert client.get("/devices/DEV-001", headers=a).json()["status"] == "online"
                assert client.get("/devices", headers=a).json()[0]["status"] == "online"
                assert client.get("/devices/DEV-001/status", headers=b).status_code == 403
                print("[PASS] Heartbeat được chia sẻ qua DB và API bảo vệ quyền")

                # Mở Session mới để chứng minh heartbeat không phụ thuộc RAM.
                with TestSessionLocal() as db:
                    row = db.get(DeviceHeartbeatState, "DEV-001")
                    assert row is not None and row.last_seen_at is not None
                    received = row.last_seen_at
                    if received.tzinfo is None:
                        received = received.replace(tzinfo=timezone.utc)
                    assert get_device_liveness(
                        db, "DEV-001", now=received + timedelta(seconds=45)
                    )[0] == "online"
                    assert get_device_liveness(
                        db, "DEV-001", now=received + timedelta(seconds=45, microseconds=1)
                    )[0] == "offline"
                    row.last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=46)
                    db.commit()
                print("[PASS] Ngưỡng timeout 45 giây chính xác")

                r = client.get("/devices/DEV-001/status", headers=a)
                assert r.status_code == 200 and r.json()["status"] == "offline"
                print("[PASS] Quá 45 giây -> offline từ dữ liệu Database")

                # Heartbeat mới làm thiết bị trở lại online.
                r = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    headers=device_key(key_1), json={},
                )
                assert r.status_code == 200
                assert client.get("/devices/DEV-001/status", headers=a).json()["status"] == "online"
                print("[PASS] Heartbeat mới khôi phục online")

                edge_event_id = str(uuid4())
                original = {
                    "edge_event_id": edge_event_id,
                    "event_time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "event_type": "fall",
                    "model_version": "model_v1",
                    "confidence": 0.94,
                }
                url = "/device-ingest/DEV-001/fall-events"
                r = client.post(url, headers=device_key(key_1), json=original)
                assert r.status_code == 201, r.text
                event_id = r.json()["event_id"]

                r = client.post(url, headers=device_key(key_1), json=original)
                assert r.status_code == 200 and r.json()["event_id"] == event_id
                assert r.json()["duplicate"] is True
                with TestSessionLocal() as db:
                    assert count_events(db) == 1
                print("[PASS] Retry cùng UUID không tạo Fall Event trùng")

                # API v2 từ chối Fall Event không gửi UUID.
                missing_uuid = {k: v for k, v in original.items() if k != "edge_event_id"}
                assert client.post(
                    url, headers=device_key(key_1), json=missing_uuid
                ).status_code == 422
                print("[PASS] Event thiếu UUID trả HTTP 422")

                # Cùng UUID với payload đã bị thay phải bị từ chối.
                changed = {**original, "confidence": 0.55}
                r = client.post(url, headers=device_key(key_1), json=changed)
                assert r.status_code == 409
                print("[PASS] Cùng UUID nhưng đổi nội dung -> HTTP 409")

                # Hai UUID khác nhau có thể đại diện hai lần ngã khác nhau.
                another = {**original, "edge_event_id": str(uuid4())}
                r = client.post(url, headers=device_key(key_1), json=another)
                assert r.status_code == 201
                with TestSessionLocal() as db:
                    assert count_events(db) == 2
                print("[PASS] Hai UUID khác nhau tạo hai bản ghi")

                # Cùng UUID ở hai Device khác nhau là hợp lệ vì khóa kép.
                assert client.post(
                    "/device-ingest/DEV-002/fall-events",
                    headers=device_key(key_2), json=original,
                ).status_code == 201
                with TestSessionLocal() as db:
                    assert count_events(db) == 3
                print("[PASS] Cùng UUID trên Device khác được chấp nhận")

                # Bản ghi v1 vẫn đọc được dù không có edge_event_id.
                with TestSessionLocal() as db:
                    db.add(FallEvent(
                        device_id="DEV-001", edge_event_id=None,
                        event_time=datetime.now(timezone.utc) - timedelta(days=1),
                        event_type="fall", model_version="model_v1", confidence=None,
                    ))
                    db.commit()
                r = client.get("/devices/DEV-001/fall-events", headers=a)
                assert r.status_code == 200 and len(r.json()) == 3
                assert any(item["edge_event_id"] is None for item in r.json())
                assert client.get("/devices/DEV-001/fall-events", headers=b).status_code == 403
                print("[PASS] Fall Event v1 vẫn đọc được, phân quyền đúng")

                # Dữ liệu không bị mất sau khi caregiver hủy quyền theo dõi.
                r = client.delete("/devices/DEV-001/link", headers=a)
                assert r.status_code == 204
                assert client.get("/fall-events", headers=a).json() == []
                with TestSessionLocal() as db:
                    assert count_events(db) == 4
                print("[PASS] Hủy liên kết không xóa dữ liệu lịch sử")

        print("\nSCHEMA V2 INTEGRATION TEST: PASS")
    finally:
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()


if __name__ == "__main__":
    run_tests()
