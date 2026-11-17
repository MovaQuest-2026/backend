"""Configuration for the Deepgram speech-to-text integration."""

from pydantic_settings import BaseSettings

from ..config.base import config


class DeepgramSettings(BaseSettings):
    """The provider settings and local safety limits for transcription requests."""

    DEEPGRAM_ENABLED: bool = config("DEEPGRAM_ENABLED", default=True, cast=bool)
    DEEPGRAM_PUBLIC_ENABLED: bool = config("DEEPGRAM_PUBLIC_ENABLED", default=False, cast=bool)
    DEEPGRAM_API_KEY: str = config("DEEPGRAM_API_KEY", default="")
    DEEPGRAM_API_URL: str = config("DEEPGRAM_API_URL", default="https://api.deepgram.com")
    DEEPGRAM_MODEL: str = config("DEEPGRAM_MODEL", default="nova-3")
    DEEPGRAM_LANGUAGE: str = config("DEEPGRAM_LANGUAGE", default="es")
    DEEPGRAM_TIMEOUT_SECONDS: float = config("DEEPGRAM_TIMEOUT_SECONDS", default=30.0, cast=float)
    DEEPGRAM_MAX_AUDIO_BYTES: int = config("DEEPGRAM_MAX_AUDIO_BYTES", default=10 * 1024 * 1024, cast=int)
    DEEPGRAM_MAX_KEYTERMS: int = config("DEEPGRAM_MAX_KEYTERMS", default=100, cast=int)
    DEEPGRAM_MAX_KEYTERM_TOKENS: int = config("DEEPGRAM_MAX_KEYTERM_TOKENS", default=500, cast=int)
