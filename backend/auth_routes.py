
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

from password_utils import (
    hash_password,
    verify_password,
)

from jwt_utils import (
    create_access_token,
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
)

from schemas import (
    AccountRegisterRequest,
    AccountResponse,
    AccountLoginRequest,
    AccessTokenResponse,
)


# Tạo nhóm API xác thực với đường dẫn bắt đầu bằng /auth.
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# =========================================================
# 1. API ĐĂNG KÝ TÀI KHOẢN
# =========================================================

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
    Đăng ký tài khoản người chăm sóc bằng email.

    Mật khẩu được băm bằng Argon2id trước khi lưu.
    Không trả mật khẩu hoặc mã băm về Client.
    """

    # Chuẩn hóa email để hạn chế trùng do chữ hoa/chữ thường.
    email = str(payload.email).strip().lower()

    # Kiểm tra email đã được sử dụng hay chưa.
    existing_account = db.scalar(
        select(Account).where(
            Account.email == email
        )
    )

    if existing_account is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email đã được đăng ký.",
        )

    # Băm mật khẩu trước khi đưa vào Database.
    hashed_password = hash_password(
        payload.password
    )

    # Tạo Account mới từ dữ liệu hợp lệ.
    account = Account(
        email=email,
        password_hash=hashed_password,
        display_name=payload.display_name,
    )

    # Đưa Account vào Session để chuẩn bị lưu.
    db.add(account)

    try:
        # Xác nhận giao dịch và lưu Account.
        db.commit()

    except IntegrityError:
        # Hủy giao dịch lỗi để phục hồi Session.
        db.rollback()

        # Kiểm tra trường hợp email bị đăng ký đồng thời.
        duplicate_account_id = db.scalar(
            select(Account.account_id).where(
                Account.email == email
            )
        )

        if duplicate_account_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email đã được đăng ký.",
            )

        # Nếu không phải email trùng thì chuyển lỗi lên trên.
        raise

    # Đọc lại thông tin sau khi Database tạo account_id.
    db.refresh(account)

    # FastAPI trả về dữ liệu theo AccountResponse.
    return account


# =========================================================
# 2. API ĐĂNG NHẬP TÀI KHOẢN
# =========================================================

@router.post(
    "/login",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
)
def login_account(
    payload: AccountLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Đăng nhập bằng email và mật khẩu.

    Quy trình xử lý:
    1. Chuẩn hóa email.
    2. Tìm Account trong Database.
    3. Kiểm tra mật khẩu bằng Argon2id.
    4. Tạo JWT Access Token có thời hạn 30 phút.
    5. Trả JWT cho Client nếu xác thực thành công.
    """

    # Chuẩn hóa email giống với bước đăng ký.
    email = str(payload.email).strip().lower()

    # Tìm tài khoản theo email.
    account = db.scalar(
        select(Account).where(
            Account.email == email
        )
    )

    # Sử dụng chung một thông báo khi đăng nhập thất bại.
    # Không tiết lộ email có tồn tại trong Database hay không.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email hoặc mật khẩu không chính xác.",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    # Nếu không tìm thấy tài khoản, từ chối đăng nhập.
    if account is None:
        raise invalid_credentials

    # Tài khoản seed cũ có thể chứa hash giả để học Database.
    # Chỉ chấp nhận định dạng hash Argon2id ở phiên bản này.
    if not account.password_hash.startswith("$argon2id$"):
        raise invalid_credentials

    # Kiểm tra mật khẩu gốc với mã băm trong Database.
    password_is_valid = verify_password(
        payload.password,
        account.password_hash,
    )

    if not password_is_valid:
        raise invalid_credentials

    # Chỉ phát hành JWT sau khi xác minh mật khẩu thành công.
    access_token = create_access_token(
        account_id=account.account_id
    )

    # Trả Access Token và thời gian hết hạn tính bằng giây.
    # Không gửi mật khẩu hoặc password_hash về Client.
    return AccessTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
