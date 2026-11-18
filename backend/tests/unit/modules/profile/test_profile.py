"""Tests for onboarding profile validation and persistence."""


import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.infrastructure.database.registry import import_models
from src.infrastructure.database.session import Base, DatabaseSession
from src.infrastructure.http_exceptions import HTTPException
from src.modules.profile.routes import get_profile, save_profile, update_profile
from src.modules.profile.schemas import ProfileFields, ProfilePatch


@pytest.fixture
def profile_db():
    import_models()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = DatabaseSession(Session(engine))
    yield session
    session._session.close()
    engine.dispose()


def test_profile_fields_trim_goal_and_reject_invalid_values():
    profile = ProfileFields(interfaceLanguage="uk", level="B1", goal="  travel  ")
    assert profile.goal == "travel"

    with pytest.raises(ValidationError):
        ProfileFields(interfaceLanguage="de", level="B1", goal="travel")

    with pytest.raises(ValidationError):
        ProfileFields(interfaceLanguage="uk", level="C1", goal="travel")


def test_profile_patch_rejects_explicit_null():
    with pytest.raises(ValidationError):
        ProfilePatch(goal=None)


async def test_profile_lifecycle_and_missing_profile(profile_db: DatabaseSession):
    with pytest.raises(HTTPException) as missing:
        await get_profile({"id": 1}, profile_db)
    assert missing.value.status_code == 404

    saved = await save_profile(
        ProfileFields(interfaceLanguage="uk", level="A1", goal="  travel  "),
        {"id": 1},
        profile_db,
    )
    assert saved.account_id == "1"
    assert saved.goal == "travel"
    assert saved.interface_language == "uk"

    updated = await update_profile(ProfilePatch(level="B1"), {"id": 1}, profile_db)
    assert updated.level == "B1"
    assert updated.goal == "travel"

    loaded = await get_profile({"id": 1}, profile_db)
    assert loaded.updated_at >= saved.updated_at
