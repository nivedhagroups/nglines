from datetime import datetime, timedelta, timezone
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.identity import normalize_phone
from app.core.security import (
    create_access_token,
    DUMMY_PASSWORD_HASH,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.models import AuthSession, Business, BusinessMembership, LoginRateLimit, User
from app.api.deps import authenticated_user


router = APIRouter(prefix="/auth", tags=["auth"])
Db = Annotated[AsyncSession, Depends(get_db)]


class PasswordLogin(BaseModel):
    identifier: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)


def normalize_identifier(value: str) -> str:
    value = value.strip()
    if "@" in value:
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise HTTPException(422, "Enter a valid email or phone number")
        return normalized
    try:
        return normalize_phone(value)
    except ValueError:
        raise HTTPException(422, "Enter a valid email or phone number") from None


async def _issue_session(db: AsyncSession, user: User, token_family_id: uuid.UUID | None = None) -> dict:
    refresh = new_refresh_token()
    session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh),
        token_family_id=token_family_id or uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
    )
    db.add(session)
    await db.flush()
    access, expires_in = create_access_token(user.id)
    if user.organization_role is not None:
        business_rows = await db.execute(select(Business).where(Business.is_active.is_(True)))
        businesses = [(business.id, business.name, user.organization_role.value) for business in business_rows.scalars()]
    else:
        membership_rows = await db.execute(
            select(BusinessMembership, Business)
            .join(Business, Business.id == BusinessMembership.business_id)
            .where(BusinessMembership.user_id == user.id, BusinessMembership.is_active.is_(True), Business.is_active.is_(True))
        )
        businesses = [
            (membership.business_id, business.name, membership.role.value)
            for membership, business in membership_rows.all()
        ]
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "refresh_token": refresh,
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "organization_role": user.organization_role.value if user.organization_role else None,
            "must_change_password": user.must_change_password,
        },
        "businesses": [
            {"id": str(business_id), "name": name, "role": role}
            for business_id, name, role in businesses
        ],
    }


@router.post("/login")
async def login(body: PasswordLogin, request: Request, db: Db) -> dict:
    identifier = normalize_identifier(body.identifier)
    now = datetime.now(timezone.utc)
    window_seconds = settings.password_login_window_seconds
    window_start = datetime.fromtimestamp(int(now.timestamp() // window_seconds) * window_seconds, timezone.utc)
    rate_statement = pg_insert(LoginRateLimit).values(
        id=uuid.uuid4(),
        identifier=identifier,
        window_started_at=window_start,
        request_count=1,
    ).on_conflict_do_update(
        constraint="uq_login_rate_window",
        set_={"request_count": LoginRateLimit.request_count + 1},
    ).returning(LoginRateLimit.request_count)
    request_count = (await db.execute(rate_statement)).scalar_one()
    if request_count > settings.password_login_limit:
        await db.commit()
        raise HTTPException(429, "Too many sign-in attempts. Try again later.", headers={"Retry-After": str(window_seconds)})

    user = await db.scalar(
        select(User).where((User.email == identifier) | (User.phone == identifier))
    )
    if user is None or not user.is_active or not user.password_hash:
        verify_password(body.password, DUMMY_PASSWORD_HASH)
        await db.commit()
        raise HTTPException(401, "Invalid email/phone or password")
    if not verify_password(body.password, user.password_hash):
        await db.commit()
        raise HTTPException(401, "Invalid email/phone or password")
    response = await _issue_session(db, user)
    await db.commit()
    return {"data": response, "request_id": getattr(request.state, "request_id", None)}


@router.post("/password/change")
async def change_password(
    body: PasswordChange,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(authenticated_user)],
) -> dict:
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(422, "Choose a password different from your temporary password")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    response = await _issue_session(db, user)
    await db.commit()
    return {"data": response, "request_id": getattr(request.state, "request_id", None)}


@router.post("/refresh")
async def refresh_session(body: RefreshRequest, request: Request, db: Db) -> dict:
    hashed = hash_refresh_token(body.refresh_token)
    session = await db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == hashed).with_for_update())
    now = datetime.now(timezone.utc)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(401, "Refresh token is invalid or expired")
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "User is inactive or unavailable")
    session.revoked_at = now
    response = await _issue_session(db, user, token_family_id=session.token_family_id)
    response_session = await db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == hash_refresh_token(response["refresh_token"]))
    )
    session.replaced_by_session_id = response_session.id if response_session else None
    await db.commit()
    return {"data": response, "request_id": getattr(request.state, "request_id", None)}


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest, db: Db) -> Response:
    session = await db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == hash_refresh_token(body.refresh_token)).with_for_update()
    )
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return Response(status_code=204)