"""replace OTP sign-in with password authentication

Revision ID: b17d2a4c9f31
Revises: 91dff227122f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b17d2a4c9f31"
down_revision: Union[str, None] = "91dff227122f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=True))
    op.execute("UPDATE users SET must_change_password = false WHERE must_change_password IS NULL")
    op.alter_column("users", "must_change_password", nullable=False)

    op.create_table(
        "login_rate_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(length=254), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identifier", "window_started_at", name="uq_login_rate_window"),
    )

    op.drop_index("ix_otp_destination_created", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_expires_at", table_name="otp_challenges")
    op.drop_table("otp_challenges")
    op.drop_table("otp_rate_limits")
    op.execute("DROP TYPE otp_channel")


def downgrade() -> None:
    bind = op.get_bind()
    otp_channel = postgresql.ENUM("email", "sms", name="otp_channel")
    otp_channel.create(bind, checkfirst=True)
    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("destination_normalized", sa.String(length=254), nullable=False),
        sa.Column("channel", otp_channel, nullable=False),
        sa.Column("code_hash", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_otp_challenges_expires_at", "otp_challenges", ["expires_at"], unique=False)
    op.create_index("ix_otp_destination_created", "otp_challenges", ["destination_normalized", "created_at"], unique=False)
    op.create_table(
        "otp_rate_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("destination_normalized", sa.String(length=254), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("destination_normalized", "window_started_at", name="uq_otp_rate_window"),
    )

    op.drop_table("login_rate_limits")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "password_hash")