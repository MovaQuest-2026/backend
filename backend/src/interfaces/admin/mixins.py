"""Mixins for SQLAdmin views to handle dataclass-based models."""

from collections.abc import AsyncGenerator
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from crudauth.utils import get_client_ip
from sqladmin.helpers import Writer, secure_filename, stream_to_csv
from starlette.requests import Request
from starlette.responses import StreamingResponse

from ...infrastructure.config.settings import get_settings
from ...infrastructure.database.session import local_session
from ...infrastructure.logging import get_logger
from ...modules.audit_log.models import AdminAuditLog

logger = get_logger()

SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
NUMERIC_CELL_TYPES = (int, float, Decimal, date, time, timedelta)
AUDIT_REDACTED_FIELDS = frozenset(
    {
        "password",
        "hashed_password",
        "token",
        "token_version",
        "google_id",
        "github_id",
        "oauth_created_at",
        "oauth_updated_at",
        "content",
    }
)


def as_spreadsheet_text(value: Any) -> str:
    """Render ``value`` for a CSV cell, prefixing formula-like text with an apostrophe.

    ``None``, numbers, dates and times render as sqladmin renders them. Any other
    value whose text starts with ``=``, ``+``, ``-``, ``@``, a tab or a carriage
    return gets the apostrophe.
    """
    cell = str(value)
    if value is None or isinstance(value, NUMERIC_CELL_TYPES):
        return cell

    return f"'{cell}" if cell.startswith(SPREADSHEET_FORMULA_PREFIXES) else cell


class TextCsvExportMixin:
    """Mixin for SQLAdmin ModelView that writes formula-like CSV cells as text.

    Covers both export paths: ``export_data`` for the plain CSV, and
    ``custom_export_cell`` for the one ``use_pretty_export`` takes. JSON exports go
    to sqladmin unchanged.

    Usage:
        class MyAdmin(TextCsvExportMixin, ModelView, model=MyModel):
            can_export = True
    """

    async def export_data(self, data: list[Any], export_type: str = "csv", request: Request | None = None) -> StreamingResponse:
        """Stream ``data`` as CSV, or hand any other format to sqladmin."""
        if export_type != "csv":
            return await super().export_data(data, export_type=export_type, request=request)  # type: ignore[misc,no-any-return]

        if self.use_pretty_export:  # type: ignore[attr-defined]
            return await super().export_data(data, export_type=export_type, request=request)  # type: ignore[misc,no-any-return]

        names = self.get_export_columns()  # type: ignore[attr-defined]

        async def generate(writer: Writer) -> AsyncGenerator[Any, None]:
            yield writer.writerow(names)

            for row in data:
                cells = [as_spreadsheet_text(await self.get_prop_value(row, name)) for name in names]  # type: ignore[attr-defined]
                yield writer.writerow(cells)

        filename = secure_filename(self.get_export_name(export_type="csv"))  # type: ignore[attr-defined]

        return StreamingResponse(
            content=stream_to_csv(generate),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment;filename={filename}"},
        )

    async def custom_export_cell(self, row: Any, name: str, value: Any) -> str | None:
        """Return the pretty export's cell for ``name``, as text where ``value`` looks like a formula."""
        cell = await super().custom_export_cell(row, name, value)  # type: ignore[misc]
        if cell is not None:
            return as_spreadsheet_text(cell)

        if as_spreadsheet_text(value) == str(value):
            return None

        _, formatted = await self.get_list_value(row, name)  # type: ignore[attr-defined]

        return as_spreadsheet_text(formatted)


