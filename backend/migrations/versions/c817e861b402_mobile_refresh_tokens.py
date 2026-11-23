"""Store hashed refresh credentials for mobile token rotation.

Revision ID: c817e861b402
Revises: ae2deece1038
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c817e861b402"
down_revision: str | Sequence[str] | None = "ae2deece1038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mobile_refresh_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_mobile_refresh_tokens_user", "mobile_refresh_tokens", ["user_id"], unique=False)
    op.create_index("ix_mobile_refresh_tokens_expires", "mobile_refresh_tokens", ["expires_at"], unique=False)
    op.create_table(
        "mobile_oauth_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_mobile_oauth_codes_expires", "mobile_oauth_codes", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mobile_oauth_codes_expires", table_name="mobile_oauth_codes")
    op.drop_table("mobile_oauth_codes")
    op.drop_index("ix_mobile_refresh_tokens_expires", table_name="mobile_refresh_tokens")
    op.drop_index("ix_mobile_refresh_tokens_user", table_name="mobile_refresh_tokens")
    op.drop_table("mobile_refresh_tokens")
