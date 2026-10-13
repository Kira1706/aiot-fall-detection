
"""Kiểm thử quản lý liên kết Device và phân quyền caregiver."""

import os

from unittest.mock import patch

from fastapi.testclient import TestClient

from sqlalchemy import (
    create_engine,
    event,
)

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import AccountDevice, Device


# =========================================================
# 1. TẠO DATABASE SQLITE RIÊNG CHO KIỂM THỬ
# =========================================================

# Database này chỉ tồn tại trong bộ nhớ.
# Không sử dụng hoặc thay đổi file aiot.db thật.
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
    """Bật Foreign Key cho Database SQLite thử nghiệm."""

    cursor = dbapi_connection.cursor()

    cursor.execute(
        "PRAGMA foreign_keys=ON"
    )

    cursor.close()


# Tạo Session Factory dành riêng cho bài test.
TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
)


def override_get_db():
    """Cung cấp Session thử nghiệm cho các FastAPI endpoint."""

    db = TestSessionLocal()

    try:
        yield db

    finally:
        db.close()


# =========================================================
# 2. CÁC HÀM HỖ TRỢ KIỂM THỬ
# =========================================================

def register_account(
    client: TestClient,
    email: str,
) -> int:
    """
    Đăng ký caregiver bằng Register API thật.

    Trả về Account ID của tài khoản vừa đăng ký.
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

    return response.json()["account_id"]


def login_account(
    client: TestClient,
    email: str,
) -> str:
    """Đăng nhập bằng Login API thật và nhận JWT."""

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "DemoPass@2026!",
        },
    )

    assert response.status_code == 200, response.text

    return response.json()["access_token"]


def bearer_headers(token: str) -> dict[str, str]:
    """Tạo Authorization header từ JWT."""

    return {
        "Authorization": f"Bearer {token}"
    }


def seed_devices():
    """Tạo hai Device đã đăng ký trong Database thử nghiệm."""

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


# =========================================================
# 3. KIỂM THỬ CÁC CHỨC NĂNG
# =========================================================

def run_tests():
    """Kiểm thử liên kết, đổi tên, hủy liên kết và quyền truy cập."""

    # Tạo các bảng đã định nghĩa trong schema v1.
    Base.metadata.create_all(
        bind=test_engine
    )

    # Thay Database thật bằng Database thử nghiệm.
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:

            # Tạo hai caregiver bằng Register API.
            account_a_id = register_account(
                client,
                "caregiver.a@example.com",
            )

            account_b_id = register_account(
                client,
                "caregiver.b@example.com",
            )

            # Hai caregiver đăng nhập và lấy JWT riêng.
            token_a = login_account(
                client,
                "caregiver.a@example.com",
            )

            token_b = login_account(
                client,
                "caregiver.b@example.com",
            )

            headers_a = bearer_headers(token_a)
            headers_b = bearer_headers(token_b)

            # Tạo Device đã đăng ký trong Database.
            seed_devices()

            print("[PASS] Tạo 2 caregiver và 2 device")


            # =============================================
            # TEST 1: CHẾ ĐỘ DEMO MẶC ĐỊNH BỊ TẮT
            # =============================================

            # Tạm tắt công tắc liên kết chỉ trong bài test.
            with patch.dict(
                os.environ,
                {"DEVICE_LINK_DEMO_MODE": "false"},
            ):
                response = client.post(
                    "/devices/link",
                    headers=headers_a,
                    json={
                        "device_id": "DEV-001",
                    },
                )

                assert response.status_code == 503

            print("[PASS] Tắt chế độ demo trả HTTP 503")


            # =============================================
            # BẬT CHẾ ĐỘ DEMO CHO NHỮNG TEST CÒN LẠI
            # =============================================

            # Thay đổi này không ghi vào file .env.
            with patch.dict(
                os.environ,
                {"DEVICE_LINK_DEMO_MODE": "true"},
            ):

                # =========================================
                # TEST 2: THIẾU JWT
                # =========================================

                response = client.post(
                    "/devices/link",
                    json={
                        "device_id": "DEV-001",
                    },
                )

                assert response.status_code == 401

                print("[PASS] Thiếu JWT trả HTTP 401")


                # =========================================
                # TEST 3: DEVICE KHÔNG TỒN TẠI
                # =========================================

                response = client.post(
                    "/devices/link",
                    headers=headers_a,
                    json={
                        "device_id": "DEV-999",
                    },
                )

                assert response.status_code == 404

                print("[PASS] Device không tồn tại trả HTTP 404")


                # =========================================
                # TEST 4: CAREGIVER A LIÊN KẾT DEV-001
                # =========================================

                response = client.post(
                    "/devices/link",
                    headers=headers_a,
                    json={
                        "device_id": "DEV-001",
                        "display_name": "  Thiết bị của A  ",
                    },
                )

                assert response.status_code == 201

                assert response.json()["device_id"] == "DEV-001"

                assert response.json()["display_name"] == (
                    "Thiết bị của A"
                )

                print("[PASS] A liên kết DEV-001 thành công")


                # =========================================
                # TEST 5: CAREGIVER B LIÊN KẾT DEV-002
                # =========================================

                response = client.post(
                    "/devices/link",
                    headers=headers_b,
                    json={
                        "device_id": "DEV-002",
                        "display_name": "Thiết bị của B",
                    },
                )

                assert response.status_code == 201

                print("[PASS] B liên kết DEV-002 thành công")


                # =========================================
                # TEST 6: KHÔNG CHO LIÊN KẾT TRÙNG
                # =========================================

                response = client.post(
                    "/devices/link",
                    headers=headers_a,
                    json={
                        "device_id": "DEV-001",
                    },
                )

                assert response.status_code == 409

                print("[PASS] Liên kết trùng trả HTTP 409")


                # =========================================
                # TEST 7: DANH SÁCH DEVICE TÁCH BIỆT
                # =========================================

                response_a = client.get(
                    "/devices",
                    headers=headers_a,
                )

                response_b = client.get(
                    "/devices",
                    headers=headers_b,
                )

                assert response_a.status_code == 200
                assert response_b.status_code == 200

                assert len(response_a.json()) == 1
                assert len(response_b.json()) == 1

                assert response_a.json()[0]["device_id"] == (
                    "DEV-001"
                )

                assert response_b.json()[0]["device_id"] == (
                    "DEV-002"
                )

                print("[PASS] Hai caregiver chỉ thấy Device của mình")


                # =========================================
                # TEST 8: A ĐỔI TÊN RIÊNG DEV-001
                # =========================================

                response = client.patch(
                    "/devices/DEV-001/nickname",
                    headers=headers_a,
                    json={
                        "display_name": "Phòng khách",
                    },
                )

                assert response.status_code == 200

                assert response.json()["display_name"] == (
                    "Phòng khách"
                )

                print("[PASS] A đổi tên riêng thành công")


                # =========================================
                # TEST 9: B KHÔNG ĐƯỢC ĐỔI TÊN DEV-001
                # =========================================

                response = client.patch(
                    "/devices/DEV-001/nickname",
                    headers=headers_b,
                    json={
                        "display_name": "Tên không hợp lệ",
                    },
                )

                assert response.status_code == 403

                print("[PASS] B không thể sửa liên kết của A")


                # =========================================
                # TEST 10: TÊN CHỈ CÓ KHOẢNG TRẮNG
                # =========================================

                response = client.patch(
                    "/devices/DEV-001/nickname",
                    headers=headers_a,
                    json={
                        "display_name": "     ",
                    },
                )

                assert response.status_code == 422

                print("[PASS] Tên chỉ có khoảng trắng bị từ chối")


                # =========================================
                # TEST 11: KHÔNG GỬI DISPLAY_NAME
                # =========================================

                response = client.patch(
                    "/devices/DEV-001/nickname",
                    headers=headers_a,
                    json={},
                )

                assert response.status_code == 422

                print("[PASS] PATCH thiếu display_name trả HTTP 422")


                # =========================================
                # TEST 12: XÓA TÊN RIÊNG BẰNG NULL
                # =========================================

                response = client.patch(
                    "/devices/DEV-001/nickname",
                    headers=headers_a,
                    json={
                        "display_name": None,
                    },
                )

                assert response.status_code == 200

                assert response.json()["display_name"] is None

                print("[PASS] Xóa tên riêng bằng null thành công")


                # =========================================
                # TEST 13: A ĐẶT LẠI TÊN RIÊNG
                # =========================================

                response = client.patch(
                    "/devices/DEV-001/nickname",
                    headers=headers_a,
                    json={
                        "display_name": "Thiết bị riêng của A",
                    },
                )

                assert response.status_code == 200

                print("[PASS] A đặt lại tên riêng thành công")


                # =========================================
                # TEST 14: B KHÔNG ĐƯỢC HỦY LIÊN KẾT CỦA A
                # =========================================

                response = client.delete(
                    "/devices/DEV-001/link",
                    headers=headers_b,
                )

                assert response.status_code == 403

                print("[PASS] B không thể hủy liên kết của A")


                # =========================================
                # TEST 15: B CŨNG LIÊN KẾT DEV-001
                # =========================================

                response = client.post(
                    "/devices/link",
                    headers=headers_b,
                    json={
                        "device_id": "DEV-001",
                        "display_name": "Thiết bị chung của B",
                    },
                )

                assert response.status_code == 201

                # A và B thấy các tên riêng khác nhau.
                response_a = client.get(
                    "/devices/DEV-001",
                    headers=headers_a,
                )

                response_b = client.get(
                    "/devices/DEV-001",
                    headers=headers_b,
                )

                assert response_a.status_code == 200
                assert response_b.status_code == 200

                assert response_a.json()["display_name"] == (
                    "Thiết bị riêng của A"
                )

                assert response_b.json()["display_name"] == (
                    "Thiết bị chung của B"
                )

                print(
                    "[PASS] Hai caregiver có tên riêng khác nhau"
                )


                # =========================================
                # TEST 16: A HỦY LIÊN KẾT DEV-001
                # =========================================

                response = client.delete(
                    "/devices/DEV-001/link",
                    headers=headers_a,
                )

                assert response.status_code == 204

                # HTTP 204 phải không có response body.
                assert response.content == b""

                print("[PASS] A hủy liên kết trả HTTP 204")


                # =========================================
                # TEST 17: A MẤT QUYỀN SAU KHI HỦY
                # =========================================

                response = client.get(
                    "/devices/DEV-001",
                    headers=headers_a,
                )

                assert response.status_code == 403

                response = client.get(
                    "/devices",
                    headers=headers_a,
                )

                assert response.status_code == 200
                assert response.json() == []

                print("[PASS] A mất quyền sau khi hủy liên kết")


                # =========================================
                # TEST 18: B VẪN THEO DÕI DEV-001
                # =========================================

                response = client.get(
                    "/devices/DEV-001",
                    headers=headers_b,
                )

                assert response.status_code == 200

                assert response.json()["display_name"] == (
                    "Thiết bị chung của B"
                )

                response = client.get(
                    "/devices",
                    headers=headers_b,
                )

                assert response.status_code == 200
                assert len(response.json()) == 2

                print("[PASS] Hủy liên kết A không ảnh hưởng B")


                # =========================================
                # TEST 19: HỦY LẠI LIÊN KẾT ĐÃ XÓA
                # =========================================

                response = client.delete(
                    "/devices/DEV-001/link",
                    headers=headers_a,
                )

                assert response.status_code == 403

                print("[PASS] Không thể hủy liên kết không còn quyền")


                # =========================================
                # TEST 20: DEVICE KHÔNG BỊ XÓA
                # =========================================

                with TestSessionLocal() as db:

                    device = db.get(
                        Device,
                        "DEV-001",
                    )

                    assert device is not None

                    # Kiểm tra liên kết của B vẫn tồn tại.
                    remaining_link = db.get(
                        AccountDevice,
                        (
                            account_b_id,
                            "DEV-001",
                        ),
                    )

                    assert remaining_link is not None

                    # Kiểm tra liên kết của A đã bị xóa.
                    deleted_link = db.get(
                        AccountDevice,
                        (
                            account_a_id,
                            "DEV-001",
                        ),
                    )

                    assert deleted_link is None

                print(
                    "[PASS] Device vẫn tồn tại sau khi hủy liên kết"
                )

        print("\nDEVICE LINKING TEST: PASS")

    finally:
        # Khôi phục dependency Database thật.
        app.dependency_overrides.pop(
            get_db,
            None,
        )

        # Giải phóng Database thử nghiệm.
        test_engine.dispose()


if __name__ == "__main__":
    run_tests()
