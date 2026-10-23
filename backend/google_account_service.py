"""Lưu tài khoản Google và tránh tự liên kết với tài khoản email cũ."""

from fastapi import HTTPException
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Account


def find_or_create_google_account(db: Session, claims: dict) -> Account:
    """
    Tìm caregiver bằng Google sub, hoặc tạo tài khoản mới.

    Google sub là định danh cố định; email có thể thay đổi.
    Không gộp tài khoản password theo email nếu chưa có bước liên kết rõ ràng.
    """
    sub = claims.get("sub")
    email = claims.get("email")
    verified = claims.get("email_verified") is True

    if (not isinstance(sub, str) or not sub or len(sub) > 255
            or not isinstance(email, str) or not email.strip()
            or len(email.strip()) > 255 or not verified):
        raise HTTPException(
            status_code=400,
            detail="Google không cung cấp danh tính và email đã xác minh.",
        )

    sub = sub.strip()
    email = email.strip().lower()
    if not sub:
        raise HTTPException(status_code=400, detail="Google sub không hợp lệ.")

    linked_account = db.scalar(select(Account).where(Account.google_sub == sub))
    if linked_account is not None:
        # Google chỉ được dùng để xác minh địa chỉ email trùng khớp.
        if linked_account.email.strip().lower() == email and linked_account.email_verified_at is None:
            linked_account.email_verified_at = datetime.now(timezone.utc)
            db.commit()
        return linked_account

    # Tài khoản email/password trước đó phải tự xác thực trước khi liên kết Google.
    # Tuyệt đối không chiếm quyền chỉ vì hai địa chỉ email trùng nhau.
    existing_email = db.scalar(select(Account).where(Account.email == email))
    if existing_email is not None:
        raise HTTPException(
            status_code=409,
            detail="Email đã được đăng ký trước đó. Hãy đăng nhập bằng mật khẩu; "
                   "tính năng liên kết tài khoản Google sẽ được bổ sung riêng.",
        )

    name = claims.get("name")
    if not isinstance(name, str) or not name.strip():
        name = email.split("@", 1)[0]

    new_account = Account(
        email=email,
        google_sub=sub,
        password_hash=None,
        email_verified_at=datetime.now(timezone.utc),
        display_name=name.strip()[:100],
    )
    db.add(new_account)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # Hai request có thể cùng đăng ký lần đầu; truy vấn lại khóa Google.
        existing = db.scalar(select(Account).where(Account.google_sub == sub))
        if existing is not None:
            return existing
        raise HTTPException(
            status_code=409,
            detail="Email đã tồn tại hoặc tài khoản đang được tạo; hãy thử lại.",
        ) from error
    db.refresh(new_account)
    return new_account
