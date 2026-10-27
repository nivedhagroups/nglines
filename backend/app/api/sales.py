from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.common import add_audit, decode_cursor, load_idempotent_response, page_result, snapshot
from app.api.deps import BusinessContext, Db, User, business_context, current_user, require_roles
from app.db.base import BusinessRole, EntityType, OrganizationRole, RecordStatus
from app.db.session import get_db
from app.core.identity import normalize_phone
from app.models.operations import StoredFile
from app.services.document_pdf import store_document_pdf
from app.services.files import resolve_storage_path
from app.models import (
    BrickRate,
    BrickType,
    BusinessSettings,
    BusinessMembership,
    Customer,
    Estimate,
    EstimateLine,
    FinancialNumberCounter,
    GstRate,
    Invoice,
    InvoiceLine,
)


router = APIRouter(tags=["sales"])
SALES_ROLES = tuple(OrganizationRole) + tuple(BusinessRole)
FINANCIAL_FIELDS = ("invoice_number", "invoice_date", "customer_id", "apply_gst", "discount_percent", "subtotal", "discount_amount", "taxable_amount", "gst_rate", "cgst_amount", "sgst_amount", "igst_amount", "total_amount", "status")
CENT = Decimal("0.01")


class LineInput(BaseModel):
    brick_type_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit_rate_override: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class InlineCustomer(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mobile: str = Field(pattern=r"^(?:\+91)?[6-9][0-9]{9}$")
    email: EmailStr | None = None
    gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    location: str | None = None

    @field_validator("mobile")
    @classmethod
    def normalize_mobile(cls, value: str) -> str:
        return normalize_phone(value)


class SaleCreate(BaseModel):
    customer_id: uuid.UUID | None = None
    new_customer: InlineCustomer | None = None
    customer_gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    responsible_manager_id: uuid.UUID | None = None
    invoice_date: date
    apply_gst: bool = False
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2)
    items: list[LineInput] = Field(min_length=1)

    @model_validator(mode="after")
    def customer_choice(self):
        if (self.customer_id is None) == (self.new_customer is None):
            raise ValueError("Provide exactly one of customer_id or new_customer")
        return self


class ConvertEstimate(BaseModel):
    invoice_date: date


async def allocate_number(db, business_id: uuid.UUID, doc_type: str, document_date: date) -> tuple[str, int, str]:
    fy_start_year = document_date.year if document_date.month >= 4 else document_date.year - 1
    financial_year = f"{fy_start_year}-{(fy_start_year + 1) % 100:02d}"
    statement = pg_insert(FinancialNumberCounter).values(
        business_id=business_id,
        financial_year=financial_year,
        record_type=doc_type,
        last_value=1,
    ).on_conflict_do_update(
        constraint="uq_financial_number_counter",
        set_={"last_value": FinancialNumberCounter.last_value + 1},
    ).returning(FinancialNumberCounter.last_value)
    sequence = (await db.execute(statement)).scalar_one()
    prefix = "INV" if doc_type == "invoice" else "EST"
    return f"{prefix}/{financial_year}/{sequence:05d}", sequence, financial_year


async def resolve_customer(db, body: SaleCreate, context: BusinessContext, user: User) -> Customer:
    if body.new_customer is not None:
        values = body.new_customer.model_dump()
        customer = Customer(
            business_id=context.business.id,
            created_by_id=user.id,
            name=str(values["name"]).strip(),
            mobile=str(values["mobile"]).strip(),
            email=values.get("email"),
            gstin=values.get("gstin"),
            location=values.get("location"),
        )
        db.add(customer)
        await db.flush()
        await add_audit(db, user, context, "create", "customer", customer.id, after={"name": customer.name, "mobile": customer.mobile, "email": customer.email, "gstin": customer.gstin, "location": customer.location, "source": "inline_sale"})
        return customer
    customer = await db.scalar(
        select(Customer).where(
            Customer.id == body.customer_id,
            Customer.business_id == context.business.id,
            Customer.deleted_at.is_(None),
        )
    )
    if customer is None:
        raise HTTPException(404, "Customer not found")
    return customer


async def resolve_responsible_manager(db, body: SaleCreate, context: BusinessContext, user: User) -> uuid.UUID:
    target_id = body.responsible_manager_id
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


