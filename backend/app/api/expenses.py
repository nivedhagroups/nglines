from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.api.common import add_audit, decode_cursor, encode_cursor, page_result, snapshot
from app.api.deps import BusinessContext, Db, User, business_context, current_user, require_roles
from app.db.base import BusinessRole, ExpenseType, OrganizationRole, SalaryPeriod
from app.db.session import get_db
from app.models import AdvanceRecovery, BusinessMembership, Employee, Expense, ExpenseCategory, FileAttachment, StoredFile, Vehicle
from app.services.files import resolve_storage_path, store_business_file


router = APIRouter(tags=["expenses"])
WRITERS = tuple(OrganizationRole) + tuple(BusinessRole)
READ_FIELDS = ("expense_type", "expense_date", "category_id", "amount", "description", "vehicle_id", "litres", "unit_rate", "employee_id", "salary_period", "recipient_name", "responsible_user_id")


class ExpenseCreate(BaseModel):
    expense_type: ExpenseType
    category_id: uuid.UUID
    expense_date: date
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    description: str | None = None
    vehicle_id: uuid.UUID | None = None
    litres: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit_rate: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    employee_id: uuid.UUID | None = None
    salary_period: SalaryPeriod | None = None
    recipient_name: str | None = Field(default=None, max_length=160)
    responsible_manager_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_type_fields(self):
        if self.expense_type == ExpenseType.DIESEL and not all((self.vehicle_id, self.litres is not None, self.unit_rate is not None)):
            raise ValueError("Diesel expenses require vehicle_id, litres, and unit_rate")
        if self.expense_type == ExpenseType.SALARY and self.salary_period is None:
            raise ValueError("Salary expenses require salary_period")
        if self.expense_type == ExpenseType.SALARY_ADVANCE and not (self.employee_id or self.recipient_name):
            raise ValueError("Salary advance requires an employee or recipient_name")
        return self


class ExpenseUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    expense_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    description: str | None = None
    vehicle_id: uuid.UUID | None = None
    litres: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit_rate: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    employee_id: uuid.UUID | None = None
    salary_period: SalaryPeriod | None = None
    recipient_name: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_patch_fields(self):
        for field in ("category_id", "expense_date", "amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be cleared")
        return self


class RecoveryCreate(BaseModel):
    recovery_date: date
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    notes: str | None = None


async def validate_refs(db, context: BusinessContext, body: ExpenseCreate | ExpenseUpdate, expense_type: ExpenseType) -> None:
    if body.category_id is not None:
        category = await db.scalar(select(ExpenseCategory).where(ExpenseCategory.id == body.category_id, ExpenseCategory.business_id == context.business.id, ExpenseCategory.deleted_at.is_(None), ExpenseCategory.is_active.is_(True)))
        if category is None or category.expense_type != expense_type:
            raise HTTPException(422, "Active category does not match the expense type")
    if body.vehicle_id:
        vehicle = await db.scalar(select(Vehicle).where(Vehicle.id == body.vehicle_id, Vehicle.business_id == context.business.id, Vehicle.deleted_at.is_(None), Vehicle.is_active.is_(True)))
        if vehicle is None:
            raise HTTPException(422, "Vehicle is unavailable")
    if body.employee_id:
        employee = await db.scalar(select(Employee).where(Employee.id == body.employee_id, Employee.business_id == context.business.id, Employee.deleted_at.is_(None), Employee.is_active.is_(True)))
        if employee is None:
            raise HTTPException(422, "Employee is unavailable")


async def resolve_responsible(db, context: BusinessContext, user: User, requested_id: uuid.UUID | None) -> uuid.UUID:
    target_id = requested_id
    if isinstance(context.role, BusinessRole):
        if target_id is not None and target_id != user.id:
            raise HTTPException(403, "Managers can assign only themselves as responsible")
        target_id = user.id
    if target_id is None:
        raise HTTPException(422, "responsible_manager_id is required for group-level users")
    membership = await db.scalar(select(BusinessMembership).where(
        BusinessMembership.business_id == context.business.id,
        BusinessMembership.user_id == target_id,
        BusinessMembership.is_active.is_(True),
    ))
    if membership is None or membership.role not in (BusinessRole.MANAGER, BusinessRole.ASST_MANAGER):
        raise HTTPException(422, "Responsible user must be an active manager in this business")
    return target_id


