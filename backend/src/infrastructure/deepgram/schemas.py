"""Public request/response schemas for speech transcription."""

from pydantic import BaseModel, Field


class TranscriptionWord(BaseModel):
    """A recognized word with optional timing and confidence information."""

    word: str
    start: float | None = None
    end: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class TranscriptionResponse(BaseModel):
    """Stable frontend contract, independent of Deepgram's full response shape."""

    transcript: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_silent: bool
    duration_seconds: float | None = None
    model: str
    language: str
    words: list[TranscriptionWord]
