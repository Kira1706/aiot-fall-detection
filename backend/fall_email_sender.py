"""Gửi nội dung cảnh báo bằng tài khoản SMTP đã dùng để xác minh email."""

import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def send_fall_alert_email(recipient: str, event: dict) -> None:
    """Gửi email cảnh báo; không ghi địa chỉ, mật khẩu hay nội dung SMTP vào log."""

    if os.getenv("ACCOUNT_MAIL_MODE", "").strip().lower() != "smtp":
        raise RuntimeError("FallEmailRequiresSMTP")

    url = os.getenv("PUBLIC_DASHBOARD_URL", "http://localhost:8000/dashboard")
    if not (url.startswith("https://") or url.startswith("http://localhost:") or url.startswith("http://127.0.0.1:")):
        raise RuntimeError("InvalidDashboardURL")

    occurred = event["event_time"]
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    local_time = occurred.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%H:%M %d/%m/%Y")

    demo = event["model_version"] == "demo_admin"
    label = "[DEMO] " if demo else ""
    device_id = event["device_id"]
    confidence = event.get("confidence")
    confidence_text = f"{confidence * 100:.1f}%" if confidence is not None else "Không có"

    message = EmailMessage()
    message["Subject"] = f"{label}[FallGuard] Cảnh báo phát hiện té ngã - {device_id}"
    message["To"] = recipient
    message["From"] = os.environ["SMTP_FROM"]
    message.set_content(
        f"{label}FallGuard ghi nhận một sự kiện có khả năng té ngã.\n\n"
        f"Thiết bị: {device_id}\n"
        f"Thời điểm (giờ Việt Nam): {local_time}\n"
        f"Độ tin cậy: {confidence_text}\n\n"
        "Vui lòng kiểm tra tình trạng người thân ngay.\n"
        f"Mở FallGuard: {url}\n\n"
        "Email này không chứng minh người thân đã an toàn.\n"
    )

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context()) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)
