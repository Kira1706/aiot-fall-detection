"""Kiểm tra thông tin cấu hình gửi email trước khi chạy demo thật."""

import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def main() -> int:
    """In tên biến còn thiếu, tuyệt đối không in giá trị mật khẩu SMTP."""
    mode = os.getenv("ACCOUNT_MAIL_MODE", "disabled").strip().lower()
    env = os.getenv("APP_ENV", "development").strip().lower()
    dashboard_url = os.getenv("PUBLIC_DASHBOARD_URL", "http://localhost:8000/dashboard")
    parsed = urlparse(dashboard_url)
    errors = []
    if mode != "smtp":
        errors.append("ACCOUNT_MAIL_MODE phải bằng smtp để người dùng nhận email thật.")
    for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        if not os.getenv(name):
            errors.append(f"Chưa cấu hình {name}.")
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        if port not in (465, 587):
            errors.append("Với account_mailer.py hiện tại, dùng SMTP_PORT=465 hoặc 587.")
    except ValueError:
        errors.append("SMTP_PORT phải là số hợp lệ.")
    if not parsed.hostname or parsed.scheme not in ("http", "https"):
        errors.append("PUBLIC_DASHBOARD_URL không hợp lệ.")
    if env == "production" and parsed.scheme != "https":
        errors.append("Môi trường production bắt buộc PUBLIC_DASHBOARD_URL dùng HTTPS.")
    if errors:
        for error in errors:
            print("[CHƯA ĐẠT]", error)
        return 1
    print("MAIL CONFIG: PASS (chỉ kiểm tra cấu hình, chưa chứng minh email đã được gửi).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
