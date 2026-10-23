"""Nghiệp vụ ghép nối an toàn và chia sẻ quyền theo dõi thiết bị."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    Account, AccountDevice, Device, DeviceOwnership, DevicePairingToken,
    DeviceShareInvitation,
)

PAIRING_TTL = timedelta(minutes=10)
INVITATION_TTL = timedelta(hours=24)


def utc_now() -> datetime:
    """Lấy thời điểm hiện tại theo UTC."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Chuẩn hóa ngày giờ đọc từ PostgreSQL hoặc SQLite về UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def token_hash(raw: str) -> str:
    """Chỉ lưu giá trị băm, không ghi mã gốc xuống Database."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_token() -> str:
    """Sinh mã 256 bit, khó đoán và đủ dài để chống thử vét cạn."""
    return secrets.token_urlsafe(32)


def require_verified(account: Account) -> None:
    """Chỉ tài khoản đã xác minh email được nhận quyền ghép/chia sẻ."""
    if account.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Hãy xác minh email trước khi thao tác thiết bị.")


def lock_device(db: Session, device_id: str) -> Device:
    """Khóa dòng Device trên PostgreSQL để tuần tự hóa việc cấp quyền."""
    device = db.scalar(
        select(Device).where(Device.device_id == device_id).with_for_update()
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Thiết bị không tồn tại.")
    return device


def owner_for(db: Session, device_id: str, account_id: int) -> DeviceOwnership:
    """Yêu cầu tài khoản đang giữ quyền chủ sở hữu của thiết bị."""
    owner = db.get(DeviceOwnership, device_id)
    if owner is None or owner.account_id != account_id:
        raise HTTPException(status_code=403, detail="Chỉ chủ sở hữu được phép quản lý chia sẻ.")
    return owner


def commit_or_conflict(db: Session) -> None:
    """Không tiết lộ lỗi SQL nội bộ khi có xung đột ràng buộc."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Thao tác bị xung đột, hãy tải lại dữ liệu.") from exc


def issue_pairing_token(db: Session, device_id: str) -> dict:
    """Cấp mã một lần cho Device chưa sở hữu và không có liên kết cũ."""
    lock_device(db, device_id)
    if db.get(DeviceOwnership, device_id) is not None:
        raise HTTPException(status_code=409, detail="Thiết bị đã có chủ sở hữu.")
    legacy = db.scalar(select(AccountDevice).where(AccountDevice.device_id == device_id).limit(1))
    if legacy is not None:
        raise HTTPException(
            status_code=409,
            detail="Thiết bị có liên kết cũ; quản trị viên phải rà soát và chỉ định chủ sở hữu.",
        )
    raw = new_token()
    now = utc_now()
    record = db.get(DevicePairingToken, device_id)
    if record is None:
        record = DevicePairingToken(
            device_id=device_id, token_hash=token_hash(raw),
            created_at=now, expires_at=now + PAIRING_TTL, used_at=None,
        )
        db.add(record)
    else:
        # Phát mã mới sẽ vô hiệu hóa ngay mã ghép nối cũ.
        record.token_hash = token_hash(raw)
        record.created_at = now
        record.expires_at = now + PAIRING_TTL
        record.used_at = None
    commit_or_conflict(db)
    return {"device_id": device_id, "pairing_token": raw, "expires_at": now + PAIRING_TTL}


def claim_device(db: Session, account: Account, raw: str) -> dict:
    """Ghép Device chưa có chủ, đảm bảo mã dùng đúng một lần."""
    require_verified(account)
    digest = token_hash(raw)
    found = db.scalar(select(DevicePairingToken.device_id).where(DevicePairingToken.token_hash == digest))
    if found is None:
        raise HTTPException(status_code=400, detail="Mã ghép nối không hợp lệ hoặc đã bị thay thế.")
    lock_device(db, found)
    record = db.get(DevicePairingToken, found)
    now = utc_now()
    if record is None or record.token_hash != digest or record.used_at is not None or as_utc(record.expires_at) <= now:
        raise HTTPException(status_code=400, detail="Mã ghép nối đã dùng hoặc hết hạn.")
    if db.get(DeviceOwnership, found) is not None:
        raise HTTPException(status_code=409, detail="Thiết bị đã có chủ sở hữu.")
    if db.scalar(select(AccountDevice).where(AccountDevice.device_id == found).limit(1)):
        raise HTTPException(status_code=409, detail="Thiết bị có liên kết cũ, cần rà soát trước.")
    db.add(DeviceOwnership(device_id=found, account_id=account.account_id, created_at=now))
    db.add(AccountDevice(account_id=account.account_id, device_id=found, display_name=None))
    record.used_at = now
    commit_or_conflict(db)
    return {"device_id": found, "role": "owner"}