class DataclassModelMixin:
    """Mixin for SQLAdmin ModelView to support dataclass-based SQLAlchemy models.

    SQLAdmin's default insert_model creates an empty model instance via model(),
    then sets attributes. This fails for MappedAsDataclass models with required
    fields that have no defaults.

    This mixin overrides insert_model to create the model WITH the form data,
    which works correctly with dataclass __init__ signatures.

    Usage:
        class MyAdmin(DataclassModelMixin, ModelView, model=MyModel):
            ...

        # For custom data transformation before model creation:
        class UserAdmin(DataclassModelMixin, ModelView, model=User):
            async def on_model_change(self, data, model, is_created, request):
                if is_created:
                    # Transform data BEFORE model is created
                    data["hashed_password"] = hash(data.pop("password"))
    """

    async def insert_model(self, request: Request, data: dict[str, Any]) -> Any:
        """Create model instance with data for dataclass compatibility.

        Instead of creating an empty model then setting attributes,
        we create the model with all data at once, which satisfies
        dataclass required field constraints.
        """
        await self.on_model_change(data, None, True, request)  # type: ignore[attr-defined]

        clean_data = {}
        for key, value in data.items():
            if hasattr(self, "_mapper") and key in self._mapper.relationships:
                rel = self._mapper.relationships[key]
                if rel.direction.name == "MANYTOONE":
                    fk_columns = list(rel.local_columns)
                    if fk_columns:
                        fk_col_name = fk_columns[0].name
                        clean_data[fk_col_name] = int(value) if value else None
                continue

            if value == "" and hasattr(self, "_mapper"):
                col = self._mapper.columns.get(key)
                if col is not None and col.nullable:
                    value = None

            clean_data[key] = value

        obj = self.model(**clean_data)  # type: ignore[attr-defined]

        async with self.session_maker(expire_on_commit=False) as session:  # type: ignore[attr-defined]
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            await self.after_model_change(data, obj, True, request)  # type: ignore[attr-defined]
            return obj


class AdminAuditMixin:
    """Persist successful SQLAdmin mutations as immutable audit events."""

    async def after_model_change(self, data: dict[str, Any], model: Any, is_created: bool, request: Request) -> None:
        """Record a successful create or update after SQLAdmin commits the change."""
        await super().after_model_change(data, model, is_created, request)  # type: ignore[misc]
        await self._record_audit_event(
            request=request,
            action="create" if is_created else "update",
            model=model,
            changes=_safe_changes(data),
        )

    async def delete_model(self, request: Request, pk: str) -> Any:
        """Record a successful delete while preserving SQLAdmin's delete behavior."""
        model = await self._load_model_for_audit(pk)
        result = await super().delete_model(request, pk)  # type: ignore[misc]
        await self._record_audit_event(
            request=request,
            action="delete",
            model=model,
            changes=_safe_model_snapshot(model),
            entity_id=str(pk),
        )
        return result

    async def _load_model_for_audit(self, pk: str) -> Any:
        """Load the row before deletion so the event remains useful after removal."""
        identifier: Any = int(pk) if pk.isdigit() else pk
        async with local_session() as session:
            return await session.get(self.model, identifier)  # type: ignore[attr-defined]

    async def _record_audit_event(
        self,
        request: Request,
        action: str,
        model: Any,
        changes: dict[str, Any],
        entity_id: str | None = None,
    ) -> None:
        """Write an audit event without turning an already-completed action into a 500."""
        settings = get_settings()
        event = AdminAuditLog(
            actor=settings.ADMIN_USERNAME or "admin",
            action=action,
            entity=type(model).__name__ if model is not None else self.model.__name__,  # type: ignore[attr-defined]
            entity_id=entity_id or _model_identifier(model),
            changes=changes,
            ip_address=get_client_ip(request, settings.TRUSTED_PROXY_HOPS),
            user_agent=request.headers.get("user-agent"),
        )
        try:
            async with local_session() as session:
                session.add(event)
                await session.commit()
        except Exception:
            logger.exception("Could not persist admin audit event", extra={"action": action, "entity": event.entity})


def _model_identifier(model: Any) -> str | None:
    """Return a stable string identifier for a model when one is available."""
    identifier = getattr(model, "id", None) if model is not None else None
    return str(identifier) if identifier is not None else None


def _safe_changes(data: dict[str, Any]) -> dict[str, Any]:
    """Keep audit payloads JSON-safe and exclude credentials and large/sensitive values."""
    return {key: _safe_value(key, value) for key, value in data.items() if key not in AUDIT_REDACTED_FIELDS}


def _safe_model_snapshot(model: Any) -> dict[str, Any]:
    """Snapshot mapped columns before deletion, excluding sensitive fields."""
    if model is None:
        return {}
    return _safe_changes({column.key: getattr(model, column.key, None) for column in model.__table__.columns})


def _safe_value(field: str, value: Any) -> Any:
    """Convert values to JSON-safe representations without leaking secrets."""
    if field in AUDIT_REDACTED_FIELDS:
        return "[REDACTED]"
    if isinstance(value, bytes):
        return f"[BINARY:{len(value)} bytes]"
    if isinstance(value, (date, time, timedelta)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
