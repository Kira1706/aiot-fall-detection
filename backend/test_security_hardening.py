"""Kiểm thử bảo mật độc lập bằng SQLite trong bộ nhớ."""

import os
import time
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from alert_websocket import router as websocket_router
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from account_security_service import change_password, hash_password
from auth_dependencies import get_current_account
from database import Base, get_db
from models import Account, SecurityAuditLog
from security_middleware import SecurityGateMiddleware, consume_bucket, security_http_audit
from security_routes import router as security_router
from security_tokens import create_secure_access_token


def main():
    """Test thu hồi một token, toàn bộ phiên, đổi mật khẩu và rate limit."""
    os.environ.setdefault("RATE_LIMIT_SECRET", "test-rate-limit-key-" + "R" * 48)
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-signing-key-" + "J" * 48)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        """Bật ràng buộc khóa ngoại trong SQLite kiểm thử."""
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        account = Account(
            email="security-a@example.com",
            display_name="Caregiver A",
            password_hash=hash_password("DemoPass@2026!"),
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(account)
        db.commit()
        account_id = account.account_id
        token_one = create_secure_access_token(account_id, db)
        token_two = create_secure_access_token(account_id, db)

    def test_db():
        """Ghi dữ liệu thử nghiệm thay vì PostgreSQL thật."""
        with factory() as db:
            yield db

    app = FastAPI()
    app.dependency_overrides[get_db] = test_db
    app.include_router(security_router)
    app.include_router(websocket_router)

    @app.get("/whoami")
    def whoami(account=Depends(get_current_account)):
        """Endpoint bảo vệ dùng để kiểm tra thu hồi JWT."""
        return {"account_id": account.account_id}

    @app.post("/auth/login")
    def fake_login():
        """Endpoint giả dành riêng cho kiểm tra rate limit."""
        return {"status": "ok"}

    @app.middleware("http")
    async def audit(request, call_next):
        """Gắn audit vào ứng dụng thử nghiệm."""
        return await security_http_audit(request, call_next, factory)

    app.add_middleware(SecurityGateMiddleware, session_factory=factory)

    with TestClient(app) as client:
        h1 = {"Authorization": f"Bearer {token_one}"}
        h2 = {"Authorization": f"Bearer {token_two}"}
        assert client.get("/whoami", headers=h1).status_code == 200
        assert client.get("/whoami", headers=h2).status_code == 200

        # Thu hồi riêng token một; token hai vẫn còn hoạt động.
        assert client.post("/security/logout", headers=h1).status_code == 200
        assert client.get("/whoami", headers=h1).status_code == 401
        assert client.get("/whoami", headers=h2).status_code == 200
        print("[PASS] Đăng xuất một phiên, phiên khác vẫn hợp lệ")

        # Thu hồi mọi JWT của cùng một Account bằng session_version.
        assert client.post("/security/logout-all", headers=h2).status_code == 200
        assert client.get("/whoami", headers=h2).status_code == 401
        with factory() as db:
            token_three = create_secure_access_token(account_id, db)
        h3 = {"Authorization": f"Bearer {token_three}"}
        assert client.get("/whoami", headers=h3).status_code == 200
        print("[PASS] Logout-all vô hiệu hóa token cũ, token mới hoạt động")

        # Đổi mật khẩu tăng session_version, thu hồi cả token hiện có.
        with factory() as db:
            account = db.get(Account, account_id)
            change_password(db, account, "DemoPass@2026!", "NewPass@2026!")
        assert client.get("/whoami", headers=h3).status_code == 401
        with factory() as db:
            new_token = create_secure_access_token(account_id, db)
        assert client.get("/whoami", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
        print("[PASS] Đổi mật khẩu thu hồi JWT trước đó")

        # WebSocket đang mở phải từ chối JWT ngay ở vòng kiểm tra tiếp theo.
        with client.websocket_connect("/ws/alerts", headers={"origin": "http://testserver"}) as ws:
            ws.send_json({"type": "auth", "token": new_token})
            assert ws.receive_json()["type"] == "authenticated"
            with factory() as db:
                account = db.get(Account, account_id)
                account.session_version += 1
                db.commit()
            try:
                ws.receive_json()
                raise AssertionError("WebSocket chưa bị đóng sau khi thu hồi phiên.")
            except WebSocketDisconnect as error:
                assert error.code == 4401
        print("[PASS] WebSocket đang mở đóng sau khi session_version thay đổi")

        # Hai session thử nghiệm dùng chung Database nên chia sẻ bộ đếm.
        with factory() as db:
            allowed1, _ = consume_bucket(db, "unit-test", "192.0.2.1", limit=2, now=1200)
        with factory() as db:
            allowed2, _ = consume_bucket(db, "unit-test", "192.0.2.1", limit=2, now=1201)
        with factory() as db:
            allowed3, retry = consume_bucket(db, "unit-test", "192.0.2.1", limit=2, now=1202)
        assert allowed1 and allowed2 and not allowed3 and retry > 0
        with factory() as db:
            allowed_next, _ = consume_bucket(db, "unit-test", "192.0.2.1", limit=2, now=1261)
        assert allowed_next
        print("[PASS] Rate limit dùng Database và reset ở cửa sổ tiếp theo")

        # Kiểm tra middleware HTTP không chỉ dựa vào test hàm rate limit.
        # Dùng nhóm riêng để tránh tác động tới các API khác.
        os.environ["RATE_LIMIT_ENABLED"] = "true"
        statuses = [client.post("/auth/login").status_code for _ in range(11)]
        assert statuses[:10] == [200] * 10
        assert statuses[10] == 429
        print("[PASS] Middleware chặn HTTP 429 và trả Retry-After")

    with factory() as db:
        total = db.scalar(select(func.count(SecurityAuditLog.audit_id)))
        assert total >= 2
        print("[PASS] Có Audit Log, không ghi JWT hay mật khẩu")

    engine.dispose()
    print("SECURITY HARDENING TEST: PASS")


if __name__ == "__main__":
    main()
