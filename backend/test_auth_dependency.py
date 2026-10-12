
"""Kiểm tra dependency xác thực bằng API thử nghiệm tạm thời."""

from datetime import datetime, timedelta, timezone

import jwt

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from auth_dependencies import get_current_account
from database import SessionLocal
from jwt_utils import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_SECRET_KEY,
    create_access_token,
)
from models import Account


# Tạo ứng dụng chỉ dùng trong bài kiểm thử.
# Không đăng ký endpoint này vào Backend chính.
test_app = FastAPI()


@test_app.get("/_test/protected")
def protected(
    account: Account = Depends(get_current_account)
):
    """
    Trả thông tin Account khi token đã được xác minh.

    Endpoint này chỉ phục vụ kiểm thử Dependency.
    """

    return {
        "account_id": account.account_id,
        "email": account.email,
    }


def run_tests():
    """Kiểm tra các tình huống xác thực Bearer JWT."""

    # Lấy tài khoản demo đã được đăng ký từ trước.
    with SessionLocal() as db:

        account = db.scalar(
            select(Account).where(
                Account.email == "caregiver.test@example.com"
            )
        )

        assert account is not None, (
            "Hãy đăng ký caregiver.test@example.com trước."
        )

        account_id = account.account_id

        # Tìm một Account ID chắc chắn chưa tồn tại.
        highest_id = db.scalar(
            select(func.max(Account.account_id))
        ) or 0

        not_found_id = highest_id + 1

    # Tạo Access Token hợp lệ cho tài khoản demo.
    valid_token = create_access_token(account_id)

    test_url = "/_test/protected"

    with TestClient(test_app) as client:

        # =================================================
        # TEST 1: JWT hợp lệ.
        # =================================================

        response = client.get(
            test_url,
            headers={
                "Authorization": f"Bearer {valid_token}"
            },
        )

        assert response.status_code == 200
        assert response.json()["account_id"] == account_id

        print("[PASS] JWT hợp lệ được chấp nhận")


        # =================================================
        # TEST 2: Không gửi Token.
        # =================================================

        response = client.get(test_url)

        assert response.status_code == 401

        assert response.headers["www-authenticate"] == (
            "Bearer"
        )

        print("[PASS] Thiếu Token trả HTTP 401")


        # =================================================
        # TEST 3: Sai phương thức xác thực.
        # =================================================

        response = client.get(
            test_url,
            headers={
                "Authorization": f"Basic {valid_token}"
            },
        )

        assert response.status_code == 401

        print("[PASS] Sai Bearer scheme trả HTTP 401")


        # =================================================
        # TEST 4: JWT sai chữ ký.
        # =================================================

        bad_signature = (
            valid_token.rsplit(".", 1)[0]
            + ".invalidsignature"
        )

        response = client.get(
            test_url,
            headers={
                "Authorization": f"Bearer {bad_signature}"
            },
        )

        assert response.status_code == 401

        print("[PASS] Token sai chữ ký trả HTTP 401")


        # =================================================
        # TEST 5: JWT đã hết hạn.
        # =================================================

        now = datetime.now(timezone.utc)

        expired_token = jwt.encode(
            {
                "sub": str(account_id),
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
            test_url,
            headers={
                "Authorization": f"Bearer {expired_token}"
            },
        )

        assert response.status_code == 401

        print("[PASS] Token hết hạn trả HTTP 401")


        # =================================================
        # TEST 6: Token hợp lệ nhưng Account không tồn tại.
        # =================================================

        removed_account_token = create_access_token(
            not_found_id
        )

        response = client.get(
            test_url,
            headers={
                "Authorization": (
                    f"Bearer {removed_account_token}"
                )
            },
        )

        assert response.status_code == 401

        print(
            "[PASS] Account không tồn tại trả HTTP 401"
        )


    # =====================================================
    # KẾT LUẬN.
    # =====================================================

    print("\nAUTH DEPENDENCY TEST: PASS")


if __name__ == "__main__":
    run_tests()
