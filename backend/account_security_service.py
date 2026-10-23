"""Xử lý mã xác minh email, khôi phục mật khẩu và hồ sơ caregiver."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher, exceptions as argon2_errors
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, AccountActionToken

# Độ mạnh Argon2id tuân theo cấu hình bên trong chuỗi hash lưu sẵn.
_hasher = PasswordHasher()

TOKEN_TTL_MINUTES = {"verify_email": 30, "reset_password": 15}
TOKEN_COOLDOWN_SECONDS = 60


def utc_now() -> datetime:
    """Lấy thời gian hiện hành theo UTC."""
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    """Đọc dữ liệu SQLite thử nghiệm theo UTC khi không có timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_token(raw: str) -> str:
    """Băm mã ngẫu nhiên trước khi lưu Database."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Băm mật khẩu mới bằng Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Kiểm tra mật khẩu và xử lý chuỗi hash sai định dạng an toàn."""
    if not stored_hash:
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except (argon2_errors.VerifyMismatchError, argon2_errors.VerificationError, argon2_errors.InvalidHashError):
        return False


def validate_password(value: str) -> None:
    """Áp dụng yêu cầu mật khẩu cho form và API."""
    if len(value) < 10 or len(value) > 128:
        raise HTTPException(status_code=422, detail="Mật khẩu mới phải có từ 10 đến 128 ký tự.")


def issue_action_token(db: Session, account: Account, purpose: str) -> str | None:
    """
    Sinh mã dùng một lần, hạn chế gửi lại tối đa một lần mỗi phút.

    Trả mã thô chỉ cho hệ thống gửi email, không trả về người gọi API.
    """
    if purpose not in TOKEN_TTL_MINUTES:
        raise ValueError("Mục đích token không hợp lệ.")
    now = utc_now()
    # Khóa tài khoản khi cấp token để tránh hai worker cùng vượt giới hạn.
    db.scalar(select(Account.account_id).where(Account.account_id == account.account_id).with_for_update())
    newest = db.scalar(
        select(AccountActionToken)
        .where(AccountActionToken.account_id == account.account_id, AccountActionToken.purpose == purpose)
        .order_by(AccountActionToken.created_at.desc())
        .limit(1)
    )
    if newest is not None and (now - aware(newest.created_at)).total_seconds() < TOKEN_COOLDOWN_SECONDS:
        return None

    raw = secrets.token_urlsafe(32)
    # Các mã còn hiệu lực cùng mục đích của tài khoản được thu hồi.
    old_tokens = db.scalars(
        select(AccountActionToken).where(
            AccountActionToken.account_id == account.account_id,
            AccountActionToken.purpose == purpose,
            AccountActionToken.consumed_at.is_(None),
        )
    ).all()
    for item in old_tokens:
        item.consumed_at = now
    db.add(AccountActionToken(
        account_id=account.account_id,
        purpose=purpose,
        token_hash=hash_token(raw),
        created_at=now,
        expires_at=now + timedelta(minutes=TOKEN_TTL_MINUTES[purpose]),
    ))
    db.commit()
    return raw


def consume_action_token(db: Session, raw: str, purpose: str, new_password: str | None = None) -> Account:
    """Kiểm tra hạn, dùng một lần và cập nhật Account trong một giao dịch."""
    if not isinstance(raw, str) or not (20 <= len(raw) <= 256) or purpose not in TOKEN_TTL_MINUTES:
        raise HTTPException(status_code=400, detail="Mã không hợp lệ hoặc đã hết hạn.")
    if purpose == "reset_password":
        if new_password is None:
            raise HTTPException(status_code=422, detail="Thiếu mật khẩu mới.")
        validate_password(new_password)

    # FOR UPDATE bảo vệ thao tác dùng một lần khi có nhiều worker PostgreSQL.
    record = db.scalar(
        select(AccountActionToken)
        .where(AccountActionToken.token_hash == hash_token(raw), AccountActionToken.purpose == purpose)
        .with_for_update()
    )
    now = utc_now()
    if record is None or record.consumed_at is not None or aware(record.expires_at) <= now:
        raise HTTPException(status_code=400, detail="Mã không hợp lệ hoặc đã hết hạn.")
    account = db.get(Account, record.account_id)
    if account is None:
        raise HTTPException(status_code=400, detail="Tài khoản không còn tồn tại.")
    if purpose == "verify_email":
        account.email_verified_at = now
    elif purpose == "reset_password":
        account.password_hash = hash_password(new_password)
    record.consumed_at = now
    # Thu hồi các mã còn lại của cùng mục đích.
    for item in db.scalars(
        select(AccountActionToken).where(
            AccountActionToken.account_id == account.account_id,
            AccountActionToken.purpose == purpose,
            AccountActionToken.consumed_at.is_(None),
        )
    ):
        item.consumed_at = now
    db.commit()
    db.refresh(account)
    return account


def change_password(db: Session, account: Account, old_password: str, new_password: str) -> None:
    """Đổi mật khẩu chỉ sau khi xác minh mật khẩu hiện tại."""
    validate_password(new_password)
    if not verify_password(old_password, account.password_hash):
        raise HTTPException(status_code=403, detail="Mật khẩu hiện tại không đúng hoặc tài khoản chưa có mật khẩu.")
    if old_password == new_password:
        raise HTTPException(status_code=422, detail="Mật khẩu mới phải khác mật khẩu cũ.")
    account.password_hash = hash_password(new_password)
    db.commit()


def link_google_identity(db: Session, account: Account, claims: dict) -> Account:
    """Liên kết Google vào tài khoản đã được xác thực bằng mật khẩu trước đó."""
    sub = claims.get("sub")
    email = claims.get("email")
    if not isinstance(sub, str) or not sub.strip() or len(sub) > 255 or claims.get("email_verified") is not True:
        raise HTTPException(status_code=400, detail="Google chưa xác minh danh tính hoặc email.")
    if not isinstance(email, str) or email.strip().lower() != account.email.strip().lower():
        raise HTTPException(status_code=409, detail="Email Google phải trùng email tài khoản hiện tại.")
    existing = db.scalar(select(Account).where(Account.google_sub == sub))
    if existing is not None and existing.account_id != account.account_id:
        raise HTTPException(status_code=409, detail="Google Account đã liên kết với người dùng khác.")
    if account.google_sub is not None and account.google_sub != sub:
        raise HTTPException(status_code=409, detail="Tài khoản hiện tại đã liên kết Google khác.")
    account.google_sub = sub
    account.email_verified_at = utc_now()
    db.commit()
    return account
