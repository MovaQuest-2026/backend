"""Validation and transport schemas for account-owned lesson progress."""

import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..common.schemas import refuse_unencodable_text

LESSON_ID_PATTERN = r"^[a-z0-9-]{1,64}$"
LESSON_ID_RE = re.compile(LESSON_ID_PATTERN)
GAP_ID_MAX_LENGTH = 64
MACHINE_MAX_BYTES = 32 * 1024


def _validate_lesson_id(value: str) -> str:
    if not LESSON_ID_RE.fullmatch(value):
        raise ValueError("lessonId must match ^[a-z0-9-]{1,64}$")
    return value


def _validate_gap_id(value: str) -> str:
    value = value.strip()
    if not value or len(value) > GAP_ID_MAX_LENGTH:
        raise ValueError("gapId must be a non-empty string no longer than 64 characters")
    refuse_unencodable_text("gapId", value)
    return value


class CompletedLesson(BaseModel):
    """A completed lesson result, using the frontend's camelCase contract."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    outcome: Literal["perfect", "partial", "missed"]
    correct: int = Field(ge=0, le=100)
    total: int = Field(ge=0, le=100)
    completed_at: datetime = Field(alias="completedAt")

    @model_validator(mode="after")
    def correct_cannot_exceed_total(self) -> "CompletedLesson":
        if self.correct > self.total:
            raise ValueError("correct cannot be greater than total")
        return self


class ActiveLesson(BaseModel):
    """An opaque lesson state and the device timestamp at which it was captured."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    machine: dict[str, Any]
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("machine")
    @classmethod
    def machine_is_bounded_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        refuse_unencodable_text("machine", value)
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        except (TypeError, ValueError) as error:
            raise ValueError("machine must be JSON serializable") from error
        if len(encoded) > MACHINE_MAX_BYTES:
            raise ValueError("machine exceeds the 32 KiB limit")
        return value


class LearnedWordItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    lesson_id: str = Field(alias="lessonId")
    gap_id: str = Field(alias="gapId")

    @field_validator("lesson_id")
    @classmethod
    def valid_lesson_id(cls, value: str) -> str:
        return _validate_lesson_id(value)

    @field_validator("gap_id")
    @classmethod
    def valid_gap_id(cls, value: str) -> str:
        return _validate_gap_id(value)


class LearnedWordsPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    items: list[LearnedWordItem] = Field(min_length=1, max_length=500)


class Progress(BaseModel):
    """The complete progress object exchanged by GET and import."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    completed_lessons: dict[str, CompletedLesson] = Field(alias="completedLessons")
    learned_words: dict[str, list[str]] = Field(alias="learnedWords")
    active_lessons: dict[str, ActiveLesson] = Field(alias="activeLessons")

    @model_validator(mode="after")
    def validate_keys_and_values(self) -> "Progress":
        for lesson_id in self.completed_lessons:
            _validate_lesson_id(lesson_id)
        for lesson_id, gap_ids in self.learned_words.items():
            _validate_lesson_id(lesson_id)
            for gap_id in gap_ids:
                _validate_gap_id(gap_id)
        for lesson_id in self.active_lessons:
            _validate_lesson_id(lesson_id)
        refuse_unencodable_text("progress", self.model_dump(mode="python", by_alias=True))
        return self


class ActiveLessonResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    machine: dict[str, Any]
    updated_at: datetime = Field(alias="updatedAt")


class ProgressResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    completed_lessons: dict[str, CompletedLesson] = Field(alias="completedLessons")
    learned_words: dict[str, list[str]] = Field(alias="learnedWords")
    active_lessons: dict[str, ActiveLessonResponse] = Field(alias="activeLessons")
