"""Khởi tạo Backend, Dashboard và kênh cảnh báo trực tiếp."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from auth_routes import router as auth_router
from alert_routes import router as alerts_router
from alert_websocket import router as alerts_ws_router
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


# Xác định đường dẫn dựa trên vị trí file, không phụ thuộc Terminal.
BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = BASE_DIR / "dashboard"

app = FastAPI(
    title="AIoT Fall Detection Backend",
    description="Backend cho hệ thống AIoT phát hiện té ngã.",
)

# Tiếp tục sử dụng các router đã PASS từ Milestone 3 đến 6.6.
app.include_router(auth_router)
app.include_router(device_router)
app.include_router(heartbeat_edge_router)
app.include_router(device_status_router)
app.include_router(fall_edge_router)
app.include_router(device_history_router)
app.include_router(history_router)

# API thông báo bền vững và WebSocket cảnh báo thời gian thực.
app.include_router(alerts_router)
app.include_router(alerts_ws_router)

# Phục vụ CSS và JavaScript cùng nguồn với API để không cần CORS.
app.mount(
    "/dashboard-assets",
    StaticFiles(directory=str(DASHBOARD_DIR)),
    name="dashboard-assets",
)


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    """Mở giao diện Dashboard; dữ liệu vẫn yêu cầu JWT trên từng API."""

    return FileResponse(
        DASHBOARD_DIR / "index.html",
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/")
def root():
    """Trả thông tin cơ bản của Backend."""

    return {"message": "AIoT Fall Detection Backend"}


@app.get("/health")
def health():
    """Kiểm tra tiến trình Backend có đang hoạt động."""

    return {"status": "ok"}
