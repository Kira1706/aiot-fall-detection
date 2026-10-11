
from datetime import datetime, timedelta, timezone

import jwt

from jwt_utils import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_SECRET_KEY,
    create_access_token,
    decode_access_token,
)


def run_demo():
    """Kiểm thử chức năng tạo và xác minh JWT Access Token."""

    # =====================================================
    # TEST 1: Tạo và kiểm tra JWT hợp lệ.
    # =====================================================

    # Sử dụng Account ID giả lập để kiểm thử.
    # Chưa cần truy vấn tài khoản từ Database.
    account_id = 1

    token = create_access_token(
        account_id=account_id
    )

    # Kiểm tra và đọc payload đã được xác minh.
    payload = decode_access_token(token)

    # Account ID trong token phải khớp giá trị ban đầu.
    assert payload["sub"] == str(account_id)

    # Thời hạn phải bằng đúng 30 phút.
    token_duration = (
        payload["exp"] - payload["iat"]
    )

    assert token_duration == (
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    print("[PASS] JWT hợp lệ, thời hạn 30 phút")


    # =====================================================
    # TEST 2: Token bị thay đổi chữ ký.
    # =====================================================

    # Thay phần chữ ký bằng giá trị không hợp lệ.
    # Không sử dụng token này để xác thực thật.
    tampered_token = (
        token.rsplit(".", 1)[0]
        + ".invalidsignature"
    )

    try:
        decode_access_token(tampered_token)

    except jwt.InvalidSignatureError:
        print("[PASS] Token sai chữ ký bị từ chối")

    else:
        raise AssertionError(
            "LỖI: Token sai chữ ký được chấp nhận."
        )


    # =====================================================
    # TEST 3: Token đã hết hạn.
    # =====================================================

    now = datetime.now(timezone.utc)

    # Tạo một token có thời gian hết hạn trong quá khứ.
    expired_payload = {
        "sub": str(account_id),
        "iat": now - timedelta(minutes=31),
        "exp": now - timedelta(minutes=1),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "token_use": "access",
    }

    expired_token = jwt.encode(
        expired_payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

    try:
        decode_access_token(expired_token)

    except jwt.ExpiredSignatureError:
        print("[PASS] Token hết hạn bị từ chối")

    else:
        raise AssertionError(
            "LỖI: Token hết hạn được chấp nhận."
        )


    # =====================================================
    # TEST 4: Token thiếu trường hết hạn.
    # =====================================================

    # Tạo payload không có trường exp.
    invalid_payload = {
        "sub": str(account_id),
        "iat": now,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "token_use": "access",
    }

    invalid_token = jwt.encode(
        invalid_payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

    try:
        decode_access_token(invalid_token)

    except jwt.MissingRequiredClaimError:
        print("[PASS] Token thiếu exp bị từ chối")

    else:
        raise AssertionError(
            "LỖI: Token thiếu exp được chấp nhận."
        )


    # =====================================================
    # TỔNG KẾT KẾT QUẢ KIỂM THỬ.
    # =====================================================

    print("\nJWT FOUNDATION TEST: PASS")


if __name__ == "__main__":
    run_demo()