async def calculate_sale(db, body: SaleCreate, context: BusinessContext, customer: Customer, user: User, preserved_rates: dict[uuid.UUID, Decimal] | None = None):
    settings = await db.scalar(select(BusinessSettings).where(BusinessSettings.business_id == context.business.id))
    if settings is None:
        raise HTTPException(409, "Business invoice settings are not configured")
    subtotal = Decimal("0")
    lines: list[dict] = []
    for item in body.items:
        brick_type = await db.scalar(select(BrickType).where(
            BrickType.id == item.brick_type_id,
            BrickType.business_id == context.business.id,
            BrickType.deleted_at.is_(None),
            BrickType.is_active.is_(True),
        ))
        if brick_type is None:
            raise HTTPException(422, "Brick type is unavailable")
        rate = item.unit_rate_override
        if item.unit_rate_override is not None and context.role not in (OrganizationRole.SUPER_ADMIN, OrganizationRole.ADMIN):
            raise HTTPException(403, "Only Admin or Super Admin may override a brick rate")
        if rate is None:
            rate = (preserved_rates or {}).get(item.brick_type_id)
            if rate is None:
                rate = await db.scalar(select(BrickRate.rate).where(
                    BrickRate.business_id == context.business.id,
                    BrickRate.brick_type_id == item.brick_type_id,
                    BrickRate.effective_from <= body.invoice_date,
                    or_(BrickRate.effective_to.is_(None), BrickRate.effective_to > body.invoice_date),
                    BrickRate.deleted_at.is_(None),
                ).order_by(BrickRate.effective_from.desc()).limit(1))
        if rate is None:
            raise HTTPException(409, f"No effective rate configured for {brick_type.name}")
        line_total = (item.quantity * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        subtotal += line_total
        lines.append({
            "brick_type_id": brick_type.id,
            "description_snapshot": brick_type.name,
            "quantity": item.quantity,
            "unit_rate": rate,
            "line_total": line_total,
        })
    discount = (subtotal * body.discount_percent / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    taxable = subtotal - discount
    gst_rate = Decimal("0")
    cgst = sgst = igst = Decimal("0")
    if body.apply_gst:
        if not settings.gstin or not settings.gst_state_code:
            raise HTTPException(409, "Company GSTIN and state code must be configured before applying GST")
        active_gst = await db.scalar(select(GstRate).where(
            GstRate.business_id == context.business.id,
            GstRate.effective_from <= body.invoice_date,
            or_(GstRate.effective_to.is_(None), GstRate.effective_to > body.invoice_date),
            GstRate.deleted_at.is_(None),
        ).order_by(GstRate.effective_from.desc()).limit(1))
        if active_gst is None:
            raise HTTPException(409, "No effective GST rate configured")
        gst_rate = active_gst.rate
        customer_gstin = body.customer_gstin or customer.gstin
        customer_state = customer_gstin[:2] if customer_gstin else settings.gst_state_code
        if settings.gst_state_code and customer_state and customer_state != settings.gst_state_code:
            igst = (taxable * gst_rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        else:
            half_rate = gst_rate / Decimal("2")
            cgst = (taxable * half_rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
            sgst = (taxable * half_rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    total = taxable + cgst + sgst + igst
    return settings, lines, subtotal, discount, taxable, gst_rate, cgst, sgst, igst, total


def sale_snapshot_fields():
    return ("invoice_number", "invoice_date", "customer_id", "apply_gst", "discount_percent", "subtotal", "discount_amount", "taxable_amount", "gst_rate", "cgst_amount", "sgst_amount", "igst_amount", "total_amount", "status")


async def create_document(db, body: SaleCreate, context: BusinessContext, user: User, doc_type: Literal["invoice", "estimate"]):
    customer = await resolve_customer(db, body, context, user)
    responsible_id = await resolve_responsible_manager(db, body, context, user)
    settings, lines, subtotal, discount, taxable, gst_rate, cgst, sgst, igst, total = await calculate_sale(db, body, context, customer, user)
    number, sequence, fy = await allocate_number(db, context.business.id, doc_type, body.invoice_date)
    customer_gstin = body.customer_gstin or customer.gstin
    snapshots = {
        "business_id": context.business.id,
        "created_by_id": user.id,
        "customer_id": customer.id,
        "responsible_user_id": responsible_id,
        "financial_year": fy,
        "sequence_number": sequence,
        "invoice_date" if doc_type == "invoice" else "estimate_date": body.invoice_date,
        "status": RecordStatus.ISSUED,
        "apply_gst": body.apply_gst,
        "discount_percent": body.discount_percent,
        "subtotal": subtotal,
        "discount_amount": discount,
        "taxable_amount": taxable,
        "gst_rate": gst_rate,
        "cgst_amount": cgst,
        "sgst_amount": sgst,
        "igst_amount": igst,
        "total_amount": total,
        "company_name_snapshot": settings.legal_name,
        "company_gstin_snapshot": settings.gstin,
        "company_address_snapshot": settings.address,
        "company_state_code_snapshot": settings.gst_state_code,
        "customer_name_snapshot": customer.name,
        "customer_mobile_snapshot": customer.mobile,
        "customer_gstin_snapshot": customer_gstin,
        "customer_location_snapshot": customer.location,
        "footer_snapshot": settings.invoice_footer,
    }
    if doc_type == "invoice":
        document = Invoice(invoice_number=number, **snapshots)
        line_type, parent_key = InvoiceLine, "invoice_id"
    else:
        document = Estimate(estimate_number=number, **snapshots)
        line_type, parent_key = EstimateLine, "estimate_id"
    db.add(document)
    await db.flush()
    for line in lines:
        db.add(line_type(**{parent_key: document.id, "business_id": context.business.id, "created_by_id": user.id, **line}))
    await db.flush()
    await add_audit(db, user, context, "create", doc_type, document.id, after={"number": number, "customer_id": customer.id, "total_amount": total, "apply_gst": body.apply_gst})
    return document


def financial_year_for(document_date: date) -> str:
    start_year = document_date.year if document_date.month >= 4 else document_date.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


async def replace_document(db, document, body: SaleCreate, context: BusinessContext, user: User, doc_type: Literal["invoice", "estimate"]):
    if financial_year_for(body.invoice_date) != document.financial_year:
        raise HTTPException(409, "Document date cannot move to a different financial year")
    customer = await resolve_customer(db, body, context, user)
    line_type = InvoiceLine if doc_type == "invoice" else EstimateLine
    parent_key = "invoice_id" if doc_type == "invoice" else "estimate_id"
    old_lines = list((await db.scalars(select(line_type).where(getattr(line_type, parent_key) == document.id, line_type.business_id == context.business.id, line_type.deleted_at.is_(None)).with_for_update())).all())
    preserved_rates = {line.brick_type_id: line.unit_rate for line in old_lines}
    settings, lines, subtotal, discount, taxable, gst_rate, cgst, sgst, igst, total = await calculate_sale(db, body, context, customer, user, preserved_rates)
    fields = sale_snapshot_fields() if doc_type == "invoice" else (
        "estimate_number", "estimate_date", "customer_id", "apply_gst", "discount_percent", "subtotal", "discount_amount", "taxable_amount", "gst_rate", "cgst_amount", "sgst_amount", "igst_amount", "total_amount", "status"
    )
    before = snapshot(document, fields)
    document.customer_id = customer.id
    document.responsible_user_id = await resolve_responsible_manager(db, body, context, user) if body.responsible_manager_id else document.responsible_user_id
    if doc_type == "invoice":
        document.invoice_date = body.invoice_date
    else:
        document.estimate_date = body.invoice_date
    document.apply_gst = body.apply_gst
    document.discount_percent = body.discount_percent
    document.subtotal = subtotal
    document.discount_amount = discount
    document.taxable_amount = taxable
    document.gst_rate = gst_rate
    document.cgst_amount = cgst
    document.sgst_amount = sgst
    document.igst_amount = igst
    document.total_amount = total
    document.company_name_snapshot = settings.legal_name
    document.company_gstin_snapshot = settings.gstin
    document.company_address_snapshot = settings.address
    document.company_state_code_snapshot = settings.gst_state_code
    document.customer_name_snapshot = customer.name
    document.customer_mobile_snapshot = customer.mobile
    document.customer_gstin_snapshot = body.customer_gstin or customer.gstin
    document.customer_location_snapshot = customer.location
    document.footer_snapshot = settings.invoice_footer
    document.updated_by_id = user.id
    for line in old_lines:
        line.deleted_at = datetime.now(timezone.utc)
        line.updated_by_id = user.id
    replacement_lines = [line_type(**{parent_key: document.id, "business_id": context.business.id, "created_by_id": user.id, **line}) for line in lines]
    db.add_all(replacement_lines)
    await db.flush()
    await store_document_pdf(db, document, replacement_lines, doc_type, user.id)
    await add_audit(db, user, context, "update", doc_type, document.id, before, {**snapshot(document, fields), "replaced_lines": len(lines)})
    await db.commit()
    return document


@router.post("/invoices", status_code=201)
async def create_invoice(
    body: SaleCreate,
    request: Request,
    db: Db,
    context: Annotated[BusinessContext, Depends(require_roles(*SALES_ROLES))],
    user: Annotated[User, Depends(current_user)],
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict:
    record, cached = await load_idempotent_response(db, context.business.id, idempotency_key, "create_invoice", body)
    if cached is not None:
        return {"data": cached, "request_id": getattr(request.state, "request_id", None)}
    invoice = await create_document(db, body, context, user, "invoice")
    invoice_lines = list((await db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id, InvoiceLine.business_id == context.business.id, InvoiceLine.deleted_at.is_(None)))).all())
    await store_document_pdf(db, invoice, invoice_lines, "invoice", user.id)
    data = {"id": str(invoice.id), "business_id": str(invoice.business_id), "invoice_number": invoice.invoice_number, "invoice_date": invoice.invoice_date.isoformat(), "status": invoice.status.value, "subtotal": str(invoice.subtotal), "discount_amount": str(invoice.discount_amount), "taxable_amount": str(invoice.taxable_amount), "gst_rate": str(invoice.gst_rate), "cgst_amount": str(invoice.cgst_amount), "sgst_amount": str(invoice.sgst_amount), "igst_amount": str(invoice.igst_amount), "total_amount": str(invoice.total_amount), "apply_gst": invoice.apply_gst, "pdf_url": f"/invoices/{invoice.id}/pdf"}
    if record is not None:
        record.response_body = data
    await db.commit()
    return {"data": data, "request_id": getattr(request.state, "request_id", None)}


@router.post("/estimates", status_code=201)
async def create_estimate(
    body: SaleCreate,
    request: Request,
    db: Db,
    context: Annotated[BusinessContext, Depends(require_roles(*SALES_ROLES))],
    user: Annotated[User, Depends(current_user)],
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict:
    record, cached = await load_idempotent_response(db, context.business.id, idempotency_key, "create_estimate", body)
    if cached is not None:
        return {"data": cached, "request_id": getattr(request.state, "request_id", None)}
    estimate = await create_document(db, body, context, user, "estimate")
    estimate_lines = list((await db.scalars(select(EstimateLine).where(EstimateLine.estimate_id == estimate.id, EstimateLine.business_id == context.business.id, EstimateLine.deleted_at.is_(None)))).all())
    await store_document_pdf(db, estimate, estimate_lines, "estimate", user.id)
    data = {"id": str(estimate.id), "business_id": str(estimate.business_id), "estimate_number": estimate.estimate_number, "estimate_date": estimate.estimate_date.isoformat(), "status": estimate.status.value, "total_amount": str(estimate.total_amount), "apply_gst": estimate.apply_gst, "document_label": "ESTIMATE - Not a Tax Invoice", "pdf_url": f"/estimates/{estimate.id}/pdf"}
    if record is not None:
        record.response_body = data
    await db.commit()
    return {"data": data, "request_id": getattr(request.state, "request_id", None)}


@router.get("/invoices")
async def list_invoices(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], q: str | None = None, customer_id: uuid.UUID | None = None, status: RecordStatus | None = None, from_date: date | None = Query(None, alias="from"), to_date: date | None = Query(None, alias="to"), limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(Invoice).where(Invoice.business_id == context.business.id, Invoice.deleted_at.is_(None))
    if customer_id:
        query = query.where(Invoice.customer_id == customer_id)
    if status:
        query = query.where(Invoice.status == status)
    if from_date:
        query = query.where(Invoice.invoice_date >= from_date)
    if to_date:
        query = query.where(Invoice.invoice_date <= to_date)
    if q:
        query = query.where(or_(Invoice.invoice_number.ilike(f"%{q}%"), Invoice.customer_name_snapshot.ilike(f"%{q}%"), Invoice.customer_mobile_snapshot.ilike(f"%{q}%")))
    rows = list((await db.scalars(query.order_by(Invoice.invoice_date.desc(), Invoice.sequence_number.desc()).offset(offset).limit(limit + 1))).all())
    values = [{"id": str(row.id), "invoice_number": row.invoice_number, "invoice_date": row.invoice_date.isoformat(), "customer_name": row.customer_name_snapshot, "total_amount": str(row.total_amount), "status": row.status.value} for row in rows]
    return page_result(values, limit, offset, getattr(request.state, "request_id", None))


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: uuid.UUID, request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)]) -> dict:
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id == context.business.id, Invoice.deleted_at.is_(None)))
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    lines = await db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id, InvoiceLine.business_id == context.business.id, InvoiceLine.deleted_at.is_(None)))
    data = {field: getattr(invoice, field) for field in sale_snapshot_fields()}
    data.update({"id": str(invoice.id), "business_id": str(invoice.business_id), "responsible_manager_id": str(invoice.responsible_user_id) if invoice.responsible_user_id else None, "customer_name": invoice.customer_name_snapshot, "customer_mobile": invoice.customer_mobile_snapshot, "customer_gstin": invoice.customer_gstin_snapshot, "pdf_url": f"/invoices/{invoice.id}/pdf", "items": [{"brick_type_id": str(line.brick_type_id), "description": line.description_snapshot, "quantity": str(line.quantity), "unit_rate": str(line.unit_rate), "line_total": str(line.line_total)} for line in lines]})
    return {"data": data, "request_id": getattr(request.state, "request_id", None)}


