from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import Account, AccountDevice


db = SessionLocal()

try:
    account = db.scalar(
        select(Account).where(
            Account.email == "demo.caregiver@example.com"
        )
    )

    assert account is not None

    duplicate_link = AccountDevice(
        account_id=account.account_id,
        device_id="DEV-001",
        display_name="Duplicate",
    )

    db.add(duplicate_link)

    print("Trying duplicate AccountDevice...")

    db.commit()

    print("ERROR: duplicate link was accepted")

except IntegrityError:
    print(
        "PASS: Composite Primary Key rejected duplicate link"
    )

    db.rollback()

finally:
    db.close()