"""Authenticated speech-to-text endpoints."""

import re
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from ...wiring.settings import settings
from ..auth.dependencies import get_session_principal
from ..http_exceptions import HTTPException
from .dependencies import DeepgramServiceDep
from .errors import DeepgramError
from .schemas import (
    PronunciationFeedback,
    PronunciationWordFeedback,
    TranscriptionResponse,
    TranscriptionWord,
)
from .service import DeepgramWord

router = APIRouter(
    tags=["Speech-to-text"],
    dependencies=[] if settings.DEEPGRAM_PUBLIC_ENABLED else [Depends(get_session_principal)],
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
        "Optionally send `expected_text` to receive a confidence-based practice signal. "
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
    expected_text: Annotated[
        str | None,
        Form(max_length=1000, description="Phrase the learner was expected to pronounce"),
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

    feedback = _pronunciation_feedback(expected_text, result.transcript, result.words) if expected_text else None
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
        pronunciation_feedback=feedback,
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


def _tokens(value: str) -> list[str]:
    """Normalize a phrase for a language-neutral, punctuation-insensitive comparison."""
    return re.findall(r"[\wÀ-ÿ']+", value.casefold())


def _pronunciation_feedback(
    expected_text: str,
    transcript: str,
    words: Sequence[DeepgramWord],
) -> PronunciationFeedback:
    """Build an explainable practice score from token similarity and Deepgram confidence."""
    expected = _tokens(expected_text)
    recognized = _tokens(transcript)
    similarity = SequenceMatcher(a=expected, b=recognized, autojunk=False).ratio() if expected else 0.0
    confidences = [word.confidence for word in words if word.confidence is not None]
    confidence = sum(confidences) / len(confidences) if confidences else similarity
    score = round((similarity * 0.7) + (confidence * 0.3), 3)

    matcher = SequenceMatcher(a=expected, b=recognized, autojunk=False)
    feedback_words: list[PronunciationWordFeedback] = []
    for tag, start_expected, end_expected, start_recognized, end_recognized in matcher.get_opcodes():
        expected_part = expected[start_expected:end_expected]
        recognized_part = recognized[start_recognized:end_recognized]
        for index in range(max(len(expected_part), len(recognized_part))):
            expected_word = expected_part[index] if index < len(expected_part) else None
            recognized_word = recognized_part[index] if index < len(recognized_part) else None
            recognized_index = start_recognized + index
            word_confidence = words[recognized_index].confidence if recognized_index < len(words) else None
            feedback_words.append(
                PronunciationWordFeedback(
                    expected=expected_word,
                    recognized=recognized_word,
                    confidence=word_confidence,
                    matched=tag == "equal",
                )
            )

    status = "not_recognized" if not recognized else "good" if score >= 0.85 else "needs_practice"
    return PronunciationFeedback(
        expected_text=expected_text.strip(),
        score=score,
        status=status,
        words=feedback_words,
    )
