from fastapi import FastAPI

from auth_routes import router as auth_router


# Khởi tạo ứng dụng Backend.
app = FastAPI(
    title="AIoT Fall Detection Backend",
    description="Backend cho hệ thống AIoT phát hiện té ngã.",
)


# Đăng ký nhóm API xác thực tài khoản.
app.include_router(auth_router)


@app.get("/")
def root():
    """
    Trả về thông tin cơ bản của Backend.
    """

    return {
        "message": "AIoT Fall Detection Backend"
    }


@app.get("/health")
def health():
    """
    Kiểm tra Backend có đang hoạt động hay không.

    Endpoint này chưa kiểm tra kết nối Database.
    """

    return {
        "status": "ok"
    }