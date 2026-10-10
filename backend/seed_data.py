from sqlalchemy import select

from datetime import datetime, timezone
from database import SessionLocal
from models import (
    Account,
    Device,
    AccountDevice,
    FallEvent,
    ModelVersion,
)


db = SessionLocal()

try:
    # =========================================================
    # 1. Seed Account
    # =========================================================
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

    # =========================================================
    # 2. Seed Device
    # =========================================================
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

    # =========================================================
    # 3. Lấy lại Account và Device đã seed
    # =========================================================
    account = db.scalar(
        select(Account).where(
            Account.email == "demo.caregiver@example.com"
        )
    )

    device_1 = db.get(Device, "DEV-001")
    device_2 = db.get(Device, "DEV-002")

    assert account is not None
    assert device_1 is not None
    assert device_2 is not None

    print("\nLoaded seeded data:")
    print("account =", account.email)
    print("device_1 =", device_1.device_id)
    print("device_2 =", device_2.device_id)

    link_1 = db.scalar(
        select(AccountDevice).where(
            AccountDevice.account_id == account.account_id,
            AccountDevice.device_id == device_1.device_id,
    )
)

    if link_1 is None:
        link_1 = AccountDevice(
            account_id=account.account_id,
            device_id=device_1.device_id,
            display_name="Demo Person 1",
        )

        db.add(link_1)
        db.commit()

        print("\nCreated AccountDevice:")
        print(account.email, "->", device_1.device_id)
    else:
        print(
            "\nAccountDevice already exists:",
            account.email,
            "->",
            device_1.device_id,
        )

    link_2 = db.scalar(
        select(AccountDevice).where(
            AccountDevice.account_id == account.account_id,
            AccountDevice.device_id == device_2.device_id,
        )
    )

    if link_2 is None:
        link_2 = AccountDevice(
            account_id=account.account_id,
            device_id=device_2.device_id,
            display_name="Demo Person 2",
        )

        db.add(link_2)
        db.commit()

        print("\nCreated AccountDevice:")
        print(account.email, "->", device_2.device_id)
    else:
        print(
            "\nAccountDevice already exists:",
            account.email,
            "->",
            device_2.device_id,
        )

    model = db.get(ModelVersion, "model_v1")

    if model is None:
        model = ModelVersion(
            version="model_v1",
            file_path="models/model_v1.tflite",
            created_at=datetime.now(timezone.utc),
        )

        db.add(model)
        db.commit()
        db.refresh(model)

        print("\nCreated ModelVersion:")
        print("version =", model.version)
        print("file_path =", model.file_path)
    else:
        print("\nModelVersion already exists:", model.version)

    existing_fall = db.scalar(
        select(FallEvent).where(
            FallEvent.device_id == device_1.device_id
        )
    )

    if existing_fall is None:
        fall_event = FallEvent(
            device_id=device_1.device_id,
            event_time=datetime.now(timezone.utc),
            event_type="fall",
            model_version="model_v1",
            confidence=0.94,
        )

        db.add(fall_event)
        db.commit()
        db.refresh(fall_event)

        print("\nCreated FallEvent:")
        print("event_id =", fall_event.event_id)
        print("device_id =", fall_event.device_id)
    else:
        print(
            "\nFallEvent already exists for",
            device_1.device_id
        )

finally:
    db.close()