@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(invoice_id: uuid.UUID, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)]) -> FileResponse:
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id == context.business.id, Invoice.deleted_at.is_(None)))
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    lines = list((await db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id, InvoiceLine.business_id == context.business.id, InvoiceLine.deleted_at.is_(None)))).all())
    stored = await db.get(StoredFile, invoice.pdf_file_id) if invoice.pdf_file_id else None
    path = resolve_storage_path(stored.storage_path) if stored else None
    if path is None or not path.is_file():
        stored = await store_document_pdf(db, invoice, lines, "invoice", user.id)
        await db.commit()
        path = resolve_storage_path(stored.storage_path)
    return FileResponse(path, media_type="application/pdf", filename=stored.original_filename)


@router.patch("/invoices/{invoice_id}")
async def update_invoice(invoice_id: uuid.UUID, body: SaleCreate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*SALES_ROLES))], user: Annotated[User, Depends(current_user)]) -> dict:
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id == context.business.id, Invoice.deleted_at.is_(None)).with_for_update())
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    invoice = await replace_document(db, invoice, body, context, user, "invoice")
    return {"data": {"id": str(invoice.id), "invoice_number": invoice.invoice_number, "invoice_date": invoice.invoice_date.isoformat(), "total_amount": str(invoice.total_amount), "status": invoice.status.value}, "request_id": getattr(request.state, "request_id", None)}


