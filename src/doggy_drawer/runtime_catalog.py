"""Versioned, read-only snapshots of the running Puppy's actual slash picker."""

from __future__ import annotations

import json
import os
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace

from doggy_drawer.catalog import Catalog, Command

SCHEMA = 1
MAX_BYTES = 4 * 1024 * 1024


def plain(value: str) -> str:
    """Remove controls and pictographs from metadata, not command source files."""
    return "".join(
        char
        for char in value
        if (char in "\n\t" or unicodedata.category(char) not in {"Cc", "Cf", "So", "Sk"})
        and not "\ufe00" <= char <= "\ufe0f"
    )


def picker_rows() -> list[dict[str, str]]:
    """Use exactly the completion entrypoint the interactive slash picker uses.

    Runs inside Puppy, after plugin loading. This runs help providers, as normal
    completion does; it never calls command handlers. Do not call from the UI.
    """
    from code_puppy.command_line.completers import SlashCompleter

    # Both prompt_toolkit and newer termflow completers use this duck-typed
    # protocol. Do not couple the plugin to either editor dependency.
    document = SimpleNamespace(text="/", text_before_cursor="/", cursor_position=1)
    event = SimpleNamespace(completion_requested=True, text_inserted=False)
    # Completion discovery may register plugin commands; collect native metadata
    # afterward so those commands receive their registry categories too.
    completions = list(SlashCompleter().get_completions(document, event))
    native = {}
    try:
        from code_puppy.command_line.command_registry import get_unique_commands

        for info in get_unique_commands():
            category = getattr(info, "category", "")
            if not isinstance(category, str):
                continue
            for name in [
                info.name,
                *getattr(info, "aliases", []),
                *getattr(info, "hidden_aliases", []),
            ]:
                native[name] = plain(category)
    except ImportError:
        pass  # Future/mocked Puppy without a registry: picker remains authoritative.

    return [
        {
            "name": completion.text.lstrip("/"),
            "description": plain(
                getattr(completion, "display_meta_text", None)
                or getattr(completion, "display_meta", None)
                or ""
            ),
            "display": plain(
                getattr(completion, "display_text", None)
                or getattr(completion, "display", None)
                or completion.text
            ),
            "category": native.get(completion.text.lstrip("/"), ""),
        }
        for completion in completions
    ]


def publish(
    path: Path,
    session: str,
    rows: list[dict[str, str]],
    error: str = "",
    *,
    origin: str = "live",
) -> None:
    payload = {
        "schema": SCHEMA,
        "origin": origin,
        "session": session,
        "pid": os.getpid(),
        "updated_at": time.time(),
        "provider": "code_puppy.command_line.completers.SlashCompleter",
        "error": plain(error),
        "commands": rows,
    }
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("Runtime catalog exceeds size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_snapshot(path: Path, session: str | None = None) -> Catalog:
    with path.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Runtime catalog exceeds size limit")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("Unsupported runtime catalog schema")
    identity = payload.get("session")
    if not isinstance(identity, str) or not identity or (session and identity != session):
        raise ValueError("Runtime catalog session mismatch")
    rows = payload.get("commands")
    if not isinstance(rows, list):
        raise ValueError("Invalid runtime commands")
    commands: dict[str, Command] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid runtime command row")
        name, description = row.get("name"), row.get("description")
        if not isinstance(name, str) or not name or not isinstance(description, str):
            raise ValueError("Invalid runtime command metadata")
        name = plain(name)
        if not name or len(name) > 512:
            raise ValueError("Invalid runtime command name")
        category = row.get("category", "")
        if not isinstance(category, str):
            raise ValueError("Invalid runtime command category")
        commands.setdefault(
            name,
            Command(
                name,
                plain(description),
                "/" + name,
                category=plain(category),
                detailed_help=(
                    "Advertised by this Puppy's slash picker. Argument syntax and "
                    "extended help are not exposed by the completion interface."
                ),
                source=f"SlashCompleter | session {identity} | {path}",
            ),
        )
    updated = payload.get("updated_at")
    if not isinstance(updated, (float, int)):
        raise ValueError("Invalid snapshot timestamp")
    origin = payload.get("origin", "live")
    if not isinstance(origin, str) or origin not in {"live", "discovery"}:
        raise ValueError("Invalid snapshot origin")
    notices = []
    if origin == "discovery":
        notices.append("Installed Puppy picker: one-time discovery, not this chat's live session.")
    if error := payload.get("error"):
        notices.append(f"Puppy catalog refresh failed: {plain(str(error))}")
    if origin == "live" and time.time() - updated > 90:
        notices.append("Snapshot is stale; Puppy may be busy, closed, or disconnected.")
    return Catalog(
        tuple(sorted(commands.values(), key=lambda cmd: cmd.name.casefold())),
        (path,),
        tuple(notices),
    )
