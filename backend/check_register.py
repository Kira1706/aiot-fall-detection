
from sqlalchemy import select

from database import SessionLocal
from models import Account
from password_utils import verify_password


# Đây là tài khoản demo đã đăng ký qua Swagger UI.
# Tuyệt đối không sử dụng thông tin đăng nhập thật ở đây.
TEST_EMAIL = "caregiver.test@example.com"
TEST_PASSWORD = "DemoPass@2026!"


def check_registered_account():
    """
    Kiểm tra tài khoản demo đã được lưu đúng trong Database.

    Các điều kiện cần đạt:
    - Account tồn tại.
    - Mật khẩu không được lưu dưới dạng gốc.
    - Mã băm sử dụng Argon2id.
    - Mật khẩu đúng được chấp nhận.
    - Mật khẩu sai bị từ chối.
    """

    with SessionLocal() as db:

        # Tìm Account đã tạo thông qua Register API.
        account = db.scalar(
            select(Account).where(
                Account.email == TEST_EMAIL
            )
        )

        # Tài khoản phải tồn tại.
        assert account is not None, (
            "Không tìm thấy tài khoản demo trong Database."
        )

        # Database không được lưu mật khẩu gốc.
        assert account.password_hash != TEST_PASSWORD, (
            "Mật khẩu đang được lưu không an toàn."
        )

        # Kiểm tra định dạng mã băm Argon2id.
        assert account.password_hash.startswith(
            "$argon2id$"
        ), "Mã băm không đúng định dạng Argon2id."

        # Kiểm tra mật khẩu đúng.
        correct_result = verify_password(
            TEST_PASSWORD,
            account.password_hash,
        )

        assert correct_result is True, (
            "Không xác minh được mật khẩu đúng."
        )

        # Kiểm tra mật khẩu sai.
        wrong_result = verify_password(
            "WrongPassword123!",
            account.password_hash,
        )

        assert wrong_result is False, (
            "Mật khẩu sai không bị từ chối."
        )

        print("Account ID:", account.account_id)
        print("Email:", account.email)
        print("Display name:", account.display_name)

        # Chỉ in kết quả kiểm tra, không in mã băm mật khẩu.
        print("Argon2id hash:", "PASS")
        print("Correct password:", correct_result)
        print("Wrong password:", wrong_result)

        print("\nREGISTER DATABASE TEST: PASS")


if __name__ == "__main__":
    check_registered_account()
