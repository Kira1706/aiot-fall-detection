"""Kiểm thử toàn bộ luồng quản trị model và phân phối tới thiết bị Edge."""

import hashlib
import json
import os
import secrets
import tempfile

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from model_routes import admin_router, edge_router
from model_storage import get_model_directory
from models import Device, ModelVersion, ModelRelease


# Dùng ứng dụng thử nghiệm gồm các router THẬT của Model Management.
# Không cần kết nối PostgreSQL hoặc khởi động Uvicorn.
test_app = FastAPI()
test_app.include_router(admin_router)
test_app.include_router(edge_router)


class TestData:
    """Lưu thông tin môi trường SQLite tạm của từng lần chạy test."""

    def __init__(self, root: Path):
        self.root = root
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def sqlite_foreign_keys(dbapi_connection, connection_record):
            """Bật khóa ngoại để kiểm tra dữ liệu giống PostgreSQL."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        Base.metadata.create_all(self.engine)

    def session_override(self):
        """Trả Session riêng, không chạm vào Database phát triển."""
        db = self.sessions()
        try:
            yield db
        finally:
            db.close()

    def directory_override(self):
        """Trả thư mục model tạm, tránh ghi file vào repository."""
        return self.root

    def seed(self):
        """Tạo hai Device và một ModelVersion cũ chưa có SHA-256."""
        with self.sessions() as db:
            db.add_all([
                Device(device_id="DEV-001", status="offline", model_version=None),
                Device(device_id="DEV-002", status="offline", model_version="old_model"),
                ModelVersion(
                    version="old_model",
                    file_path="models/old_model.tflite",
                    created_at=datetime.now(timezone.utc),
                    sha256=None,
                    size_bytes=None,
                ),
            ])
            db.commit()


def admin_headers(key: str):
    """Tạo header quản trị riêng, không sử dụng JWT caregiver."""
    return {"X-Model-Admin-Key": key}


def device_headers(key: str):
    """Tạo header xác thực dành cho ESP32."""
    return {"X-Device-Key": key}


def upload(client, key: str, version: str, blob: bytes, filename: str = "model.tflite"):
    """Gửi file model bằng multipart/form-data."""
    return client.post(
        "/model-admin/models",
        headers=admin_headers(key),
        data={"version": version},
        files={"file": (filename, blob, "application/octet-stream")},
    )


def run_tests():
    """Chạy các bài kiểm thử HTTP, file và ràng buộc phát hành."""
    with tempfile.TemporaryDirectory(prefix="aiot-m9-") as directory:
        state = TestData(Path(directory))
        state.seed()

        test_app.dependency_overrides[get_db] = state.session_override
        test_app.dependency_overrides[get_model_directory] = state.directory_override

        admin_key = secrets.token_urlsafe(40)
        key_1 = secrets.token_urlsafe(40)
        key_2 = secrets.token_urlsafe(40)

        # File giả chỉ để kiểm thử đầu mối upload/hash/HTTP.
        # Không phải model AI thực tế và không dùng được để inference.
        file_1 = b"\x20\x00\x00\x00TFL3" + b"demo-model-one" * 20
        file_2 = b"\x20\x00\x00\x00TFL3" + b"demo-model-two" * 20

        env = {
            "MODEL_ADMIN_KEY": admin_key,
            "DEVICE_KEYS_JSON": json.dumps({"DEV-001": key_1, "DEV-002": key_2}),
        }

        try:
            with patch.dict(os.environ, env, clear=False):
                with TestClient(test_app) as client:
                    # Chưa có release thì Device chỉ thấy target_version=null.
                    r = client.get(
                        "/device-ingest/DEV-001/model-manifest",
                        headers=device_headers(key_1),
                    )
                    assert r.status_code == 200 and r.json()["target_version"] is None
                    print("[PASS] Chưa phát hành model thì manifest không yêu cầu cập nhật")

                    # Phải dùng đúng khóa quản trị, không dùng khóa của Device.
                    r = upload(client, "sai-khoa", "model_v1", file_1)
                    assert r.status_code == 401
                    print("[PASS] Sai khóa quản trị bị từ chối")

                    # Sai định dạng, sai đuôi, version không hợp lệ.
                    assert upload(client, admin_key, "bad", b"not-a-model").status_code == 422
                    assert upload(client, admin_key, "bad", file_1, "model.bin").status_code == 422
                    assert upload(client, admin_key, "../bad", file_1).status_code == 422
                    assert upload(client, admin_key, "too_big", file_1 + b"a" * (4 * 1024 * 1024)).status_code == 422
                    print("[PASS] File lỗi, tên file sai, version nguy hiểm và file lớn bị chặn")

                    r = upload(client, admin_key, "model_v1", file_1)
                    assert r.status_code == 201, r.text
                    assert r.json()["sha256"] == hashlib.sha256(file_1).hexdigest()
                    assert r.json()["size_bytes"] == len(file_1)
                    assert (state.root / "model_v1.tflite").read_bytes() == file_1
                    print("[PASS] Upload model_v1 lưu đúng file, kích thước và SHA-256")

                    assert upload(client, admin_key, "model_v1", file_1).status_code == 409
                    assert (state.root / "model_v1.tflite").read_bytes() == file_1
                    print("[PASS] Upload trùng version không ghi đè model cũ")

                    r = client.get("/model-admin/models", headers=admin_headers(admin_key))
                    assert r.status_code == 200 and len(r.json()) == 2
                    assert any(x["version"] == "old_model" and x["sha256"] is None for x in r.json())
                    assert client.put(
                        "/model-admin/releases/current",
                        headers=admin_headers(admin_key),
                        json={"version": "old_model"},
                    ).status_code == 409
                    print("[PASS] ModelVersion v1 giữ nguyên nhưng chưa thể phát hành thiếu metadata")

                    r = client.put(
                        "/model-admin/releases/current",
                        headers=admin_headers(admin_key),
                        json={"version": "model_v1"},
                    )
                    assert r.status_code == 200, r.text
                    print("[PASS] Phát hành model_v1 thành công")

                    assert client.get(
                        "/device-ingest/DEV-001/model-manifest"
                    ).status_code == 401
                    assert client.get(
                        "/device-ingest/DEV-001/model-manifest",
                        headers=device_headers(key_2),
                    ).status_code == 401
                    print("[PASS] ESP32 phải có Device Key khớp device_id")

                    r = client.get(
                        "/device-ingest/DEV-001/model-manifest",
                        headers=device_headers(key_1),
                    )
                    assert r.status_code == 200 and r.json()["update_available"] is True
                    assert r.json()["target_version"] == "model_v1"
                    assert r.json()["installed_version"] is None
                    assert r.json()["download_path"].endswith("/model_v1/download")
                    print("[PASS] Manifest báo có bản cập nhật và đủ SHA-256/size")

                    r = client.get(
                        "/device-ingest/DEV-001/models/model_v1/download",
                        headers=device_headers(key_1),
                    )
                    assert r.status_code == 200, r.text
                    assert r.content == file_1
                    assert r.headers["x-model-sha256"] == hashlib.sha256(file_1).hexdigest()
                    assert client.get(
                        "/device-ingest/DEV-001/models/model_v1/download",
                        headers=device_headers(key_2),
                    ).status_code == 401
                    print("[PASS] Tải file đúng SHA-256, sai Device Key bị chặn")

                    # Mô phỏng Device cài model và báo phiên bản bằng heartbeat.
                    with state.sessions() as db:
                        d = db.get(Device, "DEV-001")
                        d.model_version = "model_v1"
                        db.commit()
                    r = client.get(
                        "/device-ingest/DEV-001/model-manifest",
                        headers=device_headers(key_1),
                    )
                    assert r.status_code == 200 and r.json()["update_available"] is False
                    assert r.json()["download_path"] is None
                    print("[PASS] Khi Device đã cài version hiện hành thì không tải lại")

                    assert upload(client, admin_key, "model_v2", file_2).status_code == 201
                    r = client.put(
                        "/model-admin/releases/current",
                        headers=admin_headers(admin_key),
                        json={"version": "model_v2"},
                    )
                    assert r.status_code == 200
                    with state.sessions() as db:
                        release = db.get(ModelRelease, 1)
                        assert release.version == "model_v2"
                    assert client.get(
                        "/device-ingest/DEV-001/models/model_v1/download",
                        headers=device_headers(key_1),
                    ).status_code == 404
                    print("[PASS] Phát hành model_v2 và chặn tải version không còn hiện hành")

                    # Nếu file bị thay đổi ngoài luồng, phải ngăn manifest và download.
                    (state.root / "model_v2.tflite").write_bytes(file_2 + b"tampered")
                    r = client.get(
                        "/device-ingest/DEV-001/model-manifest",
                        headers=device_headers(key_1),
                    )
                    assert r.status_code == 503
                    r = client.get(
                        "/device-ingest/DEV-001/models/model_v2/download",
                        headers=device_headers(key_1),
                    )
                    assert r.status_code == 503
                    print("[PASS] File bị sửa sau khi phát hành bị chặn bằng SHA-256")

            with patch.dict(os.environ, {"MODEL_ADMIN_KEY": ""}, clear=False):
                with TestClient(test_app) as client:
                    r = client.get("/model-admin/models", headers=admin_headers(admin_key))
                    assert r.status_code == 503
                    print("[PASS] Thiếu cấu hình admin key thì chức năng quản trị đóng")

        finally:
            test_app.dependency_overrides.pop(get_db, None)
            test_app.dependency_overrides.pop(get_model_directory, None)
            state.engine.dispose()

    print("\nMODEL MANAGEMENT TEST: PASS")


if __name__ == "__main__":
    run_tests()
