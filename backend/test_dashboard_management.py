"""Integration test Dashboard Management v10.8 trên SQLite độc lập.

Bài test chỉ thay dependency xác thực bằng tài khoản mẫu; kiểm tra JWT thật
vẫn do các regression test Authentication của milestone trước đảm nhiệm.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth_dependencies import get_current_account
from database import Base, get_db
from management_routes import router as management_router
from models import (
    Account, AccountDevice, AlertNotification, Device, DeviceHeartbeatState,
    DeviceOwnership, DeviceShareInvitation, FallEvent,
)
from pairing_service import accept_invitation, token_hash


engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def enable_fk(connection, record):
    """Kích hoạt kiểm tra khóa ngoại trên SQLite thử nghiệm."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(bind=engine, autoflush=False)
app = FastAPI()
app.include_router(management_router)


def test_db():
    """Thay PostgreSQL thật bằng SQLite bộ nhớ trong phạm vi test."""
    with TestSession() as db:
        yield db


def test_account(
    account_id: int | None = Header(default=None, alias="X-Test-Account"),
    db=Depends(get_db),
):
    """Mô phỏng người đã xác thực để tập trung kiểm tra quyền dữ liệu."""
    if account_id is None:
        raise HTTPException(status_code=401, detail="Yêu cầu xác thực")
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=401, detail="Tài khoản không hợp lệ")
    return account


app.dependency_overrides[get_db] = test_db
app.dependency_overrides[get_current_account] = test_account


def headers(account_id: int) -> dict:
    """Chọn caregiver thử nghiệm độc lập."""
    return {"X-Test-Account": str(account_id)}


def seed():
    """Chuẩn bị hai caregiver, hai Device và các bản ghi phân quyền."""
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with TestSession() as db:
        a = Account(email="alice@example.com", password_hash="hash", display_name="Alice", email_verified_at=now)
        b = Account(email="bob@example.com", password_hash="hash", display_name="Bob", email_verified_at=now)
        db.add_all([a, b]); db.flush()
        db.add_all([
            Device(device_id="DEV-A", status="offline", model_version="test"),
            Device(device_id="DEV-B", status="offline", model_version="test"),
        ]); db.flush()
        db.add_all([
            AccountDevice(account_id=a.account_id, device_id="DEV-A", display_name="Giường của mẹ"),
            AccountDevice(account_id=a.account_id, device_id="DEV-B", display_name="Thiết bị phụ"),
            AccountDevice(account_id=b.account_id, device_id="DEV-B", display_name="Thiết bị của Bob"),
            DeviceOwnership(device_id="DEV-A", account_id=a.account_id, created_at=now),
            DeviceOwnership(device_id="DEV-B", account_id=b.account_id, created_at=now),
            DeviceHeartbeatState(device_id="DEV-A", last_seen_at=now),
        ]); db.flush()
        events = [
            FallEvent(device_id="DEV-A", event_time=now-timedelta(hours=1), event_type="fall", model_version="test", confidence=.9),
            FallEvent(device_id="DEV-A", event_time=now-timedelta(hours=2), event_type="fall", model_version="test", confidence=.55),
            FallEvent(device_id="DEV-B", event_time=now-timedelta(hours=3), event_type="fall", model_version="test", confidence=None),
        ]
        db.add_all(events); db.flush()
        db.add_all([
            AlertNotification(account_id=a.account_id, fall_event_id=events[0].event_id, created_at=now-timedelta(hours=1), read_at=None),
            AlertNotification(account_id=a.account_id, fall_event_id=events[1].event_id, created_at=now-timedelta(hours=2), read_at=now),
            AlertNotification(account_id=a.account_id, fall_event_id=events[2].event_id, created_at=now-timedelta(hours=3), read_at=None),
            # Cố tình lưu thông báo cũ của B cho DEV-A dù B không còn liên kết.
            AlertNotification(account_id=b.account_id, fall_event_id=events[0].event_id, created_at=now, read_at=None),
        ])
        invite = DeviceShareInvitation(
            device_id="DEV-A", invited_account_id=b.account_id, invited_by_account_id=a.account_id,
            token_hash=token_hash("a"*43), created_at=now,
            expires_at=now+timedelta(hours=12), accepted_at=None, revoked_at=None,
        )
        db.add(invite); db.commit()
        return a.account_id, b.account_id, invite.invitation_id, now


