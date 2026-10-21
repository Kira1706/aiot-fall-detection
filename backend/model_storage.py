"""Lưu và kiểm tra tính toàn vẹn của file TensorFlow Lite."""

import hashlib
import os
from pathlib import Path

from fastapi import HTTPException, UploadFile, status


MODEL_MAX_BYTES = 4 * 1024 * 1024
MODEL_DIRECTORY = Path(__file__).resolve().parent / "model_artifacts"


def get_model_directory() -> Path:
    """Trả thư mục riêng chứa file model; hỗ trợ thay trong test."""
    return MODEL_DIRECTORY


def artifact_relative_path(version: str) -> str:
    """Sinh đường dẫn tương đối cố định, không nhận đường dẫn từ Client."""
    return f"model_artifacts/{version}.tflite"


def artifact_absolute_path(root: Path, version: str, saved_path: str) -> Path:
    """Từ chối file_path cũ hoặc đường dẫn không do hệ thống sinh."""
    if saved_path != artifact_relative_path(version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Model cũ chưa được đăng ký bằng cơ chế kiểm tra mới.",
        )
    resolved_root = root.resolve()
    candidate = resolved_root / f"{version}.tflite"
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(resolved_root):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đường dẫn file model nằm ngoài vùng lưu trữ.",
        )
    return candidate


def inspect_model_file(path: Path, expected_sha256: str, expected_size: int) -> None:
    """Kiểm tra file trên đĩa còn đúng nội dung lúc đăng ký."""
    try:
        with path.open("rb") as stream:
            digest = hashlib.sha256()
            total = 0
            magic = stream.read(8)
            if len(magic) < 8 or magic[4:8] != b"TFL3":
                raise ValueError("Thiếu định dạng TensorFlow Lite cơ bản.")
            stream.seek(0)
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                digest.update(chunk)
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File model không thể đọc hoặc không đúng định dạng.",
        ) from error

    if total != expected_size or digest.hexdigest() != expected_sha256:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File model không khớp SHA-256/size đã đăng ký.",
        )


async def save_model_upload(
    upload: UploadFile,
    root: Path,
    version: str,
) -> tuple[Path, str, int]:
    """Lưu file bằng cách tạo mới độc quyền và giới hạn kích thước."""
    filename = upload.filename or ""
    if not filename.lower().endswith(".tflite"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chỉ nhận file có đuôi .tflite.",
        )

    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{version}.tflite"
    digest = hashlib.sha256()
    total = 0

    try:
        # Chế độ xb từ chối ghi đè file cùng phiên bản.
        with path.open("xb") as output:
            try:
                first = await upload.read(65536)
                if len(first) < 8 or first[4:8] != b"TFL3":
                    raise ValueError("File không có dấu hiệu định dạng TFLite.")
                while first:
                    total += len(first)
                    if total > MODEL_MAX_BYTES:
                        raise ValueError("File model vượt quá giới hạn 4 MiB.")
                    digest.update(first)
                    output.write(first)
                    first = await upload.read(65536)
                output.flush()
                os.fsync(output.fileno())
            except Exception:
                # Xóa file chưa hợp lệ trong khối ngoại lệ bên ngoài.
                raise
    except FileExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đã có file model cùng phiên bản.",
        ) from error
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File TFLite không hợp lệ hoặc vượt giới hạn 4 MiB.",
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise

    return path, digest.hexdigest(), total
