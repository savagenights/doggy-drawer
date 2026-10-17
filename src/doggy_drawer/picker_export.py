"""Explicit discovery using an installed Puppy, not a source-code approximation.

This is a separate process, never advertised as the running chat's session.
Run with Puppy's interpreter; importing this module does not load Puppy.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from doggy_drawer.runtime_catalog import picker_rows, publish


def export_picker(path: Path, session: str) -> int:
    # Match normal REPL registration before querying the actual slash completer.
    # Registration/help providers run; command handlers and startup do not.
    import code_puppy.command_line.command_handler  # noqa: F401

    rows = picker_rows()
    if not rows:
        raise ValueError("Puppy slash picker returned no commands; snapshot not replaced")
    publish(path, session, rows, origin="discovery")
    return len({row["name"] for row in rows})


def main() -> None:
    parser = argparse.ArgumentParser(description="Export installed Puppy's slash picker")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    session = f"discovery-{os.getpid()}"
    count = export_picker(args.output, session)
    print(f"Exported {count} unique picker entries; session={session}")
    print("Separate discovery process, not the active chat's live session.")


if __name__ == "__main__":
    main()
