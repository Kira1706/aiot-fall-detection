"""Kiểm tra cấu hình triển khai và ghi log ra stdout."""

import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from database import BASE_DIR

load_dotenv(Path(BASE_DIR) / ".env")


def validate_runtime_configuration() -> None:
    """Không cho chạy chế độ production với các cờ demo nguy hiểm."""
    env = os.getenv("APP_ENV", "development").strip().lower()
    if env not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV không hợp lệ.")
    if env == "production":
        checks = {
            "DB_BACKEND phải dùng PostgreSQL": os.getenv("DB_BACKEND") == "postgresql",
            "Rate limit phải được bật": os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
            "Không mở chế độ ghép nối demo": os.getenv("DEVICE_LINK_DEMO_MODE", "false").lower() != "true",
            "Không cho phép email thử nghiệm": os.getenv("ALLOW_DEV_MAIL", "false").lower() != "true",
            "Cookie OAuth bắt buộc HTTPS": os.getenv("GOOGLE_COOKIE_SECURE", "false").lower() == "true",
            "PUBLIC_DASHBOARD_URL phải HTTPS": os.getenv("PUBLIC_DASHBOARD_URL", "").startswith("https://"),
        }
        bad = [name for name, passed in checks.items() if not passed]
        if bad:
            raise RuntimeError("Cấu hình production không an toàn: " + "; ".join(bad))
    if len(os.getenv("RATE_LIMIT_SECRET", "")) < 32:
        raise RuntimeError("Thiếu RATE_LIMIT_SECRET đủ mạnh.")


def setup_stdout_logs() -> None:
    """Gửi log lên stdout thay vì tự tạo log file cục bộ."""
    root = logging.getLogger("fallguard.security")
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
        root.propagate = False
