from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import DateTime, Enum, ForeignKey, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OrganizationRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    CEO = "ceo"


class BusinessRole(str, enum.Enum):
    MANAGER = "manager"
    ASST_MANAGER = "asst_manager"


class RecordStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    CANCELLED = "cancelled"


class ExpenseType(str, enum.Enum):
    DAILY = "daily"
    DIESEL = "diesel"
    SALARY = "salary"
    SALARY_ADVANCE = "salary_advance"
    MISCELLANEOUS = "miscellaneous"


class SalaryPeriod(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class FlagStatus(str, enum.Enum):
    FLAGGED = "flagged"
    REASON_SUBMITTED = "reason_submitted"
    CORRECTED = "corrected"
    RESOLVED = "resolved"


class EntityType(str, enum.Enum):
    INVOICE = "invoice"
    ESTIMATE = "estimate"
    EXPENSE = "expense"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TenantMixin(TimestampMixin):
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


@lru_cache(maxsize=None)
def enum_column(enum_type: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )