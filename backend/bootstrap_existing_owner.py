"""Chỉ định chủ sở hữu thiết bị cũ sau khi quản trị viên đã đối chiếu quyền."""

import argparse
from datetime import datetime, timezone

from sqlalchemy import select

from database import SessionLocal, engine
from models import Account, AccountDevice, Device, DeviceOwnership


def main():
    """Chỉ ghi dữ liệu khi có --confirm và đã duyệt các chia sẻ cũ."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--approve-existing-shares", action="store_true")
    args = parser.parse_args()

    if engine.dialect.name != "postgresql":
        raise SystemExit("Chỉ dùng script bootstrap trên PostgreSQL quản trị đã sao lưu.")
    with SessionLocal() as db:
        device = db.scalar(select(Device).where(Device.device_id == args.device).with_for_update())
        account = db.scalar(select(Account).where(Account.email == args.email.strip().lower()))
        if device is None or account is None:
            raise SystemExit("Không tìm thấy Device hoặc Account cần cấp quyền.")
        if account.email_verified_at is None:
            raise SystemExit("Caregiver phải xác minh email trước khi sở hữu Device.")
        if db.get(DeviceOwnership, device.device_id) is not None:
            raise SystemExit("Thiết bị đã có chủ sở hữu; không tự ghi đè.")
        links = db.execute(
            select(Account.email)
            .join(AccountDevice, AccountDevice.account_id == Account.account_id)
            .where(AccountDevice.device_id == device.device_id)
            .order_by(Account.email)
        ).scalars().all()
        print("Thiết bị:", device.device_id)
        print("Chủ sở hữu dự kiến:", account.email)
        print("Các caregiver có quyền từ các milestone cũ:")
        for email in links:
            print("  -", email)
        others = [email for email in links if email != account.email]
        if others and not args.approve_existing_shares:
            raise SystemExit(
                "Có caregiver khác đang theo dõi. Hãy kiểm tra và thêm "
                "--approve-existing-shares nếu thật sự muốn giữ họ."
            )
        if not args.confirm:
            print("DRY RUN: chưa thay đổi Database. Thêm --confirm sau khi đã duyệt.")
            return
        if db.get(AccountDevice, (account.account_id, device.device_id)) is None:
            db.add(AccountDevice(
                account_id=account.account_id,
                device_id=device.device_id,
                display_name=None,
            ))
        db.add(DeviceOwnership(
            device_id=device.device_id,
            account_id=account.account_id,
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        print("LEGACY DEVICE OWNER BOOTSTRAP: PASS")


if __name__ == "__main__":
    main()
