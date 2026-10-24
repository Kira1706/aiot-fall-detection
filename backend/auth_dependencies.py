"""Xác thực caregiver bằng JWT còn hiệu lực và chưa bị thu hồi."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import Account
from security_tokens import authenticate_secure_token

bearer = HTTPBearer(auto_error=False)


def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Account:
    """Không tin JWT chỉ vì chữ ký đúng; kiểm tra trạng thái phiên trên DB."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Thiếu Bearer token.")
    account, _ = authenticate_secure_token(credentials.credentials, db)
    return account
