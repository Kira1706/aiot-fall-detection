
"""Kiểm thử API thiết bị và quyền truy cập giữa các caregiver."""

from fastapi.testclient import TestClient

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import AccountDevice, Device


# =========================================================
# 1. TẠO DATABASE SQLITE RIÊNG CHO KIỂM THỬ
# =========================================================

# Dùng SQLite trong bộ nhớ, không đụng đến aiot.db.
test_engine = create_engine(
    "sqlite://",
    connect_args={
        "check_same_thread": False
    },
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def enable_test_foreign_keys(
    dbapi_connection,
    connection_record,
):
    """
    Bật Foreign Key cho Database SQLite thử nghiệm.

    SQLite cần bật chế độ này trên từng kết nối.
    """

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Tạo Session Factory dành riêng cho Database thử nghiệm.
TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
)


def override_get_db():
    """
    Cung cấp Session thử nghiệm thay cho Session thật.

    FastAPI sẽ sử dụng hàm này khi chạy TestClient.
    """

    db = TestSessionLocal()

    try:
        yield db

    finally:
        db.close()


def register_test_account(
    client: TestClient,
    email: str,
    display_name: str,
) -> int:
    """
    Đăng ký một caregiver bằng Register API thật.

    Trả về Account ID do Database thử nghiệm tạo.
    """

    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "DemoPass@2026!",
            "display_name": display_name,
        },
    )

    assert response.status_code == 201, response.text

    return response.json()["account_id"]


def login_test_account(
    client: TestClient,
    email: str,
) -> str:
    """
    Đăng nhập bằng Login API thật và lấy JWT.

    JWT chỉ được sử dụng nội bộ trong bài kiểm thử.
    """

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
    """Tạo Authorization header từ JWT hợp lệ."""

    return {
        "Authorization": f"Bearer {token}"
    }


# =========================================================
# 2. TẠO DỮ LIỆU THỬ NGHIỆM
# =========================================================

def seed_test_devices(
    account_a_id: int,
    account_b_id: int,
):
    """
    Tạo hai Device và liên kết riêng cho hai caregiver.

    Caregiver A theo dõi DEV-001.
    Caregiver B theo dõi DEV-002.
    """

    with TestSessionLocal() as db:

        # Tạo hai thiết bị thử nghiệm.
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

        # Mỗi caregiver chỉ được theo dõi một Device.
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
# 3. CHẠY CÁC BÀI KIỂM THỬ
# =========================================================

