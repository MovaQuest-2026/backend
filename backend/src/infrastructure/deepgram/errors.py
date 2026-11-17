"""Errors raised while communicating with Deepgram."""


class DeepgramError(Exception):
    """An error that can be safely translated into an API response."""

    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class DeepgramConfigurationError(DeepgramError):
    """Deepgram is not configured for this deployment."""

    def __init__(self) -> None:
        super().__init__("Speech transcription is not configured.", status_code=503)


class DeepgramTimeoutError(DeepgramError):
    """Deepgram did not answer within the configured timeout."""

    def __init__(self) -> None:
        super().__init__("Speech transcription timed out.", status_code=504)


class DeepgramUpstreamError(DeepgramError):
    """Deepgram returned an error or could not be reached."""
