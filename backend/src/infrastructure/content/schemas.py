"""API schemas for the lesson catalog and database-backed media."""

from pydantic import BaseModel, ConfigDict, Field


class LessonResponse(BaseModel):
    """Frontend-compatible lesson catalog entry."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: dict[str, str]
    description: dict[str, str]
    level: str
    duration_seconds: int | None = Field(default=None, serialization_alias="durationSec")
    cover: str | None = None
    added_at: str | None = Field(default=None, serialization_alias="addedAt")
    pinned: bool = False
    coming_soon: bool = Field(default=False, serialization_alias="comingSoon")
    video_url: str | None = Field(default=None, serialization_alias="videoUrl")


class MediaFileResponse(BaseModel):
    """Video metadata returned by the content API."""

    name: str
    size_bytes: int = Field(ge=0)
    content_type: str
    checksum_sha256: str = Field(min_length=64, max_length=64)
