
"""Xác thực khóa bí mật riêng của ESP32 khi gửi dữ liệu."""

import hmac
import json
import os

from pathlib import Path

from dotenv import load_dotenv
from fastapi import (
    Header,
    HTTPException,
    status,
)


# Đọc cấu hình trong thư mục backend.
load_dotenv(
    dotenv_path=Path(__file__).resolve().parent / ".env"
)


def require_device_key(
    device_id: str,
    x_device_key: str | None = Header(
        default=None,
        alias="X-Device-Key",
    ),
) -> str:
    """
    Kiểm tra khóa bí mật của Device gửi request.

    Mỗi Device ID phải có một khóa riêng được cấu hình.
    Không sử dụng JWT của caregiver để xác thực ESP32.
    """

    # Lấy danh sách khóa từ cấu hình môi trường.
    config = os.getenv(
        "DEVICE_KEYS_JSON",
        "",
    )

    try:
        # Chuyển chuỗi JSON thành từ điển Device ID và khóa.
        keys = json.loads(config)

        if not isinstance(keys, dict):
            raise ValueError(
                "Cấu hình phải là đối tượng JSON."
            )

    except (ValueError, TypeError) as error:
        # Từ chối request nếu Server chưa cấu hình khóa đúng.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cấu hình xác thực thiết bị chưa hợp lệ.",
        ) from error

    # Lấy khóa được phép sử dụng cho Device trong URL.
    expected_key = keys.get(device_id)

    # Chỉ chấp nhận khóa đủ dài và trùng chính xác.
    # compare_digest giảm rò rỉ thông tin qua so sánh chuỗi.
    if (
        not isinstance(expected_key, str)
        or len(expected_key.encode("utf-8")) < 32
        or not isinstance(x_device_key, str)
        or not hmac.compare_digest(
            x_device_key,
            expected_key,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không thể xác thực thiết bị.",
        )

    return device_id
