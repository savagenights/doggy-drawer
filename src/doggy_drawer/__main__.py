"""CLI entrypoint: live snapshot UI, static fallback, or Puppy plugin installation."""

import argparse
from pathlib import Path

from doggy_drawer.catalog import default_sources, scan_sources
from doggy_drawer.display import abbreviate_home


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Puppy command inspector")
    parser.add_argument("action", nargs="?", choices=["install-plugin"])
    parser.add_argument("--snapshot", type=Path, help="Read a running Puppy's exported catalog")
    parser.add_argument("--session", help="Require the snapshot to match this Puppy session")
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        help="Directory of Python command declarations (repeatable)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report catalog coverage without starting the terminal UI",
    )
    args = parser.parse_args()
    if args.action == "install-plugin":
        from doggy_drawer.installation import install_plugin

        print(abbreviate_home(f"Installed Puppy plugin: {install_plugin()}"))
        print("Restart Puppy, then run /drawer enable. No Puppy environment changes made.")
        return
    if args.snapshot:
        from doggy_drawer.catalog import Catalog
        from doggy_drawer.runtime_catalog import read_snapshot

        try:
            catalog = read_snapshot(args.snapshot, args.session)
        except (OSError, ValueError, TypeError) as error:
            catalog = Catalog((), (args.snapshot,), (str(error),))
    else:
        catalog = scan_sources(args.source if args.source is not None else default_sources())
    if args.check:
        kind = "Puppy slash-picker snapshot" if args.snapshot else "Partial static catalog"
        print(f"{kind}: {len(catalog.commands)} commands")
        for root in catalog.roots:
            print(abbreviate_home(f"Source: {root}"))
        for note in catalog.diagnostics:
            print(abbreviate_home(f"Notice: {note}"))
        if not catalog.commands:
            parser.exit(1, "No commands found. Supply --source PATH.\n")
        return
    from doggy_drawer.app import Drawer

    Drawer(catalog, snapshot=args.snapshot, session=args.session).run()


if __name__ == "__main__":
    main()
