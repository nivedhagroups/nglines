from dataclasses import dataclass
from typing import Annotated
import uuid

import jwt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import BusinessRole, OrganizationRole
from app.db.session import get_db
from app.models import Business, BusinessMembership, User
from app.core.security import decode_access_token


bearer = HTTPBearer(auto_error=False)
Db = Annotated[AsyncSession, Depends(get_db)]


async def authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Db,
) -> User:
    if credentials is None:
        raise HTTPException(401, "Authentication required")
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(401, "Invalid or expired access token") from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "User is inactive or unavailable")
    return user


async def current_user(request: Request, user: Annotated[User, Depends(authenticated_user)]) -> User:
    if user.must_change_password and request.url.path != "/api/v1/auth/me":
        raise HTTPException(403, "Change your temporary password to continue")
    return user


@dataclass(frozen=True)
class BusinessContext:
    business: Business
    role: OrganizationRole | BusinessRole


async def business_context(
    db: Db,
    user: Annotated[User, Depends(current_user)],
    business_id: Annotated[uuid.UUID, Header(alias="X-Business-ID")],
) -> BusinessContext:
    business = await db.get(Business, business_id)
    if business is None or not business.is_active:
        raise HTTPException(404, "Business not found")
    if user.organization_role is not None:
        return BusinessContext(business, user.organization_role)
    membership = await db.scalar(
        select(BusinessMembership).where(
            BusinessMembership.business_id == business_id,
            BusinessMembership.user_id == user.id,
            BusinessMembership.is_active.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(404, "Business not found")
    return BusinessContext(business, membership.role)


def require_roles(*roles: OrganizationRole | BusinessRole):
    async def dependency(context: Annotated[BusinessContext, Depends(business_context)]) -> BusinessContext:
        if context.role not in roles:
            raise HTTPException(403, "You do not have permission to perform this action")
        return context

    return dependency


async def super_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.organization_role != OrganizationRole.SUPER_ADMIN:
        raise HTTPException(403, "Super Admin access required")
    return user