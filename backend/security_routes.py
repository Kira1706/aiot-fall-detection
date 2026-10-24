"""Các API đăng xuất và thu hồi toàn bộ phiên đăng nhập."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Account
from security_tokens import authenticate_secure_token, revoke_all_account_tokens, revoke_single_token

router = APIRouter(prefix="/security", tags=["Security"])
bearer = HTTPBearer(auto_error=False)


def current_security_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> tuple[Account, dict, str]:
    """Lấy cả JWT gốc cho thao tác thu hồi đúng token hiện tại."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Thiếu Bearer token.")
    account, claims = authenticate_secure_token(credentials.credentials, db)
    return account, claims, credentials.credentials


@router.post("/logout")
def logout_current(
    context: tuple[Account, dict, str] = Depends(current_security_context),
    db: Session = Depends(get_db),
):
    """Đăng xuất phiên hiện tại mà không ảnh hưởng token trên thiết bị khác."""
    account, claims, token = context
    revoke_single_token(db, account.account_id, token, claims)
    return {"message": "Đã đăng xuất phiên hiện tại."}


@router.post("/logout-all")
def logout_everywhere(
    context: tuple[Account, dict, str] = Depends(current_security_context),
    db: Session = Depends(get_db),
):
    """Thu hồi mọi JWT hiện có, bao gồm các phiên Google Login."""
    account, _, _ = context
    # Khóa dòng tài khoản để tránh hai thao tác thu hồi đồng thời bị ghi đè.
    locked = db.scalar(select(Account).where(Account.account_id == account.account_id).with_for_update())
    revoke_all_account_tokens(db, locked)
    db.commit()
    return {"message": "Tất cả các phiên cũ đã được thu hồi."}
