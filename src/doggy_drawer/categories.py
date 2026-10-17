"""Explainable workflow taxonomy; no model calls or command execution."""

from __future__ import annotations

import re
from dataclasses import dataclass

from doggy_drawer.catalog import Command

# Ordered, version-controlled fallback rules. User overrides are never rewritten
# by rule changes. Exact names precede description association to avoid surprises.
RULES = (
    (
        "Models & Providers",
        "model models m add_model pin_model unpin temperature reasoning "
        "effort provider api_key oauth login logout",
    ),
    (
        "Agents & Orchestration",
        "agent agents a switch-agent sa fork herd herdr delegate swarm judges council",
    ),
    (
        "Sessions & Context",
        "session sessions history clear new resume save load autosave checkpoint "
        "context compact truncate load_context undo rewind exit quit",
    ),
    (
        "Tools & Integrations",
        "tools tool mcp skill skills plugins plugin terminal shell browser "
        "attachments clipboard image",
    ),
    (
        "Workspace & Development",
        "cd pwd dir files file diff git commit review test tests code edit project workspace init",
    ),
    (
        "Settings & Appearance",
        "set config settings theme color colors font keymap keys layout mouse sound notifications",
    ),
    (
        "Help & Diagnostics",
        "help h ? status version debug diagnostics doctor usage stats cost tokens commands",
    ),
    ("Drawer", "drawer"),
)
ASSOCIATIONS = (
    ("Models & Providers", r"\b(model|provider|inference|sampling|temperature|api key)\b"),
    ("Agents & Orchestration", r"\b(agent|delegate|orchestrat\w*|swarm)\b"),
    ("Sessions & Context", r"\b(session|conversation|history|context|checkpoint)\b"),
    ("Tools & Integrations", r"\b(tool|mcp|skill|plugin|integration|browser)\b"),
    ("Workspace & Development", r"\b(workspace|directory|git|repository|test|code review)\b"),
    ("Settings & Appearance", r"\b(setting|configuration|theme|color|appearance|keybinding)\b"),
    ("Help & Diagnostics", r"\b(help|diagnostic|status|usage|version|cost)\b"),
)


@dataclass(frozen=True)
class Assignment:
    category: str
    source: str


def fallback(command: Command) -> Assignment:
    names = {command.name.casefold(), *(alias.casefold() for alias in command.aliases)}
    # Namespaces such as skills:foo naturally associate with their root.
    names.update(re.split(r"[: /]", command.name.casefold())[:1])
    for category, words in RULES:
        if names.intersection(words.split()):
            return Assignment(category, "drawer name rule")
    for category, pattern in ASSOCIATIONS:
        if re.search(pattern, command.description, re.IGNORECASE):
            return Assignment(category, "drawer description association")
    return Assignment("Other & New", "drawer fallback (unrecognized command)")


def resolve(command: Command, preferences: dict) -> Assignment:
    native = command.category.strip()
    # Historical static/runtime labels describe provenance, not native metadata.
    if native in {"", "runtime completion", "custom plugin", "unknown"}:
        native = ""
    if preferences["category_mode"] == "puppy" and native:
        return Assignment(native, "Puppy category")
    override = preferences["overrides"].get(command.name)
    if override:
        return Assignment(override, "user override")
    return fallback(command)


def groups(commands: list[Command], preferences: dict) -> dict[str, list[Command]]:
    result: dict[str, list[Command]] = {}
    for command in commands:
        result.setdefault(resolve(command, preferences).category, []).append(command)
    return dict(sorted(result.items(), key=lambda item: item[0].casefold()))
