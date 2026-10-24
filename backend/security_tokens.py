"""Phát hành và xác thực JWT có phiên bản phiên đăng nhập."""

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import BASE_DIR
from jwt_utils import create_access_token, decode_access_token
from models import Account, SecurityRevokedToken

load_dotenv(Path(BASE_DIR) / ".env")


def token_hash(token: str) -> str:
    """Lưu dấu băm thay vì lưu chuỗi JWT nguyên bản."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_secure_access_token(account_id: int, db: Session) -> str:
    """
    Giữ toàn bộ claim chuẩn từ JWT Milestone 3 và thêm session_version.

    Chỉ hỗ trợ HS256 của cấu hình hiện tại; không tự chấp nhận thuật toán khác.
    """
    account = db.get(Account, account_id)
    if account is None:
        raise RuntimeError("Không tìm thấy Account để phát hành JWT.")

    base_token = create_access_token(account_id)
    header = jwt.get_unverified_header(base_token)
    if header.get("alg") != "HS256":
        raise RuntimeError("JWT hiện tại không dùng HS256; cần tích hợp trực tiếp vào jwt_utils.")
    claims = decode_access_token(base_token)
    claims["sv"] = account.session_version
    # JTI giúp nhận diện token trong log điều tra, không dùng làm khóa bí mật.
    import uuid
    claims["jti"] = uuid.uuid4().hex
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY phải có tối thiểu 32 ký tự.")
    return jwt.encode(claims, secret, algorithm="HS256")


def authenticate_secure_token(token: str, db: Session) -> tuple[Account, dict]:
    """Kiểm tra chữ ký/exp trước rồi kiểm tra thu hồi phiên trong PostgreSQL."""
    try:
        claims = decode_access_token(token)
        raw_id = claims.get("sub")
        if not isinstance(raw_id, str) or not raw_id.isdigit():
            raise ValueError("sub không hợp lệ")
        account = db.get(Account, int(raw_id))
        if account is None:
            raise ValueError("Tài khoản không còn tồn tại")
        version = claims.get("sv")
        if type(version) is not int or version != account.session_version:
            raise ValueError("Phiên đã bị thu hồi")
        if db.get(SecurityRevokedToken, token_hash(token)) is not None:
            raise ValueError("Token đã đăng xuất")
        return account, claims
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as error:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã hết hạn hoặc bị thu hồi.") from error


def revoke_single_token(db: Session, account_id: int, token: str, claims: dict) -> None:
    """Chặn lại JWT hiện tại đến khi hết hạn tự nhiên."""
    expiry = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
    digest = token_hash(token)
    if db.get(SecurityRevokedToken, digest) is None:
        db.add(SecurityRevokedToken(token_hash=digest, account_id=account_id, expires_at=expiry))
    db.commit()


def revoke_all_account_tokens(db: Session, account: Account) -> None:
    """Tăng session_version trong cùng transaction với thay đổi bảo mật."""
    account.session_version += 1
    # Hàm gọi quyết định commit để đảm bảo nguyên tử với thay đổi mật khẩu.