@router.delete("/invoices/{invoice_id}", status_code=204)
async def cancel_invoice(invoice_id: uuid.UUID, request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)], reason: str = Query(..., min_length=3)) -> None:
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id == context.business.id, Invoice.deleted_at.is_(None)).with_for_update())
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    before = snapshot(invoice, sale_snapshot_fields())
    invoice.status = RecordStatus.CANCELLED
    invoice.deleted_at = datetime.now(timezone.utc)
    invoice.updated_by_id = user.id
    await add_audit(db, user, context, "delete", "invoice", invoice.id, before, {"status": "cancelled", "reason": reason})
    await db.commit()


@router.get("/estimates")
async def list_estimates(request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)], q: str | None = None, customer_id: uuid.UUID | None = None, status: RecordStatus | None = None, from_date: date | None = Query(None, alias="from"), to_date: date | None = Query(None, alias="to"), limit: int = Query(25, ge=1, le=100), cursor: str | None = None) -> dict:
    offset = decode_cursor(cursor)
    query = select(Estimate).where(Estimate.business_id == context.business.id, Estimate.deleted_at.is_(None))
    if customer_id:
        query = query.where(Estimate.customer_id == customer_id)
    if status:
        query = query.where(Estimate.status == status)
    if from_date:
        query = query.where(Estimate.estimate_date >= from_date)
    if to_date:
        query = query.where(Estimate.estimate_date <= to_date)
    if q:
        query = query.where(or_(Estimate.estimate_number.ilike(f"%{q}%"), Estimate.customer_name_snapshot.ilike(f"%{q}%")))
    rows = list((await db.scalars(query.order_by(Estimate.estimate_date.desc(), Estimate.sequence_number.desc()).offset(offset).limit(limit + 1))).all())
    values = [{"id": str(row.id), "estimate_number": row.estimate_number, "estimate_date": row.estimate_date.isoformat(), "customer_name": row.customer_name_snapshot, "total_amount": str(row.total_amount), "status": row.status.value, "converted_invoice_id": str(row.converted_invoice_id) if row.converted_invoice_id else None} for row in rows]
    return page_result(values, limit, offset, getattr(request.state, "request_id", None))


