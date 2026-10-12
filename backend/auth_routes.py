
"""Các API đăng ký, đăng nhập và xác thực người chăm sóc."""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth_dependencies import get_current_account
from database import get_db
from jwt_utils import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
)
from models import Account
from password_utils import (
    hash_password,
    verify_password,
)
from schemas import (
    AccountLoginRequest,
    AccountRegisterRequest,
    AccountResponse,
    AccessTokenResponse,
)


# Gom các API xác thực vào nhóm có tiền tố /auth.
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# =========================================================
# 1. ĐĂNG KÝ TÀI KHOẢN
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
    Đăng ký tài khoản người chăm sóc.

    Mật khẩu được băm bằng Argon2id trước khi lưu.
    Không trả mật khẩu hoặc mã băm về Client.
    """

    # Chuẩn hóa email trước khi kiểm tra và lưu.
    email = str(payload.email).strip().lower()

    # Tìm tài khoản đã sử dụng email này.
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

    # Chuyển mật khẩu gốc thành mã băm.
    hashed_password = hash_password(
        payload.password
    )

    # Tạo đối tượng Account mới.
    account = Account(
        email=email,
        password_hash=hashed_password,
        display_name=payload.display_name,
    )

    db.add(account)

    try:
        # Ghi dữ liệu và xác nhận giao dịch.
        db.commit()

    except IntegrityError:
        # Hủy giao dịch thất bại để có thể truy vấn tiếp.
        db.rollback()

        # Kiểm tra trường hợp email được đăng ký đồng thời.
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

        # Chuyển tiếp lỗi nếu không phải trường hợp email trùng.
        raise

    # Đọc lại Account sau khi lưu thành công.
    db.refresh(account)

    # Chỉ trả các trường có trong AccountResponse.
    return account


# =========================================================
# 2. ĐĂNG NHẬP TÀI KHOẢN
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
    Xác minh thông tin đăng nhập của người chăm sóc.

    Nếu thành công, tạo JWT Access Token có hạn 30 phút.
    """

    # Chuẩn hóa email giống với API đăng ký.
    email = str(payload.email).strip().lower()

    # Tìm tài khoản theo email.
    account = db.scalar(
        select(Account).where(
            Account.email == email
        )
    )

    # Sử dụng một thông báo chung khi xác thực thất bại.
    # Không tiết lộ email có tồn tại trong Database hay không.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email hoặc mật khẩu không chính xác.",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    if account is None:
        raise invalid_credentials

    # Không cho phép đăng nhập bằng mã băm giả của dữ liệu seed.
    if not account.password_hash.startswith("$argon2id$"):
        raise invalid_credentials

    # Xác minh mật khẩu gốc với mã băm trong Database.
    password_is_valid = verify_password(
        payload.password,
        account.password_hash,
    )

    if not password_is_valid:
        raise invalid_credentials

    # Chỉ cấp JWT sau khi xác thực mật khẩu thành công.
    access_token = create_access_token(
        account_id=account.account_id
    )

    # Trả JWT và thời gian hết hạn tính bằng giây.
    return AccessTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# =========================================================
# 3. LẤY THÔNG TIN TÀI KHOẢN ĐANG ĐĂNG NHẬP
# =========================================================

@router.get(
    "/me",
    response_model=AccountResponse,
    status_code=status.HTTP_200_OK,
)
def get_my_account(
    current_account: Account = Depends(
        get_current_account
    ),
):
    """
    Trả về thông tin của người chăm sóc đang đăng nhập.

    Quy trình:
    1. FastAPI đọc Bearer Token từ request.
    2. Dependency kiểm tra JWT và tìm Account trong Database.
    3. Nếu xác thực thành công, trả thông tin Account.
    4. Không trả mật khẩu hoặc mã băm mật khẩu.

    Nếu xác thực thất bại, dependency trả HTTP 401
    trước khi hàm này được thực thi.
    """

    # Account được lấy từ JWT đã xác minh và Database.
    # Không nhận Account ID do Client tự nhập.
    return current_account
