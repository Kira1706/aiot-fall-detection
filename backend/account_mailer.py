"""Gửi email xác minh và khôi phục bằng SMTP hoặc thư mục thử nghiệm."""

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def build_account_link(purpose: str, raw: str) -> str:
    """Đưa token vào URL fragment để tránh truyền tới HTTP access log."""
    base = os.getenv("PUBLIC_DASHBOARD_URL", "http://localhost:8000/dashboard").rstrip("/")
    if not (base.startswith("https://") or base.startswith("http://localhost:") or base.startswith("http://127.0.0.1:")):
        raise RuntimeError("PUBLIC_DASHBOARD_URL phải là HTTPS hoặc localhost thử nghiệm.")
    fragment = "verify" if purpose == "verify_email" else "reset"
    return f"{base}#{fragment}={quote(raw, safe='')}"


def send_action_email(email: str, raw: str, purpose: str) -> None:
    """Gửi email chứa link; không ghi token ra log hoặc API response."""
    link = build_account_link(purpose, raw)
    is_verify = purpose == "verify_email"
    subject = "FallGuard - Xac minh email" if is_verify else "FallGuard - Dat lai mat khau"
    minutes = 30 if is_verify else 15
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = email
    msg["From"] = os.getenv("SMTP_FROM", "FallGuard <no-reply@example.invalid>")
    msg.set_content(
        "Xin chao,\n\n"
        + ("Hay xac minh email" if is_verify else "Hay dat lai mat khau")
        + " bang duong dan sau:\n"
        + link
        + f"\n\nDuong dan chi su dung 1 lan va het han sau {minutes} phut."
        + "\nNeu ban khong yeu cau, hay bo qua email nay.\n"
    )

    mode = os.getenv("ACCOUNT_MAIL_MODE", "disabled").strip().lower()
    if mode == "file":
        # Chỉ phục vụ localhost, tuyệt đối không bật trên Server công khai.
        if os.getenv("ALLOW_DEV_MAIL", "false").lower() != "true":
            raise RuntimeError("ACCOUNT_MAIL_MODE=file yêu cầu ALLOW_DEV_MAIL=true.")
        folder = BASE_DIR / "dev_mail"
        folder.mkdir(exist_ok=True)
        from uuid import uuid4
        target = folder / f"{uuid4().hex}.eml"
        target.write_bytes(msg.as_bytes())
        try:
            target.chmod(0o600)
        except OSError:
            pass
        return

    if mode != "smtp":
        raise RuntimeError("Chưa cấu hình gửi email: ACCOUNT_MAIL_MODE=smtp hoặc file thử nghiệm.")

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
    else:
        # Không cho phép truyền mật khẩu SMTP qua kết nối không mã hóa.
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(msg)
