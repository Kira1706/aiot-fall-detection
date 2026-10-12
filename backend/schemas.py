
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class AccountRegisterRequest(BaseModel):
    """
    Kiểm tra dữ liệu đăng ký tài khoản người chăm sóc.

    Email phải hợp lệ.
    Mật khẩu có độ dài từ 8 đến 128 ký tự.
    Tên hiển thị có độ dài từ 1 đến 100 ký tự.
    """

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    display_name: str = Field(
        min_length=1,
        max_length=100,
    )

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        """
        Loại bỏ khoảng trắng ở đầu và cuối tên hiển thị.

        Pydantic sẽ kiểm tra độ dài sau khi chuẩn hóa.
        """

        if isinstance(value, str):
            return value.strip()

        return value


class AccountResponse(BaseModel):
    """
    Quy định dữ liệu tài khoản trả về cho Client.

    Không chứa mật khẩu hoặc mã băm mật khẩu.
    """

    # Cho phép đọc thông tin từ SQLAlchemy object.
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    email: EmailStr
    display_name: str


class AccountLoginRequest(BaseModel):
    """
    Kiểm tra thông tin đăng nhập của người chăm sóc.

    Người dùng chỉ cần cung cấp email và mật khẩu.
    """

    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class AccessTokenResponse(BaseModel):
    """
    Quy định dữ liệu trả về sau khi đăng nhập thành công.

    Access Token được sử dụng để xác thực các request
    tiếp theo gửi đến Backend.
    """

    access_token: str

    token_type: Literal["bearer"] = "bearer"

    expires_in: int
