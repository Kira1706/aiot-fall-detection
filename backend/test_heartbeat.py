
"""Kiểm thử heartbeat, xác thực ESP32 và trạng thái online/offline."""

import json
import os
import secrets

from unittest.mock import patch

from fastapi.testclient import TestClient

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db

from device_heartbeat_store import (
    HeartbeatStore,
    get_heartbeat_store,
)

from main import app
from models import AccountDevice, Device


# =========================================================
# 1. ĐỒNG HỒ GIẢ LẬP
# =========================================================

class FakeClock:
    """Cho phép tăng thời gian kiểm thử mà không cần chờ thật."""

    def __init__(self):
        self.current_time = 1000.0

    def __call__(self):
        """Trả về thời gian giả lập hiện tại."""

        return self.current_time

    def advance(self, seconds: float):
        """Tăng thời gian giả lập thêm số giây yêu cầu."""

        self.current_time += seconds


# Tạo đồng hồ và bộ lưu heartbeat riêng cho bài test.
fake_clock = FakeClock()

test_heartbeat_store = HeartbeatStore(
    timeout_seconds=45,
    clock=fake_clock,
)


# =========================================================
# 2. SQLITE DATABASE THỬ NGHIỆM
# =========================================================

test_engine = create_engine(
    "sqlite://",
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def enable_test_foreign_keys(
    dbapi_connection,
    connection_record,
):
    """Bật Foreign Key cho SQLite thử nghiệm."""

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
)


def override_get_db():
    """Cung cấp Database thử nghiệm cho FastAPI."""

    db = TestSessionLocal()

    try:
        yield db

    finally:
        db.close()


def override_heartbeat_store():
    """Cung cấp bộ nhớ heartbeat riêng cho bài test."""

    return test_heartbeat_store


# =========================================================
# 3. HÀM HỖ TRỢ
# =========================================================

def register_and_login(
    client: TestClient,
    email: str,
) -> tuple[int, str]:
    """
    Đăng ký, đăng nhập và trả Account ID cùng JWT.

    Sử dụng các API thật của Backend.
    """

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
        json={
            "email": email,
            "password": "DemoPass@2026!",
        },
    )

    assert response.status_code == 200, response.text

    token = response.json()["access_token"]

    return account_id, token


def caregiver_headers(token: str) -> dict[str, str]:
    """Tạo Bearer Authorization header của caregiver."""

    return {
        "Authorization": f"Bearer {token}"
    }


def device_headers(secret_key: str) -> dict[str, str]:
    """Tạo header xác thực dành riêng cho Device."""

    return {
        "X-Device-Key": secret_key
    }


def seed_test_devices(
    account_a_id: int,
    account_b_id: int,
):
    """Tạo hai thiết bị và hai liên kết caregiver riêng biệt."""

    with TestSessionLocal() as db:

        db.add_all([
            Device(
                device_id="DEV-001",
                status="offline",
                model_version=None,
            ),
            Device(
                device_id="DEV-002",
                status="offline",
                model_version=None,
            ),
        ])

        db.commit()

        db.add_all([
            AccountDevice(
                account_id=account_a_id,
                device_id="DEV-001",
                display_name="Thiết bị của A",
            ),
            AccountDevice(
                account_id=account_b_id,
                device_id="DEV-002",
                display_name="Thiết bị của B",
            ),
        ])

        db.commit()


# =========================================================
# 4. KIỂM THỬ TÍCH HỢP
# =========================================================

