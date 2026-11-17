"""Validation tests for the frontend-owned social contract."""

import pytest
from pydantic import ValidationError

from src.infrastructure.http_exceptions import BadRequestException
from src.modules.social.routes import _parse_cursor
from src.modules.social.schemas import COMMENT_MAX_LENGTH, CommentCreate


def test_comment_text_is_trimmed_before_length_validation():
    assert CommentCreate(text="  buen viaje  ").text == "buen viaje"


def test_comment_text_rejects_blank_and_oversized_values():
    with pytest.raises(ValidationError):
        CommentCreate(text="   ")

    with pytest.raises(ValidationError):
        CommentCreate(text="x" * (COMMENT_MAX_LENGTH + 1))


def test_comment_text_rejects_nul_characters():
    with pytest.raises(ValueError):
        CommentCreate(text="hello\x00world")


def test_comment_cursor_is_numeric_and_positive():
    assert _parse_cursor(None) is None
    assert _parse_cursor("42") == 42

    with pytest.raises(BadRequestException):
        _parse_cursor("not-a-cursor")

    with pytest.raises(BadRequestException):
        _parse_cursor("0")
