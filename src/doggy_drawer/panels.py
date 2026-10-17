"""Non-command drawer tabs. These never import Puppy or dispatch commands."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, Select, Static

LABELS = {"dashboard": "Dashboard", "commands": "/CMD", "settings": "Settings"}


class Dashboard(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static("Command workspace", classes="heading", markup=False)
        yield Static(id="dashboard-summary", markup=False)
        yield Static(
            "Browse /CMD to inspect commands, not run them.\n\n"
            "[+] opens a category and closes the others. [-] closes it.\n"
            "[All] expands every category; Collapse closes them all.\n"
            "Search includes names, aliases, descriptions and categories.\n\n"
            "Ctrl+F: command search | F2: details | Escape: command list\n\n"
            "Settings stores your category policy and tab order outside Puppy.\n"
            "New commands receive a fallback category automatically.",
            markup=False,
        )


class Settings(VerticalScroll):
    def __init__(self, preferences: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.preferences = preferences

    def compose(self) -> ComposeResult:
        yield Static("Category authority", classes="heading", markup=False)
        yield Select(
            [
                ("Drawer-first (rules + overrides)", "drawer"),
                ("Puppy-first (fallback to drawer)", "puppy"),
            ],
            value=self.preferences["category_mode"],
            allow_blank=False,
            id="category-mode",
        )
        yield Static(
            "Drawer-first: your overrides, then workflow rules.\n"
            "Puppy-first: native category, then overrides/rules if missing.\n\n"
            "Assign in Puppy: /drawer category set COMMAND CATEGORY\n"
            "Reset: /drawer category reset COMMAND\n"
            "Policy: /drawer category mode drawer|puppy\n"
            "Names and overrides survive Puppy upgrades.",
            markup=False,
        )
        yield Static("Tab order", classes="heading", markup=False)
        yield Select(
            [(label, tab) for tab, label in LABELS.items()],
            value="commands",
            allow_blank=False,
            id="order-tab",
        )
        yield Button("Move earlier", id="tab-earlier")
        yield Button("Move later", id="tab-later")
        yield Static(id="settings-status", markup=False)
        yield Static("No commands are executed here. Chat and sidebar are untouched.", markup=False)
