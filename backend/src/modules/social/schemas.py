"""Public request and response schemas for lesson social features."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import EncodableText

LESSON_ID_PATTERN = r"^[a-z0-9-]{1,64}$"
COMMENT_MAX_LENGTH = 150


class ReactionsResponse(BaseModel):
    liked: list[str]
    saved: list[str]


class LessonStatsResponse(BaseModel):
    likes: int
    comments: int
    saves: int
    shares: int


class CommentCreate(EncodableText):
    text: Annotated[str, Field(min_length=1, max_length=COMMENT_MAX_LENGTH)]

    @field_validator("text", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CommentReportCreate(EncodableText):
    reason: Literal["spam", "abuse", "other"]
    details: Annotated[str | None, Field(max_length=1000)] = None

    @field_validator("details", mode="before")
    @classmethod
    def trim_details(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class LessonCommentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    author: str
    text: str
    created_at: datetime = Field(alias="createdAt")
    likes: int = 0
    own: bool = False


class CommentsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[LessonCommentResponse]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class ShareCreate(BaseModel):
    method: Literal["native", "copy"]
