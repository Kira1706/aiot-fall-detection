"""Bảng quản trị phục vụ demo FallGuard, phân quyền hoàn toàn phía Backend.

Không thay thế các API caregiver, không hiển thị Device Key hoặc khóa quản trị.
Không tự tạo liên kết Device cho tài khoản và không chạy lệnh shell từ trình duyệt.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, UUID4
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from fall_event_schemas import FallEventCreate
from fall_event_service import EventIdConflictError, save_fall_event
from models import (
    Account, AccountDevice, AlertNotification, Device, DeviceHeartbeatState,
    DeviceOwnership, FallEvent, SecurityAuditLog,
)
from pairing_service import issue_pairing_token
from security_middleware import consume_bucket

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
CONSOLE = ROOT / 'admin_console'
router = APIRouter(tags=['Admin Demo Console'])


def configured_admin_emails() -> set[str]:
    """Danh sách email admin ở biến môi trường, mặc định không cấp quyền ai."""
    raw = os.getenv('ADMIN_EMAILS', '')
    return {part.strip().casefold() for part in raw.split(',') if part.strip()}


def require_admin(account: Account = Depends(get_current_account)) -> Account:
    """Chặn caregiver thường bằng kiểm tra quyền ở Backend trên mọi request."""
    allowed = configured_admin_emails()
    if not allowed:
        raise HTTPException(status_code=503, detail='Chưa cấu hình tài khoản admin.')
    if account.email.strip().casefold() not in allowed or account.email_verified_at is None:
        raise HTTPException(status_code=403, detail='Chỉ quản trị viên đã xác minh email được phép sử dụng.')
    return account


def allow_demo() -> None:
    """Không thể bật thao tác giả lập trong môi trường production."""
    app_env = os.getenv('APP_ENV', 'development').lower()
    mode = os.getenv('ADMIN_DEMO_MODE', 'false').lower() == 'true'
    if app_env not in ('development', 'test') or not mode:
        raise HTTPException(status_code=403, detail='Chế độ mô phỏng chỉ dùng trên môi trường thử nghiệm.')


def consume_admin_action(db: Session, account: Account, action: str, limit: int = 5) -> None:
    """Chống bấm liên tục vào thao tác tạo dữ liệu hoặc sinh mã ghép nối."""
    allowed, retry = consume_bucket(db, f'admin_{action}', str(account.account_id), limit=limit)
    if not allowed:
        raise HTTPException(status_code=429, detail='Bạn thao tác quá nhanh.', headers={'Retry-After': str(retry)})


def as_iso(value):
    """Trả ngày giờ UTC nhất quán, kể cả với timestamp SQLite không kèm timezone."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def write_audit_best_effort(db: Session, account: Account, action: str, request: Request) -> None:
    """Ghi dấu vết quản trị, không đưa request body, token hay mật khẩu vào log."""
    try:
        db.add(SecurityAuditLog(
            created_at=datetime.now(timezone.utc),
            actor_account_id=account.account_id,
            action=action,
            result='success',
            request_id=uuid.uuid4().hex,
            client_hash=None,
        ))
        db.commit()
    except Exception:
        db.rollback()
        # Thao tác chính đã commit: audit ở đây mang tính best-effort.


@router.get('/admin', include_in_schema=False)
def admin_page():
    """Chỉ cung cấp trang đăng nhập; dữ liệu và thao tác vẫn yêu cầu JWT admin."""
    return FileResponse(
        CONSOLE / 'index.html',
        media_type='text/html',
        headers={
            'Cache-Control': 'no-store',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            'X-Content-Type-Options': 'nosniff',
        },
    )


@router.get('/admin/api/me')
def admin_me(account: Account = Depends(require_admin)):
    """Dùng sau Login để xác minh quyền admin ở Server."""
    return {'account_id': account.account_id, 'email': account.email,
            'display_name': account.display_name, 'role': 'admin',
            'demo_mode': os.getenv('APP_ENV', 'development') in ('development', 'test')
            and os.getenv('ADMIN_DEMO_MODE', 'false').lower() == 'true'}


