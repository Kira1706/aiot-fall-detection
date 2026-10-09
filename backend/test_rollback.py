from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from database import SessionLocal
from models import Device


db = SessionLocal()

try:
    device_1 = Device(
        device_id="ROLLBACK-TEST",
        status="offline",
        model_version=None,
    )

    device_2 = Device(
        device_id="ROLLBACK-TEST",
        status="offline",
        model_version=None,
    )

    db.add(device_1)
    db.add(device_2)

    print("Trying to commit two devices with the same PK...")

    db.commit()

except IntegrityError:
    print("Commit failed because of database constraint.")
    print("Rolling back transaction...")

    db.rollback()

    statement = select(Device).where(
        Device.device_id == "ROLLBACK-TEST"
    )

    result = db.scalar(statement)

    print(
        "ROLLBACK-TEST exists after rollback:",
        result is not None
    )

finally:
    db.close()