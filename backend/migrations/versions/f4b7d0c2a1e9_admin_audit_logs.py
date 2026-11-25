"""Store administrative mutation audit events.

Revision ID: f4b7d0c2a1e9
Revises: d4f7a2c9e611
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b7d0c2a1e9"
down_revision: str | Sequence[str] | None = "d4f7a2c9e611"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("entity", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_logs_created", "admin_audit_logs", ["created_at", "id"], unique=False)
    op.create_index("ix_admin_audit_logs_entity", "admin_audit_logs", ["entity", "entity_id"], unique=False)
    op.create_index("ix_admin_audit_logs_actor", "admin_audit_logs", ["actor", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_admin_audit_logs_actor", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_entity", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_created", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
