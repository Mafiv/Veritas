"""008 better_auth_link — users.auth_user_id for Better Auth sync

Revision ID: 008_better_auth_link
Revises: 007_enterprise
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_better_auth_link"
down_revision: Union[str, Sequence[str], None] = "007_enterprise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_user_id", sa.String(128), nullable=True))
    op.create_index("ix_users_auth_user_id", "users", ["auth_user_id"], unique=True)
    # OAuth / Better Auth users may not have a local password
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(255),
        nullable=True,
        server_default="",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(255),
        nullable=False,
        server_default=None,
    )
    op.drop_index("ix_users_auth_user_id", table_name="users")
    op.drop_column("users", "auth_user_id")
