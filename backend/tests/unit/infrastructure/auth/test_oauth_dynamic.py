"""Tests for the allowlisted, request-aware OAuth callback origin."""

from urllib.parse import parse_qs, urlsplit

import pytest
from crudauth.exceptions import BadRequestException
from starlette.requests import Request

from src.infrastructure.auth.oauth_dynamic import (
    RequestAwareGoogleOAuthProvider,
    RequestAwareRedirect,
    select_frontend_url,
    select_oauth_base_url,
    use_oauth_base_url,
)
from src.infrastructure.config.settings import settings


def _request(*, headers: dict[str, str], scheme: str = "https", host: str = "backend.example") -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": "/api/v1/auth/oauth/google",
        "raw_path": b"/api/v1/auth/oauth/google",
        "query_string": b"",
        "headers": raw_headers,
        "server": (host, 443 if scheme == "https" else 80),
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


def test_oauth_origin_uses_forwarded_host_only_when_proxy_is_trusted(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    monkeypatch.setattr(
        settings,
        "OAUTH_ALLOWED_BASE_URLS",
        "https://backend.example,http://localhost:5173",
    )

    request = _request(
        headers={
            "host": "backend.internal",
            "x-forwarded-host": "localhost:5173",
            "x-forwarded-proto": "http",
        },
        scheme="http",
        host="backend.internal",
    )

    assert select_oauth_base_url(request) == "http://localhost:5173"


def test_oauth_origin_keeps_allowlisted_local_scheme_after_proxy_tls_termination(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    monkeypatch.setattr(
        settings,
        "OAUTH_ALLOWED_BASE_URLS",
        "https://backend.example,http://localhost:5173",
    )

    request = _request(
        headers={
            "host": "backend.internal",
            "x-forwarded-host": "localhost:5173",
            "x-forwarded-proto": "https",
        },
        scheme="https",
        host="backend.internal",
    )

    assert select_oauth_base_url(request) == "http://localhost:5173"


def test_oauth_origin_rejects_an_unknown_host(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)
    monkeypatch.setattr(settings, "OAUTH_ALLOWED_BASE_URLS", "https://backend.example")

    with pytest.raises(BadRequestException):
        select_oauth_base_url(_request(headers={"host": "evil.example"}))


def test_request_aware_provider_uses_the_selected_callback_without_mutating_shared_provider():
    provider = RequestAwareGoogleOAuthProvider(
        "client-id",
        "client-secret",
        "https://backend.example/api/v1/auth/oauth/callback/google",
    )

    with use_oauth_base_url("http://localhost:5173"):
        authorization = provider.get_authorization_url()

    query = parse_qs(urlsplit(authorization["url"]).query)
    assert query["redirect_uri"] == ["http://localhost:5173/api/v1/auth/oauth/callback/google"]
    assert provider.redirect_uri == "https://backend.example/api/v1/auth/oauth/callback/google"


def test_request_aware_redirect_uses_local_frontend_when_it_is_the_selected_origin(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://frontend.example")
    monkeypatch.setattr(settings, "FRONTEND_ALLOWED_URLS", "https://frontend.example,http://localhost:5173")

    with use_oauth_base_url("http://localhost:5173"):
        assert str(RequestAwareRedirect("https://frontend.example")) == "http://localhost:5173"
        assert select_frontend_url() == "http://localhost:5173"
