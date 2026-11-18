"""Business-rule tests for progress merging without external services."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.infrastructure.database.registry import import_models
from src.infrastructure.database.session import Base, DatabaseSession
from src.modules.progress.models import ActiveLesson as ActiveLessonModel
from src.modules.progress.models import LessonResult
from src.modules.progress.routes import get_progress, import_progress, save_active_lesson
from src.modules.progress.schemas import ActiveLesson, CompletedLesson, Progress

pytestmark = pytest.mark.asyncio


@pytest.fixture
def progress_db():
    import_models()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = DatabaseSession(Session(engine))
    yield session
    session._session.close()
    engine.dispose()


async def test_import_merges_best_result_words_and_ignores_stale_active(progress_db: DatabaseSession):
    now = datetime.now(UTC)
    first = Progress(
        completedLessons={
            "hola": CompletedLesson(
                outcome="partial", correct=1, total=3, completedAt=now - timedelta(seconds=2)
            )
        },
        learnedWords={"hola": ["día"]},
        activeLessons={"hola": ActiveLesson(machine={"status": "paused"}, updatedAt=now - timedelta(seconds=1))},
    )
    await import_progress(first, {"id": 1}, progress_db)

    second = Progress(
        completedLessons={"hola": CompletedLesson(outcome="perfect", correct=3, total=3, completedAt=now)},
        learnedWords={"hola": ["día", "café"]},
        activeLessons={},
    )
    merged = await import_progress(second, {"id": 1}, progress_db)
    assert merged.completed_lessons["hola"].correct == 3
    assert set(merged.learned_words["hola"]) == {"día", "café"}

    await save_active_lesson(
        "hola",
        ActiveLesson(machine={"status": "stale"}, updatedAt=now - timedelta(seconds=1)),
        {"id": 1},
        progress_db,
    )
    current = await get_progress({"id": 1}, progress_db)
    assert "hola" not in current.active_lessons


async def test_import_accepts_empty_maps_and_naive_database_timestamps(progress_db: DatabaseSession):
    empty = Progress(completedLessons={}, learnedWords={}, activeLessons={})
    merged = await import_progress(empty, {"id": 1}, progress_db)
    assert merged.completed_lessons == {}
    assert merged.learned_words == {}
    assert merged.active_lessons == {}

    naive_completed = datetime(2026, 11, 18, 10, 0, 0)
    naive_active = datetime(2026, 11, 18, 10, 1, 0)
    progress_db.add(
        LessonResult(
            account_id=1,
            lesson_id="cafe-madrid",
            outcome="partial",
            correct=2,
            total=3,
            completed_at=naive_completed,
        )
    )
    progress_db.add(
        ActiveLessonModel(
            account_id=1,
            lesson_id="cafe-madrid",
            machine={"status": "playing"},
            client_updated_at=naive_active,
        )
    )
    await progress_db.commit()

    current = await get_progress({"id": 1}, progress_db)
    assert "cafe-madrid" in current.active_lessons
