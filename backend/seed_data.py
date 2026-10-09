from sqlalchemy import select

from database import SessionLocal
from models import Account, Device


db = SessionLocal()

try:
    statement = select(Account).where(
        Account.email == "demo.caregiver@example.com"
    )

    existing_account = db.scalar(statement)

    if existing_account is None:
        account = Account(
            email="demo.caregiver@example.com",
            password_hash="demo_hash_not_real",
            display_name="Demo Caregiver",
        )

        print("Before add:")
        print("account_id =", account.account_id)

        db.add(account)

        print("\nAfter add:")
        print("account_id =", account.account_id)

        db.commit()
        db.refresh(account)

        print("\nAfter commit + refresh:")
        print("account_id =", account.account_id)
        print("email =", account.email)
        print("display_name =", account.display_name)

    else:
        print("Demo account already exists:")
        print("account_id =", existing_account.account_id)
        print("email =", existing_account.email)

finally:
    db.close()

for device_id in ["DEV-001", "DEV-002"]:
    statement = select(Device).where(
        Device.device_id == device_id
    )

    existing_device = db.scalar(statement)

    if existing_device is None:
        device = Device(
            device_id=device_id,
            status="offline",
            model_version=None,
        )

        db.add(device)
        db.commit()
        db.refresh(device)

        print("\nCreated device:")
        print("device_id =", device.device_id)
        print("status =", device.status)
        print("model_version =", device.model_version)

    else:
        print("\nDevice already exists:", device_id)