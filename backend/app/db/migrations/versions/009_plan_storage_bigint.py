"""009 plan_storage_bigint — storage_bytes_limit exceeds int32 (5GB+)

Revision ID: 009_plan_storage_bigint
Revises: 008_better_auth_link
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_plan_storage_bigint"
down_revision: Union[str, Sequence[str], None] = "008_better_auth_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "plans",
        "storage_bytes_limit",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "plans",
        "storage_bytes_limit",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
