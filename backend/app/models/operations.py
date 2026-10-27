from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EntityType, FlagStatus, TenantMixin, TimestampMixin, enum_column


class StoredFile(TenantMixin, Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_stored_files_business_id_id"),
        Index("ix_stored_file_business_expiry", "business_id", "expires_at"),
    )

    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyRecord(TenantMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("business_id", "key", name="uq_idempotency_business_key"),)

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSONB)


class FileAttachment(TenantMixin, Base):
    __tablename__ = "file_attachments"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "file_id"], ["stored_files.business_id", "stored_files.id"], ondelete="RESTRICT"),
        Index("ix_file_attachment_owner", "business_id", "entity_type", "entity_id"),
    )

    file_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class ShareLink(TenantMixin, Base):
    __tablename__ = "share_links"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "file_id"], ["stored_files.business_id", "stored_files.id"], ondelete="RESTRICT"),
        Index("ix_share_link_entity", "business_id", "entity_type", "entity_id"),
    )

    entity_type: Mapped[EntityType] = mapped_column(enum_column(EntityType, "entity_type"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class TransactionFlag(TenantMixin, Base):
    __tablename__ = "transaction_flags"
    __table_args__ = (
        UniqueConstraint("business_id", "id", name="uq_transaction_flags_business_id_id"),
        Index("ix_transaction_flag_business_entity", "business_id", "entity_type", "entity_id"),
        Index("ix_transaction_flag_responsible", "business_id", "responsible_user_id", "status"),
    )

    entity_type: Mapped[EntityType] = mapped_column(enum_column(EntityType, "entity_type"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[FlagStatus] = mapped_column(enum_column(FlagStatus, "flag_status"), default=FlagStatus.FLAGGED, nullable=False)
    flagged_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    responsible_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlagEvent(TenantMixin, Base):
    __tablename__ = "flag_events"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "flag_id"], ["transaction_flags.business_id", "transaction_flags.id"], ondelete="RESTRICT"),
        Index("ix_flag_event_flag_time", "business_id", "flag_id", "created_at"),
    )

    flag_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    from_status: Mapped[FlagStatus | None] = mapped_column(enum_column(FlagStatus, "flag_status"))
    to_status: Mapped[FlagStatus] = mapped_column(enum_column(FlagStatus, "flag_status"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)


class Notification(TenantMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_user_unread", "business_id", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceToken(TimestampMixin, Base):
    __tablename__ = "device_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_business_time", "business_id", "occurred_at"),
        Index("ix_audit_actor_time", "actor_id", "occurred_at"),
        Index("ix_audit_entity_time", "entity_type", "entity_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="RESTRICT"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    before_values: Mapped[dict | None] = mapped_column(JSONB)
    after_values: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)