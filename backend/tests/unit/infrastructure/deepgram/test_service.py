"""Provider-facing Deepgram tests using an in-memory HTTP transport."""

import httpx
import pytest

from src.infrastructure.deepgram.errors import (
    DeepgramConfigurationError,
    DeepgramTimeoutError,
    DeepgramUpstreamError,
)
from src.infrastructure.deepgram.service import DeepgramTranscriptionService
from src.infrastructure.deepgram.settings import DeepgramSettings

pytestmark = pytest.mark.asyncio


def _settings(**overrides: object) -> DeepgramSettings:
    values: dict[str, object] = {
        "DEEPGRAM_API_KEY": "test-deepgram-key",
        "DEEPGRAM_API_URL": "https://deepgram.test",
        "DEEPGRAM_TIMEOUT_SECONDS": 1,
    }
    values.update(overrides)
    return DeepgramSettings(**values)


async def test_transcription_sends_audio_and_repeated_keyterms():
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "metadata": {"model": "nova-3", "language": "es", "duration": 1.25},
                "results": {
                    "channels": [
                        {
                            "alternatives": [
                                {
                                    "transcript": "hola",
                                    "confidence": 0.98,
                                    "words": [{"word": "hola", "start": 0, "end": 0.4, "confidence": 0.98}],
                                }
                            ]
                        }
                    ]
                },
            },
            request=request,
        )

    service = DeepgramTranscriptionService(_settings(), transport=httpx.MockTransport(handler))
    result = await service.transcribe(b"wav-bytes", "audio/wav", ["hola", "buenos dias"])

    assert result.transcript == "hola"
    assert result.confidence == 0.98
    assert result.duration_seconds == 1.25
    assert result.words[0].word == "hola"
    assert seen["authorization"] == "Token test-deepgram-key"
    assert seen["content_type"] == "audio/wav"
    assert seen["body"] == b"wav-bytes"
    assert "keyterm=hola" in str(seen["url"])
    assert "keyterm=buenos+dias" in str(seen["url"])


async def test_empty_deepgram_transcript_is_supported_as_silence():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": {"channels": [{"alternatives": [{"transcript": "", "confidence": 0}]}]}},
            request=request,
        )

    service = DeepgramTranscriptionService(_settings(), transport=httpx.MockTransport(handler))
    result = await service.transcribe(b"silence", "audio/wav", [])

    assert result.transcript == ""
    assert result.words == []


async def test_missing_key_is_rejected_before_network_call():
    service = DeepgramTranscriptionService(_settings(DEEPGRAM_API_KEY=""))

    with pytest.raises(DeepgramConfigurationError):
        await service.transcribe(b"audio", "audio/wav", [])


async def test_timeout_is_mapped_to_a_client_safe_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timeout", request=request)

    service = DeepgramTranscriptionService(_settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(DeepgramTimeoutError):
        await service.transcribe(b"audio", "audio/wav", [])


@pytest.mark.parametrize("status_code", [400, 401, 429, 500])
async def test_provider_errors_are_mapped_without_leaking_provider_body(status_code: int):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="provider secret details", request=request)

    service = DeepgramTranscriptionService(_settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(DeepgramUpstreamError) as raised:
        await service.transcribe(b"audio", "audio/wav", [])

    assert "provider secret" not in raised.value.detail
    assert raised.value.status_code in {422, 502, 503}
