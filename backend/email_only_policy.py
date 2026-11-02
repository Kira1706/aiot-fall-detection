"""Áp dụng điều kiện xác minh email trước khi sử dụng API caregiver.

Module chỉ bổ sung ràng buộc trên dependency xác thực hiện có.
Không tạo bảng mới, không thay thế cơ chế kiểm tra JWT/session_version.
"""

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from auth_dependencies import bearer, get_current_account
from database import get_db
from models import Account

# Những endpoint cần cho người dùng chưa xác minh để hoàn tất kích hoạt.
# Không thêm các API thiết bị, sự kiện, thông báo hoặc ghép nối vào danh sách này.
CHUA_XAC_MINH_DUOC_TRUY_CAP = frozenset({
    "/auth/me",
    "/account/me",
    "/account/verification/request",
    "/account/password/change",
    "/security/logout",
    "/security/logout-all",
})


def tai_khoan_da_xac_minh(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Account:
    """Giữ nguyên xác thực JWT rồi kiểm tra email theo URL đang truy cập.

    Endpoint gửi lại email xác minh và xem hồ sơ vẫn phải dùng được khi
    email chưa được xác minh; các API caregiver còn lại sẽ bị chặn HTTP 403.
    """
    account = get_current_account(credentials=credentials, db=db)
    if account.email_verified_at is None and request.url.path not in CHUA_XAC_MINH_DUOC_TRUY_CAP:
        raise HTTPException(
            status_code=403,
            detail="Vui lòng xác minh email trước khi sử dụng FallGuard.",
        )
    return account


def install_email_only_policy(app: FastAPI) -> None:
    """Áp dụng quy tắc cho router đã dùng get_current_account.

    Cần gọi sau khi đăng ký các router vào app. Nếu đã có override khác,
    từ chối để tránh làm mất cơ chế bảo mật của milestone trước.
    """
    current_override = app.dependency_overrides.get(get_current_account)
    if current_override not in (None, tai_khoan_da_xac_minh):
        raise RuntimeError("Đã tồn tại dependency override cho get_current_account; cần hợp nhất thủ công.")
    app.dependency_overrides[get_current_account] = tai_khoan_da_xac_minh
