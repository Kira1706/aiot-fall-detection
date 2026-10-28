"""Khởi tạo Backend, Dashboard và kênh cảnh báo trực tiếp."""

from pathlib import Path
import os

from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from database import SessionLocal
from security_routes import router as security_router
from security_middleware import SecurityGateMiddleware, security_http_audit
from security_config import validate_runtime_configuration, setup_stdout_logs
from reliability_routes import router as reliability_router
from admin_routes import router as admin_router, CONSOLE as ADMIN_CONSOLE_DIR

from auth_routes import router as auth_router
from google_routes import router as google_router
from account_routes import router as account_router
from alert_routes import router as alerts_router
from alert_websocket import router as alerts_ws_router
from device_routes import router as device_router
from pairing_routes import router as pairing_router
from management_routes import router as management_router
from device_status_routes import (
    edge_router as heartbeat_edge_router,
    status_router as device_status_router,
)
from model_routes import admin_router as model_admin_router, edge_router as model_edge_router
from fall_event_routes import (
    edge_router as fall_edge_router,
    device_history_router,
    history_router,
)


# Xác định đường dẫn dựa trên vị trí file, không phụ thuộc Terminal.
BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
load_dotenv(BASE_DIR / ".env")

# Cookie chỉ giữ trạng thái OAuth và quyền đổi lấy JWT trong thời gian ngắn.
SESSION_SECRET = os.getenv("GOOGLE_SESSION_SECRET", "")
if len(SESSION_SECRET) < 32:
    raise RuntimeError("Thiếu GOOGLE_SESSION_SECRET (ít nhất 32 ký tự).")

validate_runtime_configuration()
setup_stdout_logs()

app = FastAPI(
    title="AIoT Fall Detection Backend",
    description="Backend cho hệ thống AIoT phát hiện té ngã.",
    docs_url=None,
    redoc_url=None,
)

# Middleware lưu state/nonce của OIDC trong cookie ký số HttpOnly.
# Trên HTTPS bắt buộc cấu hình GOOGLE_COOKIE_SECURE=true.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.getenv("GOOGLE_COOKIE_SECURE", "false").lower() == "true",
    max_age=900,
    session_cookie="aiot_google_oauth",
)

# Rate limit dùng chung PostgreSQL giữa các worker.
app.add_middleware(SecurityGateMiddleware, session_factory=SessionLocal)


@app.middleware("http")
async def audit_http(request, call_next):
    """Ghi request ID, độ trễ và audit hành động nhạy cảm."""
    return await security_http_audit(request, call_next, SessionLocal)

# Tiếp tục sử dụng các router đã PASS từ Milestone 3 đến 6.6.
app.include_router(auth_router)
app.include_router(security_router)
app.include_router(google_router)
app.include_router(account_router)
app.include_router(device_router)
app.include_router(pairing_router)
app.include_router(management_router)
app.include_router(heartbeat_edge_router)
app.include_router(device_status_router)
app.include_router(fall_edge_router)
app.include_router(device_history_router)
app.include_router(history_router)
app.include_router(reliability_router)

# API thông báo bền vững và WebSocket cảnh báo thời gian thực.
app.include_router(alerts_router)
app.include_router(alerts_ws_router)

# Quản lý phiên bản model và cung cấp file model cho Edge Device.
app.include_router(model_admin_router)
app.include_router(model_edge_router)
app.include_router(admin_router)
from swagger_presentation import install_swagger_presentation

# Đăng ký hai giao diện tài liệu API của FallGuard.
install_swagger_presentation(app)

# Phục vụ CSS và JavaScript cùng nguồn với API để không cần CORS.
app.mount(
    "/dashboard-assets",
    StaticFiles(directory=str(DASHBOARD_DIR)),
    name="dashboard-assets",
)

# Phục vụ CSS, JavaScript của trang quản trị.
app.mount(
    "/admin-assets",
    StaticFiles(directory=str(ADMIN_CONSOLE_DIR)),
    name="admin-assets",
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


@app.get("/ready", include_in_schema=False)
def readiness():
    """Chỉ báo Backend sẵn sàng nếu kết nối PostgreSQL còn hoạt động."""
    from fastapi import HTTPException
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database chưa sẵn sàng.")
    return {"status": "ready"}
