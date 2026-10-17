"""User-owned, versioned drawer preferences, independent of Puppy releases."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

TABS = ("dashboard", "commands", "settings")
MODES = ("drawer", "puppy")


def preferences_path() -> Path:
    return Path.home() / ".code_puppy" / "doggy-drawer" / "preferences.json"


def defaults() -> dict:
    return {"schema": 1, "category_mode": "drawer", "overrides": {}, "tab_order": list(TABS)}


def validate(value: object) -> dict:
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise ValueError("Unsupported drawer preferences schema")
    if value.get("category_mode") not in MODES:
        raise ValueError("Category mode must be drawer or puppy")
    order = value.get("tab_order")
    if (
        not isinstance(order, list)
        or not all(isinstance(tab, str) for tab in order)
        or len(order) != len(TABS)
        or set(order) != set(TABS)
    ):
        raise ValueError("Tab order must contain dashboard, commands, settings exactly once")
    overrides = value.get("overrides")
    if not isinstance(overrides, dict) or len(overrides) > 10000:
        raise ValueError("Invalid category overrides")
    for name, category in overrides.items():
        if not isinstance(name, str) or not name or len(name) > 512:
            raise ValueError("Invalid override command name")
        clean_category(category)
    return value


def clean_category(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise ValueError("Category must contain 1-80 printable characters")
    if not value.isprintable():
        raise ValueError("Category must be printable")
    return value.strip()


def load(path: Path) -> dict:
    if not path.exists():
        return defaults()
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Drawer preferences exceed size limit")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def update(path: Path, **changes: object) -> dict:
    # Re-read before changing only our fields; unknown future fields survive.
    value = load(path)
    value.update(changes)
    validate(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="preferences-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return value
