
"""Các dependency dùng chung để xác thực người dùng."""

import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from database import get_db
from jwt_utils import decode_access_token
from models import Account


# Không tự động trả lỗi để thống nhất kết quả 401.
bearer_scheme = HTTPBearer(
    auto_error=False
)


def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> Account:
    """
    Xác minh Bearer Token và lấy tài khoản đang đăng nhập.

    Quy trình:
    1. Kiểm tra Client có gửi Bearer Token hay không.
    2. Xác minh chữ ký và thời hạn của JWT.
    3. Lấy Account ID từ trường sub.
    4. Truy vấn Account trong Database.
    5. Trả Account nếu hợp lệ, ngược lại trả HTTP 401.
    """

    # Tạo thông báo dùng chung cho các trường hợp xác thực thất bại.
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Thông tin xác thực không hợp lệ hoặc đã hết hạn.",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    # Header phải chứa Bearer Token hợp lệ.
    if credentials is None or not credentials.credentials:
        raise unauthorized

    try:
        # Kiểm tra chữ ký, thời hạn và các claim đã quy định.
        payload = decode_access_token(
            credentials.credentials
        )

    except jwt.PyJWTError as error:
        # Không gửi chi tiết lỗi giải mã JWT về Client.
        raise unauthorized from error

    # Hàm giải mã đã kiểm tra sub là chuỗi số nguyên dương.
    account_id = int(payload["sub"])

    # Chỉ chấp nhận tài khoản vẫn còn tồn tại trong Database.
    account = db.get(
        Account,
        account_id
    )

    if account is None:
        raise unauthorized

    return account
