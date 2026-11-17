"""Database rows for lesson reactions, comments and share events."""

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class LessonReaction(Base, TimestampMixin):
    """One user's idempotent like or save for a frontend-owned lesson."""

    __tablename__ = "lesson_reactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", "kind", name="uq_lesson_reactions_user_lesson_kind"),
        Index("ix_lesson_reactions_lesson_kind", "lesson_id", "kind"),
        Index("ix_lesson_reactions_user_kind", "user_id", "kind"),
    )


class LessonComment(Base, TimestampMixin):
    """A user comment attached to a lesson id supplied by the frontend."""

    __tablename__ = "lesson_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        Index("ix_lesson_comments_lesson_created", "lesson_id", "created_at", "id"),
        Index("ix_lesson_comments_user", "user_id"),
    )


class LessonShare(Base, TimestampMixin):
    """A share event; guests are allowed and therefore ``user_id`` is nullable."""

    __tablename__ = "lesson_shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (Index("ix_lesson_shares_lesson", "lesson_id"),)
