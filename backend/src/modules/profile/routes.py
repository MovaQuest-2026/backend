"""Onboarding profile endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select

from ...infrastructure.auth.deps import CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.http_exceptions import HTTPException
from .models import Profile
from .schemas import ProfileFields, ProfilePatch, ProfileResponse

router = APIRouter(prefix="/me/profile", tags=["Profile"])


def _utc(value: datetime) -> datetime:
    """Normalize values returned by either timestamp or timestamptz columns."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _response(row: Profile) -> ProfileResponse:
    return ProfileResponse.model_validate(
        {
            "accountId": str(row.account_id),
            "interfaceLanguage": row.interface_lang,
            "level": row.level,
            "goal": row.goal,
            "onboardedAt": _utc(row.onboarded_at),
            "updatedAt": _utc(row.updated_at),
        }
    )


def _not_found() -> HTTPException:
    # A missing onboarding profile is an expected client state, not a server error.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.get("", response_model=ProfileResponse, responses={404: {"description": "Onboarding is not complete"}})
async def get_profile(current_user: CurrentUserDep, db: AsyncSessionDep) -> ProfileResponse:
    row = await db.scalar(select(Profile).where(Profile.account_id == int(current_user["id"])))
    if row is None:
        raise _not_found()
    return _response(row)


@router.put("", response_model=ProfileResponse, summary="Create or replace my onboarding profile")
async def save_profile(
    payload: ProfileFields,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> ProfileResponse:
    now = datetime.now(UTC)
    row = await db.scalar(select(Profile).where(Profile.account_id == int(current_user["id"])))
    if row is None:
        row = Profile(
            account_id=int(current_user["id"]),
            interface_lang=payload.interface_language,
            level=payload.level,
            goal=payload.goal,
            onboarded_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.interface_lang = payload.interface_language
        row.level = payload.level
        row.goal = payload.goal
        row.updated_at = now
    await db.commit()
    return _response(row)


@router.patch("", response_model=ProfileResponse, responses={404: {"description": "Onboarding is not complete"}})
async def update_profile(
    payload: ProfilePatch,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
) -> ProfileResponse:
    row = await db.scalar(select(Profile).where(Profile.account_id == int(current_user["id"])))
    if row is None:
        raise _not_found()

    changes = payload.model_dump(exclude_unset=True, by_alias=False)
    if "interface_language" in changes:
        row.interface_lang = changes["interface_language"]
    if "level" in changes:
        row.level = changes["level"]
    if "goal" in changes:
        row.goal = changes["goal"]
    row.updated_at = datetime.now(UTC)
    await db.commit()
    return _response(row)