def run_tests():
    """Chạy bộ tình huống quản lý nâng cao và kiểm tra không vượt quyền."""
    a_id, b_id, invite_id, now = seed()
    try:
        with TestClient(app) as client:
            assert client.get("/management/summary").status_code == 401
            assert client.get("/management/alerts").status_code == 401
            print("[PASS] API quản lý đều yêu cầu xác thực")

            result = client.get("/management/summary", headers=headers(a_id))
            assert result.status_code == 200, result.text
            data = result.json()
            assert data["devices_total"] == 2 and data["devices_online"] == 1
            assert data["falls_last_30_days"] == 3
            assert data["unread_alerts"] == 2 and data["pending_invitations"] == 1
            result_b = client.get("/management/summary", headers=headers(b_id)).json()
            assert result_b["devices_total"] == 1
            assert result_b["falls_last_30_days"] == 1
            assert result_b["unread_alerts"] == 0
            print("[PASS] Thống kê tách riêng theo caregiver và quyền hiện tại")

            page = client.get("/management/fall-events?limit=1", headers=headers(a_id)).json()
            assert page["total"] == 3 and page["has_next"] and len(page["items"]) == 1
            second = client.get("/management/fall-events?limit=1&offset=1", headers=headers(a_id)).json()
            assert second["items"][0]["event_id"] != page["items"][0]["event_id"]
            print("[PASS] Phân trang Server có tổng số và thứ tự ổn định")

            only_a = client.get("/management/fall-events?device_id=DEV-A", headers=headers(a_id)).json()
            assert only_a["total"] == 2
            assert client.get("/management/fall-events?device_id=DEV-A", headers=headers(b_id)).status_code == 403
            assert client.get("/management/alerts?device_id=DEV-A", headers=headers(b_id)).status_code == 403
            restricted = client.get("/management/fall-events", headers=headers(b_id)).json()
            assert restricted["total"] == 1 and restricted["items"][0]["device_id"] == "DEV-B"
            print("[PASS] Lọc Device không thể truy cập chéo")

            search = client.get("/management/fall-events?q=Giường", headers=headers(a_id)).json()
            assert search["total"] == 2
            high = client.get("/management/fall-events?min_confidence=0.8", headers=headers(a_id)).json()
            assert high["total"] == 1 and high["items"][0]["confidence"] == .9
            print("[PASS] Lọc tên thiết bị và độ tin cậy tại Server")

            from_value = (now-timedelta(hours=1,minutes=30)).isoformat()
            date_filtered = client.get("/management/fall-events", params={"from_at": from_value}, headers=headers(a_id)).json()
            assert date_filtered["total"] == 1
            assert client.get("/management/fall-events?from_at=2026-10-23T12:00:00", headers=headers(a_id)).status_code == 422
            assert client.get("/management/alerts?read_state=bad", headers=headers(a_id)).status_code == 422
            assert client.get("/management/fall-events?limit=101", headers=headers(a_id)).status_code == 422
            print("[PASS] Bộ lọc ngày và validation giới hạn hoạt động")

            alerts = client.get("/management/alerts?read_state=all", headers=headers(a_id)).json()
            assert alerts["total"] == 3
            read = client.get("/management/alerts?read_state=read", headers=headers(a_id)).json()
            assert read["total"] == 1
            unread = client.get("/management/alerts?read_state=unread", headers=headers(a_id)).json()
            assert unread["total"] == 2
            b_alerts = client.get("/management/alerts", headers=headers(b_id)).json()
            assert b_alerts["total"] == 0
            print("[PASS] Lịch sử đã xem/chưa xem không lộ cảnh báo mất quyền")

            list_b = client.get("/management/devices/DEV-A/invitations", headers=headers(b_id))
            assert list_b.status_code == 403
            invitations = client.get("/management/devices/DEV-A/invitations", headers=headers(a_id))
            assert invitations.status_code == 200 and len(invitations.json()) == 1
            assert "token_hash" not in invitations.text and "invitation_token" not in invitations.text
            assert client.delete(f"/management/devices/DEV-A/invitations/{invite_id}", headers=headers(b_id)).status_code == 403
            print("[PASS] Chỉ owner được xem và thu hồi lời mời, không lộ token")

            assert client.delete(f"/management/devices/DEV-A/invitations/{invite_id}", headers=headers(a_id)).status_code == 204
            assert client.delete(f"/management/devices/DEV-A/invitations/{invite_id}", headers=headers(a_id)).status_code == 409
            assert client.get("/management/devices/DEV-A/invitations", headers=headers(a_id)).json() == []
            with TestSession() as db:
                assert db.get(DeviceShareInvitation, invite_id).revoked_at is not None
                assert db.scalar(select(func.count(FallEvent.event_id))) == 3
                target = db.get(Account, b_id)
                try:
                    accept_invitation(db, target, "a"*43)
                except HTTPException as error:
                    assert error.status_code == 400
                else:
                    raise AssertionError("Không được chấp nhận mã đã thu hồi")
            print("[PASS] Thu hồi mã mời chặn sử dụng lại và không xóa FallEvent")
    finally:
        engine.dispose()
    print("DASHBOARD MANAGEMENT TEST: PASS")


if __name__ == "__main__":
    run_tests()
