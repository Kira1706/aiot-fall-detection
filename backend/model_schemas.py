"""Schema phản hồi dành cho quản trị model và thiết bị Edge."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints


# Phiên bản không được chứa ký tự tạo đường dẫn hoặc khoảng trắng.
VersionName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]


class ModelVersionInfo(BaseModel):
    """Thông tin model đã đăng ký, không để lộ đường dẫn file nội bộ."""

    version: str
    sha256: str | None
    size_bytes: int | None
    created_at: datetime
    is_published: bool


class PublishModelRequest(BaseModel):
    """Phiên bản quản trị viên muốn phát hành cho tất cả thiết bị."""

    version: VersionName


class ModelReleaseInfo(BaseModel):
    """Phiên bản model được phát hành chung hiện tại."""

    target_version: str | None
    sha256: str | None
    size_bytes: int | None
    updated_at: datetime | None


class EdgeModelManifest(BaseModel):
    """Manifest để ESP32 quyết định có cần tải model mới không."""

    device_id: str
    installed_version: str | None
    target_version: str | None
    update_available: bool
    sha256: str | None
    size_bytes: int | None
    download_path: str | None
