"""FastAPI dependencies for the Deepgram integration."""

from typing import Annotated

from fastapi import Depends

from ...wiring.settings import settings
from .service import DeepgramTranscriptionService


def get_deepgram_service() -> DeepgramTranscriptionService:
    """Build a request-scoped provider client with the current application settings."""
    return DeepgramTranscriptionService(settings)


DeepgramServiceDep = Annotated[DeepgramTranscriptionService, Depends(get_deepgram_service)]
