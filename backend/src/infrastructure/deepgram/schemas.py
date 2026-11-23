"""Public request/response schemas for speech transcription."""

from typing import Literal

from pydantic import BaseModel, Field


class TranscriptionWord(BaseModel):
    """A recognized word with optional timing and confidence information."""

    word: str
    start: float | None = None
    end: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class PronunciationWordFeedback(BaseModel):
    """A token-level comparison between the expected and recognized phrase."""

    expected: str | None = None
    recognized: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    matched: bool


class PronunciationFeedback(BaseModel):
    """A confidence-based speech practice signal, not a phoneme-level diagnosis."""

    expected_text: str
    score: float = Field(ge=0, le=1)
    status: Literal["good", "needs_practice", "not_recognized"]
    words: list[PronunciationWordFeedback]


class TranscriptionResponse(BaseModel):
    """Stable frontend contract, independent of Deepgram's full response shape."""

    transcript: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_silent: bool
    duration_seconds: float | None = None
    model: str
    language: str
    words: list[TranscriptionWord]
    pronunciation_feedback: PronunciationFeedback | None = None
