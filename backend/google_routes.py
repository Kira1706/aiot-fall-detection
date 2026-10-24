"""Đăng ký/đăng nhập Google bằng OpenID Connect Authorization Code Flow."""

import os
import time

from authlib.integrations.starlette_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import BASE_DIR, get_db
from google_account_service import find_or_create_google_account
from jwt_utils import JWT_ACCESS_TOKEN_EXPIRE_MINUTES
from security_tokens import create_secure_access_token

load_dotenv(BASE_DIR / ".env")

router = APIRouter(prefix="/auth/google", tags=["Google Login"])
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID") or "not-configured",
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET") or "not-configured",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def require_google_configuration() -> str:
    """Không mở đăng nhập Google khi thiếu cấu hình thật."""
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if (not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET")
            or not redirect_uri):
        raise HTTPException(status_code=503, detail="Đăng nhập Google chưa được cấu hình.")
    if not (redirect_uri.startswith("https://")
            or redirect_uri.startswith("http://localhost:")
            or redirect_uri.startswith("http://127.0.0.1:")):
        raise HTTPException(status_code=503, detail="GOOGLE_REDIRECT_URI không an toàn.")
    return redirect_uri


@router.get("/start")
async def start_google_login(request: Request):
    """Chuyển trình duyệt tới trang chọn tài khoản Google."""
    redirect_uri = require_google_configuration()
    # Authlib tự tạo state và nonce, lưu vào session đã ký.
    return await oauth.google.authorize_redirect(
        request, redirect_uri, prompt="select_account"
    )


@router.get("/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Xác thực phản hồi Google và tạo phiên đổi JWT ngắn hạn."""
    require_google_configuration()
    try:
        # Authlib kiểm tra state và xác minh ID token OpenID Connect.
        token = await oauth.google.authorize_access_token(request)
        claims = token.get("userinfo") or {}
        account = find_or_create_google_account(db, claims)
    except OAuthError:
        request.session.clear()
        return RedirectResponse("/dashboard?google_error=oauth", status_code=303)
    except HTTPException as error:
        request.session.clear()
        reason = "conflict" if error.status_code == 409 else "verify"
        return RedirectResponse(f"/dashboard?google_error={reason}", status_code=303)
    except Exception:
        request.session.clear()
        # Không trả lỗi hoặc token Google về URL và log của trình duyệt.
        return RedirectResponse("/dashboard?google_error=server", status_code=303)

    # Cookie session chỉ giữ account_id trong tối đa 60 giây.
    # Không lưu Google access_token, refresh_token hoặc ID token vào cookie.
    request.session.clear()
    request.session["google_pending_account_id"] = account.account_id
    request.session["google_pending_at"] = int(time.time())
    return RedirectResponse("/dashboard?google=1", status_code=303)


@router.post("/complete")
def complete_google_login(request: Request, db: Session = Depends(get_db)):
    """Đổi phiên xác thực Google ngắn hạn lấy JWT của ứng dụng."""
    account_id = request.session.pop("google_pending_account_id", None)
    issued_at = request.session.pop("google_pending_at", None)
    now = int(time.time())
    if (type(account_id) is not int or type(issued_at) is not int
            or not (0 <= now - issued_at <= 60)):
        raise HTTPException(status_code=401, detail="Phiên Google không hợp lệ hoặc đã hết hạn.")

    from models import Account
    account = db.get(Account, account_id)
    if account is None or not account.google_sub:
        raise HTTPException(status_code=401, detail="Không tìm thấy tài khoản Google.")

    return {
        "access_token": create_secure_access_token(account.account_id, db),
        "token_type": "bearer",
        "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ============================================================
# Liên kết Google vào tài khoản mật khẩu đã tồn tại (M10.6).
# ============================================================

from pydantic import BaseModel
from auth_dependencies import get_current_account
from account_security_service import link_google_identity, verify_password
from models import Account


class GoogleLinkPrepareRequest(BaseModel):
    """Yêu cầu xác minh lại mật khẩu trước khi ghép Google."""
    current_password: str


@router.post("/link/prepare")
def prepare_google_link(
    payload: GoogleLinkPrepareRequest,
    request: Request,
    account: Account = Depends(get_current_account),
):
    """Tạo trạng thái liên kết đã xác thực, chưa cấp quyền cho Google."""
    if not account.password_hash or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status_code=403, detail="Cần xác minh mật khẩu hiện tại để liên kết Google.")
    if account.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Hãy xác minh email trước khi liên kết Google.")
    request.session["google_link_account_id"] = account.account_id
    request.session["google_link_issued_at"] = int(time.time())
    return {"start_path": "/auth/google/link/start"}


@router.get("/link/start")
async def start_google_link(request: Request):
    """Bắt đầu OIDC chỉ khi đã có yêu cầu liên kết sau tái xác thực."""
    account_id = request.session.get("google_link_account_id")
    started = request.session.get("google_link_issued_at")
    if (type(account_id) is not int or type(started) is not int
            or not (0 <= int(time.time()) - started <= 300)):
        raise HTTPException(status_code=401, detail="Phiên liên kết Google đã hết hạn.")
    ordinary_callback = require_google_configuration()
    if not ordinary_callback.endswith("/auth/google/callback"):
        raise HTTPException(status_code=503, detail="Cấu hình callback Google không phù hợp.")
    # Callback này phải được thêm riêng trong Google Cloud Console.
    link_callback = ordinary_callback[:-len("/callback")] + "/link/callback"
    return await oauth.google.authorize_redirect(
        request, link_callback, prompt="select_account"
    )


@router.get("/link/callback")
async def complete_google_link(request: Request, db: Session = Depends(get_db)):
    """Xác minh Google sub, không liên kết dựa vào email đơn thuần."""
    account_id = request.session.get("google_link_account_id")
    started = request.session.get("google_link_issued_at")
    if (type(account_id) is not int or type(started) is not int
            or not (0 <= int(time.time()) - started <= 300)):
        request.session.clear()
        return RedirectResponse("/dashboard?google_error=link_expired", status_code=303)
    try:
        google_token = await oauth.google.authorize_access_token(request)
        claims = google_token.get("userinfo") or {}
        account = db.get(Account, account_id)
        if account is None:
            raise HTTPException(status_code=401, detail="Tài khoản không còn tồn tại.")
        link_google_identity(db, account, claims)
    except OAuthError:
        request.session.clear()
        return RedirectResponse("/dashboard?google_error=oauth", status_code=303)
    except HTTPException:
        request.session.clear()
        return RedirectResponse("/dashboard?google_error=link_conflict", status_code=303)
    except Exception:
        request.session.clear()
        return RedirectResponse("/dashboard?google_error=server", status_code=303)

    # Đổi lại JWT sau redirect; không đưa JWT vào URL hoặc cookie.
    request.session.clear()
    request.session["google_pending_account_id"] = account.account_id
    request.session["google_pending_at"] = int(time.time())
    return RedirectResponse("/dashboard?google=1&linked=1", status_code=303)
