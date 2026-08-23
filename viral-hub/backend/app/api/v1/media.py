"""
API de multimedia — subida de videos e imágenes a Cloudflare R2/S3.

Flujo de subida:
1. POST /media/upload-url  → genera URL pre-firmada para subida directa desde el browser
2. El frontend sube el archivo directamente a R2 (sin pasar por el backend)
3. POST /media/confirm      → confirma la subida, crea MediaAsset en DB

Este patrón evita que archivos grandes pasen por el servidor backend.
"""

import uuid
import mimetypes
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_workspace_member
from app.models.user import User
from app.models.workspace import Membership
from app.models.media import MediaAsset, MediaType, AssetStatus

settings = get_settings()
router = APIRouter(prefix="/workspaces/{workspace_id}/media", tags=["Media"])

ALLOWED_VIDEO_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/webm", "video/mpeg", "video/3gpp",
}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE_BYTES = 4_000_000_000  # 4 GB (límite TikTok)


def _get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
        aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
        region_name="auto",
    )


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str   # alias: mime_type
    file_size: int      # alias: file_size_bytes


class ConfirmUploadRequest(BaseModel):
    asset_id: str           # storage_key del upload
    original_filename: str
    file_size: int          # bytes
    media_type: str         # "video" | "image"
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


@router.get("")
async def list_media(
    workspace_id: int,
    media_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    query = select(MediaAsset).where(
        MediaAsset.workspace_id == workspace_id,
        MediaAsset.status != AssetStatus.archived,
    )
    if media_type:
        query = query.where(MediaAsset.media_type == MediaType(media_type))

    query = query.order_by(MediaAsset.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    assets = result.scalars().all()

    return {"assets": [_asset_to_dict(a) for a in assets], "page": page, "per_page": per_page}


@router.post("/upload-url")
async def get_upload_url(
    workspace_id: int,
    payload: UploadUrlRequest,
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """
    Genera una URL pre-firmada para que el frontend suba directo a R2/S3.
    El archivo nunca pasa por el backend.
    """
    mime_type = payload.content_type

    if mime_type not in ALLOWED_VIDEO_TYPES | ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no soportado: {mime_type}")

    if payload.file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="El archivo supera el límite de 4 GB")

    ext = mimetypes.guess_extension(mime_type) or ""
    storage_key = f"workspaces/{workspace_id}/media/{uuid.uuid4().hex}{ext}"

    if not settings.STORAGE_ACCESS_KEY_ID:
        return {
            "upload_url": None,
            "asset_id": storage_key,
            "message": "STORAGE no configurado — configurar variables STORAGE_* en .env",
        }

    try:
        s3 = _get_s3_client()
        presigned_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.STORAGE_BUCKET,
                "Key": storage_key,
                "ContentType": mime_type,
            },
            ExpiresIn=3600,
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Error generando URL de subida: {e}")

    return {"upload_url": presigned_url, "asset_id": storage_key}


@router.post("/confirm", status_code=status.HTTP_201_CREATED)
async def confirm_upload(
    workspace_id: int,
    payload: ConfirmUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """
    Confirma que el archivo fue subido y crea el MediaAsset en DB.
    """
    storage_key = payload.asset_id
    media_type = MediaType.video if payload.media_type == "video" else MediaType.image

    public_url = None
    if settings.STORAGE_PUBLIC_BASE_URL:
        public_url = f"{settings.STORAGE_PUBLIC_BASE_URL.rstrip('/')}/{storage_key}"

    aspect_ratio = None
    if payload.width and payload.height:
        from math import gcd
        g = gcd(payload.width, payload.height)
        aspect_ratio = f"{payload.width // g}:{payload.height // g}"

    asset = MediaAsset(
        workspace_id=workspace_id,
        uploaded_by_id=current_user.id,
        name=payload.original_filename,
        original_filename=payload.original_filename,
        media_type=media_type,
        status=AssetStatus.ready,
        storage_key=storage_key,
        storage_bucket=settings.STORAGE_BUCKET,
        public_url=public_url,
        file_size_bytes=payload.file_size,
        duration_seconds=payload.duration_seconds,
        width=payload.width,
        height=payload.height,
        aspect_ratio=aspect_ratio,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return _asset_to_dict(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_asset(
    workspace_id: int,
    asset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_workspace_member),
):
    """Archiva (soft-delete) un asset. No elimina del storage."""
    result = await db.execute(
        select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.workspace_id == workspace_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset no encontrado")

    asset.status = AssetStatus.archived
    await db.commit()


def _asset_to_dict(a: MediaAsset) -> dict:
    return {
        "id": a.id,
        "original_filename": a.original_filename,
        "media_type": a.media_type.value,
        "status": a.status.value,
        "public_url": a.public_url,
        "thumbnail_url": a.thumbnail_url,
        "file_size": a.file_size_bytes,   # normalizado para el frontend
        "duration_seconds": a.duration_seconds,
        "width": a.width,
        "height": a.height,
        "aspect_ratio": a.aspect_ratio,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
