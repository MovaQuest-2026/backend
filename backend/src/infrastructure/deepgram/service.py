"""Small, testable Deepgram REST client for pre-recorded audio."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from .errors import DeepgramConfigurationError, DeepgramTimeoutError, DeepgramUpstreamError
from .settings import DeepgramSettings


@dataclass(frozen=True)
class DeepgramWord:
    """A word-level result returned by Deepgram when available."""

    word: str
    start: float | None
    end: float | None
    confidence: float | None


@dataclass(frozen=True)
class DeepgramTranscription:
    """The provider response reduced to the contract exposed by our API."""

    transcript: str
    confidence: float | None
    duration_seconds: float | None
    model: str
    language: str
    words: list[DeepgramWord]


class DeepgramTranscriptionService:
    """Send one bounded audio request to Deepgram without exposing the provider key."""

    def __init__(
        self,
        settings: DeepgramSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def transcribe(
        self,
        audio: bytes,
        content_type: str,
        keyterms: Sequence[str],
    ) -> DeepgramTranscription:
        """Transcribe audio with optional repeated ``keyterm`` query parameters."""
        if not self._settings.DEEPGRAM_ENABLED or not self._settings.DEEPGRAM_API_KEY:
            raise DeepgramConfigurationError

        params: list[tuple[str, str | int | float | bool | None]] = [
            ("model", self._settings.DEEPGRAM_MODEL),
            ("language", self._settings.DEEPGRAM_LANGUAGE),
            ("smart_format", "true"),
            ("redact_usage", "true"),
        ]
        params.extend(("keyterm", keyterm) for keyterm in keyterms)
        url = f"{self._settings.DEEPGRAM_API_URL.rstrip('/')}/v1/listen"
        headers = {
            "Authorization": f"Token {self._settings.DEEPGRAM_API_KEY}",
            "Content-Type": content_type,
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.DEEPGRAM_TIMEOUT_SECONDS),
                transport=self._transport,
            ) as client:
                response = await client.post(url, params=params, headers=headers, content=audio)
        except httpx.TimeoutException as error:
            raise DeepgramTimeoutError from error
        except httpx.RequestError as error:
            raise DeepgramUpstreamError("Speech transcription provider is unavailable.", status_code=503) from error

        if response.status_code >= 400:
            raise self._upstream_error(response)

        try:
            payload = response.json()
        except ValueError as error:
            raise DeepgramUpstreamError("Speech transcription provider returned invalid data.", status_code=502) from error

        return self._parse_response(payload)

    @staticmethod
    def _upstream_error(response: httpx.Response) -> DeepgramUpstreamError:
        """Map provider failures without returning provider internals to the client."""
        if response.status_code in {401, 403}:
            return DeepgramUpstreamError("Speech transcription provider authentication failed.", status_code=502)
        if response.status_code == 429:
            return DeepgramUpstreamError("Speech transcription provider rate limit reached.", status_code=503)
        if response.status_code in {400, 422}:
            return DeepgramUpstreamError("Deepgram rejected the audio or transcription options.", status_code=422)
        return DeepgramUpstreamError("Speech transcription provider failed.", status_code=502)

    def _parse_response(self, payload: Any) -> DeepgramTranscription:
        """Extract the first channel and alternative, including silence as an empty transcript."""
        if not isinstance(payload, dict):
            raise DeepgramUpstreamError("Speech transcription provider returned invalid data.", status_code=502)

        results = payload.get("results")
        channels = results.get("channels") if isinstance(results, dict) else None
        channel = channels[0] if isinstance(channels, list) and channels else {}
        alternatives = channel.get("alternatives") if isinstance(channel, dict) else None
        alternative = alternatives[0] if isinstance(alternatives, list) and alternatives else {}
        alternative = alternative if isinstance(alternative, dict) else {}
        metadata = payload.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}

        transcript = alternative.get("transcript", "")
        transcript = transcript if isinstance(transcript, str) else ""
        raw_words = alternative.get("words", [])
        words = (
            [self._word_from_payload(word) for word in raw_words if isinstance(word, dict)]
            if isinstance(raw_words, list)
            else []
        )

        return DeepgramTranscription(
            transcript=transcript,
            confidence=self._number(alternative.get("confidence")),
            duration_seconds=self._number(metadata.get("duration")),
            model=self._text(metadata.get("model"), self._settings.DEEPGRAM_MODEL),
            language=self._text(metadata.get("language"), self._settings.DEEPGRAM_LANGUAGE),
            words=words,
        )

    @classmethod
    def _word_from_payload(cls, payload: dict[str, Any]) -> DeepgramWord:
        return DeepgramWord(
            word=cls._text(payload.get("word"), ""),
            start=cls._number(payload.get("start")),
            end=cls._number(payload.get("end")),
            confidence=cls._number(payload.get("confidence")),
        )

    @staticmethod
    def _number(value: Any) -> float | None:
        return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None

    @staticmethod
    def _text(value: Any, fallback: str) -> str:
        return value if isinstance(value, str) and value else fallback
