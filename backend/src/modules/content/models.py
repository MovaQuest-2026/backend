"""Binary lesson media stored in PostgreSQL."""

from sqlalchemy import Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


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
