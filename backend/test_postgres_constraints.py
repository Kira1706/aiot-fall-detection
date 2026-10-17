
"""Kiểm thử ràng buộc PostgreSQL mà không lưu dữ liệu thử nghiệm."""

from uuid import uuid4

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from database import engine
from models import Account, AccountDevice


def test_duplicate_email():
    """UNIQUE phải ngăn hai Account có cùng email."""

    # Sinh email ngẫu nhiên để tránh trùng dữ liệu thật.
    email = (
        f"qa-{uuid4().hex}@example.com"
    )

    with engine.connect() as conn:

        tx = conn.begin()

        try:
            values = {
                "email": email,
                "password_hash": (
                    "hash-chi-dung-cho-kiem-thu"
                ),
                "display_name": "Tài khoản kiểm thử",
            }

            # Thêm Account thử nghiệm lần đầu.
            conn.execute(
                insert(Account.__table__).values(
                    **values
                )
            )

            try:
                # Thêm lần hai với cùng email.
                conn.execute(
                    insert(Account.__table__).values(
                        **values
                    )
                )

            except IntegrityError:
                print(
                    "[PASS] PostgreSQL chặn email trùng"
                )

            else:
                raise AssertionError(
                    "UNIQUE email không hoạt động."
                )

        finally:
            # Không giữ lại Account thử nghiệm.
            tx.rollback()


def test_foreign_key():
    """
    Khóa ngoại phải chặn liên kết tới
    Account và Device không tồn tại.
    """

    with engine.connect() as conn:

        tx = conn.begin()

        try:
            try:
                # Chủ động sử dụng các khóa không tồn tại.
                conn.execute(
                    insert(
                        AccountDevice.__table__
                    ).values(
                        account_id=2147483647,
                        device_id="DEVICE-KHONG-TON-TAI",
                        display_name="Kiểm thử",
                    )
                )

            except IntegrityError:
                print(
                    "[PASS] PostgreSQL chặn khóa ngoại sai"
                )

            else:
                raise AssertionError(
                    "FOREIGN KEY không hoạt động."
                )

        finally:
            # Không lưu liên kết thử nghiệm.
            tx.rollback()


def main():
    """Kiểm thử hai ràng buộc cơ bản trên PostgreSQL."""

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Chỉ chạy bài này khi DB_BACKEND=postgresql."
        )

    test_duplicate_email()
    test_foreign_key()

    print(
        "POSTGRESQL CONSTRAINT TEST: PASS"
    )


if __name__ == "__main__":
    main()
