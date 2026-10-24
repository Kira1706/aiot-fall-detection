"""Công việc quản trị một lần: xóa bucket/token đã hết hạn."""

from datetime import datetime, timezone
from sqlalchemy import delete
from database import SessionLocal
from models import SecurityRateBucket, SecurityRevokedToken


def main():
    """Không chạy trong mỗi request; có thể đặt lịch riêng."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        expired_limits = db.execute(delete(SecurityRateBucket).where(SecurityRateBucket.expires_at < now))
        expired_tokens = db.execute(delete(SecurityRevokedToken).where(SecurityRevokedToken.expires_at < now))
        db.commit()
    print("Đã dọn bucket hết hạn:", expired_limits.rowcount)
    print("Đã dọn dấu token hết hạn:", expired_tokens.rowcount)


if __name__ == "__main__":
    main()
