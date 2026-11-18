"""Validation tests for the frontend-owned progress contract."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.modules.progress.schemas import ActiveLesson, CompletedLesson, Progress


def test_completed_lesson_rejects_correct_above_total():
    with pytest.raises(ValidationError):
        CompletedLesson(outcome="partial", correct=2, total=1, completedAt=datetime.now(UTC))


def test_progress_validates_lesson_and_unicode_gap_ids():
    progress = Progress(
        completedLessons={},
        learnedWords={"hola": ["día"]},
        activeLessons={},
    )

    assert progress.learned_words["hola"] == ["día"]

    with pytest.raises(ValidationError):
        Progress(completedLessons={}, learnedWords={"Hola": ["día"]}, activeLessons={})


def test_active_machine_is_limited_to_32_kibibytes():
    with pytest.raises(ValidationError):
        ActiveLesson(machine={"heard": "x" * (32 * 1024)}, updatedAt=datetime.now(UTC))
