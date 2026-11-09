"""Digest validation: JSON Schema + deterministic semantic checks.

`validate_digest` returns a list of human-readable error strings (empty = valid).
The pipeline refuses to publish if this list is non-empty.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from . import config


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((config.SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def parse_iso(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None
    if dt.tzinfo is None:
        return None
    return dt


def all_items(digest: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for items in digest.get("sections", {}).values():
        yield from items


def schema_errors(doc: Any, schema_file: str) -> list[str]:
    errs = []
    for e in sorted(_validator(schema_file).iter_errors(doc), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errs.append(f"schema: {path}: {e.message[:200]}")
    return errs


def validate_digest(digest: dict[str, Any], now: datetime | None = None) -> list[str]:
    errors = schema_errors(digest, "digest.v1.schema.json")
    if errors:
        return errors  # semantic checks assume the shape is right

    now = now or datetime.now(timezone.utc)
    gen = parse_iso(digest["generatedAt"])
    if gen is None:
        errors.append("generatedAt is not a timezone-aware ISO-8601 timestamp")

    seen_ids: set[str] = set()
    ids_in_digest: set[str] = set()
    for item in all_items(digest):
        ids_in_digest.add(item["id"])
    for section, items in digest["sections"].items():
        for item in items:
            key = (section, item["id"])
            if key in seen_ids:
                errors.append(f"{section}: duplicate item id {item['id']}")
            seen_ids.add(key)
            ts = parse_iso(item["publishedAt"])
            if ts is None:
                errors.append(f"{section}/{item['id']}: bad publishedAt {item['publishedAt']!r}")
            elif ts > now + timedelta(hours=config.FUTURE_SKEW_HOURS):
                errors.append(f"{section}/{item['id']}: publishedAt is in the future")

    for key in ("promptOfTheDay", "tryThisToday"):
        based = digest[key]["basedOn"]
        if based["itemId"] not in ids_in_digest:
            errors.append(f"{key}.basedOn.itemId {based['itemId']} is not an item in this digest")

    words = len(digest["promptOfTheDay"]["prompt"].split())
    if words > config.PROMPT_MAX_WORDS:
        errors.append(f"promptOfTheDay.prompt has {words} words (max {config.PROMPT_MAX_WORDS})")

    if len(digest["sections"]["topStories"]) < config.MIN_TOP_STORIES:
        errors.append(f"topStories has fewer than {config.MIN_TOP_STORIES} items")

    return errors


def validate_index(index: dict[str, Any]) -> list[str]:
    return schema_errors(index, "index.v1.schema.json")


def validate_health(health: dict[str, Any]) -> list[str]:
    return schema_errors(health, "health.v1.schema.json")
