"""Kiểm tra nghiệp vụ schema v9, quyền truy cập và chống lùi trạng thái."""
from datetime import datetime, timezone
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from database import Base
from models import Account, AccountDevice, Device, FallEvent
from incident_models import FallIncidentResolution
from reliability_routes import _current_access


def main():
    """Kiểm thử Database độc lập, không sử dụng PostgreSQL của người dùng."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Account(email="a@example.test", password_hash="hash", display_name="A")
        b = Account(email="b@example.test", password_hash="hash", display_name="B")
        d = Device(device_id="DEV-TEST", status="offline", model_version=None)
        db.add_all([a, b, d]); db.flush()
        db.add(AccountDevice(account_id=a.account_id, device_id=d.device_id))
        db.add(FallEvent(device_id=d.device_id, event_time=datetime.now(timezone.utc),
                         event_type="fall", model_version="test", confidence=0.9))
        db.commit()
        event_id = db.query(FallEvent).first().event_id
        assert _current_access(db, a.account_id, event_id) is not None
        assert _current_access(db, b.account_id, event_id) is None
        print("[PASS] Viewer không có liên kết bị từ chối")
        row = FallIncidentResolution(fall_event_id=event_id, status="acknowledged",
             updated_by_account_id=a.account_id, updated_at=datetime.now(timezone.utc), note="Đã gọi điện")
        db.add(row); db.commit()
        assert db.get(FallIncidentResolution, event_id).status == "acknowledged"
        print("[PASS] Trạng thái xác nhận được lưu bền vững")
        row.status = "resolved"; db.commit()
        assert db.get(FallIncidentResolution, event_id).status == "resolved"
        print("[PASS] Trạng thái xử lý xong được lưu")
        db.delete(db.query(AccountDevice).first()); db.commit()
        assert _current_access(db, a.account_id, event_id) is None
        print("[PASS] Thu hồi liên kết khiến sự cố không thể được đọc")
    print("ALERT RELIABILITY UNIT TEST: PASS")


if __name__ == "__main__":
    main()
