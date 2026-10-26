"""Kiểm thử gọn phần Admin Console bằng SQLite độc lập (không đụng PostgreSQL)."""

import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Đặt cấu hình TRƯỚC khi import các module bảo mật.
os.environ['ADMIN_EMAILS'] = 'admin.test@example.com'
os.environ['ADMIN_DEMO_MODE'] = 'true'
os.environ['APP_ENV'] = 'test'
os.environ['RATE_LIMIT_SECRET'] = 'test_only_key_' * 8

from auth_dependencies import get_current_account
from database import Base, get_db
from models import Account, AccountDevice, Device, DeviceOwnership, FallEvent, AlertNotification
from admin_routes import router


def main():
    """Kiểm tra các ranh giới admin, phân quyền và mô phỏng thực sự tạo cảnh báo."""
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SessionTest = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with SessionTest() as db:
        db.add_all([
            Account(account_id=1, email='admin.test@example.com', display_name='Admin',
                    password_hash='test-only', email_verified_at=now),
            Account(account_id=2, email='viewer.test@example.com', display_name='Viewer',
                    password_hash='test-only', email_verified_at=now),
            Device(device_id='DEV-001', status='offline', model_version=None),
            Device(device_id='DEV-002', status='offline', model_version=None),
        ])
        db.flush()
        db.add(AccountDevice(account_id=2, device_id='DEV-001', display_name='Thiết bị thử'))
        db.commit()

    app = FastAPI()
    app.include_router(router)
    active = {'id': 1}

    def override_db():
        """Mỗi request sử dụng một transaction trên Database test."""
        with SessionTest() as db:
            yield db

    def override_account():
        """Giả lập tài khoản đã được xác thực để tập trung test quyền admin."""
        with SessionTest() as db:
            return db.get(Account, active['id'])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_account] = override_account
    client = TestClient(app)

    active['id'] = 2
    assert client.get('/admin/api/summary').status_code == 403
    assert client.post('/admin/api/demo/fall', json={'device_id': 'DEV-001'}).status_code == 403
    print('[PASS] Caregiver thường bị từ chối quyền quản trị')

    active['id'] = 1
    profile = client.get('/admin/api/me')
    assert profile.status_code == 200 and profile.json()['role'] == 'admin'
    assert client.get('/admin/api/summary').json()['devices'] == 2
    print('[PASS] Admin được xem thông tin tổng quan')

    response = client.get('/admin/api/devices')
    assert response.status_code == 200 and len(response.json()['items']) == 2
    watchers = client.get('/admin/api/devices/DEV-001/watchers')
    assert watchers.status_code == 200 and watchers.json()['items'][0]['email'] == 'viewer.test@example.com'
    print('[PASS] Admin xem Device và caregiver đã liên kết')

    response = client.post('/admin/api/demo/fall', json={'device_id': 'DEV-001', 'confidence': .97})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['alert_count'] == 1
    with SessionTest() as db:
        assert db.scalar(select(FallEvent).where(FallEvent.event_id == result['event_id']))
        assert db.scalar(select(AlertNotification).where(
            AlertNotification.fall_event_id == result['event_id']))
    print('[PASS] Mô phỏng tạo FallEvent và AlertNotification bằng service thật')

    response = client.get('/admin/api/events?device_id=DEV-001&limit=5')
    assert response.status_code == 200 and response.json()['total'] == 1
    assert response.json()['items'][0]['model_version'] == 'demo_admin'
    print('[PASS] Lịch sử FallEvent có phân trang và nhãn demo')

    response = client.get('/admin/api/diagnostics')
    assert response.status_code == 200 and response.json()['ok'] is True
    print('[PASS] Smoke check Database/tables')

    # Không được giả lập khi APP_ENV=production kể cả có bật nhầm cờ demo.
    os.environ['APP_ENV'] = 'production'
    response = client.post('/admin/api/demo/fall', json={'device_id': 'DEV-001'})
    assert response.status_code == 403
    print('[PASS] Môi trường production luôn chặn giả lập')
    os.environ['APP_ENV'] = 'test'

    response = client.post('/admin/api/devices/DEV-002/pairing-token')
    assert response.status_code == 200 and len(response.json()['pairing_token']) >= 32
    print('[PASS] Chỉ Device chưa có liên kết được cấp mã ghép nối')

    response = client.post('/admin/api/devices/DEV-001/pairing-token')
    assert response.status_code == 409
    print('[PASS] Thiết bị có liên kết cũ không thể bị chiếm quyền')

    with SessionTest() as db:
        owner = db.get(DeviceOwnership, 'DEV-001')
        assert owner is None
    print('\nADMIN CONSOLE UNIT TEST: PASS')


if __name__ == '__main__':
    main()