def run_tests():
    """Kiểm tra Heartbeat API, timeout và phân quyền."""

    # Tạo Database kiểm thử từ năm ORM Model hiện có.
    Base.metadata.create_all(
        bind=test_engine
    )

    # Thay Database thật và bộ lưu heartbeat thật.
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[
        get_heartbeat_store
    ] = override_heartbeat_store

    # Sinh khóa riêng cho từng Device trong bài test.
    # Không dùng khóa thật được lưu trong file .env.
    key_a = secrets.token_urlsafe(32)
    key_b = secrets.token_urlsafe(32)

    test_keys = {
        "DEV-001": key_a,
        "DEV-002": key_b,
    }

    try:
        # Chỉ thay cấu hình trong phạm vi bài kiểm thử.
        # Không chỉnh sửa file .env thật.
        with patch.dict(
            os.environ,
            {
                "DEVICE_KEYS_JSON": json.dumps(test_keys)
            },
        ):
            with TestClient(app) as client:

                # =========================================
                # TẠO HAI CAREGIVER VÀ HAI DEVICE
                # =========================================

                account_a_id, token_a = register_and_login(
                    client,
                    "heartbeat.a@example.com",
                )

                account_b_id, token_b = register_and_login(
                    client,
                    "heartbeat.b@example.com",
                )

                headers_a = caregiver_headers(token_a)
                headers_b = caregiver_headers(token_b)

                seed_test_devices(
                    account_a_id,
                    account_b_id,
                )

                print("[PASS] Tạo 2 caregiver và 2 device")


                # =========================================
                # TEST 1: CHƯA CÓ HEARTBEAT THÌ OFFLINE
                # =========================================

                response = client.get(
                    "/devices/DEV-001/status",
                    headers=headers_a,
                )

                assert response.status_code == 200

                assert response.json()["status"] == "offline"
                assert response.json()["last_seen_at"] is None

                print("[PASS] Chưa có heartbeat thì offline")


                # =========================================
                # TEST 2: THIẾU DEVICE KEY
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    json={},
                )

                assert response.status_code == 401

                print("[PASS] Thiếu Device Key trả HTTP 401")


                # =========================================
                # TEST 3: DEVICE DÙNG KHÓA CỦA DEVICE KHÁC
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    headers=device_headers(key_b),
                    json={},
                )

                assert response.status_code == 401

                print("[PASS] Device Key không khớp bị từ chối")


                # =========================================
                # TEST 4: MODEL VERSION KHÔNG HỢP LỆ
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    headers=device_headers(key_a),
                    json={
                        "model_version": "    "
                    },
                )

                assert response.status_code == 422

                print("[PASS] Model Version rỗng bị từ chối")


                # =========================================
                # TEST 5: NHẬN HEARTBEAT THÀNH CÔNG
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    headers=device_headers(key_a),
                    json={
                        "model_version": "model_v1"
                    },
                )

                assert response.status_code == 200
                assert response.json()["status"] == "online"
                assert response.json()["timeout_seconds"] == 45

                print("[PASS] Heartbeat hợp lệ trả HTTP 200")


                # =========================================
                # TEST 6: CAREGIVER A XEM TRẠNG THÁI
                # =========================================

                response = client.get(
                    "/devices/DEV-001/status",
                    headers=headers_a,
                )

                assert response.status_code == 200
                assert response.json()["status"] == "online"
                assert response.json()["last_seen_at"] is not None

                print("[PASS] A thấy DEV-001 online")


                # =========================================
                # TEST 7: B KHÔNG ĐƯỢC XEM DEV-001
                # =========================================

                response = client.get(
                    "/devices/DEV-001/status",
                    headers=headers_b,
                )

                assert response.status_code == 403

                print("[PASS] B không có quyền xem DEV-001")


                # =========================================
                # TEST 8: THIẾU JWT
                # =========================================

                response = client.get(
                    "/devices/DEV-001/status"
                )

                assert response.status_code == 401

                print("[PASS] Thiếu JWT trả HTTP 401")


                # =========================================
                # TEST 9: API DANH SÁCH VÀ CHI TIẾT
                # =========================================

                response = client.get(
                    "/devices",
                    headers=headers_a,
                )

                assert response.status_code == 200
                assert response.json()[0]["status"] == "online"

                response = client.get(
                    "/devices/DEV-001",
                    headers=headers_a,
                )

                assert response.status_code == 200
                assert response.json()["status"] == "online"
                assert response.json()["model_version"] == "model_v1"

                print("[PASS] API cũ hiển thị trạng thái mới")


                # =========================================
                # TEST 10: DEVICE KHÁC VẪN OFFLINE
                # =========================================

                response = client.get(
                    "/devices/DEV-002/status",
                    headers=headers_b,
                )

                assert response.status_code == 200
                assert response.json()["status"] == "offline"

                print("[PASS] DEV-002 không bị ảnh hưởng")


                # =========================================
                # TEST 11: ĐÚNG 45 GIÂY VẪN ONLINE
                # =========================================

                fake_clock.advance(45)

                response = client.get(
                    "/devices/DEV-001/status",
                    headers=headers_a,
                )

                assert response.status_code == 200
                assert response.json()["status"] == "online"

                print("[PASS] Đúng 45 giây vẫn online")


                # =========================================
                # TEST 12: QUÁ 45 GIÂY THÌ OFFLINE
                # =========================================

                fake_clock.advance(0.1)

                response = client.get(
                    "/devices/DEV-001/status",
                    headers=headers_a,
                )

                assert response.status_code == 200
                assert response.json()["status"] == "offline"

                print("[PASS] Quá timeout chuyển offline")


                # =========================================
                # TEST 13: HEARTBEAT MỚI KHÔI PHỤC ONLINE
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    headers=device_headers(key_a),
                    json={},
                )

                assert response.status_code == 200

                response = client.get(
                    "/devices/DEV-001/status",
                    headers=headers_a,
                )

                assert response.json()["status"] == "online"

                print("[PASS] Heartbeat mới khôi phục online")


                # =========================================
                # TEST 14: HAI DEVICE CÓ TIMEOUT RIÊNG
                # =========================================

                # Gửi heartbeat cho DEV-002.
                response = client.post(
                    "/device-ingest/DEV-002/heartbeat",
                    headers=device_headers(key_b),
                    json={},
                )

                assert response.status_code == 200

                # Sau 30 giây, DEV-001 gửi thêm heartbeat.
                fake_clock.advance(30)

                response = client.post(
                    "/device-ingest/DEV-001/heartbeat",
                    headers=device_headers(key_a),
                    json={},
                )

                assert response.status_code == 200

                # Thêm 16 giây: DEV-002 đã quá timeout.
                # DEV-001 vẫn đang trong thời hạn 45 giây.
                fake_clock.advance(16)

                response_a = client.get(
                    "/devices/DEV-001/status",
                    headers=headers_a,
                )

                response_b = client.get(
                    "/devices/DEV-002/status",
                    headers=headers_b,
                )

                assert response_a.status_code == 200
                assert response_b.status_code == 200

                assert response_a.json()["status"] == "online"
                assert response_b.json()["status"] == "offline"

                print("[PASS] Timeout độc lập theo Device")


                # =========================================
                # TEST 15: MODEL VERSION ĐƯỢC LƯU
                # =========================================

                with TestSessionLocal() as db:

                    device = db.get(
                        Device,
                        "DEV-001",
                    )

                    assert device is not None
                    assert device.model_version == "model_v1"

                print("[PASS] Model Version được lưu trong SQLite")


                # =========================================
                # TEST 16: BỘ NHỚ MỚI CHƯA CÓ HEARTBEAT
                # =========================================

                # Mô phỏng trạng thái sau khi Server restart.
                restarted_store = HeartbeatStore(
                    timeout_seconds=45,
                    clock=fake_clock,
                )

                result = restarted_store.snapshot(
                    "DEV-001"
                )

                assert result.status == "offline"
                assert result.last_seen_at is None

                print("[PASS] Bộ nhớ mới bắt đầu từ offline")

        print("\nDEVICE HEARTBEAT TEST: PASS")

    finally:
        # Khôi phục Database Dependency ban đầu.
        app.dependency_overrides.pop(
            get_db,
            None,
        )

        # Khôi phục bộ lưu heartbeat thật.
        app.dependency_overrides.pop(
            get_heartbeat_store,
            None,
        )

        # Giải phóng Database SQLite thử nghiệm.
        test_engine.dispose()


if __name__ == "__main__":
    run_tests()