def run_tests():
    """Kiểm tra xác thực và phân quyền Device API."""

    # Tạo toàn bộ năm bảng trong Database thử nghiệm.
    Base.metadata.create_all(bind=test_engine)

    # Thay dependency Database thật bằng Database thử nghiệm.
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:

            # Đăng ký hai caregiver bằng API thật.
            account_a_id = register_test_account(
                client,
                email="caregiver.a@example.com",
                display_name="Caregiver A",
            )

            account_b_id = register_test_account(
                client,
                email="caregiver.b@example.com",
                display_name="Caregiver B",
            )

            # Hai caregiver đăng nhập và nhận JWT riêng.
            token_a = login_test_account(
                client,
                "caregiver.a@example.com",
            )

            token_b = login_test_account(
                client,
                "caregiver.b@example.com",
            )

            headers_a = bearer_headers(token_a)
            headers_b = bearer_headers(token_b)

            print("[PASS] Hai caregiver đăng ký và đăng nhập")


            # Tạo hai Device và liên kết riêng.
            seed_test_devices(
                account_a_id,
                account_b_id,
            )


            # =============================================
            # TEST 1: CAREGIVER A XEM DANH SÁCH DEVICE
            # =============================================

            response = client.get(
                "/devices",
                headers=headers_a,
            )

            assert response.status_code == 200

            devices_a = response.json()

            assert len(devices_a) == 1

            assert devices_a[0]["device_id"] == "DEV-001"

            assert devices_a[0]["display_name"] == (
                "Thiết bị của A"
            )

            print(
                "[PASS] Caregiver A chỉ thấy DEV-001"
            )


            # =============================================
            # TEST 2: CAREGIVER B XEM DANH SÁCH DEVICE
            # =============================================

            response = client.get(
                "/devices",
                headers=headers_b,
            )

            assert response.status_code == 200

            devices_b = response.json()

            assert len(devices_b) == 1

            assert devices_b[0]["device_id"] == "DEV-002"

            print(
                "[PASS] Caregiver B chỉ thấy DEV-002"
            )


            # =============================================
            # TEST 3: A XEM DEVICE CÓ QUYỀN
            # =============================================

            response = client.get(
                "/devices/DEV-001",
                headers=headers_a,
            )

            assert response.status_code == 200

            assert response.json()["device_id"] == "DEV-001"

            assert response.json()["display_name"] == (
                "Thiết bị của A"
            )

            print(
                "[PASS] A truy cập DEV-001 thành công"
            )


            # =============================================
            # TEST 4: A KHÔNG ĐƯỢC XEM DEV-002
            # =============================================

            response = client.get(
                "/devices/DEV-002",
                headers=headers_a,
            )

            assert response.status_code == 403

            print(
                "[PASS] A truy cập DEV-002 bị chặn HTTP 403"
            )


            # =============================================
            # TEST 5: B KHÔNG ĐƯỢC XEM DEV-001
            # =============================================

            response = client.get(
                "/devices/DEV-001",
                headers=headers_b,
            )

            assert response.status_code == 403

            print(
                "[PASS] B truy cập DEV-001 bị chặn HTTP 403"
            )


            # =============================================
            # TEST 6: THIẾU JWT
            # =============================================

            response = client.get("/devices")

            assert response.status_code == 401

            response = client.get(
                "/devices/DEV-001"
            )

            assert response.status_code == 401

            print(
                "[PASS] Thiếu JWT bị chặn HTTP 401"
            )


            # =============================================
            # TEST 7: TOKEN KHÔNG HỢP LỆ
            # =============================================

            response = client.get(
                "/devices",
                headers=bearer_headers(
                    "invalid.jwt.token"
                ),
            )

            assert response.status_code == 401

            print(
                "[PASS] JWT không hợp lệ bị chặn HTTP 401"
            )


            # =============================================
            # TEST 8: DEVICE KHÔNG TỒN TẠI
            # =============================================

            response = client.get(
                "/devices/DEV-999",
                headers=headers_a,
            )

            assert response.status_code == 404

            print(
                "[PASS] Device không tồn tại trả HTTP 404"
            )


            # =============================================
            # TEST 9: HAI CAREGIVER CÙNG THEO DÕI MỘT DEVICE
            # =============================================

            # Bổ sung quyền theo dõi DEV-001 cho caregiver B.
            # Tên hiển thị của B khác tên hiển thị của A.
            with TestSessionLocal() as db:

                db.add(
                    AccountDevice(
                        account_id=account_b_id,
                        device_id="DEV-001",
                        display_name="Thiết bị chung của B",
                    )
                )

                db.commit()

            # Bây giờ caregiver B được phép xem DEV-001.
            response = client.get(
                "/devices/DEV-001",
                headers=headers_b,
            )

            assert response.status_code == 200

            assert response.json()["display_name"] == (
                "Thiết bị chung của B"
            )

            # Caregiver A vẫn nhìn thấy tên riêng của mình.
            response = client.get(
                "/devices/DEV-001",
                headers=headers_a,
            )

            assert response.status_code == 200

            assert response.json()["display_name"] == (
                "Thiết bị của A"
            )

            # B hiện theo dõi được cả hai thiết bị.
            response = client.get(
                "/devices",
                headers=headers_b,
            )

            assert response.status_code == 200
            assert len(response.json()) == 2

            print(
                "[PASS] Hai caregiver dùng tên riêng "
                "cho cùng một Device"
            )


            # =============================================
            # TEST 10: KIỂM TRA CẤU TRÚC RESPONSE
            # =============================================

            response = client.get(
                "/devices/DEV-001",
                headers=headers_a,
            )

            assert response.status_code == 200

            expected_fields = {
                "device_id",
                "display_name",
                "status",
                "model_version",
            }

            assert set(response.json().keys()) == (
                expected_fields
            )

            print(
                "[PASS] Response không lộ thông tin Account"
            )

        print("\nDEVICE AUTHORIZATION TEST: PASS")

    finally:
        # Khôi phục Dependency của ứng dụng.
        # Không để TestClient ảnh hưởng các bài test khác.
        app.dependency_overrides.pop(get_db, None)

        # Giải phóng Database SQLite trong bộ nhớ.
        test_engine.dispose()


if __name__ == "__main__":
    run_tests()
