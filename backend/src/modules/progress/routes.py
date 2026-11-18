"""Account progress and resumable lesson state endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Path, Response, status
from sqlalchemy import delete, select

from ...infrastructure.auth.deps import CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from .models import ActiveLesson as ActiveLessonModel
from .models import LearnedWord, LessonResult
from .schemas import (
    ActiveLesson,
    ActiveLessonResponse,
    CompletedLesson,
    LearnedWordsPayload,
    Progress,
    ProgressResponse,
)

router = APIRouter(prefix="/me/progress", tags=["Progress"])

LessonId = Annotated[str, Path(pattern=r"^[a-z0-9-]{1,64}$", description="Frontend lesson identifier")]


def _utc(value: datetime) -> datetime:
    """Make timestamps comparable and stable regardless of the DB driver's behavior."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _server_timestamp(value: datetime) -> datetime:
    """Clamp device clocks more than five minutes ahead of the server."""
    value = _utc(value)
    now = datetime.now(UTC)
    return now if value > now + timedelta(minutes=5) else value


def _result_response(row: LessonResult) -> CompletedLesson:
    return CompletedLesson.model_validate(
        {
            "outcome": row.outcome,
            "correct": row.correct,
            "total": row.total,
            "completedAt": _utc(row.completed_at),
        }
    )


def _active_response(row: ActiveLessonModel | ActiveLesson) -> ActiveLessonResponse:
    if isinstance(row, ActiveLessonModel):
        machine = row.machine
        updated_at = row.client_updated_at
    else:
        machine = row.machine
        updated_at = row.updated_at
    return ActiveLessonResponse.model_validate({"machine": machine, "updatedAt": _utc(updated_at)})


async def _progress(db: AsyncSessionDep, user_id: int) -> ProgressResponse:
    result_rows = list(
        (
            await db.execute(
                select(LessonResult).where(LessonResult.account_id == user_id).order_by(LessonResult.lesson_id)
            )
        )
        .scalars()
        .all()
    )
    word_rows = list(
        (
            await db.execute(
                select(LearnedWord).where(LearnedWord.account_id == user_id).order_by(LearnedWord.lesson_id, LearnedWord.gap_id)
            )
        )
        .scalars()
        .all()
    )
    active_rows = list(
        (
            await db.execute(
                select(ActiveLessonModel)
                .where(ActiveLessonModel.account_id == user_id)
                .order_by(ActiveLessonModel.lesson_id)
            )
        )
        .scalars()
        .all()
    )
    completed = {row.lesson_id: _result_response(row) for row in result_rows}
    learned: dict[str, list[str]] = {}
    for row in word_rows:
        learned.setdefault(row.lesson_id, []).append(row.gap_id)
    active = {
        row.lesson_id: _active_response(row)
        for row in active_rows
        if row.lesson_id not in completed or _utc(row.client_updated_at) > completed[row.lesson_id].completed_at
    }
    return ProgressResponse(completedLessons=completed, learnedWords=learned, activeLessons=active)


@router.get("", response_model=ProgressResponse, summary="Get my lesson progress")
async def get_progress(current_user: CurrentUserDep, db: AsyncSessionDep) -> ProgressResponse:
    return await _progress(db, int(current_user["id"]))