def invite_caregiver(db: Session, owner_account: Account, device_id: str, email: str) -> dict:
    """Tạo mã mời cho đúng một tài khoản đã xác minh email."""
    require_verified(owner_account)
    lock_device(db, device_id)
    owner_for(db, device_id, owner_account.account_id)
    target = db.scalar(select(Account).where(Account.email == email.strip().lower()))
    if target is None or target.email_verified_at is None:
        raise HTTPException(status_code=404, detail="Tài khoản được mời chưa sẵn sàng.")
    if target.account_id == owner_account.account_id:
        raise HTTPException(status_code=409, detail="Không thể mời chính chủ sở hữu.")
    if db.get(AccountDevice, (target.account_id, device_id)) is not None:
        raise HTTPException(status_code=409, detail="Caregiver đã theo dõi thiết bị này.")
    now = utc_now()
    # Mã mời cũ cùng người nhận sẽ không còn hiệu lực.
    previous = db.scalars(select(DeviceShareInvitation).where(
        DeviceShareInvitation.device_id == device_id,
        DeviceShareInvitation.invited_account_id == target.account_id,
        DeviceShareInvitation.accepted_at.is_(None),
        DeviceShareInvitation.revoked_at.is_(None),
    )).all()
    for old in previous:
        old.revoked_at = now
    raw = new_token()
    invitation = DeviceShareInvitation(
        device_id=device_id, invited_account_id=target.account_id,
        invited_by_account_id=owner_account.account_id,
        token_hash=token_hash(raw), created_at=now,
        expires_at=now + INVITATION_TTL, accepted_at=None, revoked_at=None,
    )
    db.add(invitation)
    commit_or_conflict(db)
    return {"device_id": device_id, "invitee_email": target.email, "invitation_token": raw, "expires_at": now + INVITATION_TTL}


def accept_invitation(db: Session, account: Account, raw: str) -> dict:
    """Chỉ cho tài khoản được chỉ định sử dụng mã mời một lần."""
    require_verified(account)
    digest = token_hash(raw)
    invitation_device = db.scalar(select(DeviceShareInvitation.device_id).where(
        DeviceShareInvitation.token_hash == digest
    ))
    if invitation_device is None:
        raise HTTPException(status_code=400, detail="Mã mời không hợp lệ.")
    lock_device(db, invitation_device)
    invitation = db.scalar(select(DeviceShareInvitation).where(DeviceShareInvitation.token_hash == digest))
    now = utc_now()
    if (invitation is None or invitation.accepted_at is not None or
        invitation.revoked_at is not None or as_utc(invitation.expires_at) <= now):
        raise HTTPException(status_code=400, detail="Mã mời đã dùng, bị thu hồi hoặc hết hạn.")
    if invitation.invited_account_id != account.account_id:
        raise HTTPException(status_code=403, detail="Lời mời không dành cho tài khoản này.")
    if db.get(DeviceOwnership, invitation.device_id) is None:
        raise HTTPException(status_code=409, detail="Thiết bị chưa có chủ sở hữu.")
    if db.get(AccountDevice, (account.account_id, invitation.device_id)) is not None:
        raise HTTPException(status_code=409, detail="Tài khoản đã theo dõi thiết bị.")
    db.add(AccountDevice(account_id=account.account_id, device_id=invitation.device_id, display_name=None))
    invitation.accepted_at = now
    commit_or_conflict(db)
    return {"device_id": invitation.device_id, "role": "viewer"}


def get_role(db: Session, account: Account, device_id: str) -> str:
    """Phân biệt owner/viewer/legacy mà không tiết lộ Device ngoài quyền."""
    if db.get(AccountDevice, (account.account_id, device_id)) is None:
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem thiết bị này.")
    owner = db.get(DeviceOwnership, device_id)
    if owner is None:
        return "legacy"
    return "owner" if owner.account_id == account.account_id else "viewer"


def list_shares(db: Session, account: Account, device_id: str) -> list[dict]:
    """Chỉ chủ sở hữu xem danh sách caregiver đang có quyền."""
    owner_for(db, device_id, account.account_id)
    rows = db.execute(select(Account, AccountDevice).join(
        AccountDevice, Account.account_id == AccountDevice.account_id
    ).where(AccountDevice.device_id == device_id).order_by(Account.account_id)).all()
    return [{"account_id": user.account_id, "email": user.email,
             "display_name": user.display_name,
             "role": "owner" if user.account_id == account.account_id else "viewer"}
            for user, _ in rows]


def revoke_share(db: Session, account: Account, device_id: str, target_id: int) -> None:
    """Chủ sở hữu thu hồi quyền của caregiver, không xóa FallEvent."""
    lock_device(db, device_id)
    owner_for(db, device_id, account.account_id)
    if target_id == account.account_id:
        raise HTTPException(status_code=409, detail="Không thể thu hồi quyền của chủ sở hữu.")
    link = db.get(AccountDevice, (target_id, device_id))
    if link is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người theo dõi.")
    db.delete(link)
    # Vô hiệu hóa mã mời đang chờ của người đã bị thu hồi.
    now = utc_now()
    invitations = db.scalars(select(DeviceShareInvitation).where(
        DeviceShareInvitation.device_id == device_id,
        DeviceShareInvitation.invited_account_id == target_id,
        DeviceShareInvitation.accepted_at.is_(None),
        DeviceShareInvitation.revoked_at.is_(None),
    )).all()
    for invitation in invitations:
        invitation.revoked_at = now
    commit_or_conflict(db)
