from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class AccountRegisterRequest(BaseModel):
    """
    Kiểm tra thông tin người chăm sóc gửi lên khi đăng ký.

    Email phải có định dạng hợp lệ.
    Mật khẩu phải có độ dài từ 8 đến 128 ký tự.
    Tên hiển thị phải có độ dài từ 1 đến 100 ký tự.
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
        Loại bỏ khoảng trắng thừa ở đầu và cuối tên hiển thị.

        Việc kiểm tra độ dài được Pydantic thực hiện
        sau khi tên đã được chuẩn hóa.
        """

        if isinstance(value, str):
            return value.strip()

        return value


class AccountResponse(BaseModel):
    """
    Quy định thông tin tài khoản được phép trả về cho Client.

    Không trả về mật khẩu gốc hoặc mã băm mật khẩu.
    """

    # Cho phép đọc dữ liệu trực tiếp từ SQLAlchemy object.
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    email: EmailStr
    display_name: str