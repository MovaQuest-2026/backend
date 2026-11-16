"""Synchronous SQLAlchemy database access with an async-compatible boundary.

The application template and FastCRUD/CRUDAuth call database methods with
``await``. The actual database work is performed by a synchronous SQLAlchemy
``Engine`` and ``Session`` using psycopg2. ``DatabaseSession`` keeps the
existing async application contract while making the driver and pool sync.
"""

from collections.abc import AsyncGenerator
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Connection, Engine, Result
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass, Session, sessionmaker

from ..config.settings import get_settings
from .registry import import_models

_engine: Engine | None = None
_session_factory: "DatabaseSessionFactory | None" = None


class _AsyncContextAdapter:
    """Expose a synchronous context manager through ``async with``."""

    def __init__(self, context: AbstractContextManager[Any]) -> None:
        self._context = context

    async def __aenter__(self) -> Any:
        return self._context.__enter__()

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None:
        return self._context.__exit__(exc_type, exc, traceback)


class DatabaseConnection:
    """Async-compatible facade over a synchronous SQLAlchemy connection."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    async def run_sync(self, callback: Any, *args: Any, **kwargs: Any) -> Any:
        """Support the ``AsyncConnection.run_sync`` call used by CRUDAuth."""
        return callback(self._connection, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class DatabaseSession:
    """Async-compatible facade over a synchronous SQLAlchemy ``Session``.

    Methods that perform database I/O are awaitable because FastCRUD and
    CRUDAuth expect ``AsyncSession``. The underlying calls are synchronous.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def bind(self) -> Engine | Connection | None:
        return self._session.bind

    def get_bind(self, *args: Any, **kwargs: Any) -> Engine | Connection:
        return self._session.get_bind(*args, **kwargs)

    def add(self, instance: Any, _warn: bool = True) -> None:
        self._session.add(instance, _warn=_warn)

    def add_all(self, instances: list[Any]) -> None:
        self._session.add_all(instances)

    def begin(self) -> _AsyncContextAdapter:
        return _AsyncContextAdapter(self._session.begin())

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()

    async def flush(self, objects: Any = None) -> None:
        self._session.flush(objects)

    async def refresh(self, instance: Any, attribute_names: Any = None, with_for_update: Any = None) -> None:
        self._session.refresh(instance, attribute_names=attribute_names, with_for_update=with_for_update)

    async def execute(self, statement: Any, params: Any = None, *, execution_options: Any = None) -> Result[Any]:
        kwargs: dict[str, Any] = {}
        if execution_options is not None:
            kwargs["execution_options"] = execution_options
        if params is None:
            return self._session.execute(statement, **kwargs)
        return self._session.execute(statement, params, **kwargs)

    async def scalar(self, statement: Any, params: Any = None, *, execution_options: Any = None) -> Any:
        kwargs: dict[str, Any] = {}
        if execution_options is not None:
            kwargs["execution_options"] = execution_options
        if params is None:
            return self._session.scalar(statement, **kwargs)
        return self._session.scalar(statement, params, **kwargs)

    async def get(self, entity: Any, ident: Any, options: Any = None, **kwargs: Any) -> Any:
        return self._session.get(entity, ident, options=options, **kwargs)

    async def delete(self, instance: Any) -> None:
        self._session.delete(instance)

    async def connection(self, **kwargs: Any) -> DatabaseConnection:
        return DatabaseConnection(self._session.connection(**kwargs))

    async def close(self) -> None:
        self._session.close()

    async def __aenter__(self) -> "DatabaseSession":
        self._session.__enter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._session.__exit__(exc_type, exc, traceback)


class DatabaseSessionFactory:
    """Callable factory matching the session-factory contract used by the app."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def __call__(self, **kwargs: Any) -> DatabaseSession:
        return DatabaseSession(self._factory(**kwargs))


def _sync_database_url(url: str) -> str:
    """Normalize Render/local PostgreSQL URLs to the psycopg2 dialect."""
    if url.startswith("sqlite+aiosqlite://"):
        return "sqlite://" + url.removeprefix("sqlite+aiosqlite://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url.removeprefix("postgres://")
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + url.removeprefix("postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url.removeprefix("postgresql://")
    return url


def build_engine(url: str | None = None, **overrides: Any) -> Engine:
    """Create the shared synchronous SQLAlchemy engine."""
    settings = get_settings()
    options: dict[str, Any] = {
        "echo": False,
        "future": True,
        "hide_parameters": True,
        "pool_pre_ping": settings.POSTGRES_POOL_PRE_PING,
        "pool_recycle": settings.POSTGRES_POOL_RECYCLE,
    }
    normalized_url = _sync_database_url(url or settings.DATABASE_URL)
    if "poolclass" not in overrides and not normalized_url.startswith("sqlite"):
        options["pool_size"] = settings.POSTGRES_POOL_SIZE
        options["max_overflow"] = settings.POSTGRES_MAX_OVERFLOW
    options.update(overrides)

    return create_engine(normalized_url, **options)


def get_engine() -> Engine:
    """Return the application's shared synchronous engine."""
    global _engine
    if _engine is None:
        _engine = build_engine()

    return _engine


def get_session_factory() -> DatabaseSessionFactory:
    """Return the application's shared synchronous session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = DatabaseSessionFactory(
            sessionmaker(bind=get_engine(), class_=Session, expire_on_commit=False)
        )

    return _session_factory


def local_session() -> DatabaseSession:
    """Open a synchronous database session through the compatibility facade."""
    return get_session_factory()()


async def async_session() -> AsyncGenerator[DatabaseSession, None]:
    """Yield a per-request synchronous session through FastAPI's async API."""
    session = local_session()
    try:
        yield session
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Close all pooled connections, if the engine was created."""
    if _engine is not None:
        _engine.dispose()


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase, MappedAsDataclass):
    """Base class for all SQLAlchemy models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


async def create_tables() -> None:
    """Create all registered model tables using the synchronous engine."""
    import_models()
    with get_engine().begin() as connection:
        Base.metadata.create_all(connection)


def __getattr__(name: str) -> Engine:
    """Keep the deprecated module-level ``engine`` importable."""
    if name == "engine":
        return get_engine()

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
