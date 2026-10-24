import hashlib
import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import StoredFile


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
PROFILE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def read_valid_upload(upload: UploadFile, allowed_types: set[str], maximum: int = MAX_UPLOAD_BYTES) -> bytes:
    if upload.content_type not in allowed_types:
        raise HTTPException(415, "Unsupported file type")
    content = await upload.read(maximum + 1)
    if not content:
        raise HTTPException(422, "Uploaded file is empty")
    if len(content) > maximum:
        raise HTTPException(413, "Uploaded file is too large")
    signatures = {
        "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
        "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": lambda data: len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        "application/pdf": lambda data: data.startswith(b"%PDF-"),
    }
    if not signatures[upload.content_type](content):
        raise HTTPException(415, "File content does not match its declared type")
    return content


async def store_business_file(
    db: AsyncSession,
    upload: UploadFile,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    purpose: str,
    expires_at: datetime | None = None,
) -> StoredFile:
    content = await read_valid_upload(upload, set(ALLOWED_CONTENT_TYPES))
    extension = ALLOWED_CONTENT_TYPES[upload.content_type]
    local_date = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    relative_path = Path(str(business_id)) / purpose / local_date / f"{uuid.uuid4()}{extension}"
    absolute_path = Path(settings.file_storage_root) / relative_path
    await asyncio.to_thread(absolute_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(absolute_path.write_bytes, content)
    record = StoredFile(
        business_id=business_id,
        created_by_id=user_id,
        storage_path=relative_path.as_posix(),
        original_filename=Path(upload.filename or "upload").name[:255],
        content_type=upload.content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        expires_at=expires_at,
    )
    db.add(record)
    await db.flush()
    return record


def resolve_storage_path(storage_path: str) -> Path:
    root = Path(settings.file_storage_root).resolve()
    target = (root / storage_path).resolve()
    if root not in target.parents:
        raise HTTPException(404, "File not found")
    return target