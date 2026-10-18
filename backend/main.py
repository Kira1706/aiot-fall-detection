"""Khởi tạo các nhóm API đã có từ Milestone 3 đến 6.6."""

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

app = FastAPI(
    title="AIoT Fall Detection Backend",
    description="Backend cho hệ thống AIoT phát hiện té ngã.",
)

# Giữ nguyên các router và đăng ký đủ các endpoint nghiệp vụ.
app.include_router(auth_router)
app.include_router(device_router)
app.include_router(heartbeat_edge_router)
app.include_router(device_status_router)
app.include_router(fall_edge_router)
app.include_router(device_history_router)
app.include_router(history_router)


@app.get("/")
def root():
    """Trả thông tin cơ bản của Backend."""

    return {"message": "AIoT Fall Detection Backend"}


@app.get("/health")
def health():
    """Kiểm tra tiến trình Backend có đang chạy."""

    return {"status": "ok"}
