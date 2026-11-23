"""The authentication transports this project registers beside the session one."""

from crudauth import BearerTransport, Transport

from ..modules.api_keys.transport import APIKeyTransport

EXTRA_TRANSPORTS: tuple[Transport, ...] = (
    BearerTransport(access_ttl=3600, refresh_ttl_days=60, refresh="body"),
    APIKeyTransport(),
)
