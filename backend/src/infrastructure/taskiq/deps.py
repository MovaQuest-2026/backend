"""Task dependencies for taskiq integration."""

from collections.abc import AsyncGenerator
from typing import Annotated

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from taskiq import TaskiqDepends

from ..database.session import DatabaseSession, DatabaseSessionFactory, build_engine

_engine: Engine | None = None
_session_factory: DatabaseSessionFactory | None = None


def get_taskiq_engine() -> Engine:
    """Return the worker's synchronous ``NullPool`` engine."""
    global _engine
    if _engine is None:
        _engine = build_engine(poolclass=NullPool)

    return _engine


def get_taskiq_session_factory() -> DatabaseSessionFactory:
    """Return the worker's synchronous session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = DatabaseSessionFactory(
            sessionmaker(bind=get_taskiq_engine(), class_=Session, expire_on_commit=False)
        )

    return _session_factory


async def dispose_taskiq_engine() -> None:
    """Close the worker engine's connections, if the engine was ever created."""
    if _engine is None:
        return

    _engine.dispose()


async def get_db_session() -> AsyncGenerator[DatabaseSession, None]:
    """Get a database session for taskiq tasks.

    Provides a database session with proper lifecycle management for
    taskiq tasks, ensuring clean connection handling and transaction management.

    Yields:
        DatabaseSession: Synchronous database session behind the async task API.
    """
    async with get_taskiq_session_factory()() as session:
        try:
            yield session
        finally:
            await session.close()


DBSession = Annotated[DatabaseSession, TaskiqDepends(get_db_session)]
