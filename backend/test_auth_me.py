
"""Kiểm thử API lấy thông tin tài khoản đang đăng nhập."""

from datetime import datetime, timedelta, timezone

import jwt

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from database import SessionLocal
from jwt_utils import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_SECRET_KEY,
    create_access_token,
)
from main import app
from models import Account


# Email demo phải được đăng ký trước bằng Register API.
TEST_EMAIL = "caregiver.test@example.com"

# Endpoint cần kiểm thử.
API_URL = "/auth/me"


def run_tests():
    """
    Kiểm thử API được bảo vệ bằng JWT Bearer.

    Bao gồm:
    - Token hợp lệ.
    - Không có token.
    - Sai phương thức xác thực.
    - Token sai chữ ký.
    - Token hết hạn.
    - Account trong token không tồn tại.
    - Response không làm lộ password_hash.
    """

    # =====================================================
    # 1. LẤY TÀI KHOẢN DEMO TỪ DATABASE
    # =====================================================

    with SessionLocal() as db:

        # Tìm tài khoản đã được đăng ký trước đó.
        account = db.scalar(
            select(Account).where(
                Account.email == TEST_EMAIL
            )
        )

        assert account is not None, (
            "Không tìm thấy tài khoản demo. "
            "Hãy đăng ký tài khoản trước khi chạy test."
        )

        # Lưu thông tin cần kiểm tra trước khi đóng Session.
        expected_account_id = account.account_id
        expected_email = account.email
        expected_display_name = account.display_name

        # Tìm một ID lớn hơn tất cả Account ID hiện tại.
        # Dùng để kiểm thử tài khoản không tồn tại.
        highest_id = db.scalar(
            select(func.max(Account.account_id))
        ) or 0

        nonexistent_account_id = highest_id + 1000

    # Tạo JWT hợp lệ cho Account demo.
    valid_token = create_access_token(
        expected_account_id
    )

    # Sử dụng ứng dụng FastAPI thật, không cần bật Uvicorn.
    with TestClient(app) as client:

        # =================================================
        # TEST 1: TOKEN HỢP LỆ
        # =================================================

        response = client.get(
            API_URL,
            headers={
                "Authorization": f"Bearer {valid_token}"
            },
        )

        assert response.status_code == 200

        response_data = response.json()

        # Account trả về phải khớp với Account trong JWT.
        assert response_data["account_id"] == (
            expected_account_id
        )

        assert response_data["email"] == expected_email

        assert response_data["display_name"] == (
            expected_display_name
        )

        # Response không được chứa thông tin mật khẩu.
        assert "password" not in response_data
        assert "password_hash" not in response_data

        print(
            "[PASS] JWT hợp lệ trả đúng Account và HTTP 200"
        )


        # =================================================
        # TEST 2: KHÔNG GỬI TOKEN
        # =================================================

        response = client.get(API_URL)

        assert response.status_code == 401

        assert response.headers.get(
            "www-authenticate"
        ) == "Bearer"

        print("[PASS] Thiếu Token trả HTTP 401")


        # =================================================
        # TEST 3: SAI PHƯƠNG THỨC XÁC THỰC
        # =================================================

        response = client.get(
            API_URL,
            headers={
                "Authorization": f"Basic {valid_token}"
            },
        )

        assert response.status_code == 401

        print(
            "[PASS] Sai Authentication Scheme trả HTTP 401"
        )


        # =================================================
        # TEST 4: TOKEN SAI CHỮ KÝ
        # =================================================

        # Thay chữ ký của JWT bằng giá trị không hợp lệ.
        invalid_signature_token = (
            valid_token.rsplit(".", 1)[0]
            + ".invalidsignature"
        )

        response = client.get(
            API_URL,
            headers={
                "Authorization": (
                    f"Bearer {invalid_signature_token}"
                )
            },
        )

        assert response.status_code == 401

        print("[PASS] Token sai chữ ký trả HTTP 401")


        # =================================================
        # TEST 5: TOKEN ĐÃ HẾT HẠN
        # =================================================

        now = datetime.now(timezone.utc)

        # Tạo JWT có thời điểm hết hạn trong quá khứ.
        expired_token = jwt.encode(
            {
                "sub": str(expected_account_id),
                "iat": now - timedelta(minutes=31),
                "exp": now - timedelta(minutes=1),
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "token_use": "access",
            },
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )

        response = client.get(
            API_URL,
            headers={
                "Authorization": f"Bearer {expired_token}"
            },
        )

        assert response.status_code == 401

        print("[PASS] Token hết hạn trả HTTP 401")


        # =================================================
        # TEST 6: TOKEN HỢP LỆ NHƯNG ACCOUNT KHÔNG TỒN TẠI
        # =================================================

        # Tạo JWT hợp lệ về chữ ký cho Account ID chưa tồn tại.
        nonexistent_account_token = create_access_token(
            nonexistent_account_id
        )

        response = client.get(
            API_URL,
            headers={
                "Authorization": (
                    f"Bearer {nonexistent_account_token}"
                )
            },
        )

        assert response.status_code == 401

        print(
            "[PASS] Account không tồn tại trả HTTP 401"
        )


        # =================================================
        # TEST 7: KIỂM TRA TRƯỜNG DỮ LIỆU RESPONSE
        # =================================================

        response = client.get(
            API_URL,
            headers={
                "Authorization": f"Bearer {valid_token}"
            },
        )

        assert response.status_code == 200

        # Chỉ chấp nhận ba trường được định nghĩa trong
        # AccountResponse của Milestone 3.2.
        expected_fields = {
            "account_id",
            "email",
            "display_name",
        }

        assert set(response.json().keys()) == (
            expected_fields
        )

        print(
            "[PASS] Response chỉ chứa các trường được phép"
        )

    # =====================================================
    # KẾT LUẬN KIỂM THỬ
    # =====================================================

    print("\nAUTH ME API TEST: PASS")


if __name__ == "__main__":
    run_tests()