@router.get("/estimates/{estimate_id}")
async def get_estimate(estimate_id: uuid.UUID, request: Request, db: Db, context: Annotated[BusinessContext, Depends(business_context)]) -> dict:
    estimate = await db.scalar(select(Estimate).where(Estimate.id == estimate_id, Estimate.business_id == context.business.id, Estimate.deleted_at.is_(None)))
    if estimate is None:
        raise HTTPException(404, "Estimate not found")
    lines = await db.scalars(select(EstimateLine).where(EstimateLine.estimate_id == estimate.id, EstimateLine.business_id == context.business.id, EstimateLine.deleted_at.is_(None)))
    return {"data": {"id": str(estimate.id), "estimate_number": estimate.estimate_number, "estimate_date": estimate.estimate_date.isoformat(), "customer_name": estimate.customer_name_snapshot, "total_amount": str(estimate.total_amount), "apply_gst": estimate.apply_gst, "converted_invoice_id": str(estimate.converted_invoice_id) if estimate.converted_invoice_id else None, "document_label": "ESTIMATE - Not a Tax Invoice", "pdf_url": f"/estimates/{estimate.id}/pdf", "items": [{"description": line.description_snapshot, "quantity": str(line.quantity), "unit_rate": str(line.unit_rate), "line_total": str(line.line_total)} for line in lines]}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/estimates/{estimate_id}/pdf")
async def download_estimate_pdf(estimate_id: uuid.UUID, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)]) -> FileResponse:
    estimate = await db.scalar(select(Estimate).where(Estimate.id == estimate_id, Estimate.business_id == context.business.id, Estimate.deleted_at.is_(None)))
    if estimate is None:
        raise HTTPException(404, "Estimate not found")
    lines = list((await db.scalars(select(EstimateLine).where(EstimateLine.estimate_id == estimate.id, EstimateLine.business_id == context.business.id, EstimateLine.deleted_at.is_(None)))).all())
    stored = await db.get(StoredFile, estimate.pdf_file_id) if estimate.pdf_file_id else None
    path = resolve_storage_path(stored.storage_path) if stored else None
    if path is None or not path.is_file():
        stored = await store_document_pdf(db, estimate, lines, "estimate", user.id)
        await db.commit()
        path = resolve_storage_path(stored.storage_path)
    return FileResponse(path, media_type="application/pdf", filename=stored.original_filename)


