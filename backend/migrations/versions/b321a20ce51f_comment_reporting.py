"""Add comment moderation and reports.

Revision ID: b321a20ce51f
Revises: c817e861b402
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b321a20ce51f"
down_revision: str | Sequence[str] | None = "c817e861b402"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lesson_comments", sa.Column("is_hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_table(
        "lesson_comment_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("comment_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=10), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["comment_id"], ["lesson_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comment_id", "user_id", name="uq_comment_report_comment_user"),
    )
    op.create_index("ix_lesson_comment_reports_comment", "lesson_comment_reports", ["comment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_lesson_comment_reports_comment", table_name="lesson_comment_reports")
    op.drop_table("lesson_comment_reports")
    op.drop_column("lesson_comments", "is_hidden")
