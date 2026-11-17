"""Request-aware OAuth origins for deployments serving several frontends.

The crudauth OAuth router keeps a provider object for the lifetime of the process,
while Google requires the exact callback URL in both the authorization and token
requests.  This module keeps the provider immutable between requests by cloning it
with the request's allowlisted callback origin, and stores that origin in a context
variable for the duration of the current request.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import cast
from urllib.parse import urlsplit

from crudauth.exceptions import BadRequestException
from crudauth.oauth.provider import AbstractOAuthProvider
from crudauth.oauth.providers.github import GitHubOAuthProvider
from crudauth.oauth.providers.google import GoogleOAuthProvider
from fastapi import Request

from ...wiring.settings import settings

_current_oauth_base_url: ContextVar[str | None] = ContextVar("current_oauth_base_url", default=None)


def _configured_origins(value: str) -> list[str]:
    """Parse absolute origins and reject paths or query strings in configuration."""
    origins: list[str] = []
    for raw in value.split(","):
        origin = raw.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"OAuth origins must be absolute URLs without a path: {origin!r}")
        origins.append(origin)
    return origins


def _same_origin(left: str, right: str) -> bool:
    """Compare scheme and host case-insensitively, including the port."""
    return left.rstrip("/").casefold() == right.rstrip("/").casefold()


def _origin_host(origin: str) -> str:
    """Return the normalized host and port from an absolute configured origin."""
    return urlsplit(origin).netloc.casefold()


def _forwarded_value(request: Request, name: str) -> str | None:
    """Read proxy headers only when the deployment explicitly trusts a proxy hop."""
    if settings.TRUSTED_PROXY_HOPS <= 0:
        return None
    value = request.headers.get(name)
    return value.split(",", 1)[0].strip() if value else None


def select_oauth_base_url(request: Request) -> str:
    """Select the request origin from the configured OAuth callback allowlist."""
    allowed = _configured_origins(settings.OAUTH_ALLOWED_BASE_URLS)
    if not allowed:
        return settings.OAUTH_REDIRECT_BASE_URL.rstrip("/")

    host = _forwarded_value(request, "x-forwarded-host") or request.headers.get("host", "")
    for origin in allowed:
        # Render can expose a local Vite request as HTTPS after TLS termination.
        # The allowlist is authoritative for the scheme; the request host selects
        # which configured origin is used for Google's callback.
        if _origin_host(origin) == host.casefold():
            return origin

    raise BadRequestException("This host is not allowed for OAuth.")


def select_frontend_url() -> str:
    """Return the frontend paired with the current OAuth request.

    A local Vite proxy has the frontend origin in ``X-Forwarded-Host`` and is
    therefore matched directly.  A production request reaches the Render API
    origin, so it falls back to the canonical ``FRONTEND_URL``.
    """
    current = _current_oauth_base_url.get()
    allowed_frontends = _configured_origins(settings.FRONTEND_ALLOWED_URLS)
    if current:
        for frontend in allowed_frontends:
            if _same_origin(frontend, current):
                return frontend
    return settings.FRONTEND_URL.rstrip("/")


async def bind_oauth_request(request: Request) -> AsyncIterator[None]:
    """Bind the allowlisted callback origin for crudauth's authorize/callback routes."""
    if not settings.OAUTH_ALLOWED_BASE_URLS:
        yield
        return

    token = _current_oauth_base_url.set(select_oauth_base_url(request))
    try:
        yield
    finally:
        _current_oauth_base_url.reset(token)


@contextmanager
def use_oauth_base_url(origin: str) -> Iterator[None]:
    """Temporarily bind an OAuth origin in tests or another controlled caller."""
    token = _current_oauth_base_url.set(origin.rstrip("/"))
    try:
        yield
    finally:
        _current_oauth_base_url.reset(token)


class RequestAwareRedirect(str):
    """A string accepted by crudauth that resolves to the current frontend origin."""

    fallback: str

    def __new__(cls, fallback: str) -> RequestAwareRedirect:
        instance = super().__new__(cls, fallback.rstrip("/"))
        instance.fallback = fallback.rstrip("/")
        return instance

    def __str__(self) -> str:
        return select_frontend_url() if _current_oauth_base_url.get() else self.fallback

    def __format__(self, format_spec: str) -> str:
        return format(str(self), format_spec)


class RequestAwareProviderMixin:
    """Clone a provider with the request-specific callback URI before each operation."""

    redirect_uri: str

    def _for_current_request(self) -> AbstractOAuthProvider:
        origin = _current_oauth_base_url.get()
        if not origin:
            return cast(AbstractOAuthProvider, self)

        provider = cast(AbstractOAuthProvider, copy.copy(self))
        callback_path = urlsplit(self.redirect_uri).path
        provider.redirect_uri = f"{origin}{callback_path}"
        return provider

    def get_authorization_url(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        provider = self._for_current_request()
        return AbstractOAuthProvider.get_authorization_url(provider, *args, **kwargs)

    async def exchange_code(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        provider = self._for_current_request()
        return await AbstractOAuthProvider.exchange_code(provider, *args, **kwargs)


class RequestAwareGoogleOAuthProvider(RequestAwareProviderMixin, GoogleOAuthProvider):
    """Google provider whose callback origin follows the trusted request origin."""


class RequestAwareGitHubOAuthProvider(RequestAwareProviderMixin, GitHubOAuthProvider):
    """GitHub provider with the same request-aware callback behavior."""
