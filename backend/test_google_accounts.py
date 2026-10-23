"""Kiểm thử logic đăng ký Google trên SQLite riêng; không gọi Google thật."""

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from google_account_service import find_or_create_google_account
from models import Account


def run_tests():
    """Kiểm tra đăng ký, đăng nhập lại và ngăn tự gộp email cũ."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Factory = sessionmaker(bind=engine)
    with Factory() as db:
        info = {
            "sub": "google-user-001", "email": "new.user@gmail.com",
            "email_verified": True, "name": "Người chăm sóc Google",
        }
        user = find_or_create_google_account(db, info)
        assert user.account_id > 0
        assert user.password_hash is None
        assert user.google_sub == "google-user-001"
        print("[PASS] Google lần đầu tạo caregiver không cần mật khẩu")

        again = find_or_create_google_account(db, info)
        assert again.account_id == user.account_id
        print("[PASS] Google đăng nhập lại dùng đúng một Account")

        # Cùng email nhưng sub khác không được chiếm tài khoản.
        try:
            find_or_create_google_account(db, {**info, "sub": "google-other"})
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError("Không được liên kết Google sub khác theo email.")
        print("[PASS] Google sub khác không được chiếm cùng email")

        # Email đã có tài khoản mật khẩu không được tự động liên kết.
        db.add(Account(email="old@gmail.com", password_hash="argon2-test", display_name="A"))
        db.commit()
        try:
            find_or_create_google_account(db, {
                **info, "sub": "google-existing", "email": "old@gmail.com"
            })
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError("Không được tự gộp tài khoản mật khẩu.")
        print("[PASS] Chặn tự động gộp Google vào tài khoản mật khẩu")

        try:
            find_or_create_google_account(db, {**info, "sub": "google-unverified", "email_verified": False})
        except HTTPException as error:
            assert error.status_code == 400
        else:
            raise AssertionError("Email Google chưa xác minh không được đăng ký.")
        print("[PASS] Từ chối email Google chưa xác minh")

        count = len(db.scalars(select(Account)).all())
        assert count == 2
        print("GOOGLE ACCOUNT LOGIC TEST: PASS")
    engine.dispose()


if __name__ == "__main__":
    run_tests()
