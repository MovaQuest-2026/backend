"""Hashed refresh-token records for revocable, rotating mobile sessions."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class MobileRefreshToken(Base):
    """One active mobile refresh credential; only its SHA-256 digest is stored."""

    __tablename__ = "mobile_refresh_tokens"
    __table_args__ = (
        Index("ix_mobile_refresh_tokens_user", "user_id"),
        Index("ix_mobile_refresh_tokens_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, init=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MobileOAuthCode(Base):
    """Short-lived, single-use code exchanged by the native app for mobile tokens."""

    __tablename__ = "mobile_oauth_codes"
    __table_args__ = (Index("ix_mobile_oauth_codes_expires", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, init=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