@router.patch("/estimates/{estimate_id}")
async def update_estimate(estimate_id: uuid.UUID, body: SaleCreate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*SALES_ROLES))], user: Annotated[User, Depends(current_user)]) -> dict:
    estimate = await db.scalar(select(Estimate).where(Estimate.id == estimate_id, Estimate.business_id == context.business.id, Estimate.deleted_at.is_(None)).with_for_update())
    if estimate is None:
        raise HTTPException(404, "Estimate not found")
    if estimate.converted_invoice_id is not None:
        raise HTTPException(409, "Converted estimates cannot be edited")
    estimate = await replace_document(db, estimate, body, context, user, "estimate")
    return {"data": {"id": str(estimate.id), "estimate_number": estimate.estimate_number, "estimate_date": estimate.estimate_date.isoformat(), "total_amount": str(estimate.total_amount)}, "request_id": getattr(request.state, "request_id", None)}


@router.delete("/estimates/{estimate_id}", status_code=204)
async def delete_estimate(estimate_id: uuid.UUID, db: Db, context: Annotated[BusinessContext, Depends(business_context)], user: Annotated[User, Depends(current_user)], reason: str = Query(..., min_length=3)) -> None:
    estimate = await db.scalar(select(Estimate).where(Estimate.id == estimate_id, Estimate.business_id == context.business.id, Estimate.deleted_at.is_(None)).with_for_update())
    if estimate is None:
        raise HTTPException(404, "Estimate not found")
    if estimate.converted_invoice_id:
        raise HTTPException(409, "Converted estimate cannot be deleted")
    estimate.deleted_at = datetime.now(timezone.utc)
    estimate.updated_by_id = user.id
    await add_audit(db, user, context, "delete", "estimate", estimate.id, {"estimate_number": estimate.estimate_number, "total_amount": estimate.total_amount}, {"reason": reason})
    await db.commit()


