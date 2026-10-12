
"""Khởi tạo ứng dụng FastAPI cho hệ thống phát hiện té ngã."""

from fastapi import FastAPI

from auth_routes import router as auth_router
from device_routes import router as device_router


# Khởi tạo ứng dụng Backend.
app = FastAPI(
    title="AIoT Fall Detection Backend",
    description="Backend cho hệ thống AIoT phát hiện té ngã.",
)


# Đăng ký các API xác thực tài khoản.
app.include_router(auth_router)


# Đăng ký các API đọc thông tin thiết bị.
app.include_router(device_router)


@app.get("/")
def root():
    """Trả thông tin cơ bản của ứng dụng."""

    return {
        "message": "AIoT Fall Detection Backend"
    }


@app.get("/health")
def health():
    """Kiểm tra tiến trình Backend có đang hoạt động."""

    return {
        "status": "ok"
    }
