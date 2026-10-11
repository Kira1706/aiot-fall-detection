from pwdlib import PasswordHash


# Khởi tạo công cụ băm mật khẩu bằng cấu hình được khuyến nghị.
# Thuật toán được sử dụng hiện tại là Argon2.
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    Chuyển mật khẩu gốc thành mã băm an toàn.

    Mã băm được sử dụng để lưu vào Database.
    Không lưu trực tiếp mật khẩu người dùng.
    """

    return password_hasher.hash(password)


def verify_password(
    password: str,
    hashed_password: str,
) -> bool:
    """
    Kiểm tra mật khẩu người dùng nhập có chính xác hay không.

    Trả về True nếu mật khẩu đúng.
    Trả về False nếu mật khẩu sai.
    """

    return password_hasher.verify(
        password,
        hashed_password,
    )