@router.put("/lessons/{lesson_id}", response_model=CompletedLesson, summary="Save a lesson result")
async def save_lesson_result(
    lesson_id: LessonId,
    payload: CompletedLesson,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> CompletedLesson:
    user_id = int(current_user["id"])
    completed_at = _server_timestamp(payload.completed_at)
    row = await db.scalar(
        select(LessonResult).where(LessonResult.account_id == user_id, LessonResult.lesson_id == lesson_id)
    )
    if row is None:
        row = LessonResult(
            account_id=user_id,
            lesson_id=lesson_id,
            outcome=payload.outcome,
            correct=payload.correct,
            total=payload.total,
            completed_at=completed_at,
        )
        db.add(row)
    elif payload.correct >= row.correct:
        row.outcome = payload.outcome
        row.correct = payload.correct
        row.total = payload.total
        row.completed_at = completed_at
        row.updated_at = datetime.now(UTC)

    # Completion and removal of a resumable snapshot are one database transaction.
    await db.execute(
        delete(ActiveLessonModel).where(
            ActiveLessonModel.account_id == user_id,
            ActiveLessonModel.lesson_id == lesson_id,
        )
    )
    await db.commit()
    return _result_response(row)


@router.post("/words", status_code=status.HTTP_204_NO_CONTENT, summary="Mark learned words")
async def mark_words_learned(
    payload: LearnedWordsPayload,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> Response:
    user_id = int(current_user["id"])
    existing = {
        (lesson_id, gap_id)
        for lesson_id, gap_id in (
            await db.execute(select(LearnedWord.lesson_id, LearnedWord.gap_id).where(LearnedWord.account_id == user_id))
        ).all()
    }
    now = datetime.now(UTC)
    for item in payload.items:
        key = (item.lesson_id, item.gap_id)
        if key not in existing:
            db.add(LearnedWord(account_id=user_id, lesson_id=item.lesson_id, gap_id=item.gap_id, learned_at=now))
            existing.add(key)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/active/{lesson_id}", response_model=ActiveLessonResponse, summary="Save a resumable lesson snapshot")
async def save_active_lesson(
    lesson_id: LessonId,
    payload: ActiveLesson,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> ActiveLessonResponse:
    user_id = int(current_user["id"])
    client_updated_at = _server_timestamp(payload.updated_at)
    completed_at = await db.scalar(
        select(LessonResult.completed_at).where(
            LessonResult.account_id == user_id,
            LessonResult.lesson_id == lesson_id,
        )
    )
    row = await db.scalar(
        select(ActiveLessonModel).where(
            ActiveLessonModel.account_id == user_id,
            ActiveLessonModel.lesson_id == lesson_id,
        )
    )
    if completed_at is not None and client_updated_at <= _utc(completed_at):
        # A delayed browser write must not resurrect a lesson completed elsewhere.
        await db.commit()
        return _active_response(row) if row is not None else _active_response(payload)

    if row is None:
        row = ActiveLessonModel(
            account_id=user_id,
            lesson_id=lesson_id,
            machine=payload.machine,
            client_updated_at=client_updated_at,
        )
        db.add(row)
    elif client_updated_at >= _utc(row.client_updated_at):
        row.machine = payload.machine
        row.client_updated_at = client_updated_at
        row.updated_at = datetime.now(UTC)
    await db.commit()
    return _active_response(row)


@router.delete("/active/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Clear a resumable lesson snapshot")
async def clear_active_lesson(
    lesson_id: LessonId,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> Response:
    await db.execute(
        delete(ActiveLessonModel).where(
            ActiveLessonModel.account_id == int(current_user["id"]),
            ActiveLessonModel.lesson_id == lesson_id,
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/import", response_model=ProgressResponse, summary="Merge local progress into my account")
async def import_progress(
    payload: Progress,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> ProgressResponse:
    user_id = int(current_user["id"])

    for lesson_id, incoming_result in payload.completed_lessons.items():
        completed_at = _server_timestamp(incoming_result.completed_at)
        result_row = await db.scalar(
            select(LessonResult).where(LessonResult.account_id == user_id, LessonResult.lesson_id == lesson_id)
        )
        if result_row is None:
            db.add(
                LessonResult(
                    account_id=user_id,
                    lesson_id=lesson_id,
                    outcome=incoming_result.outcome,
                    correct=incoming_result.correct,
                    total=incoming_result.total,
                    completed_at=completed_at,
                )
            )
        elif incoming_result.correct >= result_row.correct:
            result_row.outcome = incoming_result.outcome
            result_row.correct = incoming_result.correct
            result_row.total = incoming_result.total
            result_row.completed_at = completed_at
            result_row.updated_at = datetime.now(UTC)

    existing_words = {
        (lesson_id, gap_id)
        for lesson_id, gap_id in (
            await db.execute(select(LearnedWord.lesson_id, LearnedWord.gap_id).where(LearnedWord.account_id == user_id))
        ).all()
    }
    now = datetime.now(UTC)
    for lesson_id, gap_ids in payload.learned_words.items():
        for gap_id in gap_ids:
            if (lesson_id, gap_id) not in existing_words:
                db.add(LearnedWord(account_id=user_id, lesson_id=lesson_id, gap_id=gap_id, learned_at=now))
                existing_words.add((lesson_id, gap_id))

    for lesson_id, incoming_active in payload.active_lessons.items():
        client_updated_at = _server_timestamp(incoming_active.updated_at)
        completed_at = await db.scalar(
            select(LessonResult.completed_at).where(
                LessonResult.account_id == user_id,
                LessonResult.lesson_id == lesson_id,
            )
        )
        if completed_at is not None and client_updated_at <= _utc(completed_at):
            continue
        active_row = await db.scalar(
            select(ActiveLessonModel).where(
                ActiveLessonModel.account_id == user_id,
                ActiveLessonModel.lesson_id == lesson_id,
            )
        )
        if active_row is None:
            db.add(
                ActiveLessonModel(
                    account_id=user_id,
                    lesson_id=lesson_id,
                    machine=incoming_active.machine,
                    client_updated_at=client_updated_at,
                )
            )
        elif client_updated_at >= _utc(active_row.client_updated_at):
            active_row.machine = incoming_active.machine
            active_row.client_updated_at = client_updated_at
            active_row.updated_at = datetime.now(UTC)

    await db.commit()
    return await _progress(db, user_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Reset all my lesson progress")
async def reset_progress(current_user: CurrentUserDep, db: AsyncSessionDep) -> Response:
    user_id = int(current_user["id"])
    for model in (ActiveLessonModel, LearnedWord, LessonResult):
        await db.execute(delete(model).where(model.account_id == user_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