@router.post("/estimates/{estimate_id}/convert", status_code=201)
async def convert_estimate(estimate_id: uuid.UUID, body: ConvertEstimate, request: Request, db: Db, context: Annotated[BusinessContext, Depends(require_roles(*SALES_ROLES))], user: Annotated[User, Depends(current_user)], idempotency_key: str | None = Header(None, alias="Idempotency-Key")) -> dict:
    record, cached = await load_idempotent_response(db, context.business.id, idempotency_key, f"convert_estimate:{estimate_id}", body)
    if cached is not None:
        return {"data": cached, "request_id": getattr(request.state, "request_id", None)}
    estimate = await db.scalar(select(Estimate).where(Estimate.id == estimate_id, Estimate.business_id == context.business.id, Estimate.deleted_at.is_(None)).with_for_update())
    if estimate is None:
        raise HTTPException(404, "Estimate not found")
    if estimate.converted_invoice_id:
        invoice = await db.get(Invoice, estimate.converted_invoice_id)
        data = {"id": str(invoice.id), "invoice_number": invoice.invoice_number}
        if record is not None:
            record.response_body = data
        await db.commit()
        return {"data": data, "request_id": getattr(request.state, "request_id", None)}
    invoice_number, sequence, fy = await allocate_number(db, context.business.id, "invoice", body.invoice_date)
    invoice = Invoice(
        business_id=context.business.id,
        created_by_id=user.id,
        customer_id=estimate.customer_id,
        responsible_user_id=estimate.responsible_user_id,
        financial_year=fy,
        sequence_number=sequence,
        invoice_number=invoice_number,
        invoice_date=body.invoice_date,
        status=RecordStatus.ISSUED,
        apply_gst=estimate.apply_gst,
        discount_percent=estimate.discount_percent,
        subtotal=estimate.subtotal,
        discount_amount=estimate.discount_amount,
        taxable_amount=estimate.taxable_amount,
        gst_rate=estimate.gst_rate,
        cgst_amount=estimate.cgst_amount,
        sgst_amount=estimate.sgst_amount,
        igst_amount=estimate.igst_amount,
        total_amount=estimate.total_amount,
        company_name_snapshot=estimate.company_name_snapshot,
        company_gstin_snapshot=estimate.company_gstin_snapshot,
        company_address_snapshot=estimate.company_address_snapshot,
        company_state_code_snapshot=estimate.company_state_code_snapshot,
        customer_name_snapshot=estimate.customer_name_snapshot,
        customer_mobile_snapshot=estimate.customer_mobile_snapshot,
        customer_gstin_snapshot=estimate.customer_gstin_snapshot,
        customer_location_snapshot=estimate.customer_location_snapshot,
        footer_snapshot=estimate.footer_snapshot,
    )
    db.add(invoice)
    await db.flush()
    estimate_lines = await db.scalars(select(EstimateLine).where(EstimateLine.estimate_id == estimate.id, EstimateLine.business_id == context.business.id, EstimateLine.deleted_at.is_(None)))
    for line in estimate_lines:
        db.add(InvoiceLine(business_id=context.business.id, created_by_id=user.id, invoice_id=invoice.id, brick_type_id=line.brick_type_id, description_snapshot=line.description_snapshot, quantity=line.quantity, unit_rate=line.unit_rate, line_total=line.line_total))
    converted_lines = list((await db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id, InvoiceLine.business_id == context.business.id, InvoiceLine.deleted_at.is_(None)))).all())
    await store_document_pdf(db, invoice, converted_lines, "invoice", user.id)
    estimate.converted_invoice_id = invoice.id
    estimate.updated_by_id = user.id
    await add_audit(db, user, context, "convert", "estimate", estimate.id, {"converted_invoice_id": None}, {"converted_invoice_id": invoice.id, "invoice_number": invoice_number})
    data = {"id": str(invoice.id), "invoice_number": invoice.invoice_number, "total_amount": str(invoice.total_amount), "pdf_url": f"/invoices/{invoice.id}/pdf"}
    if record is not None:
        record.response_body = data
    await db.commit()
    return {"data": data, "request_id": getattr(request.state, "request_id", None)}