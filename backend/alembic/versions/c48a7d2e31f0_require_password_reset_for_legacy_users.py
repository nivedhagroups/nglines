"""require temporary passwords for users carried over from OTP auth

Revision ID: c48a7d2e31f0
Revises: b17d2a4c9f31
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c48a7d2e31f0"
down_revision: Union[str, None] = "b17d2a4c9f31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET must_change_password = true WHERE password_hash IS NULL")


def downgrade() -> None:
    op.execute("UPDATE users SET must_change_password = false WHERE password_hash IS NULL")