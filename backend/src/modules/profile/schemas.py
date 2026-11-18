"""Validation and transport schemas for onboarding profiles."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..common.schemas import EncodableText

InterfaceLanguage = Literal["en", "uk", "es"]
Level = Literal["A1", "A2", "B1", "B2"]


class ProfileFields(EncodableText):
    """The fields selected during onboarding."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    interface_language: InterfaceLanguage = Field(alias="interfaceLanguage")
    level: Level
    goal: str = Field(default="", max_length=200)

    @field_validator("goal", mode="before")
    @classmethod
    def trim_goal(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ProfilePatch(EncodableText):
    """A partial onboarding profile update; explicit null is not a valid value."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    interface_language: InterfaceLanguage | None = Field(default=None, alias="interfaceLanguage")
    level: Level | None = None
    goal: str | None = Field(default=None, max_length=200)

    @field_validator("goal", mode="before")
    @classmethod
    def trim_goal(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: object) -> object:
        nullable_fields = ("interfaceLanguage", "interface_language", "level", "goal")
        if isinstance(value, dict) and any(field in value and value[field] is None for field in nullable_fields):
            raise ValueError("Profile fields cannot be null")
        return value


class ProfileResponse(BaseModel):
    """The frontend-facing onboarding profile."""

    model_config = ConfigDict(populate_by_name=True)

    account_id: str = Field(alias="accountId")
    interface_language: InterfaceLanguage = Field(alias="interfaceLanguage")
    level: Level
    goal: str
    onboarded_at: datetime = Field(alias="onboardedAt")
    updated_at: datetime = Field(alias="updatedAt")
