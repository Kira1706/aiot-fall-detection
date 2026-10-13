
"""Theo dõi heartbeat thiết bị trong bộ nhớ của Backend."""

import time

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Callable


# Chu kỳ gửi heartbeat đề xuất cho ESP32.
HEARTBEAT_INTERVAL_SECONDS = 15

# Quá thời gian này mà không có heartbeat mới thì offline.
HEARTBEAT_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class HeartbeatRecord:
    """Thời điểm Server nhận heartbeat gần nhất."""

    monotonic_time: float
    received_at: datetime


@dataclass(frozen=True)
class DeviceLiveness:
    """Trạng thái kết nối được tính tại thời điểm truy vấn."""

    status: str
    last_seen_at: datetime | None


class HeartbeatStore:
    """Lưu heartbeat và tính online/offline an toàn giữa các luồng."""

    def __init__(
        self,
        timeout_seconds: int = HEARTBEAT_TIMEOUT_SECONDS,
        clock: Callable[[], float] | None = None,
    ):
        # Thời gian chờ trước khi kết luận thiết bị offline.
        self.timeout_seconds = timeout_seconds

        # Cho phép thay đồng hồ khi kiểm thử timeout.
        self._clock = (
            clock if clock is not None
            else time.monotonic
        )

        # Mỗi Device ID chỉ lưu heartbeat mới nhất.
        self._records: dict[str, HeartbeatRecord] = {}

        # Khóa giúp nhiều request không sửa dữ liệu cùng lúc.
        self._lock = Lock()

    def record(self, device_id: str) -> datetime:
        """
        Ghi nhận heartbeat mới từ một Device.

        Sử dụng thời gian Server, không tin thời gian ESP32 gửi.
        """

        now = HeartbeatRecord(
            monotonic_time=self._clock(),
            received_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._records[device_id] = now

        return now.received_at

    def snapshot(self, device_id: str) -> DeviceLiveness:
        """
        Trả trạng thái kết nối và heartbeat cuối cùng.

        Nếu chưa nhận heartbeat thì trả offline.
        Nếu quá timeout thì trả offline.
        """

        # Lấy bản ghi mới nhất trong vùng được bảo vệ.
        with self._lock:
            record = self._records.get(device_id)

        if record is None:
            return DeviceLiveness(
                status="offline",
                last_seen_at=None,
            )

        # Tính số giây đã trôi qua từ heartbeat cuối.
        elapsed = self._clock() - record.monotonic_time

        # Tại đúng ngưỡng timeout vẫn xem là online.
        online = (
            0 <= elapsed <= self.timeout_seconds
        )

        return DeviceLiveness(
            status="online" if online else "offline",
            last_seen_at=record.received_at,
        )


# Một bộ lưu heartbeat chung cho tiến trình Backend.
heartbeat_store = HeartbeatStore()


def get_heartbeat_store() -> HeartbeatStore:
    """
    Cung cấp bộ lưu heartbeat cho FastAPI Dependency.

    Sau này có thể thay phần lưu trữ bằng Redis.
    """

    return heartbeat_store
