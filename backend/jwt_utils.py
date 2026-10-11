
import os

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt

from dotenv import load_dotenv


# Đọc file .env nằm trong thư mục backend.
# Không ghi đè biến môi trường đã được cấu hình sẵn.
BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    dotenv_path=BASE_DIR / ".env"
)


# Lấy Secret Key từ biến môi trường.
# Không ghi Secret Key trực tiếp trong source code.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")


# Cấu hình thuật toán và thời gian sử dụng Access Token.
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30


# Xác định Backend phát hành và API được phép nhận token.
JWT_ISSUER = "aiot-fall-detection-backend"
JWT_AUDIENCE = "aiot-caregiver-api"


# Từ chối chạy nếu Secret Key chưa được cấu hình hợp lệ.
# Độ dài chỉ là kiểm tra tối thiểu;
# Secret Key thực tế phải được sinh ngẫu nhiên.
if len(JWT_SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY phải là khóa ngẫu nhiên "
        "có ít nhất 32 byte. "
        "Hãy cấu hình backend/.env trước khi chạy."
    )


def create_access_token(account_id: int) -> str:
    """
    Tạo JWT Access Token cho tài khoản đã xác thực.

    Token chứa Account ID và có thời hạn 30 phút.

    Hàm này không kiểm tra mật khẩu hoặc truy vấn Database.
    Việc xác thực Account sẽ do Login API thực hiện.
    """

    # Chỉ cho phép Account ID là số nguyên dương.
    if (
        isinstance(account_id, bool)
        or not isinstance(account_id, int)
        or account_id <= 0
    ):
        raise ValueError(
            "account_id phải là số nguyên dương."
        )

    # Lấy thời điểm hiện tại theo UTC.
    issued_at = datetime.now(timezone.utc)

    # Tính thời điểm Access Token hết hạn.
    expires_at = issued_at + timedelta(
        minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )

    # Tạo nội dung của JWT.
    # Không đưa mật khẩu hoặc mã băm vào payload.
    payload = {
        "sub": str(account_id),
        "iat": issued_at,
        "exp": expires_at,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "token_use": "access",
    }

    # Ký JWT bằng Secret Key với thuật toán HS256.
    encoded_token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

    return encoded_token


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Kiểm tra và giải mã payload của JWT Access Token.

    Các thông tin được kiểm tra:
    - Chữ ký JWT có hợp lệ không.
    - Token đã hết hạn chưa.
    - Token có đủ các trường bắt buộc không.
    - Token có đúng Backend phát hành và API nhận không.
    - Token có đúng mục đích Access Token không.
    - Account ID trong token có hợp lệ không.

    Nếu token không hợp lệ, PyJWT sẽ phát sinh lỗi.
    """

    # Kiểm tra chữ ký và các thông tin bảo mật của JWT.
    # Thuật toán cho phép được cố định ở phía Backend.
    payload = jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        options={
            "require": [
                "sub",
                "iat",
                "exp",
                "iss",
                "aud",
                "token_use",
            ],
        },
    )

    # Chỉ chấp nhận token dùng để truy cập API.
    if payload.get("token_use") != "access":
        raise jwt.InvalidTokenError(
            "Token không phải Access Token."
        )

    # Lấy Account ID từ payload.
    subject = payload.get("sub")

    # Account ID phải là chuỗi biểu diễn số nguyên dương.
    if (
        not isinstance(subject, str)
        or not subject.isdecimal()
        or int(subject) <= 0
    ):
        raise jwt.InvalidTokenError(
            "Account ID trong token không hợp lệ."
        )

    return payload
