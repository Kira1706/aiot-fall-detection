"""Xác thực quyền quản trị phát hành model bằng khóa riêng của Backend."""

import hmac
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Header, HTTPException, status


load_dotenv(Path(__file__).resolve().parent / ".env")


def require_model_admin_key(
    x_model_admin_key: str | None = Header(default=None, alias="X-Model-Admin-Key"),
) -> None:
    """Chỉ cho quản trị viên có khóa riêng upload và phát hành model."""
    configured = os.getenv("MODEL_ADMIN_KEY", "")

    # Không hoạt động khi môi trường chưa có khóa đủ dài.
    if len(configured.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chưa cấu hình quyền quản trị model.",
        )

    if not x_model_admin_key or not hmac.compare_digest(x_model_admin_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Khóa quản trị model không hợp lệ.",
        )
