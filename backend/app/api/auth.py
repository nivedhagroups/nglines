from datetime import datetime, timedelta, timezone
import re
import secrets
import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.identity import normalize_phone
from app.core.security import (
    create_access_token,
    hash_otp,
    hash_refresh_token,
    new_refresh_token,
    verify_otp,
)
from app.db.base import OtpChannel
from app.db.session import get_db
from app.models import AuthSession, Business, BusinessMembership, OtpChallenge, OtpRateLimit, User
from app.providers.otp import get_otp_delivery


router = APIRouter(prefix="/auth", tags=["auth"])
Db = Annotated[AsyncSession, Depends(get_db)]
logger = logging.getLogger(__name__)


class OtpRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=254)
    channel: OtpChannel | None = None


class OtpVerify(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)


class Identifier(BaseModel):
    kind: OtpChannel
    normalized: str


def normalize_identifier(value: str, channel: OtpChannel | None = None) -> Identifier:
    value = value.strip()
    if channel == OtpChannel.EMAIL or (channel is None and "@" in value):
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise HTTPException(422, "Enter a valid email or phone number")
        return Identifier(kind=OtpChannel.EMAIL, normalized=normalized)
    try:
        digits = normalize_phone(value)
    except ValueError:
        raise HTTPException(422, "Enter a valid email or phone number") from None
    return Identifier(kind=OtpChannel.SMS, normalized=digits)


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
        },
        "businesses": [
            {"id": str(business_id), "name": name, "role": role}
            for business_id, name, role in businesses
        ],
    }


@router.post("/otp/request", status_code=202)
async def request_otp(body: OtpRequest, request: Request, db: Db) -> dict:
    identity = normalize_identifier(body.identifier, body.channel)
    now = datetime.now(timezone.utc)
    window_seconds = settings.otp_limit_window_seconds
    window_start = datetime.fromtimestamp(int(now.timestamp() // window_seconds) * window_seconds, timezone.utc)
    rate_statement = pg_insert(OtpRateLimit).values(
        id=uuid.uuid4(),
        destination_normalized=identity.normalized,
        window_started_at=window_start,
        request_count=1,
    ).on_conflict_do_update(
        constraint="uq_otp_rate_window",
        set_={"request_count": OtpRateLimit.request_count + 1},
    ).returning(OtpRateLimit.request_count)
    request_count = (await db.execute(rate_statement)).scalar_one()
    if request_count > settings.otp_limit_count:
        await db.commit()
        raise HTTPException(429, "Too many OTP requests. Try again later.", headers={"Retry-After": str(window_seconds)})

    user = await db.scalar(
        select(User).where(
            User.is_active.is_(True),
            (User.email == identity.normalized) if identity.kind == OtpChannel.EMAIL else (User.phone == identity.normalized),
        )
    )
    # Keep account existence private; only create/send a challenge for registered identities.
    if user is not None:
        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = OtpChallenge(
            destination_normalized=identity.normalized,
            channel=identity.kind,
            code_hash=hash_otp(code),
            expires_at=now + timedelta(seconds=settings.otp_expiry_seconds),
            max_attempts=settings.otp_max_attempts,
        )
        db.add(challenge)
        await db.flush()
        pending_delivery = (identity.normalized, identity.kind, code)
        response = {"challenge_id": str(challenge.id), "expires_in_seconds": settings.otp_expiry_seconds}
    else:
        pending_delivery = None
        response = {"challenge_id": str(uuid.uuid4()), "expires_in_seconds": settings.otp_expiry_seconds}
    await db.commit()
    if pending_delivery is not None:
        try:
            await get_otp_delivery().send(*pending_delivery)
        except Exception as exc:
            logger.exception("OTP provider delivery failed")
            raise HTTPException(503, "OTP delivery is temporarily unavailable") from exc
    return {"data": response, "request_id": getattr(request.state, "request_id", None)}


@router.post("/otp/verify")
async def verify_challenge(body: OtpVerify, request: Request, db: Db) -> dict:
    challenge = await db.scalar(select(OtpChallenge).where(OtpChallenge.id == body.challenge_id).with_for_update())
    now = datetime.now(timezone.utc)
    if (
        challenge is None
        or challenge.consumed_at is not None
        or challenge.expires_at <= now
        or challenge.attempts >= challenge.max_attempts
    ):
        raise HTTPException(401, "OTP is invalid or expired")
    challenge.attempts += 1
    if not verify_otp(body.code, challenge.code_hash):
        await db.commit()
        raise HTTPException(401, "OTP is invalid or expired")
    user = await db.scalar(
        select(User).where(
            User.is_active.is_(True),
            (User.email == challenge.destination_normalized)
            if challenge.channel == OtpChannel.EMAIL
            else (User.phone == challenge.destination_normalized),
        )
    )
    if user is None:
        await db.commit()
        raise HTTPException(401, "OTP is invalid or expired")
    challenge.consumed_at = now
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