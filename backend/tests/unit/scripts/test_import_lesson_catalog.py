"""Tests for importing the frontend lesson catalog."""

from datetime import date

import pytest

from scripts.import_lesson_catalog import _entry


def _item() -> dict:
    return {
        "id": "hola-lucia",
        "title": {"es": "Conoce a Lucía", "en": "Meet Lucía", "uk": "Знайомтеся, Лусія"},
        "description": {"es": "Una escena", "en": "A scene", "uk": "Сцена"},
        "level": "A1",
        "durationSec": 21,
        "cover": "/clips/hola-lucia/cover.jpg",
        "addedAt": "2026-11-15",
        "pinned": True,
        "comingSoon": False,
    }


def test_catalog_entry_maps_camel_case_fields_to_the_lesson_model():
    entry = _entry(_item())

    assert entry["slug"] == "hola-lucia"
    assert entry["duration_seconds"] == 21
    assert entry["added_at"] == date(2026, 11, 15)
    assert entry["title_uk"] == "Знайомтеся, Лусія"
    assert entry["coming_soon"] is False


@pytest.mark.parametrize("field", ["title", "description"])
def test_catalog_entry_requires_localized_objects(field: str):
    item = _item()
    item[field] = "not-an-object"

    with pytest.raises(ValueError, match=field):
        _entry(item)
