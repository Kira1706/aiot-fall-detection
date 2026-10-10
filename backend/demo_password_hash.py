
from password_utils import hash_password, verify_password


# Sử dụng mật khẩu mẫu dành riêng cho bài kiểm thử.
# Không sử dụng mật khẩu thật của bất kỳ tài khoản nào.
demo_password = "DemoPass@2026!"


# Băm cùng một mật khẩu hai lần để kiểm tra salt ngẫu nhiên.
first_hash = hash_password(demo_password)
second_hash = hash_password(demo_password)


# Kiểm tra hai mã băm được tạo ra.
print("Hai mã băm khác nhau:", first_hash != second_hash)


# Kiểm tra mật khẩu đúng với cả hai mã băm.
correct_password = verify_password(
    demo_password,
    first_hash
)

print("Mật khẩu đúng:", correct_password)


# Kiểm tra trường hợp người dùng nhập sai mật khẩu.
incorrect_password = verify_password(
    "WrongPassword123",
    first_hash
)

print("Mật khẩu sai:", incorrect_password)


# Xác nhận chương trình hoạt động đúng như mong đợi.
assert first_hash != second_hash
assert correct_password is True
assert incorrect_password is False

# Xác nhận mã băm thứ hai cũng kiểm tra được mật khẩu gốc.
assert verify_password(demo_password, second_hash) is True

print("\nPASSWORD HASHING TEST: PASS")
