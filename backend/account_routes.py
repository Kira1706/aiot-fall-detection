"""API xác minh email, quên mật khẩu, hồ sơ và đổi mật khẩu."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from models import Account
from account_mailer import send_action_email
from account_security_service import (
    change_password, consume_action_token, issue_action_token,
)

router = APIRouter(prefix="/account", tags=["Account Security"])
GENERIC_MESSAGE = "Nếu yêu cầu hợp lệ, hướng dẫn sẽ được gửi tới email tương ứng."


class StrictBody(BaseModel):
    """Không nhận thêm trường ngoài hợp đồng API."""
    model_config = ConfigDict(extra="forbid")


class EmailRequest(StrictBody):
    """Địa chỉ nhận email khôi phục."""
    email: EmailStr


class TokenRequest(StrictBody):
    """Mã từ đường dẫn email."""
    token: str = Field(min_length=20, max_length=256)


class PasswordResetRequest(TokenRequest):
    """Mã khôi phục và mật khẩu mới."""
    new_password: str = Field(min_length=10, max_length=128)


class PasswordChangeRequest(StrictBody):
    """Thông tin để tự đổi mật khẩu."""
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class ProfileUpdateRequest(StrictBody):
    """Tên hiển thị mới, không tự đổi email định danh."""
    display_name: str = Field(min_length=1, max_length=100)


@router.get("/me")
def get_profile(account: Account = Depends(get_current_account)):
    """Đọc hồ sơ của chính caregiver hiện tại."""
    return {
        "account_id": account.account_id,
        "email": account.email,
        "display_name": account.display_name,
        "email_verified": account.email_verified_at is not None,
        "has_password": bool(account.password_hash),
        "google_linked": bool(account.google_sub),
    }


@router.patch("/me")
def edit_profile(payload: ProfileUpdateRequest, account: Account = Depends(get_current_account), db: Session = Depends(get_db)):
    """Cập nhật tên hiển thị của tài khoản đăng nhập."""
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tên hiển thị không được để trống.")
    account.display_name = name
    db.commit()
    return {"display_name": name}


@router.post("/verification/request")
def request_verification(background: BackgroundTasks, account: Account = Depends(get_current_account), db: Session = Depends(get_db)):
    """Gửi đường dẫn xác minh tới email tài khoản đang đăng nhập."""
    if account.email_verified_at is None:
        raw = issue_action_token(db, account, "verify_email")
        if raw:
            background.add_task(send_action_email, account.email, raw, "verify_email")
    return {"message": GENERIC_MESSAGE}


@router.post("/verification/confirm")
def confirm_verification(payload: TokenRequest, db: Session = Depends(get_db)):
    """Xác minh email với token một lần."""
    consume_action_token(db, payload.token, "verify_email")
    return {"message": "Email đã được xác minh thành công."}


@router.post("/password/forgot")
def forgot_password(payload: EmailRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Trả phản hồi đồng nhất dù email tồn tại hay không."""
    email = str(payload.email).strip().lower()
    account = db.scalar(select(Account).where(Account.email == email))
    if account is not None:
        raw = issue_action_token(db, account, "reset_password")
        if raw:
            background.add_task(send_action_email, account.email, raw, "reset_password")
    return {"message": GENERIC_MESSAGE}


@router.post("/password/reset")
def reset_password(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    """Đặt lại mật khẩu bằng token gửi qua email."""
    consume_action_token(db, payload.token, "reset_password", payload.new_password)
    return {"message": "Mật khẩu đã được thay đổi. Hãy đăng nhập lại."}


@router.post("/password/change")
def change_my_password(payload: PasswordChangeRequest, account: Account = Depends(get_current_account), db: Session = Depends(get_db)):
    """Đổi mật khẩu khi biết mật khẩu hiện tại."""
    change_password(db, account, payload.current_password, payload.new_password)
    return {"message": "Mật khẩu đã thay đổi. Hãy đăng nhập lại."}
