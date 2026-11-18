"""Database row for the account's onboarding profile."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class Profile(Base):
    """One onboarding profile per account."""

    __tablename__ = "profiles"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    interface_lang: Mapped[str] = mapped_column(String(2), nullable=False)
    level: Mapped[str] = mapped_column(String(2), nullable=False)
    goal: Mapped[str] = mapped_column(String(200), nullable=False)
    onboarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
