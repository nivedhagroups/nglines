from typing import Annotated
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import select

from app.api.deps import Db, User, current_user
from app.api.common import add_audit
from app.models import Business, BusinessMembership
from app.core.identity import normalize_phone
from app.core.config import settings
from app.api.common import add_audit
from app.services.files import PROFILE_CONTENT_TYPES, read_valid_upload
import hashlib
import uuid
import asyncio


router = APIRouter(tags=["profile"])


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=8, max_length=20)

    @field_validator("phone")
    @classmethod
    def normalize_profile_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else value

    @model_validator(mode="after")
    def require_name(self):
        if self.name is None and "name" in self.model_fields_set:
            raise ValueError("Name cannot be cleared")
        return self


@router.get("/auth/me")
async def who_am_i(request: Request, db: Db, user: Annotated[User, Depends(current_user)]) -> dict:
    memberships = await db.execute(
        select(BusinessMembership, Business)
        .join(Business, Business.id == BusinessMembership.business_id)
        .where(BusinessMembership.user_id == user.id, BusinessMembership.is_active.is_(True), Business.is_active.is_(True))
    )
    businesses = [
        {"id": str(membership.business_id), "name": business.name, "role": membership.role.value}
        for membership, business in memberships.all()
    ]
    if user.organization_role:
        available = await db.scalars(select(Business).where(Business.is_active.is_(True)))
        businesses = [{"id": str(b.id), "name": b.name, "role": user.organization_role.value} for b in available]
    return {"data": {"id": str(user.id), "name": user.name, "email": user.email, "phone": user.phone, "organization_role": user.organization_role.value if user.organization_role else None, "must_change_password": user.must_change_password, "avatar_storage_key": user.avatar_storage_key, "businesses": businesses}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/profile")
async def get_profile(request: Request, user: Annotated[User, Depends(current_user)]) -> dict:
    return {"data": {"id": str(user.id), "name": user.name, "email": user.email, "phone": user.phone, "role": user.organization_role.value if user.organization_role else "business_member", "avatar_storage_key": user.avatar_storage_key}, "request_id": getattr(request.state, "request_id", None)}


@router.patch("/profile")
async def update_profile(body: ProfileUpdate, request: Request, db: Db, user: Annotated[User, Depends(current_user)]) -> dict:
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(422, "Provide at least one profile field")
    new_email = values.get("email", user.email)
    new_phone = values.get("phone", user.phone)
    if not new_email and not new_phone:
        raise HTTPException(422, "Keep at least one login contact: email or phone")
    before = {"name": user.name, "email": user.email, "phone": user.phone}
    for key, value in values.items():
        setattr(user, key, str(value).casefold() if key == "email" and value else value)
    await add_audit(db, user, None, "update", "user_profile", user.id, before, {"name": user.name, "email": user.email, "phone": user.phone})
    await db.commit()
    return {"data": {"id": str(user.id), "name": user.name, "email": user.email, "phone": user.phone}, "request_id": getattr(request.state, "request_id", None)}


@router.post("/profile/picture")
async def upload_profile_picture(request: Request, db: Db, user: Annotated[User, Depends(current_user)], picture: UploadFile = File(...)) -> dict:
    content = await read_valid_upload(picture, PROFILE_CONTENT_TYPES, maximum=5 * 1024 * 1024)
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[picture.content_type]
    relative_path = Path("profile") / str(user.id) / f"{uuid.uuid4()}{extension}"
    absolute_path = Path(settings.file_storage_root) / relative_path
    await asyncio.to_thread(absolute_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(absolute_path.write_bytes, content)
    old_key = user.avatar_storage_key
    before = {"avatar_storage_key": user.avatar_storage_key}
    user.avatar_storage_key = relative_path.as_posix()
    await add_audit(db, user, None, "update", "user_profile_picture", user.id, before, {"sha256": hashlib.sha256(content).hexdigest()})
    await db.commit()
    if old_key:
        root = Path(settings.file_storage_root).resolve()
        old_path = (root / old_key).resolve()
        if root in old_path.parents and old_path != absolute_path.resolve() and old_path.is_file():
            await asyncio.to_thread(old_path.unlink)
    return {"data": {"avatar_url": "/api/v1/profile/picture", "content_type": picture.content_type, "size_bytes": len(content)}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/profile/picture")
async def get_profile_picture(user: Annotated[User, Depends(current_user)]) -> FileResponse:
    if not user.avatar_storage_key:
        raise HTTPException(404, "Profile picture not found")
    root = Path(settings.file_storage_root).resolve()
    path = (root / user.avatar_storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Profile picture not found")
    return FileResponse(path)