"""Display-only home abbreviation; never rewrite paths used for IO or metadata."""

import os
import re
from pathlib import Path

from rich.text import Text


def _home_pattern() -> re.Pattern[str]:
    home = str(Path.home()).rstrip("/\\")
    # Diagnostics may contain repr-escaped backslashes as well as normal paths.
    parts = re.split(r"[/\\]", home)
    prefix = r"(?:/|\\{1,2})".join(re.escape(part) for part in parts)
    return re.compile(
        r"(?<![\w./\\-])" + prefix + r"(?=$|[/\\\s'\":,;)])",
        re.IGNORECASE if os.name == "nt" else 0,
    )


def abbreviate_home(value: str) -> str:
    """Replace home prefixes anywhere in prose, without matching neighbor names."""
    return _home_pattern().sub("%USERPROFILE%", value)


def display_text(value: str | Text = "") -> Text:
    """Abbreviate rendered text while preserving existing Rich styles/spans."""
    text = value.copy() if isinstance(value, Text) else Text(value)
    for match in reversed(list(_home_pattern().finditer(text.plain))):
        replacement = Text("%USERPROFILE%", style=text.style)
        text = text[: match.start()] + replacement + text[match.end() :]
    return text
