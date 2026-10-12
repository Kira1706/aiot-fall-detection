
import json

from urllib.request import Request, urlopen
from urllib.error import HTTPError

from jwt_utils import (
    decode_access_token,
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
)


# Địa chỉ Login API đang chạy trên máy.
API_URL = "http://127.0.0.1:8000/auth/login"


# Chỉ sử dụng tài khoản demo đã đăng ký bằng Register API.
# Không đưa thông tin đăng nhập thật vào source code.
TEST_EMAIL = "caregiver.test@example.com"
TEST_PASSWORD = "DemoPass@2026!"


def send_login_request(email: str, password: str):
    """
    Gửi HTTP POST request tới Login API.

    Trả về mã HTTP status và nội dung JSON response.
    Không in mật khẩu hoặc Access Token ra Terminal.
    """

    # Tạo dữ liệu JSON gửi lên Backend.
    payload = {
        "email": email,
        "password": password,
    }

    request_body = json.dumps(
        payload
    ).encode("utf-8")

    # Chuẩn bị HTTP POST request.
    request = Request(
        API_URL,
        data=request_body,
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    try:
        # Gửi request và đọc response thành công.
        with urlopen(request, timeout=10) as response:
            body = json.loads(
                response.read().decode("utf-8")
            )

            return response.status, body

    except HTTPError as error:
        # Đọc response khi Backend trả HTTP 4xx hoặc 5xx.
        body = json.loads(
            error.read().decode("utf-8")
        )

        return error.code, body


def run_tests():
    """Kiểm thử các trường hợp chính của Login API."""

    # =====================================================
    # TEST 1: Đăng nhập thành công.
    # =====================================================

    status_code, response = send_login_request(
        TEST_EMAIL,
        TEST_PASSWORD,
    )

    assert status_code == 200
    assert response["token_type"] == "bearer"
    assert response["expires_in"] == 1800
    assert isinstance(response["access_token"], str)

    # Kiểm tra JWT do Backend trả về.
    token_payload = decode_access_token(
        response["access_token"]
    )

    assert int(token_payload["sub"]) > 0

    # Xác nhận thời hạn JWT là 30 phút.
    token_duration = (
        token_payload["exp"] - token_payload["iat"]
    )

    assert token_duration == (
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    # Login Response không được chứa mật khẩu.
    assert "password" not in response
    assert "password_hash" not in response

    print("[PASS] Login hợp lệ trả HTTP 200 và JWT 30 phút")


    # =====================================================
    # TEST 2: Mật khẩu không chính xác.
    # =====================================================

    status_code, response = send_login_request(
        TEST_EMAIL,
        "WrongPassword@2026!",
    )

    assert status_code == 401
    assert response["detail"] == (
        "Email hoặc mật khẩu không chính xác."
    )

    print("[PASS] Sai mật khẩu trả HTTP 401")


    # =====================================================
    # TEST 3: Email không tồn tại.
    # =====================================================

    status_code, response = send_login_request(
        "unknown.caregiver@example.com",
        TEST_PASSWORD,
    )

    assert status_code == 401
    assert response["detail"] == (
        "Email hoặc mật khẩu không chính xác."
    )

    print("[PASS] Email không tồn tại trả HTTP 401")


    # =====================================================
    # TEST 4: Email sai định dạng.
    # =====================================================

    status_code, response = send_login_request(
        "invalid-email",
        TEST_PASSWORD,
    )

    assert status_code == 422

    print("[PASS] Email sai định dạng trả HTTP 422")


    # =====================================================
    # TEST 5: Mật khẩu rỗng.
    # =====================================================

    status_code, response = send_login_request(
        TEST_EMAIL,
        "",
    )

    assert status_code == 422

    print("[PASS] Mật khẩu rỗng trả HTTP 422")


    # =====================================================
    # KẾT LUẬN KIỂM THỬ.
    # =====================================================

    print("\nLOGIN API TEST: PASS")


if __name__ == "__main__":
    run_tests()
