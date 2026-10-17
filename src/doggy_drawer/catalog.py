"""Extract literal command metadata without importing or executing Puppy code."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from doggy_drawer.display import abbreviate_home


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    usage: str
    aliases: tuple[str, ...] = ()
    category: str = "core"
    detailed_help: str = ""
    source: str = ""

    def matches(self, query: str) -> bool:
        haystack = " ".join((self.name, self.description, self.category, *self.aliases)).casefold()
        return all(word in haystack for word in query.casefold().split())


@dataclass(frozen=True)
class Catalog:
    commands: tuple[Command, ...]
    roots: tuple[Path, ...]
    diagnostics: tuple[str, ...] = ()


def display_declaration(source: str) -> str:
    """Abbreviate only the current user's home, leaving stored evidence intact."""
    return abbreviate_home(source)


def default_sources() -> list[Path]:
    """Find installed files, never import code_puppy (which can initialize plugins)."""
    bases: list[Path] = []
    try:
        bases.append(Path(metadata.distribution("code-puppy").locate_file("")))
    except metadata.PackageNotFoundError:
        pass
    home = Path.home()
    tool_dirs = [home / ".local/share/uv/tools", home / "AppData/Roaming/uv/tools"]
    if value := os.environ.get("UV_TOOL_DIR"):
        tool_dirs.insert(0, Path(value))
    for tools in tool_dirs:
        tool = tools / "code-puppy"
        bases.append(tool / "Lib/site-packages")
        bases.extend(sorted((tool / "lib").glob("python*/site-packages")))
    for base in bases:
        core = base / "code_puppy/command_line"
        if core.is_dir():
            roots = [core]
            plugins = base / "code_puppy_core_plugins"
            if plugins.is_dir():
                roots.append(plugins)
            return roots
    return []


def _literal(node: ast.AST) -> object:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _command(call: ast.Call, source: str) -> Command | None:
    # Match the real registry's positional signature, excluding hidden aliases.
    fields = (
        "name",
        "description",
        "usage",
        "aliases",
        "hidden_aliases",
        "category",
        "detailed_help",
    )
    values = {key: _literal(value) for key, value in zip(fields, call.args)}
    values.update({kw.arg: _literal(kw.value) for kw in call.keywords if kw.arg})
    name = values.get("name")
    description = values.get("description")
    if not isinstance(name, str) or not name or not isinstance(description, str):
        return None
    aliases = values.get("aliases", ())
    if not isinstance(aliases, (list, tuple)):
        aliases = ()
    return Command(
        name=name.removeprefix("/"),
        description=description,
        usage=value if isinstance(value := values.get("usage"), str) and value else f"/{name}",
        aliases=tuple(alias.removeprefix("/") for alias in aliases if isinstance(alias, str)),
        category=value if isinstance(value := values.get("category"), str) else "core",
        detailed_help=value if isinstance(value := values.get("detailed_help"), str) else "",
        source=source,
    )


def scan_sources(roots: list[Path]) -> Catalog:
    """Best-effort static catalog; decorators are evidence, not a runtime manifest.

    Dynamic registrations, help callbacks, user plugins, and nonliteral fields are
    intentionally not evaluated. Duplicate names retain the first declaration.
    """
    commands: dict[str, Command] = {}
    diagnostics: list[str] = []
    resolved = tuple(dict.fromkeys(root.resolve() for root in roots))
    seen: set[Path] = set()
    for root in resolved:
        if not root.is_dir():
            diagnostics.append(f"Source directory not found: {root}")
            continue
        for path in sorted(root.rglob("*.py")):
            real = path.resolve()
            if not real.is_relative_to(root) or real in seen:
                continue
            seen.add(real)
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            except (OSError, UnicodeError, SyntaxError) as exc:
                diagnostics.append(f"Could not parse {path.name}: {exc}")
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for call in node.decorator_list:
                    if not isinstance(call, ast.Call):
                        continue
                    func = call.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                    if name != "register_command":
                        continue
                    source = f"{path}:{call.lineno}"
                    command = _command(call, source)
                    if command is None:
                        diagnostics.append(f"Skipped dynamic declaration: {source}")
                    elif command.name in commands:
                        diagnostics.append(f"Duplicate /{command.name}; kept first: {source}")
                    else:
                        commands[command.name] = command
    return Catalog(
        tuple(sorted(commands.values(), key=lambda cmd: cmd.name)), resolved, tuple(diagnostics)
    )
