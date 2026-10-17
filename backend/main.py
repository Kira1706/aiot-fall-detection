"""Khởi tạo FastAPI Backend cho hệ thống phát hiện té ngã."""

from fastapi import FastAPI

from auth_routes import router as auth_router

from device_routes import router as device_router

from device_status_routes import (
    edge_router as heartbeat_edge_router,
    status_router as device_status_router,
)

from fall_event_routes import (
    edge_router as fall_edge_router,
    device_history_router,
    history_router,
)


# Khởi tạo Backend.
app = FastAPI(
    title="AIoT Fall Detection Backend",
    description="Backend cho hệ thống AIoT phát hiện té ngã.",
)


# Nhóm API xác thực caregiver.
app.include_router(auth_router)


# Nhóm API quản lý thiết bị.
app.include_router(device_router)


# Nhóm API heartbeat và trạng thái kết nối.
app.include_router(heartbeat_edge_router)
app.include_router(device_status_router)


# Nhóm API tiếp nhận và truy vấn Fall Event.
app.include_router(fall_edge_router)
app.include_router(device_history_router)
app.include_router(history_router)


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