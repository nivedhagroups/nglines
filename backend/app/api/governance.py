from datetime import date, datetime, time, timedelta, timezone
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import add_audit, decode_cursor, page_result
from app.api.deps import BusinessContext, Db, User, business_context, current_user, require_roles, super_admin
from app.db.base import BusinessRole, EntityType, FlagStatus, OrganizationRole
from app.models import AuditLog, DeviceToken, Expense, FlagEvent, Invoice, Notification, TransactionFlag
from app.providers.push import get_push_delivery


router = APIRouter(tags=["governance"])
FLAGGERS = (OrganizationRole.CEO, OrganizationRole.SUPER_ADMIN)


class FlagCreate(BaseModel):
    entity_type: EntityType
    entity_id: uuid.UUID
    reason: str | None = None


class FlagResponse(BaseModel):
    response_text: str = Field(min_length=1, max_length=5000)


class Resolution(BaseModel):
    resolution_note: str | None = None


class DeviceTokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    platform: str = Field(pattern="^(ios|android)$")


async def responsible_user_id(db, context: BusinessContext, entity_type: EntityType, entity_id: uuid.UUID) -> uuid.UUID:
    model = {EntityType.INVOICE: Invoice, EntityType.EXPENSE: Expense}.get(entity_type)
    if model is None:
        raise HTTPException(422, "Only invoices and expenses can be flagged")
    row = await db.scalar(select(model).where(model.id == entity_id, model.business_id == context.business.id, model.deleted_at.is_(None)))
    if row is None:
        raise HTTPException(404, "Transaction not found")
    responsible_id = row.responsible_user_id
    if responsible_id is None:
        raise HTTPException(409, "Transaction has no responsible user")
    return responsible_id


async def notify_user(db, context: BusinessContext, user_id: uuid.UUID, title: str, body: str, entity_type: str, entity_id: uuid.UUID) -> None:
    db.add(Notification(business_id=context.business.id, user_id=user_id, title=title, body=body, entity_type=entity_type, entity_id=entity_id))


async def dispatch_push(db, user_id: uuid.UUID, title: str, body: str, entity_type: str, entity_id: uuid.UUID) -> None:
    tokens = list((await db.scalars(select(DeviceToken.token).where(DeviceToken.user_id == user_id, DeviceToken.disabled_at.is_(None)))).all())
    try:
        await get_push_delivery().send(tokens, title, body, {"entity_type": entity_type, "entity_id": str(entity_id)})
    except Exception:
        # The in-app notification is already committed; push outages must not undo the flag transaction.
        return


@router.post("/flags", status_code=201)
async def create_flag(body: FlagCreate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*FLAGGERS))], user: Annotated[User, Depends(current_user)]) -> dict:
    responsible_id = await responsible_user_id(db, context, body.entity_type, body.entity_id)
    flag = TransactionFlag(
        business_id=context.business.id,
        created_by_id=user.id,
        flagged_by_id=user.id,
        responsible_user_id=responsible_id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        status=FlagStatus.FLAGGED,
        response_text=None,
    )
    db.add(flag)
    await db.flush()
    db.add(FlagEvent(business_id=context.business.id, created_by_id=user.id, flag_id=flag.id, from_status=None, to_status=FlagStatus.FLAGGED, actor_id=user.id, reason=body.reason))
    await notify_user(db, context, responsible_id, "Transaction flagged as doubtful", body.reason or "A transaction needs your review.", body.entity_type.value, body.entity_id)
    await add_audit(db, user, context, "flag", body.entity_type.value, body.entity_id, after={"flag_id": flag.id, "status": FlagStatus.FLAGGED, "responsible_user_id": responsible_id, "reason": body.reason})
    await db.commit()
    await dispatch_push(db, responsible_id, "Transaction flagged as doubtful", body.reason or "A transaction needs your review.", body.entity_type.value, body.entity_id)
    return {"data": {"id": str(flag.id), "status": flag.status.value, "responsible_user_id": str(responsible_id)}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/flags")
async def list_flags(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)], status: FlagStatus | None = None, entity_type: EntityType | None = None, limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(TransactionFlag).where(TransactionFlag.business_id == context.business.id, TransactionFlag.deleted_at.is_(None))
    if status:
        query = query.where(TransactionFlag.status == status)
    if entity_type:
        query = query.where(TransactionFlag.entity_type == entity_type)
    if context.role in (BusinessRole.MANAGER, BusinessRole.ASST_MANAGER):
        query = query.where(TransactionFlag.responsible_user_id == user.id)
    elif context.role not in (*FLAGGERS, OrganizationRole.ADMIN):
        raise HTTPException(403, "Flag access denied")
    rows = list((await db.scalars(query.order_by(TransactionFlag.created_at.desc()).offset(offset).limit(limit + 1))).all())
    data = [{"id": str(row.id), "entity_type": row.entity_type.value, "entity_id": str(row.entity_id), "status": row.status.value, "flagged_by_id": str(row.flagged_by_id), "responsible_user_id": str(row.responsible_user_id), "response_text": row.response_text, "created_at": row.created_at.isoformat()} for row in rows]
    return page_result(data, limit, offset, getattr(request.state, "request_id", None))


