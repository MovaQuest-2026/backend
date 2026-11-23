"""Lesson likes, saved lessons, counters, comments and sharing."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from ...infrastructure.auth.deps import CurrentUserDep, OptionalUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import BadRequestException, NotFoundException
from ..user.models import User
from .models import LessonComment, LessonCommentReport, LessonReaction, LessonShare
from .schemas import (
    CommentCreate,
    CommentReportCreate,
    CommentsResponse,
    LessonCommentResponse,
    LessonStatsResponse,
    ReactionsResponse,
    ShareCreate,
)

router = APIRouter(tags=["Social"])

LessonId = Annotated[str, Path(pattern=r"^[a-z0-9-]{1,64}$", description="Frontend lesson identifier")]
CommentId = Annotated[int, Path(ge=1, description="Comment identifier")]


@router.get("/me/reactions", response_model=ReactionsResponse, summary="Get my lesson reactions")
async def get_my_reactions(current_user: CurrentUserDep, db: AsyncSessionDep) -> ReactionsResponse:
    """Return the authenticated user's likes and saved lessons."""
    rows = (
        await db.execute(
            select(LessonReaction.kind, LessonReaction.lesson_id)
            .where(LessonReaction.user_id == current_user["id"])
            .order_by(LessonReaction.lesson_id)
        )
    ).all()
    return ReactionsResponse(
        liked=[lesson_id for kind, lesson_id in rows if kind == "like"],
        saved=[lesson_id for kind, lesson_id in rows if kind == "save"],
    )


async def _set_reaction(db: AsyncSessionDep, user_id: int, lesson_id: str, kind: str) -> None:
    """Create a reaction once, treating a concurrent duplicate as success."""
    existing = await db.scalar(
        select(LessonReaction.id).where(
            LessonReaction.user_id == user_id,
            LessonReaction.lesson_id == lesson_id,
            LessonReaction.kind == kind,
        )
    )
    if existing is not None:
        return

    db.add(LessonReaction(user_id=user_id, lesson_id=lesson_id, kind=kind))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()


async def _delete_reaction(db: AsyncSessionDep, user_id: int, lesson_id: str, kind: str) -> None:
    await db.execute(
        delete(LessonReaction).where(
            LessonReaction.user_id == user_id,
            LessonReaction.lesson_id == lesson_id,
            LessonReaction.kind == kind,
        )
    )
    await db.commit()


@router.put("/lessons/{lesson_id}/like", status_code=status.HTTP_204_NO_CONTENT, summary="Like a lesson")
async def like_lesson(lesson_id: LessonId, current_user: CurrentUserDep, db: AsyncSessionDep) -> None:
    await _set_reaction(db, current_user["id"], lesson_id, "like")


