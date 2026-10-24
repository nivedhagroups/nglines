import base64
import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import BusinessContext
from app.models import AuditLog, IdempotencyRecord, User


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        value = int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
        if value < 0:
            raise ValueError
        return value
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid page cursor") from None


def page_result(rows: list[Any], limit: int, offset: int, request_id: str | None) -> dict:
    next_cursor = encode_cursor(offset + limit) if len(rows) > limit else None
    return {
        "data": rows[:limit],
        "page": {"limit": limit, "next_cursor": next_cursor},
        "request_id": request_id,
    }


def json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return json_value(value.model_dump(mode="json"))
    if isinstance(value, (uuid.UUID, date, datetime)):
        return value.isoformat() if not isinstance(value, uuid.UUID) else str(value)
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


async def add_audit(
    db: AsyncSession,
    user: User,
    context: BusinessContext | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            business_id=context.business.id if context else None,
            actor_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_values=json_value(before),
            after_values=json_value(after),
        )
    )


def snapshot(model: Any, fields: tuple[str, ...]) -> dict:
    return {field: json_value(getattr(model, field)) for field in fields}


async def load_idempotent_response(db: AsyncSession, business_id: uuid.UUID, key: str | None, operation: str, request_body: Any) -> tuple[IdempotencyRecord | None, dict | None]:
    if key is None:
        return None, None
    if not 8 <= len(key) <= 128:
        raise HTTPException(422, "Idempotency-Key must contain 8 to 128 characters")
    body_json = json.dumps(json_value(request_body), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(body_json.encode()).hexdigest()
    await db.execute(
        pg_insert(IdempotencyRecord)
        .values(business_id=business_id, key=key, operation=operation, request_hash=digest)
        .on_conflict_do_nothing(constraint="uq_idempotency_business_key")
    )
    record = await db.scalar(
        select(IdempotencyRecord).where(IdempotencyRecord.business_id == business_id, IdempotencyRecord.key == key).with_for_update()
    )
    if record is None:
        raise HTTPException(503, "Unable to reserve request key")
    if record.operation != operation or record.request_hash != digest:
        raise HTTPException(409, "Idempotency-Key was already used for a different request")
    return record, record.response_body


def assert_not_deleted(model: Any) -> None:
    if model is None or getattr(model, "deleted_at", None) is not None:
        raise HTTPException(404, "Record not found")