"""Idempotently import the frontend ``index.json`` lesson catalog."""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.modules.content.models import Lesson  # noqa: E402

SUPPORTED_LANGUAGES = ("es", "en", "uk")


def _text_map(value: Any, field: str, slug: str) -> dict[str, str]:
    """Validate one localized index.json object and keep the supported languages."""
    if not isinstance(value, dict):
        raise ValueError(f"{slug}: {field} must be an object")
    return {language: str(value.get(language, "")) for language in SUPPORTED_LANGUAGES}


def _entry(item: Any) -> dict[str, Any]:
    """Normalize one frontend catalog item for the relational lesson model."""
    if not isinstance(item, dict):
        raise ValueError("Every catalog entry must be an object")
    slug = item.get("id")
    if not isinstance(slug, str) or not slug or len(slug) > 128:
        raise ValueError("Every catalog entry needs a non-empty id up to 128 characters")

    title = _text_map(item.get("title"), "title", slug)
    description = _text_map(item.get("description"), "description", slug)
    duration = item.get("durationSec")
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int) or duration < 0):
        raise ValueError(f"{slug}: durationSec must be a non-negative integer")

    added_at = item.get("addedAt")
    if added_at is not None:
        try:
            added_at = date.fromisoformat(added_at)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{slug}: addedAt must use YYYY-MM-DD") from error

    cover = item.get("cover")
    if cover is not None and not isinstance(cover, str):
        raise ValueError(f"{slug}: cover must be a string")

    return {
        "slug": slug,
        "title_es": title["es"],
        "title_en": title["en"],
        "title_uk": title["uk"],
        "description_es": description["es"],
        "description_en": description["en"],
        "description_uk": description["uk"],
        "level": str(item.get("level", "A1")),
        "duration_seconds": duration,
        "cover_path": cover,
        "added_at": added_at,
        "pinned": bool(item.get("pinned", False)),
        "coming_soon": bool(item.get("comingSoon", False)),
    }


async def import_catalog(path: Path) -> tuple[int, int]:
    """Upsert catalog entries without deleting rows absent from the source file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Catalog root must be a JSON array")
    entries = [_entry(item) for item in raw]
    if len({entry["slug"] for entry in entries}) != len(entries):
        raise ValueError("Catalog contains duplicate ids")

    import_models()
    created = 0
    updated = 0
    async with local_session() as db:
        for values in entries:
            lesson = await db.get(Lesson, values["slug"])
            if lesson is None:
                db.add(Lesson(**values))
                created += 1
                continue
            for field, value in values.items():
                setattr(lesson, field, value)
            updated += 1
        await db.commit()
    return created, updated


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="Path to the frontend index.json")
    args = parser.parse_args()
    try:
        created, updated = await import_catalog(args.catalog)
    finally:
        await close_database()
    print(f"Imported lessons: {created} created, {updated} updated")


if __name__ == "__main__":
    asyncio.run(main())
