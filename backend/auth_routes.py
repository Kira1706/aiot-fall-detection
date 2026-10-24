"""Authentication tương thích tài khoản mật khẩu và JWT session_version."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from account_security_service import hash_password, verify_password
from auth_dependencies import get_current_account
from database import get_db
from jwt_utils import JWT_ACCESS_TOKEN_EXPIRE_MINUTES
from models import Account
from security_tokens import create_secure_access_token
from security_middleware import consume_bucket

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    """Nhận dữ liệu tạo tài khoản caregiver bằng email/mật khẩu."""
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    """Nhận thông tin xác thực tài khoản bằng mật khẩu."""
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Tạo tài khoản nhưng không mặc định email đã được xác minh."""
    email = str(payload.email).strip().lower()
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tên hiển thị không hợp lệ.")
    account = Account(email=email, display_name=name, password_hash=hash_password(payload.password))
    db.add(account)
    try:
        db.commit()
        db.refresh(account)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email đã được đăng ký.") from error
    return {"account_id": account.account_id, "email": account.email, "display_name": account.display_name}


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Xác minh mật khẩu và cấp JWT có session_version."""
    email = str(payload.email).strip().lower()
    # Giới hạn theo email đã được HMAC băm, bổ sung lớp giới hạn theo IP.
    # Áp dụng giống nhau cho email tồn tại và không tồn tại.
    allowed, retry = consume_bucket(db, "login_email", email, limit=5)
    if not allowed:
        raise HTTPException(status_code=429, detail="Quá nhiều lần đăng nhập. Hãy thử lại sau.", headers={"Retry-After": str(retry)})
    account = db.scalar(select(Account).where(Account.email == email))
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng.")
    return {
        "access_token": create_secure_access_token(account.account_id, db),
        "token_type": "bearer",
        "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me")
def me(account: Account = Depends(get_current_account)):
    """Trả thông tin an toàn cho tài khoản đã đăng nhập."""
    return {"account_id": account.account_id, "email": account.email, "display_name": account.display_name}
