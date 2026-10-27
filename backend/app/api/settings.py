from datetime import date, datetime
from decimal import Decimal
import logging
import secrets
import uuid
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, or_, select

from app.api.common import add_audit, decode_cursor, page_result, snapshot
from app.api.deps import BusinessContext, Db, User, business_context, current_user, require_roles
from app.db.base import BusinessRole, ExpenseType, OrganizationRole
from app.models import AuthSession, BrickRate, BrickType, Business, BusinessMembership, BusinessSettings, Employee, ExpenseCategory, GstRate, User as AppUser, Vehicle
from app.core.identity import normalize_phone
from app.core.security import hash_password
from app.providers.email import SMTPEmailDelivery


router = APIRouter(tags=["settings"])
logger = logging.getLogger(__name__)
ALL_BUSINESS_ROLES = tuple(OrganizationRole) + tuple(BusinessRole)
ADMINS = (OrganizationRole.SUPER_ADMIN, OrganizationRole.ADMIN)
GST_CONFIGURATORS = (*ADMINS, OrganizationRole.CEO)


class BusinessSettingsUpdate(BaseModel):
    legal_name: str | None = Field(default=None, min_length=1, max_length=200)
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    gst_state_code: str | None = Field(default=None, pattern=r"^\d{2}$")
    address: str | None = None
    invoice_footer: str | None = None
    timezone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def require_names_when_provided(self):
        for field in ("legal_name", "display_name"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be cleared")
        return self


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    legal_name: str = Field(min_length=1, max_length=200)
    gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    gst_state_code: str | None = Field(default=None, pattern=r"^\d{2}$")
    address: str | None = None
    invoice_footer: str | None = None


class EffectiveRateCreate(BaseModel):
    rate: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    effective_from: date


class BrickTypeInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class BrickRateInput(BaseModel):
    brick_type_id: uuid.UUID
    rate: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    effective_from: date


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expense_type: ExpenseType


class VehicleInput(BaseModel):
    registration_number: str = Field(min_length=3, max_length=24)
    description: str | None = None


class EmployeeInput(BaseModel):
    employee_code: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    mobile: str | None = Field(default=None, max_length=20)


class ActiveUpdate(BaseModel):
    is_active: bool


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    organization_role: OrganizationRole | None = None
    business_id: uuid.UUID | None = None
    business_role: BusinessRole | None = None

    @model_validator(mode="after")
    def validate_assignment(self):
        if not self.email and not self.phone:
            raise ValueError("Provide an email or phone number")
        if self.organization_role is not None and (self.business_id is not None or self.business_role is not None):
            raise ValueError("Organization roles cannot also have a business role")
        if (self.business_id is None) != (self.business_role is None):
            raise ValueError("business_id and business_role must be provided together")
        if self.organization_role is None and self.business_role is None:
            raise ValueError("Assign an organization role or business role")
        return self

    @field_validator("phone")
    @classmethod
    def normalize_user_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else value


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    organization_role: OrganizationRole | None = None
    business_id: uuid.UUID | None = None
    business_role: BusinessRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_assignment(self):
        if self.organization_role is not None and (self.business_id is not None or self.business_role is not None):
            raise ValueError("Organization roles cannot also set a business role")
        if (self.business_id is None) != (self.business_role is None):
            raise ValueError("business_id and business_role must be provided together")
        if "organization_role" in self.model_fields_set and self.organization_role is None and self.business_role is None:
            raise ValueError("A user must keep an organization or business role")
        return self

    @field_validator("phone")
    @classmethod
    def normalize_user_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else value

    @model_validator(mode="after")
    def require_name_when_provided(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name cannot be cleared")
        return self


async def prepare_rate_history(db, model, business_id: uuid.UUID, effective_from: date) -> tuple[date | None, list[tuple[object, date | None]]]:
    existing = list((await db.scalars(select(model).where(
        model.business_id == business_id,
        model.deleted_at.is_(None),
    ).order_by(model.effective_from).with_for_update())).all())
    if any(row.effective_from == effective_from for row in existing):
        raise HTTPException(409, "A rate already exists with this effective date")
    prior = [row for row in existing if row.effective_from < effective_from]
    future = [row for row in existing if row.effective_from > effective_from]
    next_start = future[0].effective_from if future else None
    changed = []
    if prior:
        changed.append((prior[-1], prior[-1].effective_to))
        prior[-1].effective_to = effective_from
    if next_start:
        return next_start, changed
    return None, changed


@router.get("/businesses")
async def list_businesses(request: Request, db: Db, user: Annotated[AppUser, Depends(current_user)], limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    if user.organization_role is not None:
        query = select(Business).where(Business.is_active.is_(True))
    else:
        query = select(Business).join(BusinessMembership).where(BusinessMembership.user_id == user.id, BusinessMembership.is_active.is_(True), Business.is_active.is_(True))
    rows = list((await db.scalars(query.order_by(Business.name).offset(offset).limit(limit + 1))).all())
    return page_result([{"id": str(b.id), "name": b.name, "slug": b.slug} for b in rows], limit, offset, getattr(request.state, "request_id", None))


@router.post("/businesses", status_code=201)
async def create_business(body: BusinessCreate, request: Request, db: Db, actor: Annotated[AppUser, Depends(current_user)]) -> dict:
    if actor.organization_role not in ADMINS:
        raise HTTPException(403, "Admin access required")
    business = Business(name=body.name, slug=body.slug, is_active=True)
    db.add(business)
    await db.flush()
    db.add(BusinessSettings(
        business_id=business.id,
        created_by_id=actor.id,
        legal_name=body.legal_name,
        display_name=body.name,
        gstin=body.gstin,
        gst_state_code=body.gst_state_code,
        address=body.address,
        invoice_footer=body.invoice_footer,
    ))
    for category_name, expense_type in (
        ("Daily expenses", ExpenseType.DAILY),
        ("Vehicle diesel", ExpenseType.DIESEL),
        ("Labour salary", ExpenseType.SALARY),
        ("Labour advance", ExpenseType.SALARY_ADVANCE),
        ("Miscellaneous", ExpenseType.MISCELLANEOUS),
    ):
        db.add(ExpenseCategory(business_id=business.id, created_by_id=actor.id, name=category_name, expense_type=expense_type, is_active=True))
    await add_audit(db, actor, None, "create", "business", business.id, after={"name": business.name, "slug": business.slug})
    await db.commit()
    return {"data": {"id": str(business.id), "name": business.name, "slug": business.slug}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/settings/business")
async def get_business_settings(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)]) -> dict:
    settings = await db.scalar(select(BusinessSettings).where(BusinessSettings.business_id == context.business.id, BusinessSettings.deleted_at.is_(None)))
    if settings is None:
        raise HTTPException(404, "Business settings are not configured")
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    current_rate = await db.scalar(select(GstRate).where(
        GstRate.business_id == context.business.id,
        GstRate.effective_from <= today,
        or_(GstRate.effective_to.is_(None), GstRate.effective_to > today),
        GstRate.deleted_at.is_(None),
    ).order_by(GstRate.effective_from.desc()).limit(1))
    data = {key: getattr(settings, key) for key in ("legal_name", "display_name", "gstin", "gst_state_code", "address", "logo_storage_key", "invoice_footer", "timezone", "currency")}
    data["current_gst_rate"] = str(current_rate.rate) if current_rate else None
    return {"data": data, "request_id": getattr(request.state, "request_id", None)}


@router.post("/settings/business", status_code=201)
async def create_business_settings(body: BusinessSettingsUpdate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    if not body.legal_name or not body.display_name:
        raise HTTPException(422, "legal_name and display_name are required for initial settings")
    existing = await db.scalar(select(BusinessSettings).where(BusinessSettings.business_id == context.business.id))
    if existing is not None:
        raise HTTPException(409, "Business settings already exist")
    row = BusinessSettings(business_id=context.business.id, created_by_id=user.id, **body.model_dump(exclude_unset=True))
    db.add(row)
    await db.flush()
    await add_audit(db, user, context, "create", "business_settings", row.id, after=body.model_dump(exclude_unset=True))
    await db.commit()
    return {"data": {"id": str(row.id), "legal_name": row.legal_name, "display_name": row.display_name}, "request_id": getattr(request.state, "request_id", None)}


@router.patch("/settings/business")
async def update_business_settings(body: BusinessSettingsUpdate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    settings = await db.scalar(select(BusinessSettings).where(BusinessSettings.business_id == context.business.id, BusinessSettings.deleted_at.is_(None)).with_for_update())
    if settings is None:
        raise HTTPException(409, "Create initial business settings before editing")
    fields = tuple(body.model_fields)
    before = snapshot(settings, fields)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)
    settings.updated_by_id = user.id
    await add_audit(db, user, context, "update", "business_settings", settings.id, before, snapshot(settings, fields))
    await db.commit()
    return {"data": {key: getattr(settings, key) for key in fields}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/settings/gst-rates")
async def list_gst_rates(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    rows = list((await db.scalars(select(GstRate).where(GstRate.business_id == context.business.id, GstRate.deleted_at.is_(None)).order_by(GstRate.effective_from.desc()).offset(offset).limit(limit + 1))).all())
    return page_result([{"id": str(row.id), "rate": str(row.rate), "effective_from": row.effective_from.isoformat(), "effective_to": row.effective_to.isoformat() if row.effective_to else None} for row in rows], limit, offset, getattr(request.state, "request_id", None))


@router.post("/settings/gst-rates", status_code=201)
async def create_gst_rate(body: EffectiveRateCreate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*GST_CONFIGURATORS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    next_start, changed_rates = await prepare_rate_history(db, GstRate, context.business.id, body.effective_from)
    for previous, old_end in changed_rates:
        await add_audit(db, user, context, "update", "gst_rate", previous.id, {"effective_to": old_end}, {"effective_to": previous.effective_to})
    rate = GstRate(business_id=context.business.id, created_by_id=user.id, configured_by_id=user.id, effective_to=next_start, **body.model_dump())
    db.add(rate)
    await db.flush()
    await add_audit(db, user, context, "create", "gst_rate", rate.id, after={"rate": rate.rate, "effective_from": rate.effective_from})
    await db.commit()
    return {"data": {"id": str(rate.id), "rate": str(rate.rate), "effective_from": rate.effective_from.isoformat()}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/settings/brick-types")
async def list_brick_types(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], include_inactive: bool = False, limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(BrickType).where(BrickType.business_id == context.business.id, BrickType.deleted_at.is_(None))
    if not include_inactive:
        query = query.where(BrickType.is_active.is_(True))
    rows = list((await db.scalars(query.order_by(BrickType.name).offset(offset).limit(limit + 1))).all())
    return page_result([{"id": str(row.id), "name": row.name, "description": row.description, "is_active": row.is_active} for row in rows], limit, offset, getattr(request.state, "request_id", None))


@router.post("/settings/brick-types", status_code=201)
async def create_brick_type(body: BrickTypeInput, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    row = BrickType(business_id=context.business.id, created_by_id=user.id, **body.model_dump())
    db.add(row)
    await db.flush()
    await add_audit(db, user, context, "create", "brick_type", row.id, after=body.model_dump())
    await db.commit()
    return {"data": {"id": str(row.id), **body.model_dump(), "is_active": row.is_active}, "request_id": getattr(request.state, "request_id", None)}


@router.patch("/settings/brick-types/{brick_type_id}")
async def update_brick_type(brick_type_id: uuid.UUID, body: BrickTypeInput, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    row = await db.scalar(select(BrickType).where(BrickType.id == brick_type_id, BrickType.business_id == context.business.id, BrickType.deleted_at.is_(None)).with_for_update())
    if row is None:
        raise HTTPException(404, "Brick type not found")
    before = snapshot(row, ("name", "description", "is_active"))
    row.name, row.description, row.updated_by_id = body.name, body.description, user.id
    await add_audit(db, user, context, "update", "brick_type", row.id, before, snapshot(row, tuple(before)))
    await db.commit()
    return {"data": {"id": str(row.id), **snapshot(row, tuple(before))}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/settings/brick-rates")
async def list_brick_rates(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], brick_type_id: uuid.UUID | None = None, limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(BrickRate).where(BrickRate.business_id == context.business.id, BrickRate.deleted_at.is_(None))
    if brick_type_id:
        query = query.where(BrickRate.brick_type_id == brick_type_id)
    rows = list((await db.scalars(query.order_by(BrickRate.effective_from.desc()).offset(offset).limit(limit + 1))).all())
    return page_result([{"id": str(row.id), "brick_type_id": str(row.brick_type_id), "rate": str(row.rate), "effective_from": row.effective_from.isoformat(), "effective_to": row.effective_to.isoformat() if row.effective_to else None} for row in rows], limit, offset, getattr(request.state, "request_id", None))


@router.post("/settings/brick-rates", status_code=201)
async def create_brick_rate(body: BrickRateInput, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    brick = await db.scalar(select(BrickType).where(BrickType.id == body.brick_type_id, BrickType.business_id == context.business.id, BrickType.deleted_at.is_(None)))
    if brick is None:
        raise HTTPException(404, "Brick type not found")
    next_start, changed_rates = await prepare_rate_history(db, BrickRate, context.business.id, body.effective_from)
    for previous, old_end in changed_rates:
        await add_audit(db, user, context, "update", "brick_rate", previous.id, {"effective_to": old_end}, {"effective_to": previous.effective_to})
    row = BrickRate(business_id=context.business.id, created_by_id=user.id, effective_to=next_start, **body.model_dump())
    db.add(row)
    await db.flush()
    await add_audit(db, user, context, "create", "brick_rate", row.id, after=body.model_dump())
    await db.commit()
    return {"data": {"id": str(row.id), "brick_type_id": str(row.brick_type_id), "rate": str(row.rate), "effective_from": row.effective_from.isoformat()}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/settings/expense-categories")
async def list_categories(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], include_inactive: bool = False, limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(ExpenseCategory).where(ExpenseCategory.business_id == context.business.id, ExpenseCategory.deleted_at.is_(None))
    if not include_inactive:
        query = query.where(ExpenseCategory.is_active.is_(True))
    rows = list((await db.scalars(query.order_by(ExpenseCategory.name).offset(offset).limit(limit + 1))).all())
    return page_result([{"id": str(row.id), "name": row.name, "expense_type": row.expense_type.value, "is_active": row.is_active} for row in rows], limit, offset, getattr(request.state, "request_id", None))


@router.post("/settings/expense-categories", status_code=201)
async def create_category(body: CategoryInput, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    row = ExpenseCategory(business_id=context.business.id, created_by_id=user.id, **body.model_dump())
    db.add(row)
    await db.flush()
    await add_audit(db, user, context, "create", "expense_category", row.id, after=body.model_dump())
    await db.commit()
    return {"data": {"id": str(row.id), "name": row.name, "expense_type": row.expense_type.value}, "request_id": getattr(request.state, "request_id", None)}


@router.patch("/settings/expense-categories/{category_id}")
async def update_category(category_id: uuid.UUID, body: ActiveUpdate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    row = await db.scalar(select(ExpenseCategory).where(ExpenseCategory.id == category_id, ExpenseCategory.business_id == context.business.id, ExpenseCategory.deleted_at.is_(None)).with_for_update())
    if row is None:
        raise HTTPException(404, "Expense category not found")
    before = {"is_active": row.is_active}
    row.is_active = body.is_active
    row.updated_by_id = user.id
    await add_audit(db, user, context, "update", "expense_category", row.id, before, {"is_active": row.is_active})
    await db.commit()
    return {"data": {"id": str(row.id), "is_active": row.is_active}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/settings/vehicles")
async def list_vehicles(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], include_inactive: bool = False, limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(Vehicle).where(Vehicle.business_id == context.business.id, Vehicle.deleted_at.is_(None))
    if not include_inactive:
        query = query.where(Vehicle.is_active.is_(True))
    rows = list((await db.scalars(query.order_by(Vehicle.registration_number).offset(offset).limit(limit + 1))).all())
    return page_result([{"id": str(row.id), "registration_number": row.registration_number, "description": row.description, "is_active": row.is_active} for row in rows], limit, offset, getattr(request.state, "request_id", None))


@router.post("/settings/vehicles", status_code=201)
async def create_vehicle(body: VehicleInput, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    row = Vehicle(business_id=context.business.id, created_by_id=user.id, **body.model_dump())
    db.add(row)
    await db.flush()
    await add_audit(db, user, context, "create", "vehicle", row.id, after=body.model_dump())
    await db.commit()
    return {"data": {"id": str(row.id), **body.model_dump(), "is_active": row.is_active}, "request_id": getattr(request.state, "request_id", None)}


@router.patch("/settings/vehicles/{vehicle_id}")
async def update_vehicle(vehicle_id: uuid.UUID, body: VehicleInput | ActiveUpdate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    row = await db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.business_id == context.business.id, Vehicle.deleted_at.is_(None)).with_for_update())
    if row is None:
        raise HTTPException(404, "Vehicle not found")
    before = {"registration_number": row.registration_number, "description": row.description, "is_active": row.is_active}
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_by_id = user.id
    await add_audit(db, user, context, "update", "vehicle", row.id, before, snapshot(row, tuple(before)))
    await db.commit()
    return {"data": {"id": str(row.id), **snapshot(row, tuple(before))}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/settings/employees")
async def list_employees(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], q: str | None = None, include_inactive: bool = False, limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(Employee).where(Employee.business_id == context.business.id, Employee.deleted_at.is_(None))
    if not include_inactive:
        query = query.where(Employee.is_active.is_(True))
    if q:
        query = query.where(or_(Employee.name.ilike(f"%{q}%"), Employee.employee_code.ilike(f"%{q}%"), Employee.mobile.ilike(f"%{q}%")))
    rows = list((await db.scalars(query.order_by(Employee.name).offset(offset).limit(limit + 1))).all())
    return page_result([{"id": str(row.id), "employee_code": row.employee_code, "name": row.name, "mobile": row.mobile, "is_active": row.is_active} for row in rows], limit, offset, getattr(request.state, "request_id", None))


@router.get("/settings/responsible-managers")
async def list_responsible_managers(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)]) -> dict:
    rows = await db.execute(
        select(AppUser, BusinessMembership)
        .join(BusinessMembership, BusinessMembership.user_id == AppUser.id)
        .where(
            BusinessMembership.business_id == context.business.id,
            BusinessMembership.is_active.is_(True),
            AppUser.is_active.is_(True),
        )
        .order_by(AppUser.name)
    )
    data = [
        {"id": str(user.id), "name": user.name, "role": membership.role.value}
        for user, membership in rows.all()
        if membership.role in (BusinessRole.MANAGER, BusinessRole.ASST_MANAGER)
    ]
    return {"data": data, "request_id": getattr(request.state, "request_id", None)}


@router.post("/settings/employees", status_code=201)
async def create_employee(body: EmployeeInput, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    row = Employee(business_id=context.business.id, created_by_id=user.id, **body.model_dump())
    db.add(row)
    await db.flush()
    await add_audit(db, user, context, "create", "employee", row.id, after=body.model_dump())
    await db.commit()
    return {"data": {"id": str(row.id), **body.model_dump(), "is_active": row.is_active}, "request_id": getattr(request.state, "request_id", None)}


@router.patch("/settings/employees/{employee_id}")
async def update_employee(employee_id: uuid.UUID, body: EmployeeInput | ActiveUpdate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*ADMINS))], user: Annotated[AppUser, Depends(current_user)]) -> dict:
    row = await db.scalar(select(Employee).where(Employee.id == employee_id, Employee.business_id == context.business.id, Employee.deleted_at.is_(None)).with_for_update())
    if row is None:
        raise HTTPException(404, "Employee not found")
    before = {"employee_code": row.employee_code, "name": row.name, "mobile": row.mobile, "is_active": row.is_active}
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_by_id = user.id
    await add_audit(db, user, context, "update", "employee", row.id, before, snapshot(row, tuple(before)))
    await db.commit()
    return {"data": {"id": str(row.id), **snapshot(row, tuple(before))}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/users")
async def list_users(request: Request, db: Db, user: Annotated[AppUser, Depends(current_user)], business_id: uuid.UUID | None = None, q: str | None = None, limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    if user.organization_role not in ADMINS:
        raise HTTPException(403, "Admin access required")
    offset = decode_cursor(cursor)
    query = select(AppUser).where(AppUser.is_active.is_(True))
    if q:
        query = query.where(or_(AppUser.name.ilike(f"%{q}%"), AppUser.email.ilike(f"%{q}%"), AppUser.phone.ilike(f"%{q}%")))
    if business_id:
        member_ids = select(BusinessMembership.user_id).where(
            BusinessMembership.business_id == business_id,
            BusinessMembership.is_active.is_(True),
        )
        query = query.where(or_(AppUser.organization_role.is_not(None), AppUser.id.in_(member_ids)))
    rows = list((await db.scalars(query.order_by(AppUser.name).offset(offset).limit(limit + 1))).all())
    data = []
    for row in rows:
        data.append({"id": str(row.id), "name": row.name, "email": row.email, "phone": row.phone, "organization_role": row.organization_role.value if row.organization_role else None, "is_active": row.is_active})
    return page_result(data, limit, offset, getattr(request.state, "request_id", None))


@router.post("/users", status_code=201)
async def create_user(body: UserCreate, request: Request, db: Db, actor: Annotated[AppUser, Depends(current_user)]) -> dict:
    if actor.organization_role not in ADMINS:
        raise HTTPException(403, "Admin access required")
    if body.organization_role == OrganizationRole.SUPER_ADMIN and actor.organization_role != OrganizationRole.SUPER_ADMIN:
        raise HTTPException(403, "Only Super Admin can grant Super Admin")
    if body.business_id is not None:
        business = await db.get(Business, body.business_id)
        if business is None or not business.is_active:
            raise HTTPException(404, "Business not found")
    values = body.model_dump(exclude={"business_id", "business_role"})
    values["email"] = str(body.email).casefold() if body.email else None
    temporary_password = secrets.token_urlsafe(18)
    values["password_hash"] = hash_password(temporary_password)
    values["must_change_password"] = True
    target = AppUser(**values)
    db.add(target)
    await db.flush()
    context = None
    if body.business_id and body.business_role:
        db.add(BusinessMembership(user_id=target.id, business_id=body.business_id, role=body.business_role, is_active=True))
        business = await db.get(Business, body.business_id)
        context = BusinessContext(business=business, role=actor.organization_role)
    await add_audit(db, actor, context, "create", "user", target.id, after={"name": target.name, "email": target.email, "phone": target.phone, "organization_role": target.organization_role.value if target.organization_role else None, "business_id": body.business_id, "business_role": body.business_role.value if body.business_role else None})
    await db.commit()
    invite_sent = False if target.email else None
    if target.email:
        try:
            await SMTPEmailDelivery().send_invitation(target.email, target.name, temporary_password)
            invite_sent = True
        except Exception:
            logger.exception("User invitation email delivery failed", extra={"user_id": str(target.id)})
    return {"data": {"id": str(target.id), "name": target.name, "email": target.email, "phone": target.phone, "organization_role": target.organization_role.value if target.organization_role else None, "invite_sent": invite_sent, "temporary_password": None if invite_sent else temporary_password}, "request_id": getattr(request.state, "request_id", None)}


@router.post("/users/{target_id}/temporary-password")
async def reset_user_temporary_password(target_id: uuid.UUID, request: Request, db: Db, actor: Annotated[AppUser, Depends(current_user)]) -> dict:
    if actor.organization_role not in ADMINS:
        raise HTTPException(403, "Admin access required")
    if target_id == actor.id:
        raise HTTPException(409, "Use change password to update your own password")
    target = await db.scalar(select(AppUser).where(AppUser.id == target_id).with_for_update())
    if target is None:
        raise HTTPException(404, "User not found")
    if target.organization_role == OrganizationRole.SUPER_ADMIN and actor.organization_role != OrganizationRole.SUPER_ADMIN:
        raise HTTPException(403, "Only Super Admin can reset a Super Admin password")
    temporary_password = secrets.token_urlsafe(18)
    target.password_hash = hash_password(temporary_password)
    target.must_change_password = True
    await db.execute(
        AuthSession.__table__.update()
        .where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    await add_audit(db, actor, None, "password_reset", "user", target.id, after={"must_change_password": True})
    await db.commit()
    invite_sent = False if target.email else None
    if target.email:
        try:
            await SMTPEmailDelivery().send_invitation(target.email, target.name, temporary_password)
            invite_sent = True
        except Exception:
            logger.exception("Temporary password email delivery failed", extra={"user_id": str(target.id)})
    return {"data": {"user_id": str(target.id), "invite_sent": invite_sent, "temporary_password": None if invite_sent else temporary_password}, "request_id": getattr(request.state, "request_id", None)}


@router.patch("/users/{target_id}")
async def update_user(target_id: uuid.UUID, body: UserUpdate, request: Request, db: Db, actor: Annotated[AppUser, Depends(current_user)]) -> dict:
    if actor.organization_role not in ADMINS:
        raise HTTPException(403, "Admin access required")
    target = await db.scalar(select(AppUser).where(AppUser.id == target_id).with_for_update())
    if target is None:
        raise HTTPException(404, "User not found")
    values = body.model_dump(exclude_unset=True)
    requested_role = values.get("organization_role")
    if requested_role == OrganizationRole.SUPER_ADMIN and actor.organization_role != OrganizationRole.SUPER_ADMIN:
        raise HTTPException(403, "Only Super Admin can grant Super Admin")
    if target.organization_role == OrganizationRole.SUPER_ADMIN and actor.organization_role != OrganizationRole.SUPER_ADMIN:
        raise HTTPException(403, "Only Super Admin can edit a Super Admin")
    before = {"name": target.name, "email": target.email, "phone": target.phone, "organization_role": target.organization_role.value if target.organization_role else None, "is_active": target.is_active}
    business_id = values.pop("business_id", None)
    business_role = values.pop("business_role", None)
    for key, value in values.items():
        if key == "email" and value:
            value = str(value).casefold()
        setattr(target, key, value)
    if business_id is not None:
        business = await db.get(Business, business_id)
        if business is None or not business.is_active:
            raise HTTPException(404, "Business not found")
        membership = await db.scalar(select(BusinessMembership).where(BusinessMembership.user_id == target.id, BusinessMembership.is_active.is_(True)).with_for_update())
        if membership is not None:
            membership.business_id = business_id
            membership.role = business_role
        else:
            db.add(BusinessMembership(user_id=target.id, business_id=business_id, role=business_role, is_active=True))
        target.organization_role = None
    elif requested_role is not None:
        await db.execute(
            BusinessMembership.__table__.update().where(BusinessMembership.user_id == target.id).values(is_active=False)
        )
    if target.is_active is False:
        await db.execute(
            AuthSession.__table__.update().where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None)).values(revoked_at=func.now())
        )
    after = {"name": target.name, "email": target.email, "phone": target.phone, "organization_role": target.organization_role.value if target.organization_role else None, "business_id": business_id, "business_role": business_role.value if business_role else None, "is_active": target.is_active}
    await add_audit(db, actor, None, "update", "user", target.id, before, after)
    await db.commit()
    return {"data": {"id": str(target.id), **after}, "request_id": getattr(request.state, "request_id", None)}


@router.delete("/users/{target_id}", status_code=204)
async def deactivate_user(target_id: uuid.UUID, db: Db, actor: Annotated[AppUser, Depends(current_user)]) -> None:
    if actor.organization_role not in ADMINS:
        raise HTTPException(403, "Admin access required")
    if target_id == actor.id:
        raise HTTPException(409, "You cannot deactivate your own account")
    target = await db.scalar(select(AppUser).where(AppUser.id == target_id).with_for_update())
    if target is None:
        raise HTTPException(404, "User not found")
    if target.organization_role == OrganizationRole.SUPER_ADMIN and actor.organization_role != OrganizationRole.SUPER_ADMIN:
        raise HTTPException(403, "Only Super Admin can deactivate a Super Admin")
    target.is_active = False
    await db.execute(AuthSession.__table__.update().where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None)).values(revoked_at=func.now()))
    await add_audit(db, actor, None, "deactivate", "user", target.id, {"is_active": True}, {"is_active": False})
    await db.commit()