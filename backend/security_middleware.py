"""Rate limit chia sẻ qua PostgreSQL, audit log và log HTTP an toàn."""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from database import BASE_DIR
from models import SecurityAuditLog, SecurityRateBucket

load_dotenv(Path(BASE_DIR) / ".env")
logger = logging.getLogger("fallguard.security")

# Giới hạn mỗi phút cho một IP và một nhóm thao tác.
# Không đọc hoặc lưu mật khẩu, body, mã ghép nối hoặc query string.
LIMIT_RULES = {
    "/auth/login": ("login", 10),
    "/auth/register": ("register", 6),
    "/account/password/forgot": ("forgot", 6),
    "/account/verification/request": ("verification", 6),
    "/account/password/reset": ("password_reset", 6),
    "/account/password/change": ("password_change", 10),
    "/pairing/claim": ("pairing_claim", 8),
    "/shares/accept": ("share_accept", 8),
    "/auth/google/link/prepare": ("google_link", 8),
}

AUDIT_ACTIONS = {
    "/auth/login": "caregiver.login",
    "/account/password/change": "account.password.change",
    "/account/password/reset": "account.password.reset",
    "/account/verification/confirm": "account.email.verify",
    "/auth/google/link/prepare": "account.google.link.prepare",
    "/security/logout": "account.logout",
    "/security/logout-all": "account.logout_all",
    "/pairing/claim": "device.pairing.claim",
    "/shares/accept": "device.share.accept",
}


def route_rule(path: str, method: str) -> tuple[str, int] | None:
    """Phân loại endpoint theo mẫu path, không lưu Device ID hay email."""
    if method not in {"POST", "PUT"}:
        return None
    if method == "POST" and path in LIMIT_RULES:
        return LIMIT_RULES[path]
    if path.startswith("/pairing-admin/devices/") and path.endswith("/issue"):
        return "pairing_admin", 8
    if path.startswith("/model-admin/"):
        return "model_admin", 15
    if path.endswith("/shares/invitations") and path.startswith("/devices/"):
        return "share_invite", 12
    return None


def action_name(path: str, method: str) -> str | None:
    """Chỉ ghi nhật ký các hành động cần truy vết."""
    if method == "POST" and path in AUDIT_ACTIONS:
        return AUDIT_ACTIONS[path]
    if path.startswith("/pairing-admin/devices/") and path.endswith("/issue") and method == "POST":
        return "device.pairing.issue"
    if path.startswith("/devices/") and "/shares/" in path and method in {"POST", "DELETE"}:
        return "device.share.manage"
    if path.startswith("/model-admin/") and method in {"POST", "PUT"}:
        return "model.release.manage"
    if path.startswith("/management/devices/") and method == "DELETE":
        return "device.invitation.revoke"
    return None


def secret_bytes() -> bytes:
    """Lấy khóa riêng dùng để băm IP/bucket, không dùng JWT secret."""
    value = os.getenv("RATE_LIMIT_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("RATE_LIMIT_SECRET phải có ít nhất 32 ký tự.")
    return value.encode("utf-8")


def masked_client_ip(ip: str) -> str:
    """Chỉ ghi HMAC của IP, không lưu địa chỉ IP dạng rõ."""
    return hmac.new(secret_bytes(), ip.encode(), hashlib.sha256).hexdigest()


def consume_bucket(db, action: str, ip: str, limit: int, now: float | None = None, window: int = 60) -> tuple[bool, int]:
    """
    Tăng bộ đếm nguyên tử bằng UPSERT theo một cửa sổ cố định.

    PostgreSQL xử lý đồng thời giữa nhiều worker. Nếu Database lỗi,
    middleware không bỏ qua giới hạn mà trả 503 (fail closed).
    """
    now = time.time() if now is None else now
    window_id = int(now // window)
    raw = f"{action}:{ip}:{window_id}"
    bucket_key = hmac.new(secret_bytes(), raw.encode(), hashlib.sha256).hexdigest()
    expires = datetime.fromtimestamp((window_id + 1) * window, tz=timezone.utc)
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        insert = pg_insert(SecurityRateBucket)
    elif dialect == "sqlite":
        insert = sqlite_insert(SecurityRateBucket)
    else:
        raise RuntimeError("Chưa hỗ trợ rate limit cho Database khác.")
    statement = insert.values(bucket_key=bucket_key, count=1, expires_at=expires)
    statement = statement.on_conflict_do_update(
        index_elements=["bucket_key"],
        set_={"count": SecurityRateBucket.count + 1},
    ).returning(SecurityRateBucket.count)
    try:
        hits = db.scalar(statement)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return hits <= limit, max(1, int((window_id + 1) * window - now))


class SecurityGateMiddleware:
    """ASGI middleware: giới hạn request trước khi route xử lý body."""

    def __init__(self, app, session_factory: sessionmaker):
        self.app = app
        self.session_factory = session_factory

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "true":
            await self.app(scope, receive, send)
            return
        rule = route_rule(scope.get("path", ""), scope.get("method", ""))
        if rule is None:
            await self.app(scope, receive, send)
            return
        # Không tự tin X-Forwarded-For trừ khi reverse proxy đã chuẩn hóa scope client.
        ip = (scope.get("client") or ("unknown", 0))[0]
        try:
            with self.session_factory() as db:
                allowed, retry = consume_bucket(db, rule[0], ip, rule[1])
        except Exception:
            logger.exception("Bộ đếm giới hạn không sẵn sàng")
            response = JSONResponse({"detail": "Dịch vụ bảo vệ đang tạm thời không sẵn sàng."}, status_code=503)
            await response(scope, receive, send)
            return
        if not allowed:
            response = JSONResponse(
                {"detail": "Quá nhiều yêu cầu. Vui lòng thử lại sau."},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def security_http_audit(request: Request, call_next, session_factory):
    """
    Ghi thời gian xử lý và audit thao tác nhạy cảm vào Database.

    Audit middleware mang tính best-effort; audit bắt buộc tuyệt đối phải đặt
    trong cùng transaction nghiệp vụ ở các thao tác quan trọng về sau.
    """
    started = time.perf_counter()
    request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    path = request.url.path
    action = action_name(path, request.method)
    actor_id = None
    if action:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            # Token phải được xác thực mới lấy actor ID cho log.
            try:
                from jwt_utils import decode_access_token
                # Chữ ký hợp lệ đủ để ghi actor, kể cả khi action vừa thu hồi token.
                # Không cấp thêm quyền từ thông tin này.
                claims = decode_access_token(auth[7:])
                if str(claims.get("sub", "")).isdigit():
                    actor_id = int(claims["sub"])
            except Exception:
                actor_id = None
        try:
            with session_factory() as db:
                db.add(SecurityAuditLog(
                    created_at=datetime.now(timezone.utc),
                    actor_account_id=actor_id,
                    action=action,
                    result="success" if response.status_code < 400 else "failure",
                    request_id=request_id,
                    client_hash=masked_client_ip(request.client.host if request.client else "unknown"),
                ))
                db.commit()
        except Exception:
            logger.exception("Không thể ghi nhật ký bảo mật")
    logger.info(json.dumps({
        "event": "http_request",
        "request_id": request_id,
        "method": request.method,
        "route": path if not action else action,
        "status": response.status_code,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }, ensure_ascii=False))
    return response
