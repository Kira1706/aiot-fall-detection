from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Account
from password_utils import hash_password
from schemas import (
    AccountRegisterRequest,
    AccountResponse,
)


# Tạo nhóm các API liên quan đến xác thực tài khoản.
# Tất cả endpoint trong router này đều bắt đầu bằng /auth.
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_account(
    payload: AccountRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Đăng ký tài khoản mới cho người chăm sóc.

    Quy trình:
    1. Nhận và kiểm tra dữ liệu đăng ký.
    2. Chuẩn hóa và kiểm tra email trùng.
    3. Băm mật khẩu trước khi lưu.
    4. Tạo tài khoản trong Database.
    5. Trả về thông tin tài khoản không chứa mật khẩu.
    """

    # Chuẩn hóa email để hạn chế trùng do khác chữ hoa/chữ thường.
    email = str(payload.email).strip().lower()

    # Tìm tài khoản đã sử dụng email này.
    existing_account = db.scalar(
        select(Account).where(
            Account.email == email
        )
    )

    # Nếu email đã tồn tại, trả về HTTP 409.
    if existing_account is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email đã được đăng ký.",
        )

    # Chỉ băm mật khẩu sau khi dữ liệu đầu vào hợp lệ.
    # Không lưu mật khẩu gốc vào Database.
    hashed_password = hash_password(
        payload.password
    )

    # Tạo SQLAlchemy Account object.
    account = Account(
        email=email,
        password_hash=hashed_password,
        display_name=payload.display_name,
    )

    # Đưa Account vào Session để chuẩn bị lưu.
    db.add(account)

    try:
        # Ghi dữ liệu xuống Database và xác nhận giao dịch.
        db.commit()

    except IntegrityError:
        # Hủy transaction thất bại để Session có thể dùng lại.
        db.rollback()

        # Kiểm tra lại email để xử lý trường hợp
        # hai request đăng ký cùng một email gần như đồng thời.
        duplicate_account_id = db.scalar(
            select(Account.account_id).where(
                Account.email == email
            )
        )

        # Nếu nguyên nhân là email trùng, trả HTTP 409.
        if duplicate_account_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email đã được đăng ký.",
            )

        # Nếu là lỗi Database khác, chuyển lỗi lên
        # hệ thống xử lý lỗi thay vì báo sai là email trùng.
        raise

    # Đọc lại thông tin bản ghi sau khi lưu thành công.
    # Việc này giúp lấy account_id do Database tự tạo.
    db.refresh(account)

    # FastAPI tự chuyển Account thành AccountResponse.
    # Không trả về password_hash cho Client.
    return account