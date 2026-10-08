
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