@router.get("/expenses")
async def list_expenses(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], expense_type: ExpenseType | None = None, category_id: uuid.UUID | None = None, vehicle_id: uuid.UUID | None = None, employee_id: uuid.UUID | None = None, from_date: date | None = Query(None, alias="from"), to_date: date | None = Query(None, alias="to"), limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(Expense).where(Expense.business_id == context.business.id, Expense.deleted_at.is_(None))
    for column, value in ((Expense.expense_type, expense_type), (Expense.category_id, category_id), (Expense.vehicle_id, vehicle_id), (Expense.employee_id, employee_id)):
        if value is not None:
            query = query.where(column == value)
    if from_date:
        query = query.where(Expense.expense_date >= from_date)
    if to_date:
        query = query.where(Expense.expense_date <= to_date)
    rows = list((await db.scalars(query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).offset(offset).limit(limit + 1))).all())
    data = [{"id": str(row.id), **snapshot(row, READ_FIELDS)} for row in rows]
    return page_result(data, limit, offset, getattr(request.state, "request_id", None))


@router.post("/expenses", status_code=201)
async def create_expense(body: ExpenseCreate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*WRITERS))], user: Annotated[User, Depends(current_user)]) -> dict:
    await validate_refs(db, context, body, body.expense_type)
    responsible_id = await resolve_responsible(db, context, user, body.responsible_manager_id)
    values = body.model_dump()
    values.pop("responsible_manager_id", None)
    if body.expense_type == ExpenseType.DIESEL:
        calculated = (body.litres * body.unit_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if calculated != body.amount:
            raise HTTPException(422, "Diesel amount must equal litres multiplied by unit rate")
    expense = Expense(business_id=context.business.id, created_by_id=user.id, responsible_user_id=responsible_id, **values)
    db.add(expense)
    await db.flush()
    await add_audit(db, user, context, "create", "expense", expense.id, after=snapshot(expense, READ_FIELDS))
    await db.commit()
    return {"data": {"id": str(expense.id), **snapshot(expense, READ_FIELDS)}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/expenses/{expense_id}")
async def get_expense(expense_id: uuid.UUID, request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)]) -> dict:
    expense = await db.scalar(select(Expense).where(Expense.id == expense_id, Expense.business_id == context.business.id, Expense.deleted_at.is_(None)))
    if expense is None:
        raise HTTPException(404, "Expense not found")
    attachments = await db.execute(
        select(FileAttachment, StoredFile)
        .join(StoredFile, (StoredFile.id == FileAttachment.file_id) & (StoredFile.business_id == FileAttachment.business_id))
        .where(FileAttachment.business_id == context.business.id, FileAttachment.entity_type == "expense", FileAttachment.entity_id == expense.id, FileAttachment.deleted_at.is_(None), StoredFile.deleted_at.is_(None))
    )
    files = [{"id": str(link.id), "filename": file.original_filename, "content_type": file.content_type, "size_bytes": file.size_bytes} for link, file in attachments.all()]
    return {"data": {"id": str(expense.id), **snapshot(expense, READ_FIELDS), "attachments": files}, "request_id": getattr(request.state, "request_id", None)}


