"""Worker độc lập gửi email cảnh báo từ PostgreSQL theo nguyên tắc 12-Factor."""

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from database import SessionLocal  # noqa: E402
from fall_email_service import enabled, process_one  # noqa: E402


def run() -> None:
    """Gửi email còn chờ; có thể chạy liên tục hoặc một lượt để kiểm thử."""
    parser = argparse.ArgumentParser(description="Worker gửi email cảnh báo FallGuard")
    parser.add_argument("--once", action="store_true", help="Chỉ xử lý một công việc đã đến hạn")
    parser.add_argument("--drain", action="store_true", help="Xử lý hết các công việc đã đến hạn")
    args = parser.parse_args()
    if not enabled():
        raise SystemExit("FALL_EMAIL_ENABLED chưa bật. Kiểm tra .env.")
    if os.getenv("ACCOUNT_MAIL_MODE", "").lower() != "smtp":
        raise SystemExit("Cần ACCOUNT_MAIL_MODE=smtp để gửi email cảnh báo.")

    print("FallGuard email worker đã khởi động. Không hiển thị email/token trong log.")
    while True:
        try:
            result = process_one(SessionLocal)
        except Exception as exc:
            # Chỉ báo tên kiểu lỗi; worker tiếp tục khi Database phục hồi.
            print(f"Lỗi worker: {type(exc).__name__}")
            result = None
        if result:
            print(f"Kết quả email: {result}")
        if args.once:
            break
        if args.drain and result is None:
            break
        if not result:
            time.sleep(3)


if __name__ == "__main__":
    run()