async def load_flag(db, context: BusinessContext, flag_id: uuid.UUID) -> TransactionFlag:
    row = await db.scalar(select(TransactionFlag).where(TransactionFlag.id == flag_id, TransactionFlag.business_id == context.business.id, TransactionFlag.deleted_at.is_(None)).with_for_update())
    if row is None:
        raise HTTPException(404, "Flag not found")
    return row


@router.post("/flags/{flag_id}/response")
async def respond_to_flag(flag_id: uuid.UUID, body: FlagResponse, request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)]) -> dict:
    flag = await load_flag(db, context, flag_id)
    if flag.responsible_user_id != user.id and context.role not in (OrganizationRole.ADMIN, OrganizationRole.SUPER_ADMIN):
        raise HTTPException(403, "Only the responsible manager may respond")
    if flag.status not in (FlagStatus.FLAGGED, FlagStatus.REASON_SUBMITTED, FlagStatus.CORRECTED):
        raise HTTPException(409, "Flag is already resolved")
    previous = flag.status
    flag.status = FlagStatus.REASON_SUBMITTED
    flag.response_text = body.response_text
    flag.updated_by_id = user.id
    db.add(FlagEvent(business_id=context.business.id, created_by_id=user.id, flag_id=flag.id, from_status=previous, to_status=flag.status, actor_id=user.id, reason=body.response_text))
    await add_audit(db, user, context, "flag_response", flag.entity_type.value, flag.entity_id, {"status": previous}, {"status": flag.status, "response_text": body.response_text})
    await db.commit()
    return {"data": {"id": str(flag.id), "status": flag.status.value}, "request_id": getattr(request.state, "request_id", None)}


@router.post("/flags/{flag_id}/corrected")
async def mark_flag_corrected(flag_id: uuid.UUID, body: FlagResponse, request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)]) -> dict:
    flag = await load_flag(db, context, flag_id)
    if flag.responsible_user_id != user.id:
        raise HTTPException(403, "Only the responsible manager may record this correction")
    if flag.status not in (FlagStatus.FLAGGED, FlagStatus.REASON_SUBMITTED):
        raise HTTPException(409, "Flag cannot be corrected from its current state")
    model = Invoice if flag.entity_type == EntityType.INVOICE else Expense
    transaction = await db.scalar(select(model).where(model.id == flag.entity_id, model.business_id == context.business.id, model.deleted_at.is_(None)))
    if transaction is None or transaction.updated_at <= flag.created_at:
        raise HTTPException(409, "Correct the transaction before marking this flag corrected")
    previous = flag.status
    flag.status = FlagStatus.CORRECTED
    flag.response_text = body.response_text
    flag.updated_by_id = user.id
    db.add(FlagEvent(business_id=context.business.id, created_by_id=user.id, flag_id=flag.id, from_status=previous, to_status=flag.status, actor_id=user.id, reason=body.response_text))
    await add_audit(db, user, context, "flag_corrected", flag.entity_type.value, flag.entity_id, {"status": previous}, {"status": flag.status, "correction_summary": body.response_text})
    await db.commit()
    return {"data": {"id": str(flag.id), "status": flag.status.value}, "request_id": getattr(request.state, "request_id", None)}


@router.post("/flags/{flag_id}/resolve")
async def resolve_flag(flag_id: uuid.UUID, body: Resolution, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*FLAGGERS))], user: Annotated[User, Depends(current_user)]) -> dict:
    flag = await load_flag(db, context, flag_id)
    if flag.status not in (FlagStatus.REASON_SUBMITTED, FlagStatus.CORRECTED):
        raise HTTPException(409, "A reason or correction is required before resolution")
    previous = flag.status
    flag.status = FlagStatus.RESOLVED
    flag.resolved_at = datetime.now(timezone.utc)
    flag.updated_by_id = user.id
    db.add(FlagEvent(business_id=context.business.id, created_by_id=user.id, flag_id=flag.id, from_status=previous, to_status=flag.status, actor_id=user.id, reason=body.resolution_note))
    await add_audit(db, user, context, "flag_resolved", flag.entity_type.value, flag.entity_id, {"status": previous}, {"status": flag.status, "resolution_note": body.resolution_note})
    await db.commit()
    return {"data": {"id": str(flag.id), "status": flag.status.value}, "request_id": getattr(request.state, "request_id", None)}


