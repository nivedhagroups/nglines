from datetime import date, datetime, timezone
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import add_audit, decode_cursor, encode_cursor, page_result, snapshot
from app.api.deps import BusinessContext, Db, User, business_context, current_user
from app.db.base import BusinessRole, OrganizationRole
from app.core.identity import normalize_phone
from app.models import Customer, Invoice


router = APIRouter(prefix="/customers", tags=["customers"])
READ_ROLES = tuple(OrganizationRole) + tuple(BusinessRole)


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mobile: str = Field(pattern=r"^(?:\+91)?[6-9][0-9]{9}$")
    email: str | None = Field(default=None, max_length=254)
    gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    location: str | None = None

    @field_validator("mobile")
    @classmethod
    def normalize_mobile(cls, value: str) -> str:
        return normalize_phone(value)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    mobile: str | None = Field(default=None, pattern=r"^(?:\+91)?[6-9][0-9]{9}$")
    email: str | None = Field(default=None, max_length=254)
    gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    location: str | None = None

    @field_validator("mobile")
    @classmethod
    def normalize_mobile(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else value

    @model_validator(mode="after")
    def require_name_and_mobile_when_provided(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name cannot be cleared")
        if "mobile" in self.model_fields_set and self.mobile is None:
            raise ValueError("Mobile cannot be cleared")
        return self


@router.get("")
async def list_customers(
    request: Request,
    db: Db,
    context: Annotated[BusinessContext, Depends(business_context)],
    q: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
) -> dict:
    offset = decode_cursor(cursor)
    query = select(Customer).where(Customer.business_id == context.business.id, Customer.deleted_at.is_(None))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Customer.name.ilike(pattern), Customer.mobile.ilike(pattern), Customer.gstin.ilike(pattern)))
    if from_date or to_date:
        invoice_filter = select(Invoice.customer_id).where(Invoice.business_id == context.business.id, Invoice.deleted_at.is_(None))
        if from_date:
            invoice_filter = invoice_filter.where(Invoice.invoice_date >= from_date)
        if to_date:
            invoice_filter = invoice_filter.where(Invoice.invoice_date <= to_date)
        query = query.where(Customer.id.in_(invoice_filter))
    rows = list((await db.scalars(query.order_by(Customer.name).offset(offset).limit(limit + 1))).all())
    data = [{"id": str(item.id), "name": item.name, "mobile": item.mobile, "email": item.email, "gstin": item.gstin, "location": item.location} for item in rows]
    return page_result(data, limit, offset, getattr(request.state, "request_id", None))


@router.post("", status_code=201)
async def create_customer(
    body: CustomerCreate,
    request: Request,
    db: Db,
    context: Annotated[BusinessContext, Depends(business_context)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    customer = Customer(business_id=context.business.id, created_by_id=user.id, **body.model_dump())
    db.add(customer)
    await db.flush()
    await add_audit(db, user, context, "create", "customer", customer.id, after=snapshot(customer, ("name", "mobile", "email", "gstin", "location")))
    await db.commit()
    return {"data": {"id": str(customer.id), **body.model_dump()}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    request: Request,
    db: Db,
    context: Annotated[BusinessContext, Depends(business_context)],
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = None,
) -> dict:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, "from must be on or before to")
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id, Customer.business_id == context.business.id, Customer.deleted_at.is_(None)))
    if customer is None:
        raise HTTPException(404, "Customer not found")
    offset = decode_cursor(cursor)
    query = select(Invoice).where(Invoice.business_id == context.business.id, Invoice.customer_id == customer_id, Invoice.deleted_at.is_(None))
    if from_date:
        query = query.where(Invoice.invoice_date >= from_date)
    if to_date:
        query = query.where(Invoice.invoice_date <= to_date)
    invoices = list((await db.scalars(query.order_by(Invoice.invoice_date.desc()).offset(offset).limit(limit + 1))).all())
    total_query = select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(
        Invoice.business_id == context.business.id,
        Invoice.customer_id == customer_id,
        Invoice.deleted_at.is_(None),
    )
    if from_date:
        total_query = total_query.where(Invoice.invoice_date >= from_date)
    if to_date:
        total_query = total_query.where(Invoice.invoice_date <= to_date)
    total = await db.scalar(total_query)
    return {
        "data": {
            "customer": {"id": str(customer.id), "name": customer.name, "mobile": customer.mobile, "email": customer.email, "gstin": customer.gstin, "location": customer.location},
            "purchase_total": str(total or 0),
            "invoices": [{"id": str(row.id), "invoice_number": row.invoice_number, "invoice_date": row.invoice_date.isoformat(), "total_amount": str(row.total_amount)} for row in invoices[:limit]],
            "page": {"limit": limit, "next_cursor": encode_cursor(offset + limit) if len(invoices) > limit else None},
        },
        "request_id": getattr(request.state, "request_id", None),
    }


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    request: Request,
    db: Db,
    context: Annotated[BusinessContext, Depends(business_context)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id, Customer.business_id == context.business.id, Customer.deleted_at.is_(None)).with_for_update())
    if customer is None:
        raise HTTPException(404, "Customer not found")
    before = snapshot(customer, ("name", "mobile", "email", "gstin", "location"))
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(customer, key, value)
    customer.updated_by_id = user.id
    await add_audit(db, user, context, "update", "customer", customer.id, before, snapshot(customer, tuple(before)))
    await db.commit()
    return {"data": {"id": str(customer.id), **snapshot(customer, tuple(before))}, "request_id": getattr(request.state, "request_id", None)}


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: uuid.UUID,
    db: Db,
    context: Annotated[BusinessContext, Depends(business_context)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    customer = await db.scalar(select(Customer).where(Customer.id == customer_id, Customer.business_id == context.business.id, Customer.deleted_at.is_(None)).with_for_update())
    if customer is None:
        raise HTTPException(404, "Customer not found")
    before = snapshot(customer, ("name", "mobile", "email", "gstin", "location"))
    customer.deleted_at = datetime.now(timezone.utc)
    customer.updated_by_id = user.id
    await add_audit(db, user, context, "delete", "customer", customer.id, before, {"deleted_at": customer.deleted_at.isoformat()})
    await db.commit()