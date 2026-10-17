"""Puppy lifecycle integration. Importing registers nothing and installs nothing."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import uuid
from pathlib import Path

from doggy_drawer.herdr_setup import ensure_herdr, in_herdr, run
from doggy_drawer.preference_commands import USAGE, handle
from doggy_drawer.runtime_catalog import picker_rows, publish

log = logging.getLogger(__name__)


def plugin_home() -> Path:
    # Puppy user plugins are rooted here, independently of working directory.
    return Path.home() / ".code_puppy" / "doggy-drawer"


def load_config(home: Path) -> dict:
    path = home / "config.json"
    if not path.exists():
        return {"enabled": False}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("enabled"), bool):
        raise ValueError("Invalid doggy-drawer configuration; activation refused")
    return value


def save_config(home: Path, value: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    temporary = home / "config.tmp"
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(home / "config.json")


class PuppyDrawer:
    def __init__(self, home: Path | None = None) -> None:
        self.home = home or plugin_home()
        self.session = f"{os.getpid()}-{uuid.uuid4().hex}"
        self.snapshot = self.home / "sessions" / self.session / "catalog.json"
        self.pane_id: str | None = None
        self.herdr: str | None = None
        self.rows: list[dict[str, str]] = []
        self.error = ""
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def export(self, *_args, **_kwargs) -> None:
        # Main lifecycle thread only: help providers can access Puppy state.
        try:
            with self.lock:
                self.rows = picker_rows()
                self.error = ""
                publish(self.snapshot, self.session, self.rows)
        except Exception as error:
            log.exception("doggy-drawer catalog refresh failed")
            with self.lock:
                self.error = str(error)
                publish(self.snapshot, self.session, self.rows, self.error)

    def heartbeat(self) -> None:
        # Never run plugin help providers from this background thread.
        while not self.stop.wait(20):
            try:
                if not load_config(self.home)["enabled"]:
                    continue
                with self.lock:
                    publish(self.snapshot, self.session, self.rows, self.error)
            except (OSError, ValueError):
                log.exception("doggy-drawer heartbeat failed")

    def open(self, *, allow_download: bool = False) -> str:
        self.herdr = ensure_herdr(self.home, allow_download=allow_download)
        if not in_herdr():
            return (
                f"herdr ready: {self.herdr}\n"
                "Activation saved. Launch herdr, then start Puppy in it. "
                "The drawer opens on that Puppy's next startup; this session is not migrated."
            )
        if self.pane_id:
            panes = json.loads(run([self.herdr, "pane", "list"]))["result"]["panes"]
            if any(pane["pane_id"] == self.pane_id for pane in panes):
                return f"Drawer already open: {self.pane_id}"
            self.pane_id = None
        config = load_config(self.home)
        python = str(config.get("ui_python") or sys.executable)
        manifest_dir = self.snapshot.parent
        manifest_dir.mkdir(parents=True, exist_ok=True)
        command = [
            python,
            "-m",
            "doggy_drawer",
            "--snapshot",
            str(self.snapshot),
            "--session",
            self.session,
        ]
        # JSON quoted strings/arrays are valid TOML basic strings/arrays.
        manifest = (
            'id = "doggy-drawer"\nname = "doggy-drawer"\nversion = "0.1.0"\n'
            'min_herdr_version = "0.9.5"\n'
            'description = "Live read-only Code Puppy command inspector"\n'
            'platforms = ["windows", "linux", "macos"]\n\n'
            '[[panes]]\nid = "inspector"\ntitle = "doggy-drawer (read only)"\n'
            'placement = "split"\ncommand = ' + json.dumps(command) + "\n"
        )
        (manifest_dir / "herdr-plugin.toml").write_text(manifest, encoding="utf-8")
        run([self.herdr, "plugin", "link", str(manifest_dir)])
        response = json.loads(
            run(
                [
                    self.herdr,
                    "plugin",
                    "pane",
                    "open",
                    "--plugin",
                    "doggy-drawer",
                    "--entrypoint",
                    "inspector",
                    "--placement",
                    "split",
                    "--direction",
                    "right",
                    "--target-pane",
                    os.environ["HERDR_PANE_ID"],
                    "--no-focus",
                ]
            )
        )
        self.pane_id = response["result"]["plugin_pane"]["pane"]["pane_id"]
        return f"Drawer opened: {self.pane_id}; {len(self.rows)} slash-picker entries"

    def startup(self, *_args, **_kwargs) -> None:
        try:
            if not load_config(self.home)["enabled"]:
                return
            self.export()
            self.thread = threading.Thread(target=self.heartbeat, daemon=True)
            self.thread.start()
            self.message(self.open())
        except Exception as error:
            self.message(f"Drawer startup failed: {error}. Run /drawer enable to retry.")

    def awaiting(self, awaiting: bool, *_args, **_kwargs) -> None:
        try:
            if awaiting and load_config(self.home)["enabled"]:
                self.export()
        except (OSError, ValueError):
            log.exception("doggy-drawer configuration could not be read")

    def shutdown(self, *_args, **_kwargs) -> None:
        self.stop.set()
        if self.snapshot.exists():
            publish(self.snapshot, self.session, self.rows, "Puppy session ended")

    @staticmethod
    def message(text: str) -> None:
        from code_puppy.messaging import emit_info

        from doggy_drawer.display import abbreviate_home

        emit_info(abbreviate_home(text))

    def command(self, command: str, name: str):
        if name != "drawer":
            return None
        action = command.strip().split()[1:]
        try:
            config = load_config(self.home)
            if action[:1] in (["category"], ["tabs"]):
                self.message(handle(self.home, action))
            elif action == ["enable"]:
                # Download authorization is the explicit enable action, not import/startup.
                self.herdr = ensure_herdr(self.home, allow_download=True)
                config["enabled"] = True
                save_config(self.home, config)
                self.export()
                if self.thread is None:
                    self.thread = threading.Thread(target=self.heartbeat, daemon=True)
                    self.thread.start()
                self.message(self.open())
            elif action == ["disable"]:
                config["enabled"] = False
                save_config(self.home, config)
                if self.pane_id and self.herdr:
                    run([self.herdr, "plugin", "pane", "close", self.pane_id])
                    self.pane_id = None
                self.message(
                    "Drawer disabled; startup activation is off. Installed files retained."
                )
            elif action == ["refresh"]:
                self.export()
                self.message(f"Published {len(self.rows)} slash-picker entries")
            elif action in ([], ["status"]):
                self.message(
                    f"Drawer enabled: {config['enabled']} | session: {self.session}\n"
                    f"Snapshot: {self.snapshot}\n"
                    "Usage: /drawer enable | disable | refresh | status\n" + USAGE
                )
            else:
                self.message("Usage: /drawer enable | disable | refresh | status\n" + USAGE)
        except Exception as error:
            self.message(f"Drawer error: {error}")
        return True


def register() -> PuppyDrawer:
    from code_puppy.callbacks import register_callback

    plugin = PuppyDrawer()
    register_callback(
        "custom_command_help",
        lambda: [("drawer", "Drawer activation, category policy/overrides, tab order, and status")],
    )
    register_callback("custom_command", plugin.command)
    register_callback("startup", plugin.startup)
    register_callback("awaiting_user_input", plugin.awaiting)
    register_callback("shutdown", plugin.shutdown)
    return plugin
