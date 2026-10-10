from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import AccountDevice


db = SessionLocal()

try:
    invalid_link = AccountDevice(
        account_id=999999,
        device_id="DEV-DOES-NOT-EXIST",
        display_name="Invalid",
    )

    db.add(invalid_link)

    print("Trying invalid AccountDevice...")

    db.commit()

    print("ERROR: invalid link was accepted")

except IntegrityError:
    print(
        "PASS: Foreign Key rejected invalid AccountDevice"
    )

    db.rollback()

finally:
    db.close()