@router.post("/expenses/{expense_id}/attachments", status_code=201)
async def upload_expense_attachment(expense_id: uuid.UUID, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*WRITERS))], user: Annotated[User, Depends(current_user)], attachment: UploadFile = File(...)) -> dict:
    expense = await db.scalar(select(Expense).where(Expense.id == expense_id, Expense.business_id == context.business.id, Expense.deleted_at.is_(None)))
    if expense is None:
        raise HTTPException(404, "Expense not found")
    stored = await store_business_file(db, attachment, context.business.id, user.id, "expense-attachments")
    link = FileAttachment(business_id=context.business.id, created_by_id=user.id, file_id=stored.id, entity_type="expense", entity_id=expense.id)
    db.add(link)
    await db.flush()
    await add_audit(db, user, context, "create", "expense_attachment", link.id, after={"expense_id": expense.id, "file_id": stored.id, "sha256": stored.sha256})
    await db.commit()
    return {"data": {"id": str(link.id), "filename": stored.original_filename, "content_type": stored.content_type, "size_bytes": stored.size_bytes}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/expenses/{expense_id}/attachments/{attachment_id}")
async def get_expense_attachment(expense_id: uuid.UUID, attachment_id: uuid.UUID, db: Db, context: Annotated[BusinessContext, Depends(business_context)]) -> FileResponse:
    expense = await db.scalar(select(Expense.id).where(Expense.id == expense_id, Expense.business_id == context.business.id, Expense.deleted_at.is_(None)))
    if expense is None:
        raise HTTPException(404, "Attachment not found")
    link = await db.scalar(select(FileAttachment).where(FileAttachment.id == attachment_id, FileAttachment.business_id == context.business.id, FileAttachment.entity_type == "expense", FileAttachment.entity_id == expense_id, FileAttachment.deleted_at.is_(None)))
    if link is None:
        raise HTTPException(404, "Attachment not found")
    stored = await db.scalar(select(StoredFile).where(StoredFile.id == link.file_id, StoredFile.business_id == context.business.id, StoredFile.deleted_at.is_(None)))
    if stored is None:
        raise HTTPException(404, "Attachment not found")
    path = resolve_storage_path(stored.storage_path)
    if not path.is_file():
        raise HTTPException(404, "Attachment file not found")
    return FileResponse(path, media_type=stored.content_type, filename=stored.original_filename)


@router.patch("/expenses/{expense_id}")
async def update_expense(expense_id: uuid.UUID, body: ExpenseUpdate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*WRITERS))], user: Annotated[User, Depends(current_user)]) -> dict:
    expense = await db.scalar(select(Expense).where(Expense.id == expense_id, Expense.business_id == context.business.id, Expense.deleted_at.is_(None)).with_for_update())
    if expense is None:
        raise HTTPException(404, "Expense not found")
    before = snapshot(expense, READ_FIELDS)
    values = body.model_dump(exclude_unset=True)
    combined = {**before, **values}
    validation_body = ExpenseUpdate.model_validate({key: combined[key] for key in ExpenseUpdate.model_fields if key in combined})
    await validate_refs(db, context, validation_body, expense.expense_type)
    if expense.expense_type == ExpenseType.DIESEL:
        diesel_values = {**combined, **values}
        if not diesel_values.get("vehicle_id") or diesel_values.get("litres") is None or diesel_values.get("unit_rate") is None:
            raise HTTPException(422, "Diesel expenses require vehicle, litres, and unit rate")
    for key, value in values.items():
        setattr(expense, key, value)
    if expense.expense_type == ExpenseType.DIESEL and (expense.litres * expense.unit_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != expense.amount:
        raise HTTPException(422, "Diesel amount must equal litres multiplied by unit rate")
    expense.updated_by_id = user.id
    await add_audit(db, user, context, "update", "expense", expense.id, before, snapshot(expense, READ_FIELDS))
    await db.commit()
    return {"data": {"id": str(expense.id), **snapshot(expense, READ_FIELDS)}, "request_id": getattr(request.state, "request_id", None)}


@router.delete("/expenses/{expense_id}", status_code=204)
async def delete_expense(expense_id: uuid.UUID, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)], reason: str = Query(..., min_length=3)) -> None:
    expense = await db.scalar(select(Expense).where(Expense.id == expense_id, Expense.business_id == context.business.id, Expense.deleted_at.is_(None)).with_for_update())
    if expense is None:
        raise HTTPException(404, "Expense not found")
    if expense.expense_type == ExpenseType.SALARY_ADVANCE:
        recovered = await db.scalar(select(func.coalesce(func.sum(AdvanceRecovery.amount), 0)).where(AdvanceRecovery.advance_expense_id == expense.id, AdvanceRecovery.business_id == context.business.id, AdvanceRecovery.deleted_at.is_(None)))
        if recovered:
            raise HTTPException(409, "Salary advances with recorded recoveries cannot be deleted")
    before = snapshot(expense, READ_FIELDS)
    expense.deleted_at = datetime.now(timezone.utc)
    expense.updated_by_id = user.id
    await add_audit(db, user, context, "delete", "expense", expense.id, before, {"reason": reason})
    await db.commit()


