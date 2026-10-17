"""Explicit /drawer preferences commands; never dispatch inspected commands."""

from pathlib import Path

from doggy_drawer import preferences as prefs

USAGE = (
    "/drawer category mode drawer|puppy\n"
    "/drawer category set COMMAND CATEGORY\n"
    "/drawer category reset COMMAND\n"
    "/drawer category list\n"
    "/drawer tabs dashboard commands settings (any order)"
)


def handle(home: Path, arguments: list[str]) -> str:
    path = home / "preferences.json"
    value = prefs.load(path)
    if arguments == ["category", "list"]:
        overrides = "\n".join(
            f"/{name}: {category}" for name, category in sorted(value["overrides"].items())
        )
        return (
            f"Category authority: {value['category_mode']}-first\n"
            f"{overrides or 'No user overrides.'}"
        )
    if len(arguments) == 3 and arguments[:2] == ["category", "mode"]:
        prefs.update(path, category_mode=arguments[2])
        return f"Category authority saved: {arguments[2]}-first"
    if len(arguments) >= 4 and arguments[:2] == ["category", "set"]:
        name = arguments[2].lstrip("/")
        category = prefs.clean_category(" ".join(arguments[3:]))
        overrides = dict(value["overrides"])
        overrides[name] = category
        prefs.update(path, overrides=overrides)
        return f"Saved /{name}: {category}. Policy: {value['category_mode']}-first"
    if len(arguments) == 3 and arguments[:2] == ["category", "reset"]:
        name = arguments[2].lstrip("/")
        overrides = dict(value["overrides"])
        overrides.pop(name, None)
        prefs.update(path, overrides=overrides)
        return f"Removed override for /{name}; native/fallback policy applies."
    if arguments[:1] == ["tabs"] and len(arguments) == 4:
        prefs.update(path, tab_order=arguments[1:])
        return "Saved tab order: " + " > ".join(arguments[1:])
    return USAGE
