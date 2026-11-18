"""Database rows for account-owned lesson progress."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base

MACHINE_JSON = JSON().with_variant(JSONB(), "postgresql")


class LessonResult(Base, TimestampMixin):
    """The best result an account achieved for a frontend-owned lesson."""

    __tablename__ = "lesson_results"

    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    correct: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("account_id", "lesson_id", name="pk_lesson_results"),
        Index("ix_lesson_results_account", "account_id"),
    )


class LearnedWord(Base):
    """A gap answered correctly at least once by an account."""

    __tablename__ = "learned_words"

    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gap_id: Mapped[str] = mapped_column(String(64), nullable=False)
    learned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("account_id", "lesson_id", "gap_id", name="pk_learned_words"),
        Index("ix_learned_words_account_lesson", "account_id", "lesson_id"),
    )


class ActiveLesson(Base, TimestampMixin):
    """The latest opaque lesson-machine snapshot for an account."""

    __tablename__ = "active_lessons"

    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    machine: Mapped[dict[str, Any]] = mapped_column(MACHINE_JSON, nullable=False)
    client_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("account_id", "lesson_id", name="pk_active_lessons"),
        Index("ix_active_lessons_account", "account_id"),
    )
