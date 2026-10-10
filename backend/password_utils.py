
from pwdlib import PasswordHash


# Khởi tạo bộ băm mật khẩu với cấu hình được thư viện khuyến nghị.
# Cấu hình này hiện sử dụng thuật toán Argon2.
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    Chuyển mật khẩu gốc thành mã băm để lưu trong Database.

    Args:
        password: Mật khẩu gốc do người dùng cung cấp.

    Returns:
        Chuỗi mã băm dùng để lưu trong accounts.password_hash.
    """
    return password_hasher.hash(password)


def verify_password(
    password: str,
    hashed_password: str
) -> bool:
    """
    Kiểm tra mật khẩu người dùng nhập có khớp với mã băm không.

    Args:
        password: Mật khẩu người dùng nhập khi đăng nhập.
        hashed_password: Mã băm lấy từ Database.

    Returns:
        True nếu mật khẩu đúng, False nếu sai.
    """
    return password_hasher.verify(
        password,
        hashed_password
    )
