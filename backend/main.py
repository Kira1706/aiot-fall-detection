
"""Khởi tạo ứng dụng FastAPI cho hệ thống phát hiện té ngã."""

from fastapi import FastAPI

from auth_routes import router as auth_router
from device_routes import router as device_router

from device_status_routes import (
    edge_router,
    status_router,
)


# Khởi tạo ứng dụng Backend.
app = FastAPI(
    title="AIoT Fall Detection Backend",
    description="Backend cho hệ thống AIoT phát hiện té ngã.",
)


# Các API xác thực và quản lý tài khoản.
app.include_router(auth_router)

# Các API quản lý liên kết và đọc thông tin Device.
app.include_router(device_router)

# API nhận heartbeat từ ESP32.
app.include_router(edge_router)

# API xem trạng thái kết nối dành cho caregiver.
app.include_router(status_router)


@app.get("/")
def root():
    """Trả thông tin cơ bản của Backend."""

    return {
        "message": "AIoT Fall Detection Backend"
    }


@app.get("/health")
def health():
    """Kiểm tra tiến trình Backend có đang hoạt động."""

    return {
        "status": "ok"
    }
