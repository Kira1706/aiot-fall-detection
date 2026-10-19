"""Kiểm thử Dashboard Web và các API thật bằng SQLite trong bộ nhớ."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import (
    AccountDevice,
    Device,
    DeviceHeartbeatState,
    FallEvent,
)


# Mọi dữ liệu thử nghiệm đều nằm trong SQLite riêng, không sửa PostgreSQL.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def enable_foreign_keys(dbapi_connection, connection_record):
    """Bật ràng buộc khóa ngoại trên SQLite thử nghiệm."""

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False)


def override_get_db():
    """Cấp Session thử nghiệm cho các endpoint có Depends(get_db)."""

    with TestSessionLocal() as db:
        yield db


def register_and_login(client: TestClient, email: str) -> tuple[int, str]:
    """Đăng ký và đăng nhập qua chính API Authentication đã xây dựng."""

    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "DemoPass@2026!",
            "display_name": "Caregiver thử nghiệm",
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


def run_tests():
    """Kiểm tra giao diện, đăng nhập, quyền và dữ liệu Dashboard."""

    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            # Tập tin giao diện được phục vụ công khai; dữ liệu API vẫn bảo vệ.
            page = client.get("/dashboard")
            assert page.status_code == 200
            assert "text/html" in page.headers["content-type"]
            assert "FallGuard" in page.text
            print("[PASS] Dashboard HTML được phục vụ")

            css = client.get("/dashboard-assets/styles.css")
            js = client.get("/dashboard-assets/app.js")
            assert css.status_code == 200
            assert js.status_code == 200
            assert "text/css" in css.headers["content-type"]
            print("[PASS] CSS và JavaScript tải thành công")

            # Tạo hai caregiver bằng API thật.
            id_a, token_a = register_and_login(client, "dashboard-a@example.com")
            id_b, token_b = register_and_login(client, "dashboard-b@example.com")
            headers_a = {"Authorization": f"Bearer {token_a}"}
            headers_b = {"Authorization": f"Bearer {token_b}"}
            print("[PASS] Đăng ký và đăng nhập hai caregiver")

            # Chuẩn bị hai Device, chỉ A theo dõi DEV-001.
            with TestSessionLocal() as db:
                db.add_all([
                    Device(device_id="DEV-001", status="offline", model_version="model_v1"),
                    Device(device_id="DEV-002", status="offline", model_version=None),
                ])
                db.flush()
                db.add_all([
                    AccountDevice(account_id=id_a, device_id="DEV-001", display_name="Thiết bị của A"),
                    AccountDevice(account_id=id_b, device_id="DEV-002", display_name="Thiết bị của B"),
                    DeviceHeartbeatState(device_id="DEV-001", last_seen_at=datetime.now(timezone.utc)),
                    FallEvent(
                        device_id="DEV-001",
                        edge_event_id=str(uuid4()),
                        event_time=datetime.now(timezone.utc),
                        event_type="fall",
                        model_version="model_v1",
                        confidence=0.95,
                    ),
                ])
                db.commit()

            # Chưa đăng nhập thì dữ liệu của caregiver không được truy cập.
            for path in ("/auth/me", "/devices", "/fall-events", "/devices/DEV-001/status"):
                assert client.get(path).status_code == 401
            print("[PASS] Các API dữ liệu yêu cầu JWT")

            me = client.get("/auth/me", headers=headers_a)
            assert me.status_code == 200
            assert me.json()["account_id"] == id_a
            assert "password_hash" not in me.json()
            print("[PASS] Dashboard lấy đúng thông tin caregiver")

            devices_a = client.get("/devices", headers=headers_a)
            devices_b = client.get("/devices", headers=headers_b)
            assert devices_a.status_code == 200
            assert devices_b.status_code == 200
            assert [x["device_id"] for x in devices_a.json()] == ["DEV-001"]
            assert [x["device_id"] for x in devices_b.json()] == ["DEV-002"]
            print("[PASS] Danh sách Device phân quyền theo caregiver")

            status_a = client.get("/devices/DEV-001/status", headers=headers_a)
            status_b = client.get("/devices/DEV-001/status", headers=headers_b)
            assert status_a.status_code == 200
            assert status_a.json()["status"] == "online"
            assert status_a.json()["last_seen_at"] is not None
            assert status_b.status_code == 403
            print("[PASS] Device Status đúng và chặn truy cập chéo")

            events_a = client.get("/fall-events?limit=11&offset=0", headers=headers_a)
            events_b = client.get("/fall-events?limit=11&offset=0", headers=headers_b)
            assert events_a.status_code == 200
            assert len(events_a.json()) == 1
            assert events_a.json()[0]["device_id"] == "DEV-001"
            assert events_a.json()[0]["edge_event_id"] is not None
            assert events_b.status_code == 200
            assert events_b.json() == []
            print("[PASS] Lịch sử FallEvent chỉ chứa sự kiện được phép")

            detail_events = client.get(
                "/devices/DEV-001/fall-events?limit=11&offset=0", headers=headers_a
            )
            forbidden_events = client.get(
                "/devices/DEV-001/fall-events?limit=11&offset=0", headers=headers_b
            )
            assert detail_events.status_code == 200
            assert len(detail_events.json()) == 1
            assert forbidden_events.status_code == 403
            print("[PASS] Lọc lịch sử theo Device vẫn kiểm tra quyền")

        print("\nDASHBOARD BACKEND INTEGRATION TEST: PASS")

    finally:
        # Không để bài test ảnh hưởng những kiểm thử khác.
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()


if __name__ == "__main__":
    run_tests()
