"""Lesson catalog and binary media stored in PostgreSQL."""

from datetime import date

from sqlalchemy import Boolean, Date, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Lesson(Base, TimestampMixin):
    """A multilingual lesson entry imported from the frontend catalog."""

    __tablename__ = "lessons"

    slug: Mapped[str] = mapped_column(String(128), primary_key=True)
    title_es: Mapped[str] = mapped_column(String(255), default="")
    title_en: Mapped[str] = mapped_column(String(255), default="")
    title_uk: Mapped[str] = mapped_column(String(255), default="")
    description_es: Mapped[str] = mapped_column(Text, default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_uk: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(8), default="A1")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    cover_path: Mapped[str | None] = mapped_column(String(512), default=None)
    added_at: Mapped[date | None] = mapped_column(Date, default=None)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    coming_soon: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    video_name: Mapped[str | None] = mapped_column(String(128), default=None)

    __table_args__ = (
        Index("ix_lessons_published", "coming_soon", "pinned", "added_at", "slug"),
        Index("ix_lessons_video_name", "video_name"),
    )

    def __repr__(self) -> str:
        return self.slug


class MediaVideo(Base, TimestampMixin):
    """A video object and its metadata stored in a PostgreSQL BYTEA column."""

    __tablename__ = "media_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    __table_args__ = (Index("ix_media_videos_created", "created_at", "id"),)