@router.get("/reports/expenses/diesel")
async def diesel_report(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], vehicle_id: uuid.UUID, from_date: date = Query(..., alias="from"), to_date: date = Query(..., alias="to"), group_by: str = Query("day", pattern="^(day|week|month)$")) -> dict:
    if from_date > to_date:
        raise HTTPException(422, "from must be on or before to")
    bucket = func.date_trunc(group_by, Expense.expense_date).label("period")
    rows = await db.execute(select(bucket, func.sum(Expense.litres), func.sum(Expense.amount)).where(
        Expense.business_id == context.business.id,
        Expense.vehicle_id == vehicle_id,
        Expense.expense_type == ExpenseType.DIESEL,
        Expense.expense_date.between(from_date, to_date),
        Expense.deleted_at.is_(None),
    ).group_by(bucket).order_by(bucket))
    return {"data": [{"period": period.date().isoformat(), "litres": str(litres or 0), "amount": str(amount or 0)} for period, litres, amount in rows], "request_id": getattr(request.state, "request_id", None)}


@router.get("/employees/{employee_id}/advances")
async def employee_advances(employee_id: uuid.UUID, request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], from_date: date | None = Query(None, alias="from"), to_date: date | None = Query(None, alias="to"), limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    employee = await db.scalar(select(Employee).where(Employee.id == employee_id, Employee.business_id == context.business.id, Employee.deleted_at.is_(None)))
    if employee is None:
        raise HTTPException(404, "Employee not found")
    offset = decode_cursor(cursor)
    query = select(Expense).where(Expense.business_id == context.business.id, Expense.employee_id == employee_id, Expense.expense_type == ExpenseType.SALARY_ADVANCE, Expense.deleted_at.is_(None))
    if from_date:
        query = query.where(Expense.expense_date >= from_date)
    if to_date:
        query = query.where(Expense.expense_date <= to_date)
    advances = list((await db.scalars(query.order_by(Expense.expense_date.desc()).offset(offset).limit(limit + 1))).all())
    result = []
    for advance in advances[:limit]:
        recovered = await db.scalar(select(func.coalesce(func.sum(AdvanceRecovery.amount), 0)).where(AdvanceRecovery.advance_expense_id == advance.id, AdvanceRecovery.business_id == context.business.id, AdvanceRecovery.deleted_at.is_(None)))
        result.append({"expense_id": str(advance.id), "date": advance.expense_date.isoformat(), "amount": str(advance.amount), "recovered": str(recovered), "outstanding": str(advance.amount - recovered)})
    return {"data": result, "page": {"limit": limit, "next_cursor": encode_cursor(offset + limit) if len(advances) > limit else None}, "request_id": getattr(request.state, "request_id", None)}


@router.post("/expenses/{expense_id}/recoveries", status_code=201)
async def add_recovery(expense_id: uuid.UUID, body: RecoveryCreate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*WRITERS))], user: Annotated[User, Depends(current_user)]) -> dict:
    advance = await db.scalar(select(Expense).where(Expense.id == expense_id, Expense.business_id == context.business.id, Expense.expense_type == ExpenseType.SALARY_ADVANCE, Expense.deleted_at.is_(None)).with_for_update())
    if advance is None:
        raise HTTPException(404, "Salary advance not found")
    recovered = await db.scalar(select(func.coalesce(func.sum(AdvanceRecovery.amount), 0)).where(AdvanceRecovery.advance_expense_id == advance.id, AdvanceRecovery.business_id == context.business.id, AdvanceRecovery.deleted_at.is_(None)))
    if recovered + body.amount > advance.amount:
        raise HTTPException(409, "Recovery exceeds outstanding advance balance")
    recovery = AdvanceRecovery(business_id=context.business.id, created_by_id=user.id, advance_expense_id=advance.id, **body.model_dump())
    db.add(recovery)
    await db.flush()
    await add_audit(db, user, context, "create", "advance_recovery", recovery.id, after={"advance_expense_id": advance.id, "amount": body.amount})
    await db.commit()
    return {"data": {"id": str(recovery.id), "advance_expense_id": str(advance.id), "amount": str(recovery.amount), "outstanding": str(advance.amount - recovered - recovery.amount)}, "request_id": getattr(request.state, "request_id", None)}