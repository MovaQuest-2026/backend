"""Validation tests for the public transcription contract."""

from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.infrastructure.deepgram.errors import DeepgramUpstreamError
from src.infrastructure.deepgram.routes import _normalize_keyterms, transcribe_audio
from src.infrastructure.deepgram.service import DeepgramTranscription, DeepgramWord
from src.infrastructure.http_exceptions import HTTPException
from src.wiring.settings import settings

pytestmark = pytest.mark.asyncio


class StubDeepgramService:
    """A provider double that proves what the route sends downstream."""

    def __init__(self, result: DeepgramTranscription | None = None) -> None:
        self.keyterms: list[str] = []
        self.result = result or DeepgramTranscription(
            transcript="hola",
            confidence=0.9,
            duration_seconds=0.5,
            model="nova-3",
            language="es",
            words=[DeepgramWord("hola", 0, 0.5, 0.9)],
        )

    async def transcribe(self, audio: bytes, content_type: str, keyterms: list[str]) -> DeepgramTranscription:
        self.keyterms = keyterms
        assert audio == b"audio"
        assert content_type == "audio/webm"
        return self.result


def _upload(content: bytes = b"audio", content_type: str = "audio/webm") -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename="answer.webm",
        headers=Headers({"content-type": content_type}),
    )


async def test_keyterms_are_trimmed_and_deduplicated_case_insensitively():
    assert _normalize_keyterms([" hola ", "HOLA", "", " buenos dias "]) == ["hola", "buenos dias"]


async def test_route_forwards_hints_and_returns_stable_contract():
    service = StubDeepgramService()

    response = await transcribe_audio(_upload(), service, [" hola ", "HOLA", "viaje"])

    assert response.transcript == "hola"
    assert response.is_silent is False
    assert response.words[0].word == "hola"
    assert service.keyterms == ["hola", "viaje"]


async def test_route_rejects_non_audio_content_type():
    with pytest.raises(HTTPException) as raised:
        await transcribe_audio(_upload(content_type="text/plain"), StubDeepgramService())

    assert raised.value.status_code == 415


async def test_route_rejects_audio_over_the_configured_limit(monkeypatch):
    monkeypatch.setattr(settings, "DEEPGRAM_MAX_AUDIO_BYTES", 4)

    with pytest.raises(HTTPException) as raised:
        await transcribe_audio(_upload(content=b"12345"), StubDeepgramService())

    assert raised.value.status_code == 413


async def test_route_maps_provider_failures_to_http_errors():
    class FailingService(StubDeepgramService):
        async def transcribe(self, audio: bytes, content_type: str, keyterms: list[str]) -> DeepgramTranscription:
            raise DeepgramUpstreamError("provider failed", status_code=502)

    with pytest.raises(HTTPException) as raised:
        await transcribe_audio(_upload(), FailingService())

    assert raised.value.status_code == 502
    assert raised.value.detail == "provider failed"
