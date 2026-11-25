"""Tests for safe audit payload construction."""

from datetime import UTC, datetime

from src.interfaces.admin.mixins import _safe_changes


def test_audit_payload_excludes_credentials_and_large_binary_values():
    changes = _safe_changes(
        {
            "email": "user@example.com",
            "hashed_password": "secret-hash",
            "google_id": "oauth-id",
            "content": b"video-bytes",
        }
    )

    assert changes == {"email": "user@example.com"}


def test_audit_payload_serializes_datetime_values():
    created_at = datetime(2026, 11, 23, 12, 30, tzinfo=UTC)

    assert _safe_changes({"created_at": created_at}) == {"created_at": created_at.isoformat()}
