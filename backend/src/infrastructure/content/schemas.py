"""API schemas for database-backed media."""

from pydantic import BaseModel, Field


class MediaFileResponse(BaseModel):
    """Video metadata returned by the content API."""

    name: str
    size_bytes: int = Field(ge=0)
    content_type: str
    checksum_sha256: str = Field(min_length=64, max_length=64)
