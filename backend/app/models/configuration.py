from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, ForeignKeyConstraint, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin


class BusinessSettings(TenantMixin, Base):
    __tablename__ = "business_settings"
    __table_args__ = (UniqueConstraint("business_id", name="uq_business_settings_business"),)

    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15))
    gst_state_code: Mapped[str | None] = mapped_column(String(2))
    address: Mapped[str | None] = mapped_column(Text)
    logo_storage_key: Mapped[str | None] = mapped_column(String(512))
    invoice_footer: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)


class GstRate(TenantMixin, Base):
    __tablename__ = "gst_rates"
    __table_args__ = (
        CheckConstraint("rate >= 0 AND rate <= 100", name="ck_gst_rate_range"),
        CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_gst_rate_dates"),
        UniqueConstraint("business_id", "effective_from", name="uq_gst_rate_effective_from"),
    )

    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)
    configured_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class BrickType(TenantMixin, Base):
    __tablename__ = "brick_types"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_brick_types_business_id_id"),
        UniqueConstraint("business_id", "name", name="uq_brick_type_business_name"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BrickRate(TenantMixin, Base):
    __tablename__ = "brick_rates"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "brick_type_id"], ["brick_types.business_id", "brick_types.id"], ondelete="RESTRICT"),
        CheckConstraint("rate >= 0", name="ck_brick_rate_nonnegative"),
        CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_brick_rate_dates"),
        UniqueConstraint("business_id", "brick_type_id", "effective_from", name="uq_brick_rate_effective_from"),
    )

    brick_type_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)


class Customer(TenantMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_customers_business_id_id"),
        UniqueConstraint("business_id", "mobile", name="uq_customer_business_mobile"),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mobile: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    gstin: Mapped[str | None] = mapped_column(String(15))
    location: Mapped[str | None] = mapped_column(Text)