"""Kiểm thử tiếp nhận, lưu trữ và phân quyền Fall Event."""

import json
import os
import secrets

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from sqlalchemy import (
    create_engine,
    event,
    select,
    func,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from fall_event_service import resolve_alert_recipient_account_ids
from main import app
from models import AccountDevice, Device, FallEvent


# =========================================================
# 1. DATABASE RIÊNG CHO KIỂM THỬ
# =========================================================

# SQLite này chỉ tồn tại trong bộ nhớ.
# Không thay đổi aiot.db của môi trường phát triển.
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
    """Bật kiểm tra Foreign Key cho SQLite thử nghiệm."""

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
)


def override_get_db():
    """Cung cấp Session thử nghiệm cho FastAPI."""

    db = TestSessionLocal()

    try:
        yield db

    finally:
        db.close()


# =========================================================
# 2. CÁC HÀM HỖ TRỢ
# =========================================================

def create_caregiver(
    client: TestClient,
    email: str,
) -> tuple[int, str]:
    """
    Đăng ký và đăng nhập caregiver qua API thật.

    Trả Account ID và JWT để sử dụng trong bài test.
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

    return account_id, response.json()["access_token"]


def caregiver_headers(token: str) -> dict[str, str]:
    """Tạo Authorization header của caregiver."""

    return {
        "Authorization": f"Bearer {token}",
    }


def edge_headers(device_key: str) -> dict[str, str]:
    """Tạo header xác thực cho ESP32."""

    return {
        "X-Device-Key": device_key,
    }


def seed_devices(
    account_a_id: int,
    account_b_id: int,
):
    """
    Tạo hai Device đã đăng ký và các liên kết theo dõi.

    A và B cùng theo dõi DEV-001.
    B còn theo dõi DEV-002.
    """

    with TestSessionLocal() as db:

        db.add_all([
            Device(
                device_id="DEV-001",
                status="offline",
                model_version="model_v1",
            ),
            Device(
                device_id="DEV-002",
                status="offline",
                model_version="model_v1",
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
                device_id="DEV-001",
                display_name="Thiết bị chung của B",
            ),
            AccountDevice(
                account_id=account_b_id,
                device_id="DEV-002",
                display_name="Thiết bị thứ hai của B",
            ),
        ])

        db.commit()


def count_fall_events() -> int:
    """Đếm số Fall Event đang được lưu trong Database thử nghiệm."""

    with TestSessionLocal() as db:
        return db.scalar(
            select(func.count(FallEvent.event_id))
        ) or 0


# =========================================================
# 3. CHẠY KIỂM THỬ
# =========================================================

def run_tests():
    """Kiểm thử Fall Event API và các ranh giới phân quyền."""

    # Tạo toàn bộ bảng từ ORM Model hiện có.
    Base.metadata.create_all(bind=test_engine)

    # Thay kết nối Database thật bằng Database thử nghiệm.
    app.dependency_overrides[get_db] = override_get_db

    # Tạo khóa riêng cho từng thiết bị, không dùng khóa thật.
    key_1 = secrets.token_urlsafe(32)
    key_2 = secrets.token_urlsafe(32)

    test_keys = {
        "DEV-001": key_1,
        "DEV-002": key_2,
    }

    # Tạo hai thời điểm sự kiện khác nhau.
    now = datetime.now(timezone.utc).replace(
        microsecond=0
    )

    first_time = now - timedelta(seconds=20)
    second_time = now - timedelta(seconds=10)

    # ESP32 phải giữ nguyên payload của sự kiện khi retry.
    first_event = {
        "event_time": first_time.isoformat(),
        "event_type": "fall",
        "model_version": "model_v1",
        "confidence": 0.94,
    }

    second_event = {
        "event_time": second_time.isoformat(),
        "event_type": "fall",
        "model_version": "model_v1",
        "confidence": None,
    }

    try:
        # Chỉ cấp khóa thử nghiệm trong phạm vi bài test.
        with patch.dict(
            os.environ,
            {"DEVICE_KEYS_JSON": json.dumps(test_keys)},
        ):
            with TestClient(app) as client:

                # Tạo ba caregiver độc lập.
                account_a_id, token_a = create_caregiver(
                    client,
                    "fall.a@example.com",
                )

                account_b_id, token_b = create_caregiver(
                    client,
                    "fall.b@example.com",
                )

                account_c_id, token_c = create_caregiver(
                    client,
                    "fall.c@example.com",
                )

                headers_a = caregiver_headers(token_a)
                headers_b = caregiver_headers(token_b)
                headers_c = caregiver_headers(token_c)

                seed_devices(account_a_id, account_b_id)

                print("[PASS] Tạo 3 caregiver và 2 Device")


                # =========================================
                # TEST 1: CHƯA CÓ FALL EVENT
                # =========================================

                response = client.get(
                    "/devices/DEV-001/fall-events",
                    headers=headers_a,
                )

                assert response.status_code == 200
                assert response.json() == []

                print("[PASS] Chưa có sự kiện trả danh sách rỗng")


                # =========================================
                # TEST 2: ESP32 KHÔNG GỬI DEVICE KEY
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    json=first_event,
                )

                assert response.status_code == 401
                assert count_fall_events() == 0

                print("[PASS] Thiếu Device Key trả HTTP 401")


                # =========================================
                # TEST 3: KHÓA CỦA DEVICE KHÁC
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    headers=edge_headers(key_2),
                    json=first_event,
                )

                assert response.status_code == 401
                assert count_fall_events() == 0

                print("[PASS] Khóa sai thiết bị bị từ chối")


                # =========================================
                # TEST 4: KHÔNG CHẤP NHẬN NORMAL EVENT
                # =========================================

                invalid_event = {
                    **first_event,
                    "event_type": "normal",
                }

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    headers=edge_headers(key_1),
                    json=invalid_event,
                )

                assert response.status_code == 422

                print("[PASS] Loại sự kiện không hợp lệ bị từ chối")


                # =========================================
                # TEST 5: CONFIDENCE NGOÀI KHOẢNG 0 ĐẾN 1
                # =========================================

                invalid_event = {
                    **first_event,
                    "confidence": 1.5,
                }

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    headers=edge_headers(key_1),
                    json=invalid_event,
                )

                assert response.status_code == 422

                print("[PASS] Confidence không hợp lệ bị từ chối")


                # =========================================
                # TEST 6: EVENT TIME THIẾU MÚI GIỜ
                # =========================================

                invalid_event = {
                    **first_event,
                    "event_time": "2026-10-13T14:30:00",
                }

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    headers=edge_headers(key_1),
                    json=invalid_event,
                )

                assert response.status_code == 422

                print("[PASS] Event Time thiếu múi giờ bị từ chối")


                # =========================================
                # TEST 7: TRƯỜNG NGOÀI HỢP ĐỒNG API
                # =========================================

                invalid_event = {
                    **first_event,
                    "account_id": account_a_id,
                }

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    headers=edge_headers(key_1),
                    json=invalid_event,
                )

                assert response.status_code == 422

                print("[PASS] Không nhận Account ID từ ESP32")


                # =========================================
                # TEST 8: LƯU FALL EVENT ĐẦU TIÊN
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    headers=edge_headers(key_1),
                    json=first_event,
                )

                assert response.status_code == 201

                first_receipt = response.json()

                assert first_receipt["status"] == "recorded"
                assert first_receipt["duplicate"] is False

                first_event_id = first_receipt["event_id"]

                assert count_fall_events() == 1

                print("[PASS] Fall Event mới được lưu, HTTP 201")


                # =========================================
                # TEST 9: GỬI LẠI CÙNG FALL EVENT
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    headers=edge_headers(key_1),
                    json=first_event,
                )

                assert response.status_code == 200

                assert response.json()["duplicate"] is True

                assert response.json()["event_id"] == (
                    first_event_id
                )

                assert count_fall_events() == 1

                print("[PASS] Retry không tạo bản ghi trùng")


                # =========================================
                # TEST 10: CÙNG THỜI ĐIỂM, KHÁC MÚI GIỜ
                # =========================================

                # Biểu diễn cùng một thời điểm theo múi giờ +07.
                same_time_vietnam = first_time.astimezone(
                    timezone(timedelta(hours=7))
                )

                equivalent_event = {
                    **first_event,
                    "event_time": same_time_vietnam.isoformat(),
                }

                response = client.post(
                    "/device-ingest/DEV-001/fall-events",
                    headers=edge_headers(key_1),
                    json=equivalent_event,
                )

                assert response.status_code == 200
                assert response.json()["duplicate"] is True
                assert count_fall_events() == 1

                print("[PASS] Chuẩn hóa UTC giúp nhận diện retry")


                # =========================================
                # TEST 11: TÌM ĐỦ CAREGIVER THEO DÕI DEV-001
                # =========================================

                with TestSessionLocal() as db:
                    recipients = resolve_alert_recipient_account_ids(
                        db,
                        "DEV-001",
                    )

                assert recipients == sorted([
                    account_a_id,
                    account_b_id,
                ])

                print("[PASS] DEV-001 có đúng hai caregiver cần cảnh báo")


                # =========================================
                # TEST 12: A VÀ B ĐƯỢC XEM LỊCH SỬ DEV-001
                # =========================================

                for headers in (headers_a, headers_b):
                    response = client.get(
                        "/devices/DEV-001/fall-events",
                        headers=headers,
                    )

                    assert response.status_code == 200
                    assert len(response.json()) == 1
                    assert response.json()[0]["event_id"] == (
                        first_event_id
                    )

                print("[PASS] A và B cùng xem được Fall Event DEV-001")


                # =========================================
                # TEST 13: C KHÔNG CÓ QUYỀN THEO DÕI
                # =========================================

                response = client.get(
                    "/devices/DEV-001/fall-events",
                    headers=headers_c,
                )

                assert response.status_code == 403

                print("[PASS] C không có quyền xem DEV-001")


                # =========================================
                # TEST 14: THIẾU JWT VÀ DEVICE KHÔNG TỒN TẠI
                # =========================================

                response = client.get(
                    "/devices/DEV-001/fall-events"
                )

                assert response.status_code == 401

                response = client.get(
                    "/devices/DEV-999/fall-events",
                    headers=headers_a,
                )

                assert response.status_code == 404

                print("[PASS] Thiếu JWT 401, Device không tồn tại 404")


                # =========================================
                # TEST 15: LỊCH SỬ TỔNG HỢP THEO CAREGIVER
                # =========================================

                response_a = client.get(
                    "/fall-events",
                    headers=headers_a,
                )

                response_b = client.get(
                    "/fall-events",
                    headers=headers_b,
                )

                response_c = client.get(
                    "/fall-events",
                    headers=headers_c,
                )

                assert len(response_a.json()) == 1
                assert len(response_b.json()) == 1
                assert response_c.json() == []

                print("[PASS] Lịch sử tổng hợp tách biệt theo quyền")


                # =========================================
                # TEST 16: DEV-002 GỬI FALL EVENT
                # =========================================

                response = client.post(
                    "/device-ingest/DEV-002/fall-events",
                    headers=edge_headers(key_2),
                    json=second_event,
                )

                assert response.status_code == 201
                assert count_fall_events() == 2

                response_a = client.get(
                    "/fall-events",
                    headers=headers_a,
                )

                response_b = client.get(
                    "/fall-events",
                    headers=headers_b,
                )

                assert len(response_a.json()) == 1
                assert len(response_b.json()) == 2

                print("[PASS] A không xem được sự kiện riêng của B")


                # =========================================
                # TEST 17: PHÂN TRANG LỊCH SỬ
                # =========================================

                response = client.get(
                    "/fall-events?limit=1&offset=0",
                    headers=headers_b,
                )

                assert response.status_code == 200
                assert len(response.json()) == 1

                # Sự kiện mới hơn của DEV-002 phải ở trước.
                assert response.json()[0]["device_id"] == (
                    "DEV-002"
                )

                response = client.get(
                    "/fall-events?limit=0",
                    headers=headers_b,
                )

                assert response.status_code == 422

                print("[PASS] Phân trang và giới hạn dữ liệu")


                # =========================================
                # TEST 18: A HỦY LIÊN KẾT DEV-001
                # =========================================

                response = client.delete(
                    "/devices/DEV-001/link",
                    headers=headers_a,
                )

                assert response.status_code == 204

                response = client.get(
                    "/devices/DEV-001/fall-events",
                    headers=headers_a,
                )

                assert response.status_code == 403

                response = client.get(
                    "/fall-events",
                    headers=headers_a,
                )

                assert response.status_code == 200
                assert response.json() == []

                print("[PASS] Hủy liên kết làm mất quyền xem lịch sử")


                # =========================================
                # TEST 19: B VẪN ĐƯỢC XEM, DỮ LIỆU VẪN CÒN
                # =========================================

                response = client.get(
                    "/devices/DEV-001/fall-events",
                    headers=headers_b,
                )

                assert response.status_code == 200
                assert len(response.json()) == 1

                assert count_fall_events() == 2

                with TestSessionLocal() as db:
                    recipients = resolve_alert_recipient_account_ids(
                        db,
                        "DEV-001",
                    )

                assert recipients == [account_b_id]

                print("[PASS] Dữ liệu còn và chỉ B có quyền theo dõi")


                # =========================================
                # TEST 20: RESPONSE KHÔNG LỘ THÔNG TIN ACCOUNT
                # =========================================

                response = client.get(
                    "/fall-events",
                    headers=headers_b,
                )

                assert response.status_code == 200

                expected_fields = {
                    "event_id",
                    "device_id",
                    "event_time",
                    "event_type",
                    "model_version",
                    "confidence",
                }

                for event_data in response.json():
                    assert set(event_data.keys()) == (
                        expected_fields
                    )

                print("[PASS] Response không lộ Account hoặc khóa")


        print("\nFALL EVENT BACKEND TEST: PASS")

    finally:
        # Khôi phục kết nối Database thật sau kiểm thử.
        app.dependency_overrides.pop(get_db, None)

        # Giải phóng Database SQLite thử nghiệm.
        test_engine.dispose()


if __name__ == "__main__":
    run_tests()