@router.get('/admin/api/summary')
def admin_summary(
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Bộ đếm hệ thống dành cho quản trị viên, không gồm thông tin bí mật."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=45)
    return {
        'devices': db.scalar(select(func.count()).select_from(Device)) or 0,
        'accounts': db.scalar(select(func.count()).select_from(Account)) or 0,
        'fall_events': db.scalar(select(func.count()).select_from(FallEvent)) or 0,
        'alerts': db.scalar(select(func.count()).select_from(AlertNotification)) or 0,
        'online_devices': db.scalar(select(func.count()).select_from(DeviceHeartbeatState)
            .where(DeviceHeartbeatState.last_seen_at >= cutoff)) or 0,
    }


@router.get('/admin/api/devices')
def admin_devices(
    q: str = Query(default='', max_length=100),
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Liệt kê tối đa 100 Device, chủ sở hữu và số caregiver đang theo dõi."""
    stmt = select(Device).order_by(Device.device_id).limit(100)
    if q.strip():
        stmt = select(Device).where(Device.device_id.ilike(f'%{q.strip()}%')).order_by(Device.device_id).limit(100)
    rows = db.scalars(stmt).all()
    now = datetime.now(timezone.utc)
    result = []
    for device in rows:
        owner = db.get(DeviceOwnership, device.device_id)
        owner_account = db.get(Account, owner.account_id) if owner else None
        heartbeat = db.get(DeviceHeartbeatState, device.device_id)
        watchers = db.scalar(select(func.count()).select_from(AccountDevice)
            .where(AccountDevice.device_id == device.device_id)) or 0
        seconds = None
        if heartbeat:
            last = heartbeat.last_seen_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            seconds = (now - last).total_seconds()
        result.append({
            'device_id': device.device_id,
            'status': 'online' if seconds is not None and seconds <= 45 else 'offline',
            'last_seen_at': as_iso(heartbeat.last_seen_at) if heartbeat else None,
            'owner_email': owner_account.email if owner_account else None,
            'watcher_count': watchers,
            'model_version': device.model_version,
        })
    return {'items': result, 'truncated': len(result) == 100}


@router.get('/admin/api/devices/{device_id}/watchers')
def admin_watchers(
    device_id: str,
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Xem liên kết hiện tại theo Device để hỗ trợ demo chia sẻ caregiver."""
    if not db.get(Device, device_id):
        raise HTTPException(status_code=404, detail='Không tìm thấy thiết bị.')
    owner = db.get(DeviceOwnership, device_id)
    rows = db.execute(select(AccountDevice, Account)
        .join(Account, Account.account_id == AccountDevice.account_id)
        .where(AccountDevice.device_id == device_id)
        .order_by(Account.account_id)).all()
    return {'device_id': device_id, 'items': [
        {'account_id': a.account_id, 'email': a.email,
         'display_name': link.display_name or a.display_name,
         'role': 'owner' if owner and owner.account_id == a.account_id else 'viewer'}
        for link, a in rows]}


@router.get('/admin/api/accounts')
def admin_accounts(
    q: str = Query(default='', max_length=100),
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Tra cứu tài khoản đã xác minh và số thiết bị theo dõi, không trả dữ liệu xác thực."""
    stmt = select(Account).order_by(Account.account_id.desc()).limit(100)
    if q.strip():
        stmt = select(Account).where(Account.email.ilike(f'%{q.strip()}%')).order_by(Account.account_id.desc()).limit(100)
    users = db.scalars(stmt).all()
    return {'items': [{
        'account_id': user.account_id,
        'email': user.email,
        'display_name': user.display_name,
        'verified': user.email_verified_at is not None,
        'devices': db.scalar(select(func.count()).select_from(AccountDevice)
            .where(AccountDevice.account_id == user.account_id)) or 0,
        'is_admin': user.email.strip().casefold() in configured_admin_emails(),
    } for user in users], 'truncated': len(users) == 100}


@router.get('/admin/api/events')
def admin_events(
    device_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Xem lịch sử FallEvent và số thông báo đã tạo, có phân trang."""
    stmt = select(FallEvent)
    if device_id:
        stmt = stmt.where(FallEvent.device_id == device_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    events = db.scalars(stmt.order_by(FallEvent.event_id.desc()).limit(limit).offset(offset)).all()
    result = []
    for event in events:
        recipients = db.scalar(select(func.count()).select_from(AlertNotification)
            .where(AlertNotification.fall_event_id == event.event_id)) or 0
        result.append({
            'event_id': event.event_id, 'device_id': event.device_id,
            'event_time': as_iso(event.event_time), 'confidence': event.confidence,
            'model_version': event.model_version,
            'edge_event_id': event.edge_event_id, 'alert_count': recipients,
        })
    return {'items': result, 'total': total, 'limit': limit, 'offset': offset,
            'has_next': offset + len(result) < total}


class DemoFallRequest(BaseModel):
    """Chỉ định sự kiện mô phỏng; UUID tùy chọn để kiểm tra chống trùng."""
    model_config = ConfigDict(extra='forbid')
    device_id: str = Field(min_length=1, max_length=64)
    confidence: float = Field(default=.95, ge=0, le=1, allow_inf_nan=False)
    edge_event_id: UUID4 | None = None


@router.post('/admin/api/demo/fall')
def admin_demo_fall(
    body: DemoFallRequest,
    request: Request,
    response: Response,
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Giả lập một FallEvent bằng cùng service ghi sự kiện và tạo alert của Device thật."""
    allow_demo()
    consume_admin_action(db, account, 'demo_fall')
    if db.get(Device, body.device_id) is None:
        raise HTTPException(status_code=404, detail='Thiết bị không tồn tại.')
    payload = FallEventCreate(
        edge_event_id=body.edge_event_id or uuid.uuid4(),
        event_time=datetime.now(timezone.utc), event_type='fall',
        model_version='demo_admin', confidence=body.confidence,
    )
    # Chỉ dùng lại UUID để kiểm tra trùng nếu nội dung sự kiện không thay đổi.
    # Nếu UUID có trước và nội dung khác thì service trả xung đột 409 đúng thiết kế.
    try:
        event, duplicate = save_fall_event(db, body.device_id, payload)
    except EventIdConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    recipients = db.scalar(select(func.count()).select_from(AlertNotification)
        .where(AlertNotification.fall_event_id == event.event_id)) or 0
    write_audit_best_effort(db, account, 'admin.demo.fall', request)
    response.status_code = 200 if duplicate else 201
    return {'event_id': event.event_id, 'device_id': event.device_id,
            'status': 'duplicate' if duplicate else 'recorded',
            'edge_event_id': event.edge_event_id, 'alert_count': recipients,
            'note': 'Sự kiện DEMO, không phải té ngã thực tế.'}


@router.post('/admin/api/devices/{device_id}/pairing-token')
def admin_pairing(
    device_id: str,
    request: Request,
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Cấp mã ghép nối cho Device chưa có owner và chưa có liên kết cũ."""
    allow_demo()
    consume_admin_action(db, account, 'pairing')
    result = issue_pairing_token(db, device_id)
    write_audit_best_effort(db, account, 'admin.pairing.issue', request)
    return result


@router.get('/admin/api/diagnostics')
def admin_diagnostics(
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Kiểm tra nhanh phụ thuộc quan trọng; không thực thi command hoặc regression test qua Web."""
    checks = []
    for name, sql in [
        ('PostgreSQL', 'SELECT 1'),
        ('Device registry', 'SELECT 1 FROM devices LIMIT 1'),
        ('FallEvent registry', 'SELECT 1 FROM fall_events LIMIT 1'),
        ('Alert notifications', 'SELECT 1 FROM alert_notifications LIMIT 1'),
        ('Owner roles', 'SELECT 1 FROM device_ownerships LIMIT 1'),
    ]:
        try:
            db.execute(text(sql))
            checks.append({'name': name, 'status': 'pass'})
        except Exception:
            db.rollback()
            checks.append({'name': name, 'status': 'fail'})
    return {'checks': checks, 'ok': all(item['status'] == 'pass' for item in checks),
            'notice': 'Đây là smoke check, không thay thế regression test.'}


@router.get('/admin/api/audit')
def admin_audit(
    limit: int = Query(default=15, ge=1, le=50),
    account: Account = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Hiển thị log hành động bảo mật gần nhất, tuyệt đối không có secrets."""
    rows = db.scalars(select(SecurityAuditLog)
        .order_by(SecurityAuditLog.audit_id.desc()).limit(limit)).all()
    return {'items': [{
        'audit_id': row.audit_id, 'created_at': as_iso(row.created_at),
        'actor_account_id': row.actor_account_id,
        'action': row.action, 'result': row.result,
        'request_id': row.request_id,
    } for row in rows]}
