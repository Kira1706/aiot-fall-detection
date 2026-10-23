"""API cấp mã ghép nối, nhận lời mời và phân quyền chủ sở hữu."""

import hmac
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from models import Account
from pairing_service import (
    accept_invitation, claim_device, get_role, invite_caregiver,
    issue_pairing_token, list_shares, revoke_share,
)

load_dotenv(Path(__file__).resolve().parent / ".env")
router = APIRouter(tags=["Secure Pairing & Sharing"])


def require_pairing_admin_key(
    key: str | None = Header(default=None, alias="X-Pairing-Admin-Key"),
) -> None:
    """Dùng khóa quản trị riêng để cấp mã ghép nối, không dùng JWT caregiver."""
    configured = os.getenv("PAIRING_ADMIN_KEY", "")
    if len(configured.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="Quản trị ghép nối chưa được cấu hình.")
    if not key or not hmac.compare_digest(key, configured):
        raise HTTPException(status_code=401, detail="Khóa quản trị ghép nối không hợp lệ.")


class SecretInput(BaseModel):
    """Mã ghép nối hoặc mã mời bí mật được gửi một lần."""
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class InviteInput(BaseModel):
    """Email caregiver được chủ sở hữu mời theo dõi."""
    model_config = ConfigDict(extra="forbid")
    invitee_email: EmailStr


class AccessResult(BaseModel):
    """Trạng thái cấp quyền sau ghép nối hoặc chấp nhận lời mời."""
    device_id: str
    role: Literal["owner", "viewer"]


@router.post("/pairing-admin/devices/{device_id}/issue", dependencies=[Depends(require_pairing_admin_key)])
def issue_pairing(device_id: str, db: Session = Depends(get_db)):
    """Quản trị viên phát mã một lần cho Device mới, chưa có chủ."""
    return issue_pairing_token(db, device_id)


@router.post("/pairing/claim", response_model=AccessResult)
def claim(
    payload: SecretInput,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Caregiver đã xác minh email nhận quyền chủ sở hữu Device."""
    return claim_device(db, account, payload.token)


@router.post("/shares/accept", response_model=AccessResult)
def accept(
    payload: SecretInput,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Caregiver có tên trong lời mời chấp nhận quyền theo dõi."""
    return accept_invitation(db, account, payload.token)


@router.get("/devices/{device_id}/pairing-role")
def role(
    device_id: str,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Trả vai trò của tài khoản trên Device đang theo dõi."""
    return {"device_id": device_id, "role": get_role(db, account, device_id)}


@router.get("/devices/{device_id}/shares")
def shares(
    device_id: str,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Chỉ chủ sở hữu xem các caregiver đang theo dõi Device."""
    return list_shares(db, account, device_id)


@router.post("/devices/{device_id}/shares/invitations", status_code=201)
def issue_invitation(
    device_id: str,
    payload: InviteInput,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Chủ sở hữu cấp mã mời cho đúng email đã xác minh."""
    return invite_caregiver(db, account, device_id, str(payload.invitee_email))


@router.delete("/devices/{device_id}/shares/{account_id}", status_code=204)
def remove_share(
    device_id: str,
    account_id: int,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    """Chủ sở hữu hủy quyền theo dõi của caregiver khác."""
    revoke_share(db, account, device_id, account_id)
    return None