@router.delete("/lessons/{lesson_id}/like", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a lesson like")
async def unlike_lesson(lesson_id: LessonId, current_user: CurrentUserDep, db: AsyncSessionDep) -> None:
    await _delete_reaction(db, current_user["id"], lesson_id, "like")


@router.put("/lessons/{lesson_id}/save", status_code=status.HTTP_204_NO_CONTENT, summary="Save a lesson")
async def save_lesson(lesson_id: LessonId, current_user: CurrentUserDep, db: AsyncSessionDep) -> None:
    await _set_reaction(db, current_user["id"], lesson_id, "save")


@router.delete("/lessons/{lesson_id}/save", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a saved lesson")
async def unsave_lesson(lesson_id: LessonId, current_user: CurrentUserDep, db: AsyncSessionDep) -> None:
    await _delete_reaction(db, current_user["id"], lesson_id, "save")


@router.get("/lessons/{lesson_id}/stats", response_model=LessonStatsResponse, summary="Get lesson counters")
async def get_lesson_stats(lesson_id: LessonId, db: AsyncSessionDep) -> LessonStatsResponse:
    """Return counters built from stored social events; no lesson catalog is required."""
    likes = await _count_reactions(db, lesson_id, "like")
    saves = await _count_reactions(db, lesson_id, "save")
    comments = await db.scalar(
        select(func.count(LessonComment.id)).where(LessonComment.lesson_id == lesson_id, LessonComment.is_hidden.is_(False))
    )
    shares = await db.scalar(select(func.count(LessonShare.id)).where(LessonShare.lesson_id == lesson_id))
    return LessonStatsResponse(likes=likes, comments=int(comments or 0), saves=saves, shares=int(shares or 0))


async def _count_reactions(db: AsyncSessionDep, lesson_id: str, kind: str) -> int:
    count = await db.scalar(
        select(func.count(LessonReaction.id)).where(
            LessonReaction.lesson_id == lesson_id,
            LessonReaction.kind == kind,
        )
    )
    return int(count or 0)


@router.get("/lessons/{lesson_id}/comments", response_model=CommentsResponse, summary="List lesson comments")
async def get_lesson_comments(
    lesson_id: LessonId,
    db: AsyncSessionDep,
    current_user: OptionalUserDep,
    cursor: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CommentsResponse:
    """Return newest comments first, using the last comment id as an opaque cursor."""
    cursor_id = _parse_cursor(cursor)
    statement = (
        select(LessonComment,)
        .where(LessonComment.lesson_id == lesson_id, LessonComment.is_hidden.is_(False))
        .order_by(LessonComment.id.desc())
        .limit(limit + 1)
    )
    if cursor_id is not None:
        statement = statement.where(LessonComment.id < cursor_id)

    comments = list((await db.execute(statement)).scalars().all())
    has_more = len(comments) > limit
    comments = comments[:limit]
    user_names = await _user_names(db, {comment.user_id for comment in comments})
    items = [
        _comment_response(comment, user_names.get(comment.user_id, "User"), current_user)
        for comment in comments
    ]
    return CommentsResponse.model_validate(
        {"items": items, "nextCursor": str(comments[-1].id) if has_more and comments else None}
    )


@router.post("/lessons/{lesson_id}/comments", response_model=LessonCommentResponse, status_code=201, summary="Add a comment")
async def add_lesson_comment(
    lesson_id: LessonId,
    payload: CommentCreate,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> LessonCommentResponse:
    comment = LessonComment(user_id=current_user["id"], lesson_id=lesson_id, text=payload.text)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return _comment_response(comment, current_user.get("name") or current_user["username"], current_user)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete my comment")
async def delete_comment(comment_id: CommentId, current_user: CurrentUserDep, db: AsyncSessionDep) -> None:
    comment = await db.get(LessonComment, comment_id)
    if comment is None or comment.user_id != current_user["id"]:
        raise NotFoundException(detail="Comment not found")
    await db.delete(comment)
    await db.commit()


@router.post("/comments/{comment_id}/report", status_code=status.HTTP_204_NO_CONTENT, summary="Report a comment")
async def report_comment(
    comment_id: CommentId,
    payload: CommentReportCreate,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> Response:
    """Record one report per account and hide a comment once three accounts report it."""
    comment = await db.get(LessonComment, comment_id)
    if comment is None:
        raise NotFoundException(detail="Comment not found")
    db.add(
        LessonCommentReport(
            comment_id=comment_id,
            user_id=current_user["id"],
            reason=payload.reason,
            details=payload.details,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        # A duplicate report is idempotent and cannot increase the moderation count.
        await db.rollback()

    reports = await db.scalar(
        select(func.count(LessonCommentReport.id)).where(LessonCommentReport.comment_id == comment_id)
    )
    if int(reports or 0) >= 3:
        await db.execute(
            update(LessonComment)
            .where(LessonComment.id == comment_id, LessonComment.is_hidden.is_(False))
            .values(is_hidden=True)
        )
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lessons/{lesson_id}/share", status_code=status.HTTP_204_NO_CONTENT, summary="Record a lesson share")
async def record_lesson_share(
    lesson_id: LessonId,
    payload: ShareCreate,
    db: AsyncSessionDep,
    current_user: OptionalUserDep,
) -> Response:
    user_id = current_user["id"] if current_user is not None else None
    db.add(LessonShare(user_id=user_id, lesson_id=lesson_id, method=payload.method))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _parse_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    try:
        value = int(cursor)
    except ValueError as error:
        raise BadRequestException(detail="Invalid comments cursor") from error
    if value < 1:
        raise BadRequestException(detail="Invalid comments cursor")
    return value


async def _user_names(db: AsyncSessionDep, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}

    rows = (await db.execute(select(User.id, User.name, User.username).where(User.id.in_(user_ids)))).all()
    return {user_id: name or username for user_id, name, username in rows}


def _comment_response(comment: LessonComment, author: str, current_user: dict | None) -> LessonCommentResponse:
    return LessonCommentResponse.model_validate(
        {
            "id": str(comment.id),
            "author": author,
            "text": comment.text,
            "createdAt": comment.created_at,
            "own": current_user is not None and comment.user_id == current_user["id"],
        }
    )