@router.post("/flags/{flag_id}/reflag", status_code=201)
async def reflag(flag_id: uuid.UUID, body: FlagResponse, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*FLAGGERS))], user: Annotated[User, Depends(current_user)]) -> dict:
    previous = await load_flag(db, context, flag_id)
    if previous.status != FlagStatus.RESOLVED:
        raise HTTPException(409, "Only a resolved flag can be re-flagged")
    responsible_id = await responsible_user_id(db, context, previous.entity_type, previous.entity_id)
    flag = TransactionFlag(business_id=context.business.id, created_by_id=user.id, flagged_by_id=user.id, responsible_user_id=responsible_id, entity_type=previous.entity_type, entity_id=previous.entity_id, status=FlagStatus.FLAGGED)
    db.add(flag)
    await db.flush()
    db.add(FlagEvent(business_id=context.business.id, created_by_id=user.id, flag_id=flag.id, to_status=FlagStatus.FLAGGED, actor_id=user.id, reason=body.response_text))
    await notify_user(db, context, responsible_id, "Transaction re-flagged", body.response_text, previous.entity_type.value, previous.entity_id)
    await add_audit(db, user, context, "reflag", previous.entity_type.value, previous.entity_id, after={"flag_id": flag.id, "previous_flag_id": previous.id, "reason": body.response_text})
    await db.commit()
    await dispatch_push(db, responsible_id, "Transaction re-flagged", body.response_text, previous.entity_type.value, previous.entity_id)
    return {"data": {"id": str(flag.id), "status": flag.status.value}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/notifications")
async def list_notifications(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)], unread_only: bool = False, limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(Notification).where(Notification.business_id == context.business.id, Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = list((await db.scalars(query.order_by(Notification.created_at.desc()).offset(offset).limit(limit + 1))).all())
    return page_result([{"id": str(row.id), "title": row.title, "body": row.body, "entity_type": row.entity_type, "entity_id": str(row.entity_id) if row.entity_id else None, "read_at": row.read_at.isoformat() if row.read_at else None, "created_at": row.created_at.isoformat()} for row in rows], limit, offset, getattr(request.state, "request_id", None))


@router.post("/notifications/{notification_id}/read", status_code=204)
async def mark_notification_read(notification_id: uuid.UUID, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)]) -> None:
    row = await db.scalar(select(Notification).where(Notification.id == notification_id, Notification.business_id == context.business.id, Notification.user_id == user.id).with_for_update())
    if row is None:
        raise HTTPException(404, "Notification not found")
    row.read_at = datetime.now(timezone.utc)
    await db.commit()


@router.put("/notifications/device-token")
async def register_device_token(body: DeviceTokenInput, db: Db, user: Annotated[User, Depends(current_user)]) -> dict:
    row = await db.scalar(select(DeviceToken).where(DeviceToken.token == body.token).with_for_update())
    if row is None:
        row = DeviceToken(user_id=user.id, token=body.token, platform=body.platform)
        db.add(row)
    else:
        if row.user_id != user.id:
            raise HTTPException(409, "Device token is already assigned")
        row.platform = body.platform
        row.disabled_at = None
    await db.commit()
    return {"data": {"registered": True}}


@router.delete("/notifications/device-token", status_code=204)
async def unregister_device_token(body: DeviceTokenInput, db: Db, user: Annotated[User, Depends(current_user)]) -> None:
    row = await db.scalar(select(DeviceToken).where(DeviceToken.token == body.token, DeviceToken.user_id == user.id).with_for_update())
    if row is not None:
        row.disabled_at = datetime.now(timezone.utc)
        await db.commit()


@router.get("/audit-logs")
async def list_audit_logs(request: Request, db: Db, _user: Annotated[User, Depends(super_admin)], business_id: uuid.UUID | None = None, actor_id: uuid.UUID | None = None, entity_type: str | None = None, entity_id: uuid.UUID | None = None, action: str | None = None, from_date: date | None = Query(None, alias="from"), to_date: date | None = Query(None, alias="to"), limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(AuditLog)
    filters = ((AuditLog.business_id, business_id), (AuditLog.actor_id, actor_id), (AuditLog.entity_type, entity_type), (AuditLog.entity_id, entity_id), (AuditLog.action, action))
    for column, value in filters:
        if value is not None:
            query = query.where(column == value)
    if from_date:
        query = query.where(AuditLog.occurred_at >= datetime.combine(from_date, time.min, timezone.utc))
    if to_date:
        query = query.where(AuditLog.occurred_at < datetime.combine(to_date + timedelta(days=1), time.min, timezone.utc))
    rows = list((await db.scalars(query.order_by(AuditLog.occurred_at.desc()).offset(offset).limit(limit + 1))).all())
    data = [{"id": str(row.id), "business_id": str(row.business_id) if row.business_id else None, "actor_id": str(row.actor_id) if row.actor_id else None, "action": row.action, "entity_type": row.entity_type, "entity_id": str(row.entity_id), "before": row.before_values, "after": row.after_values, "occurred_at": row.occurred_at.isoformat()} for row in rows]
    return page_result(data, limit, offset, getattr(request.state, "request_id", None))