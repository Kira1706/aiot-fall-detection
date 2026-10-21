"""API quản trị phiên bản AI model và API tải model cho ESP32."""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from device_auth import require_device_key
from model_auth import require_model_admin_key
from model_schemas import (
    EdgeModelManifest,
    ModelReleaseInfo,
    ModelVersionInfo,
    PublishModelRequest,
)
from model_storage import (
    artifact_absolute_path,
    artifact_relative_path,
    get_model_directory,
    inspect_model_file,
    save_model_upload,
)
from models import Device, ModelRelease, ModelVersion


admin_router = APIRouter(
    prefix="/model-admin",
    tags=["Model Management"],
    dependencies=[Depends(require_model_admin_key)],
)

edge_router = APIRouter(
    prefix="/device-ingest",
    tags=["Device Model Updates"],
)


def verified_artifact(model: ModelVersion, root: Path) -> Path:
    """Chỉ chấp nhận model có metadata và file còn đúng SHA-256."""
    if not model.sha256 or model.size_bytes is None or model.size_bytes <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Model cũ chưa có SHA-256/size để phát hành.",
        )
    path = artifact_absolute_path(root, model.version, model.file_path)
    inspect_model_file(path, model.sha256, model.size_bytes)
    return path


def current_release(db: Session) -> tuple[ModelRelease | None, ModelVersion | None]:
    """Lấy phiên bản được phát hành chung, nếu đã thiết lập."""
    row = db.get(ModelRelease, 1)
    if row is None:
        return None, None
    model = db.get(ModelVersion, row.version)
    if model is None:
        raise HTTPException(status_code=503, detail="Phiên bản phát hành không tồn tại.")
    return row, model


@admin_router.post(
    "/models",
    response_model=ModelVersionInfo,
    status_code=status.HTTP_201_CREATED,
)
async def upload_model(
    version: str = Form(
        ..., min_length=1, max_length=50,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    root: Path = Depends(get_model_directory),
):
    """Đăng ký file TFLite bất biến theo một version duy nhất."""
    if db.get(ModelVersion, version) is not None:
        raise HTTPException(status_code=409, detail="Model Version đã tồn tại.")

    path, sha256, size_bytes = await save_model_upload(file, root, version)
    model = ModelVersion(
        version=version,
        file_path=artifact_relative_path(version),
        created_at=datetime.now(timezone.utc),
        sha256=sha256,
        size_bytes=size_bytes,
    )

    try:
        db.add(model)
        db.commit()
        db.refresh(model)
    except IntegrityError as error:
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Model Version đã tồn tại.") from error
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise

    return ModelVersionInfo(
        version=model.version,
        sha256=model.sha256,
        size_bytes=model.size_bytes,
        created_at=model.created_at,
        is_published=False,
    )


@admin_router.get("/models", response_model=list[ModelVersionInfo])
def list_models(db: Session = Depends(get_db)):
    """Liệt kê phiên bản model; bản cũ có thể thiếu metadata."""
    release, _ = current_release(db)
    models = db.scalars(
        select(ModelVersion).order_by(ModelVersion.created_at.desc(), ModelVersion.version)
    ).all()
    return [
        ModelVersionInfo(
            version=m.version,
            sha256=m.sha256,
            size_bytes=m.size_bytes,
            created_at=m.created_at,
            is_published=bool(release and release.version == m.version),
        )
        for m in models
    ]


@admin_router.put("/releases/current", response_model=ModelReleaseInfo)
def publish_model(
    payload: PublishModelRequest,
    db: Session = Depends(get_db),
    root: Path = Depends(get_model_directory),
):
    """Đặt phiên bản model phát hành hiện hành sau khi xác minh file."""
    model = db.get(ModelVersion, payload.version)
    if model is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy Model Version.")

    verified_artifact(model, root)
    release = db.get(ModelRelease, 1)
    now = datetime.now(timezone.utc)
    if release is None:
        release = ModelRelease(release_id=1, version=model.version, updated_at=now)
        db.add(release)
    else:
        release.version = model.version
        release.updated_at = now

    try:
        db.commit()
        db.refresh(release)
    except Exception:
        db.rollback()
        raise

    return ModelReleaseInfo(
        target_version=model.version,
        sha256=model.sha256,
        size_bytes=model.size_bytes,
        updated_at=release.updated_at,
    )


@admin_router.get("/releases/current", response_model=ModelReleaseInfo)
def get_published_model(db: Session = Depends(get_db)):
    """Trả version hiện hành hoặc null nếu chưa phát hành."""
    release, model = current_release(db)
    return ModelReleaseInfo(
        target_version=model.version if model else None,
        sha256=model.sha256 if model else None,
        size_bytes=model.size_bytes if model else None,
        updated_at=release.updated_at if release else None,
    )


@edge_router.get(
    "/{device_id}/model-manifest",
    response_model=EdgeModelManifest,
)
def get_edge_model_manifest(
    device_id: str = Depends(require_device_key),
    db: Session = Depends(get_db),
    root: Path = Depends(get_model_directory),
):
    """ESP32 xác minh Device Key trước khi nhận metadata model hiện hành."""
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thiết bị.")

    _, model = current_release(db)
    if model is not None:
        verified_artifact(model, root)

    needs_update = bool(model and device.model_version != model.version)
    return EdgeModelManifest(
        device_id=device.device_id,
        installed_version=device.model_version,
        target_version=model.version if model else None,
        update_available=needs_update,
        sha256=model.sha256 if model else None,
        size_bytes=model.size_bytes if model else None,
        download_path=(
            f"/device-ingest/{device.device_id}/models/{model.version}/download"
            if needs_update and model else None
        ),
    )


@edge_router.get("/{device_id}/models/{version}/download")
def download_edge_model(
    version: str,
    device_id: str = Depends(require_device_key),
    db: Session = Depends(get_db),
    root: Path = Depends(get_model_directory),
):
    """Chỉ cho Device đã xác thực tải phiên bản đang phát hành."""
    if db.get(Device, device_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thiết bị.")

    _, model = current_release(db)
    if model is None or version != model.version:
        raise HTTPException(status_code=404, detail="Phiên bản này chưa được phát hành.")

    path = verified_artifact(model, root)
    return FileResponse(
        path,
        filename=f"{model.version}.tflite",
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Model-SHA256": model.sha256,
        },
    )
