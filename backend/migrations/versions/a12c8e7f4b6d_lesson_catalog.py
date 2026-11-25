"""Store the frontend lesson catalog in the backend.

Revision ID: a12c8e7f4b6d
Revises: f4b7d0c2a1e9
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a12c8e7f4b6d"
down_revision: str | Sequence[str] | None = "f4b7d0c2a1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lessons",
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("title_es", sa.String(length=255), nullable=False),
        sa.Column("title_en", sa.String(length=255), nullable=False),
        sa.Column("title_uk", sa.String(length=255), nullable=False),
        sa.Column("description_es", sa.Text(), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=False),
        sa.Column("description_uk", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("cover_path", sa.String(length=512), nullable=True),
        sa.Column("added_at", sa.Date(), nullable=True),
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("coming_soon", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("video_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("slug"),
    )
    op.create_index(
        "ix_lessons_published",
        "lessons",
        ["coming_soon", "pinned", "added_at", "slug"],
        unique=False,
    )
    op.create_index("ix_lessons_video_name", "lessons", ["video_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_lessons_video_name", table_name="lessons")
    op.drop_index("ix_lessons_published", table_name="lessons")
    op.drop_table("lessons")
