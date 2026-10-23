"""Kiểm thử dịch vụ và API Account Security trên SQLite riêng trong bộ nhớ."""

from datetime import timedelta
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from auth_dependencies import get_current_account
from account_routes import router
import account_routes
from account_security_service import (
    change_password, hash_password, issue_action_token, consume_action_token,
    verify_password, link_google_identity, utc_now,
)
from models import Account, AccountActionToken


def main():
    """Chạy các kịch bản bảo mật tài khoản không sửa Database thật."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with Factory() as db:
        a = Account(email="caregiver-a@example.com", display_name="A", password_hash=hash_password("StrongPass@2026"))
        b = Account(email="caregiver-b@example.com", display_name="B", password_hash=hash_password("StrongPass@2026"))
        c = Account(email="caregiver-c@example.com", display_name="C", password_hash=hash_password("StrongPass@2026"))
        db.add_all([a, b, c]); db.commit()
        aid, bid = a.account_id, b.account_id

        # Tài khoản mật khẩu chưa được xác minh email mặc định.
        assert a.email_verified_at is None
        token = issue_action_token(db, a, "verify_email")
        assert token and len(token) > 30
        assert issue_action_token(db, a, "verify_email") is None
        record = db.scalar(select(AccountActionToken).where(AccountActionToken.account_id == aid))
        assert record.token_hash != token and len(record.token_hash) == 64
        consume_action_token(db, token, "verify_email")
        assert a.email_verified_at is not None
        try:
            consume_action_token(db, token, "verify_email")
        except Exception as e:
            assert getattr(e, "status_code", None) == 400
        else:
            raise AssertionError("Mã đã dùng vẫn được chấp nhận.")
        print("[PASS] Token xác minh băm SHA-256, dùng một lần và có cooldown")

        reset = issue_action_token(db, a, "reset_password")
        consume_action_token(db, reset, "reset_password", "NewStrongPass@2026")
        assert verify_password("NewStrongPass@2026", a.password_hash)
        assert not verify_password("StrongPass@2026", a.password_hash)
        try:
            consume_action_token(db, reset, "reset_password", "AnotherPass@2026")
        except Exception as e:
            assert getattr(e, "status_code", None) == 400
        else:
            raise AssertionError("Mã reset đã dùng vẫn được chấp nhận.")
        print("[PASS] Đổi mật khẩu qua email, không dùng lại mã khôi phục")

        # Giả lập token hết hạn để không cần chờ thực tế.
        expired = issue_action_token(db, b, "reset_password")
        row = db.scalar(select(AccountActionToken).where(AccountActionToken.account_id == bid))
        row.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
        try:
            consume_action_token(db, expired, "reset_password", "AnotherPass@2026")
        except Exception as e:
            assert getattr(e, "status_code", None) == 400
        else:
            raise AssertionError("Mã hết hạn vẫn dùng được.")
        print("[PASS] Mã hết hạn bị từ chối")

        try:
            change_password(db, a, "WrongOldPassword", "DifferentPass@2026")
        except Exception as e:
            assert getattr(e, "status_code", None) == 403
        else:
            raise AssertionError("Đổi mật khẩu không kiểm tra mật khẩu cũ.")
        change_password(db, a, "NewStrongPass@2026", "DifferentPass@2026")
        assert verify_password("DifferentPass@2026", a.password_hash)
        print("[PASS] Đổi mật khẩu phải xác minh mật khẩu cũ")

        claims = {"sub": "google-a-unique", "email": a.email, "email_verified": True}
        link_google_identity(db, a, claims)
        assert a.google_sub == "google-a-unique"
        try:
            link_google_identity(db, b, {**claims, "email": b.email})
        except Exception as e:
            assert getattr(e, "status_code", None) == 409
        else:
            raise AssertionError("Google sub đã dùng bị liên kết thêm.")
        try:
            link_google_identity(db, b, {"sub": "google-b", "email": a.email, "email_verified": True})
        except Exception as e:
            assert getattr(e, "status_code", None) == 409
        else:
            raise AssertionError("Email khác được liên kết.")
        print("[PASS] Không chiếm Google sub hoặc liên kết sai email")

    current = {"id": aid}
    app = FastAPI()
    app.include_router(router)
    sent = []
    original_mail = account_routes.send_action_email
    account_routes.send_action_email = lambda email, raw, purpose: sent.append((email, raw, purpose))

    def fake_db():
        with Factory() as db:
            yield db

    def fake_current(db=Depends(get_db)):
        return db.get(Account, current["id"])

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_account] = fake_current

    try:
        with TestClient(app) as client:
            profile = client.get("/account/me")
            assert profile.status_code == 200, profile.text
            assert profile.json()["email_verified"] is True
            response = client.patch("/account/me", json={"display_name": "Tên mới"})
            assert response.status_code == 200
            assert client.get("/account/me").json()["display_name"] == "Tên mới"
            unknown = client.post("/account/password/forgot", json={"email": "not-exists@example.com"})
            known = client.post("/account/password/forgot", json={"email": "caregiver-c@example.com"})
            assert unknown.status_code == known.status_code == 200
            assert unknown.json() == known.json()
            assert len(sent) == 1 and sent[0][2] == "reset_password"
            print("[PASS] Profile API; quên mật khẩu không tiết lộ email tồn tại")
    finally:
        account_routes.send_action_email = original_mail
        engine.dispose()

    print("ACCOUNT SECURITY TEST: PASS")


if __name__ == "__main__":
    main()
