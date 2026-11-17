"""Authenticated speech-to-text endpoints."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from ...wiring.settings import settings
from ..auth.dependencies import get_session_principal
from ..http_exceptions import HTTPException
from .dependencies import DeepgramServiceDep
from .errors import DeepgramError
from .schemas import TranscriptionResponse, TranscriptionWord

router = APIRouter(
    tags=["Speech-to-text"],
    dependencies=[Depends(get_session_principal)],
)

_ALLOWED_AUDIO_TYPES = {"application/octet-stream", "video/mp4"}


@router.post(
    "",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcribe audio",
    description=(
        "Transcribes a short audio recording with Deepgram Nova-3. "
        "Send the expected answer as repeated `hint` multipart fields; the backend forwards them as keyterms. "
        "An empty transcript means that the recording was silent or unintelligible."
    ),
    responses={
        401: {"description": "Authentication required"},
        413: {"description": "Audio file exceeds the configured size limit"},
        415: {"description": "Unsupported audio content type"},
        422: {"description": "Invalid hints or Deepgram rejected the audio"},
        503: {"description": "Deepgram is unavailable or rate-limited"},
        504: {"description": "Deepgram request timed out"},
    },
)
async def transcribe_audio(
    audio: Annotated[UploadFile, File(description="Audio recorded by the browser or mobile device")],
    deepgram: DeepgramServiceDep,
    hints: Annotated[
        list[str] | None,
        Form(alias="hint", description="Expected word or accepted variant; repeat the field for multiple terms"),
    ] = None,
) -> TranscriptionResponse:
    """Validate a bounded upload and return a provider-independent transcription result."""
    content_type = audio.content_type or "application/octet-stream"
    if not (content_type.startswith("audio/") or content_type in _ALLOWED_AUDIO_TYPES):
        raise HTTPException(status_code=415, detail="Unsupported audio content type.")

    audio_bytes = await audio.read(settings.DEEPGRAM_MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > settings.DEEPGRAM_MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file is too large.")
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="Audio file is empty.")

    keyterms = _normalize_keyterms(hints or [])
    if len(keyterms) > settings.DEEPGRAM_MAX_KEYTERMS:
        raise HTTPException(status_code=422, detail="Too many speech hints.")
    if sum(len(re.findall(r"\S+", keyterm)) for keyterm in keyterms) > settings.DEEPGRAM_MAX_KEYTERM_TOKENS:
        raise HTTPException(status_code=422, detail="Speech hints are too long.")

    try:
        result = await deepgram.transcribe(audio_bytes, content_type, keyterms)
    except DeepgramError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    return TranscriptionResponse(
        transcript=result.transcript,
        confidence=result.confidence,
        is_silent=not result.transcript.strip(),
        duration_seconds=result.duration_seconds,
        model=result.model,
        language=result.language,
        words=[
            TranscriptionWord(word=word.word, start=word.start, end=word.end, confidence=word.confidence)
            for word in result.words
        ],
    )


def _normalize_keyterms(values: list[str]) -> list[str]:
    """Trim, de-duplicate and discard empty hints before sending them upstream."""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = value.strip()
        key = term.casefold()
        if term and key not in seen:
            normalized.append(term)
            seen.add(key)
    return normalized
