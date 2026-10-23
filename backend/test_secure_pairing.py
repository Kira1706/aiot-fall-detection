"""Integration test ghép nối/chia sẻ độc lập, không thay đổi PostgreSQL thật."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth_dependencies import get_current_account
from database import Base, get_db
from models import (
    Account, AccountDevice, Device, DeviceOwnership,
    DevicePairingToken, DeviceShareInvitation, FallEvent,
)
from pairing_routes import router
from device_routes import router as device_router
from device_permissions import get_authorized_device


def main():
    """Kiểm thử 17 kịch bản bảo mật bằng SQLite trong bộ nhớ."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_fk(dbapi_connection, connection_record):
        """Bật Foreign Key để thử nghiệm sát với PostgreSQL."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with factory() as db:
        accounts = [
            Account(email="a@example.com", display_name="A", password_hash="hash", email_verified_at=now),
            Account(email="b@example.com", display_name="B", password_hash="hash", email_verified_at=now),
            Account(email="c@example.com", display_name="C", password_hash="hash", email_verified_at=now),
            Account(email="d@example.com", display_name="D", password_hash="hash", email_verified_at=None),
        ]
        db.add_all(accounts)
        db.add_all([
            Device(device_id="DEV-NEW", status="offline", model_version=None),
            Device(device_id="DEV-OLD", status="offline", model_version=None),
            Device(device_id="DEV-EMPTY", status="offline", model_version=None),
        ])
        db.flush()
        ids = [a.account_id for a in accounts]
        db.add(AccountDevice(account_id=ids[0], device_id="DEV-OLD", display_name="Thiết bị cũ"))
        db.add(FallEvent(
            device_id="DEV-NEW", event_time=now, event_type="fall",
            model_version="test-model", confidence=0.9, edge_event_id=None,
        ))
        db.commit()

    current = {"id": ids[0]}
    app = FastAPI()
    app.include_router(router)
    app.include_router(device_router)

    def test_db():
        """Cấp phát session SQLite của bài test."""
        with factory() as db:
            yield db

    def test_current(db=Depends(get_db)):
        """Giả lập JWT hợp lệ của tài khoản đang chọn."""
        return db.get(Account, current["id"])

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_account] = test_current

    def test_authorized_device(
        device_id: str,
        db=Depends(get_db),
        account=Depends(get_current_account),
    ):
        """Giả lập quyền xem Device đúng như dependency hiện tại."""
        from fastapi import HTTPException
        device = db.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=404)
        link = db.get(AccountDevice, (account.account_id, device_id))
        if link is None:
            raise HTTPException(status_code=403)
        return device, link

    app.dependency_overrides[get_authorized_device] = test_authorized_device
    secret = "demo-key-only-for-test-" + "S" * 35

    try:
        with patch.dict(os.environ, {"PAIRING_ADMIN_KEY": secret}):
            with TestClient(app) as client:
                endpoint = "/pairing-admin/devices/DEV-NEW/issue"
                assert client.post(endpoint).status_code == 401
                assert client.post(endpoint, headers={"X-Pairing-Admin-Key": "wrong"}).status_code == 401
                issued = client.post(endpoint, headers={"X-Pairing-Admin-Key": secret})
                assert issued.status_code == 200, issued.text
                token = issued.json()["pairing_token"]
                assert len(token) >= 40
                with factory() as db:
                    assert db.get(DevicePairingToken, "DEV-NEW").token_hash != token
                print("[PASS] Chỉ admin hợp lệ cấp mã; Database không lưu mã gốc")

                current["id"] = ids[3]
                assert client.post("/pairing/claim", json={"token": token}).status_code == 403
                current["id"] = ids[0]
                first_claim = client.post("/pairing/claim", json={"token": token})
                assert first_claim.status_code == 200 and first_claim.json()["role"] == "owner", first_claim.text
                assert client.post("/pairing/claim", json={"token": token}).status_code == 400
                assert client.post(endpoint, headers={"X-Pairing-Admin-Key": secret}).status_code == 409
                print("[PASS] Email chưa xác minh bị chặn, mã dùng một lần, không đổi chủ")

                with factory() as db:
                    owner = db.get(DeviceOwnership, "DEV-NEW")
                    assert owner.account_id == ids[0]
                    assert db.get(AccountDevice, (ids[0], "DEV-NEW")) is not None
                assert client.delete("/devices/DEV-NEW/link").status_code == 409
                assert client.post("/devices/link", json={"device_id": "DEV-EMPTY"}).status_code == 410
                print("[PASS] Không được xóa owner hoặc dùng API liên kết chỉ bằng Device ID")
                print("[PASS] Cấp owner và AccountDevice trong cùng thao tác")

                assert client.get("/devices/DEV-NEW/pairing-role").json()["role"] == "owner"
                current["id"] = ids[1]
                assert client.get("/devices/DEV-NEW/pairing-role").status_code == 403
                assert client.get("/devices/DEV-NEW/shares").status_code == 403
                assert client.post("/devices/DEV-NEW/shares/invitations", json={"invitee_email": "c@example.com"}).status_code == 403
                print("[PASS] Caregiver chưa được chia sẻ không thể xem/quản lý quyền")

                current["id"] = ids[0]
                legacy = client.post(
                    "/pairing-admin/devices/DEV-OLD/issue",
                    headers={"X-Pairing-Admin-Key": secret},
                )
                assert legacy.status_code == 409
                assert client.get("/devices/DEV-OLD/pairing-role").json()["role"] == "legacy"
                print("[PASS] Thiết bị cũ không bị gán chủ sở hữu tự động")

                invitation = client.post(
                    "/devices/DEV-NEW/shares/invitations",
                    json={"invitee_email": "b@example.com"},
                )
                assert invitation.status_code == 201, invitation.text
                invite_token = invitation.json()["invitation_token"]
                with factory() as db:
                    saved = db.scalar(select(DeviceShareInvitation).where(
                        DeviceShareInvitation.device_id == "DEV-NEW"
                    ))
                    assert saved.token_hash != invite_token
                print("[PASS] Mã mời được băm và chỉ dành cho tài khoản mục tiêu")

                current["id"] = ids[2]
                assert client.post("/shares/accept", json={"token": invite_token}).status_code == 403
                current["id"] = ids[3]
                assert client.post("/shares/accept", json={"token": invite_token}).status_code == 403
                current["id"] = ids[1]
                accepted = client.post("/shares/accept", json={"token": invite_token})
                assert accepted.status_code == 200 and accepted.json()["role"] == "viewer", accepted.text
                assert client.post("/shares/accept", json={"token": invite_token}).status_code == 400
                assert client.get("/devices/DEV-NEW/pairing-role").json()["role"] == "viewer"
                assert client.get("/devices/DEV-NEW/shares").status_code == 403
                print("[PASS] Chỉ đúng caregiver chấp nhận, không dùng lại mã, không cấp quyền quản trị")

                current["id"] = ids[0]
                share_list = client.get("/devices/DEV-NEW/shares")
                assert share_list.status_code == 200 and len(share_list.json()) == 2
                assert client.post("/devices/DEV-NEW/shares/invitations", json={"invitee_email": "b@example.com"}).status_code == 409
                assert client.delete(f"/devices/DEV-NEW/shares/{ids[0]}").status_code == 409
                print("[PASS] Không mời người đã có quyền và không thu hồi chủ sở hữu")

                fresh_invitation = client.post(
                    "/devices/DEV-NEW/shares/invitations", json={"invitee_email": "c@example.com"}
                )
                assert fresh_invitation.status_code == 201
                expired_token = fresh_invitation.json()["invitation_token"]
                with factory() as db:
                    row = db.scalar(select(DeviceShareInvitation).where(
                        DeviceShareInvitation.invited_account_id == ids[2]
                    ))
                    row.expires_at = now - timedelta(minutes=1)
                    db.commit()
                current["id"] = ids[2]
                assert client.post("/shares/accept", json={"token": expired_token}).status_code == 400
                print("[PASS] Lời mời hết hạn bị từ chối")

                current["id"] = ids[0]
                assert client.delete(f"/devices/DEV-NEW/shares/{ids[1]}").status_code == 204
                with factory() as db:
                    assert db.get(AccountDevice, (ids[1], "DEV-NEW")) is None
                    assert db.get(DeviceOwnership, "DEV-NEW").account_id == ids[0]
                    assert db.scalar(select(func.count(FallEvent.event_id))) == 1
                current["id"] = ids[1]
                assert client.get("/devices/DEV-NEW/pairing-role").status_code == 403
                print("[PASS] Thu hồi viewer không xóa FallEvent hoặc thay chủ")

                current["id"] = ids[0]
                with factory() as db:
                    issued_old = db.get(DevicePairingToken, "DEV-EMPTY")
                assert issued_old is None
                new_token_resp = client.post(
                    "/pairing-admin/devices/DEV-EMPTY/issue", headers={"X-Pairing-Admin-Key": secret}
                )
                old_token = new_token_resp.json()["pairing_token"]
                replacement = client.post(
                    "/pairing-admin/devices/DEV-EMPTY/issue", headers={"X-Pairing-Admin-Key": secret}
                )
                assert replacement.status_code == 200
                assert client.post("/pairing/claim", json={"token": old_token}).status_code == 400
                with factory() as db:
                    row = db.get(DevicePairingToken, "DEV-EMPTY")
                    row.expires_at = now - timedelta(minutes=1)
                    db.commit()
                current["id"] = ids[2]
                assert client.post("/pairing/claim", json={"token": replacement.json()["pairing_token"]}).status_code == 400
                print("[PASS] Mã ghép nối bị thay thế/hết hạn không cấp quyền")
        print("SECURE PAIRING TEST: PASS")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
