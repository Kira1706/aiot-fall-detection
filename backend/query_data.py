from sqlalchemy import select

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
    account = db.scalar(
        select(Account).where(
            Account.email == "demo.caregiver@example.com"
        )
    )

    assert account is not None

    print("Account:")
    print(account.account_id, account.email)

    links = db.scalars(
        select(AccountDevice).where(
            AccountDevice.account_id == account.account_id
        )
    ).all()

    print("\nDevices followed by this account:")

    for link in links:
        print(
            link.device_id,
            "- display_name:",
            link.display_name,
        )
    events = db.scalars(
        select(FallEvent).where(
            FallEvent.device_id == "DEV-001"
        )
    ).all()

    print("\nFall events of DEV-001:")

    for event in events:
        print(
            "event_id =", event.event_id,
            "| type =", event.event_type,
            "| model =", event.model_version,
            "| confidence =", event.confidence,
        )

    models = db.scalars(
        select(ModelVersion)
    ).all()

    print("\nModel versions:")

    for model in models:
        print(
            model.version,
            "->",
            model.file_path,
        )

    followers = db.scalars(
        select(AccountDevice).where(
            AccountDevice.device_id == "DEV-001"
        )
    ).all()

    print("\nAccounts following DEV-001:")

    for link in followers:
        follower = db.get(
            Account,
            link.account_id,
        )

        print(
            follower.account_id,
            follower.email,
            "- device name:",
            link.display_name,
        )

finally:
    db.close()