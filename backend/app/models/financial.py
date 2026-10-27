from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, Enum, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EntityType, ExpenseType, RecordStatus, SalaryPeriod, TenantMixin, enum_column


class FinancialNumberCounter(Base):
    __tablename__ = "financial_number_counters"
    __table_args__ = (UniqueConstraint("business_id", "financial_year", "record_type", name="uq_financial_number_counter"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)
    last_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Invoice(TenantMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_invoices_business_id_id"),
        UniqueConstraint("business_id", "financial_year", "sequence_number", name="uq_invoice_business_fy_sequence"),
        UniqueConstraint("business_id", "invoice_number", name="uq_invoice_business_number"),
        ForeignKeyConstraint(["business_id", "customer_id"], ["customers.business_id", "customers.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["business_id", "responsible_user_id"], ["business_memberships.business_id", "business_memberships.user_id"], ondelete="RESTRICT"),
        CheckConstraint("discount_percent >= 0 AND discount_percent <= 100", name="ck_invoice_discount_percent"),
        CheckConstraint("subtotal >= 0 AND discount_amount >= 0 AND taxable_amount >= 0 AND total_amount >= 0", name="ck_invoice_amounts_nonnegative"),
        ForeignKeyConstraint(["business_id", "pdf_file_id"], ["stored_files.business_id", "stored_files.id"], ondelete="RESTRICT"),
        Index("ix_invoice_business_date", "business_id", "invoice_date"),
        Index("ix_invoice_business_customer", "business_id", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[RecordStatus] = mapped_column(enum_column(RecordStatus, "record_status"), default=RecordStatus.ISSUED, nullable=False)
    apply_gst: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    company_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    company_gstin_snapshot: Mapped[str | None] = mapped_column(String(15))
    company_address_snapshot: Mapped[str | None] = mapped_column(Text)
    company_state_code_snapshot: Mapped[str | None] = mapped_column(String(2))
    customer_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_mobile_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_gstin_snapshot: Mapped[str | None] = mapped_column(String(15))
    customer_location_snapshot: Mapped[str | None] = mapped_column(Text)
    footer_snapshot: Mapped[str | None] = mapped_column(Text)
    pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class InvoiceLine(TenantMixin, Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "invoice_id"], ["invoices.business_id", "invoices.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["business_id", "brick_type_id"], ["brick_types.business_id", "brick_types.id"], ondelete="RESTRICT"),
        CheckConstraint("quantity > 0 AND unit_rate >= 0 AND line_total >= 0", name="ck_invoice_line_values"),
        Index("ix_invoice_line_business_invoice", "business_id", "invoice_id"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    brick_type_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    description_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class Estimate(TenantMixin, Base):
    __tablename__ = "estimates"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_estimates_business_id_id"),
        UniqueConstraint("business_id", "financial_year", "sequence_number", name="uq_estimate_business_fy_sequence"),
        ForeignKeyConstraint(["business_id", "customer_id"], ["customers.business_id", "customers.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["business_id", "responsible_user_id"], ["business_memberships.business_id", "business_memberships.user_id"], ondelete="RESTRICT"),
        CheckConstraint("discount_percent >= 0 AND discount_percent <= 100", name="ck_estimate_discount_percent"),
        CheckConstraint("subtotal >= 0 AND discount_amount >= 0 AND taxable_amount >= 0 AND total_amount >= 0", name="ck_estimate_amounts_nonnegative"),
        ForeignKeyConstraint(["business_id", "converted_invoice_id"], ["invoices.business_id", "invoices.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["business_id", "pdf_file_id"], ["stored_files.business_id", "stored_files.id"], ondelete="RESTRICT"),
        Index("ix_estimate_business_date", "business_id", "estimate_date"),
        Index("ix_estimate_business_customer", "business_id", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    estimate_number: Mapped[str] = mapped_column(String(32), nullable=False)
    estimate_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[RecordStatus] = mapped_column(enum_column(RecordStatus, "record_status"), default=RecordStatus.ISSUED, nullable=False)
    converted_invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    apply_gst: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    company_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    company_gstin_snapshot: Mapped[str | None] = mapped_column(String(15))
    company_address_snapshot: Mapped[str | None] = mapped_column(Text)
    company_state_code_snapshot: Mapped[str | None] = mapped_column(String(2))
    customer_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_mobile_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_gstin_snapshot: Mapped[str | None] = mapped_column(String(15))
    customer_location_snapshot: Mapped[str | None] = mapped_column(Text)
    footer_snapshot: Mapped[str | None] = mapped_column(Text)
    pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class EstimateLine(TenantMixin, Base):
    __tablename__ = "estimate_lines"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "estimate_id"], ["estimates.business_id", "estimates.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["business_id", "brick_type_id"], ["brick_types.business_id", "brick_types.id"], ondelete="RESTRICT"),
        CheckConstraint("quantity > 0 AND unit_rate >= 0 AND line_total >= 0", name="ck_estimate_line_values"),
        Index("ix_estimate_line_business_estimate", "business_id", "estimate_id"),
    )

    estimate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    brick_type_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    description_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class ExpenseCategory(TenantMixin, Base):
    __tablename__ = "expense_categories"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_expense_categories_business_id_id"),
        UniqueConstraint("business_id", "name", name="uq_expense_category_business_name"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    expense_type: Mapped[ExpenseType] = mapped_column(enum_column(ExpenseType, "expense_type"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Vehicle(TenantMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_vehicles_business_id_id"),
        UniqueConstraint("business_id", "registration_number", name="uq_vehicle_business_registration"),
    )

    registration_number: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Employee(TenantMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_employees_business_id_id"),
        UniqueConstraint("business_id", "employee_code", name="uq_employee_business_code"),
    )

    employee_code: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mobile: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Expense(TenantMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_expenses_business_id_id"),
        ForeignKeyConstraint(["business_id", "category_id"], ["expense_categories.business_id", "expense_categories.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["business_id", "vehicle_id"], ["vehicles.business_id", "vehicles.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["business_id", "employee_id"], ["employees.business_id", "employees.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["business_id", "responsible_user_id"], ["business_memberships.business_id", "business_memberships.user_id"], ondelete="RESTRICT"),
        CheckConstraint("amount >= 0", name="ck_expense_amount_nonnegative"),
        CheckConstraint("litres IS NULL OR litres > 0", name="ck_expense_litres_positive"),
        CheckConstraint("unit_rate IS NULL OR unit_rate >= 0", name="ck_expense_unit_rate_nonnegative"),
        CheckConstraint("expense_type <> 'diesel' OR (vehicle_id IS NOT NULL AND litres IS NOT NULL AND unit_rate IS NOT NULL)", name="ck_diesel_expense_vehicle_details"),
        CheckConstraint("expense_type <> 'salary_advance' OR (employee_id IS NOT NULL OR recipient_name IS NOT NULL)", name="ck_advance_recipient_required"),
        Index("ix_expense_business_date", "business_id", "expense_date"),
        Index("ix_expense_business_category_date", "business_id", "category_id", "expense_date"),
        Index("ix_expense_business_vehicle_date", "business_id", "vehicle_id", "expense_date"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    expense_type: Mapped[ExpenseType] = mapped_column(enum_column(ExpenseType, "expense_type"), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    litres: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    salary_period: Mapped[SalaryPeriod | None] = mapped_column(enum_column(SalaryPeriod, "salary_period"))
    recipient_name: Mapped[str | None] = mapped_column(String(160))


class AdvanceRecovery(TenantMixin, Base):
    __tablename__ = "advance_recoveries"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "advance_expense_id"], ["expenses.business_id", "expenses.id"], ondelete="RESTRICT"),
        CheckConstraint("amount > 0", name="ck_advance_recovery_amount_positive"),
        Index("ix_advance_recovery_business_date", "business_id", "recovery_date"),
    )

    advance_expense_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recovery_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)