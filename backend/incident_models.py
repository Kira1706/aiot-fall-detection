"""ORM bổ sung cho Milestone 10.10; import module này khi khởi động Alembic."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class FallIncidentResolution(Base):
    """Trạng thái xử lý chung của một sự kiện ngã, khác với read_at riêng từng người."""
    __tablename__ = "fall_incident_resolutions"
    __table_args__ = (CheckConstraint("status IN ('acknowledged', 'resolved')", name="ck_incident_resolution_status"),)

    fall_event_id: Mapped[int] = mapped_column(ForeignKey("fall_events.event_id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_by_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
