import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


def hash_otp(code: str) -> str:
    return hmac.new(settings.otp_hmac_secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def verify_otp(code: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(code), expected_hash)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    lifetime = settings.access_token_minutes * 60
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(user_id), "type": "access", "iat": now, "exp": now + timedelta(seconds=lifetime)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return token, lifetime


def decode_access_token(token: str) -> uuid.UUID:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return uuid.UUID(payload["sub"])