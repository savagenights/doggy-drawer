"""Install a self-contained Puppy user plugin without changing Puppy's venv."""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

from doggy_drawer.puppy_plugin import load_config, plugin_home, save_config


def install_plugin(root: Path | None = None, ui_python: str | None = None) -> Path:
    puppy = root or Path.home() / ".code_puppy"
    plugins = puppy / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    destination = plugins / "doggy_drawer"
    source = Path(__file__).parent
    if source.resolve() == destination.resolve():
        raise RuntimeError("Run install-plugin from the standalone app environment")
    staging = plugins / (".doggy-drawer-stage-" + uuid.uuid4().hex)
    backup = plugins / (".doggy-drawer-backup-" + uuid.uuid4().hex)
    shutil.copytree(source, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    replaced = destination.exists()
    try:
        if replaced:
            destination.rename(backup)
        staging.rename(destination)
    except OSError:
        if replaced and backup.exists() and not destination.exists():
            backup.rename(destination)
        raise
    home = puppy / "doggy-drawer" if root else plugin_home()
    config = load_config(home)
    config["ui_python"] = ui_python or sys.executable
    save_config(home, config)
    return destination
