
from sqlalchemy import String, ForeignKey, DateTime, Float
from datetime import datetime
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


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    model_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )


class AccountDevice(Base):
    __tablename__ = "account_devices"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.account_id"),
        primary_key=True,
        nullable=False
    )

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id"),
        primary_key=True,
        nullable=False
    )

    display_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )


class FallEvent(Base):
    __tablename__ = "fall_events"

    event_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id"),
        nullable=False
    )

    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    event_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    model_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )
