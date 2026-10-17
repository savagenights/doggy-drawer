"""One terminal app; two independent scroll regions; no execution transport."""

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Input,
    OptionList,
    Select,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option

from doggy_drawer import preferences as prefs
from doggy_drawer.catalog import Catalog, Command, display_declaration
from doggy_drawer.categories import groups, resolve
from doggy_drawer.display import display_text
from doggy_drawer.panels import LABELS, Dashboard, Settings
from doggy_drawer.runtime_catalog import read_snapshot


class Drawer(App[None]):
    TITLE = "doggy-drawer (read only)"
    CSS = """
    Screen { layout: vertical; min-width: 24; }
    TabbedContent { height: 1fr; }
    TabPane { padding: 0; }
    #scope { height: 2; color: $text-muted; }
    .heading { height: auto; color: $accent; text-style: bold; margin: 1 0; }
    Dashboard, Settings { padding: 0 1; }
    Dashboard Static, Settings Static { height: auto; margin-bottom: 1; }
    #tree-controls { height: 1; margin: 0; padding: 0; }
    #tree-controls Button {
        min-width: 9; width: 1fr; height: 1; min-height: 1;
        margin: 0; padding: 0 1; border: none;
    }
    #tree-controls Button:focus { border: none; text-style: bold underline; }
    #settings-status { color: $accent; }
    #details-scroll { height: 3fr; border: round $primary; padding: 0 1; }
    #details-scroll:focus { border: double $accent; }
    #details { height: auto; }
    #search { height: 1; min-height: 1; margin: 0; padding: 0 1; border: none; }
    #search:focus { border: none; }
    #count { height: 1; color: $text-muted; }
    #command-tree { height: 2fr; min-height: 6; border: round $primary; }
    #command-tree:focus { border: double $accent; }
    Footer { height: 1; }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "Close"),
        Binding("ctrl+f", "search", "Search"),
        Binding("escape", "list", "List"),
        Binding("f2", "details", "Details"),
    ]

    def __init__(
        self,
        catalog: Catalog,
        snapshot: Path | None = None,
        session: str | None = None,
        preferences: Path | None = None,
        initial_tab: str = "dashboard",
    ) -> None:
        super().__init__()
        self.catalog = catalog
        self.snapshot = snapshot
        self.session = session
        self.filtered_commands: list[Command] = []
        self.selected_name: str | None = None
        self.preferences_path = preferences or prefs.preferences_path()
        self.preference_error = ""
        try:
            self.preferences = prefs.load(self.preferences_path)
        except (OSError, ValueError) as error:
            self.preferences = prefs.defaults()
            self.preference_error = str(error)
        self.initial_tab = initial_tab
        self.expanded: set[str] = set()
        self.all_expanded = False
        self.last_query = ""
        self.before_search: tuple[set[str], bool] | None = None
        self.tree_initialized = False
        self.grouped: dict[str, list[Command]] = {}

    def compose(self) -> ComposeResult:
        with TabbedContent(initial=self.initial_tab, id="workspace-tabs"):
            for tab in self.preferences["tab_order"]:
                with TabPane(LABELS[tab], id=tab):
                    if tab == "dashboard":
                        yield Dashboard()
                    elif tab == "settings":
                        yield Settings(self.preferences)
                    else:
                        yield from self.command_widgets()
        yield Footer()

    def command_widgets(self) -> ComposeResult:
        yield Static(
            "Partial local declarations; not a live agent manifest.\n"
            "No target attached. Nothing here sends commands.",
            id="scope",
            markup=False,
        )
        with VerticalScroll(id="details-scroll", can_focus=True):
            yield Static(id="details", markup=False)
        yield Input(placeholder="Search commands, aliases, descriptions...", id="search")
        yield Static(id="count", markup=False)
        with Horizontal(id="tree-controls"):
            yield Button("[All]", id="expand-all")
            yield Button("Collapse", id="collapse-all")
        yield OptionList(id="command-tree")

    def on_mount(self) -> None:
        self.query_one("#details-scroll").border_title = "Command details"
        self.query_one("#command-tree").border_title = "Commands"
        self.filter_commands("")
        if self.initial_tab == "commands":
            self.query_one("#search", Input).focus()
        self.update_dashboard()
        self.set_interval(1, self.refresh_preferences)
        if self.snapshot:
            self.refresh_runtime()
            self.set_interval(1, self.refresh_runtime)

    def refresh_runtime(self) -> None:
        if self.snapshot is None:
            return
        try:
            catalog = read_snapshot(self.snapshot, self.session)
            if catalog != self.catalog:
                self.catalog = catalog
                self.filter_commands(self.query_one("#search", Input).value)
            status = "; ".join(catalog.diagnostics) or "Snapshot connected"
        except (OSError, ValueError, TypeError) as error:
            status = f"Disconnected; keeping last good catalog: {error}"
        self.query_one("#scope", Static).update(
            display_text(f"Puppy slash-picker snapshot | {status}\nRead only. No command dispatch.")
        )
        self.update_dashboard()

    def update_dashboard(self) -> None:
        mode = self.preferences["category_mode"]
        status = "; ".join(self.catalog.diagnostics) or (
            "Snapshot connected" if self.snapshot else "Static fallback catalog"
        )
        category_count = len(groups(list(self.catalog.commands), self.preferences))
        self.query_one("#dashboard-summary", Static).update(
            display_text(
                f"{len(self.catalog.commands)} commands | {category_count} categories\n"
                f"Category authority: {mode}-first\n{status}\n"
                f"Session: {self.session or 'standalone'}\n"
                f"{self.preference_error}"
            )
        )
        self.query_one("#settings-status", Static).update(
            display_text(
                f"Order: {' > '.join(LABELS[tab] for tab in self.preferences['tab_order'])}\n"
                f"Preferences: {self.preferences_path}\n{self.preference_error}"
            )
        )

    def refresh_preferences(self) -> None:
        try:
            value = prefs.load(self.preferences_path)
            if value != self.preferences:
                self.preferences = value
                self.apply_tab_order()
                self.query_one("#category-mode", Select).value = value["category_mode"]
                self.filter_commands(self.query_one("#search", Input).value)
            self.preference_error = ""
        except (OSError, ValueError) as error:
            self.preference_error = f"Preferences unavailable; keeping last good settings: {error}"
        self.update_dashboard()

    def apply_tab_order(self) -> None:
        tabs = self.query_one("#workspace-tabs", TabbedContent)
        previous = None
        for name in self.preferences["tab_order"]:
            tab = tabs.get_tab(name)
            if previous is not None and tab.parent:
                tab.parent.move_child(tab, after=previous)
            previous = tab

    def save_preferences(self, **changes: object) -> None:
        try:
            self.preferences = prefs.update(self.preferences_path, **changes)
            self.preference_error = ""
            self.apply_tab_order()
            self.filter_commands(self.query_one("#search", Input).value)
        except (OSError, ValueError) as error:
            self.preference_error = f"Settings not saved: {error}"
        self.update_dashboard()

    @on(Select.Changed, "#category-mode")
    def category_mode_changed(self, event: Select.Changed) -> None:
        if event.value in prefs.MODES and event.value != self.preferences["category_mode"]:
            self.save_preferences(category_mode=event.value)

    @on(Button.Pressed)
    def button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button in {"expand-all", "collapse-all"}:
            self.all_expanded = button == "expand-all"
            self.expanded = set(self.grouped) if self.all_expanded else set()
            self.filter_commands(self.query_one("#search", Input).value)
        elif button in {"tab-earlier", "tab-later"}:
            tab = self.query_one("#order-tab", Select).value
            order = list(self.preferences["tab_order"])
            index = order.index(tab)
            target = index + (-1 if button == "tab-earlier" else 1)
            if 0 <= target < len(order):
                order[index], order[target] = order[target], order[index]
                self.save_preferences(tab_order=order)

    @on(Input.Changed, "#search")
    def search_changed(self, event: Input.Changed) -> None:
        self.filter_commands(event.value)

    @on(Input.Submitted, "#search")
    def search_submitted(self) -> None:
        self.action_list()

    def filter_commands(self, query: str) -> None:
        self.filtered_commands = [
            cmd
            for cmd in self.catalog.commands
            if cmd.matches(query)
            or (
                query.strip()
                and query.casefold() in resolve(cmd, self.preferences).category.casefold()
            )
        ]
        self.grouped = groups(self.filtered_commands, self.preferences)
        if not self.tree_initialized and self.grouped:
            self.expanded = {next(iter(self.grouped))}
            self.tree_initialized = True
        if query != self.last_query:
            if query.strip():
                if self.before_search is None:
                    self.before_search = (set(self.expanded), self.all_expanded)
                self.all_expanded = True
            elif self.before_search is not None:
                self.expanded, self.all_expanded = self.before_search
                self.before_search = None
            self.last_query = query
        options = self.query_one("#command-tree", OptionList)
        options.clear_options()
        for category, commands in self.grouped.items():
            opened = self.all_expanded or category in self.expanded
            marker = "[-]" if opened else "[+]"
            options.add_option(
                Option(
                    display_text(f"{marker} {category} ({len(commands)})"),
                    id="category:" + category,
                )
            )
            if opened:
                options.add_options(
                    Option(display_text(f"  /{cmd.name}"), id="command:" + cmd.name)
                    for cmd in commands
                )
        self.query_one("#count", Static).update(
            f"{len(self.filtered_commands)}/{len(self.catalog.commands)} commands | "
            f"{len(self.catalog.diagnostics)} scan notices"
        )
        index = next(
            (i for i, cmd in enumerate(self.filtered_commands) if cmd.name == self.selected_name), 0
        )
        if self.filtered_commands:
            command_id = "command:" + self.filtered_commands[index].name
            options.highlighted = next(
                (
                    i
                    for i in range(options.option_count)
                    if options.get_option_at_index(i).id == command_id
                ),
                0,
            )
            self.show_command(self.filtered_commands[index])
        else:
            self.selected_name = None
            message = "No matching commands. Clear or change the search."
            if not self.catalog.commands:
                message = (
                    "No slash-picker entries received. Run /drawer refresh in Puppy.\n\n"
                    if self.snapshot
                    else "No literal command declarations found.\n"
                    "Run with --source PATH pointing at Puppy's command_line directory.\n\n"
                ) + "\n".join(self.catalog.diagnostics)
            self.query_one("#details", Static).update(display_text(message))

    @on(OptionList.OptionHighlighted, "#command-tree")
    @on(OptionList.OptionSelected, "#command-tree")
    def command_changed(
        self, event: OptionList.OptionHighlighted | OptionList.OptionSelected
    ) -> None:
        # Queued highlight events can outlive a search rebuild. Match stable IDs,
        # never use a stale list index against the newly filtered collection.
        identity = event.option.id or ""
        if identity.startswith("category:"):
            if isinstance(event, OptionList.OptionSelected):
                category = identity.removeprefix("category:")
                opened = self.all_expanded or category in self.expanded
                self.all_expanded = False
                self.expanded = set() if opened else {category}
                self.filter_commands(self.query_one("#search", Input).value)
            return
        command = next(
            (cmd for cmd in self.filtered_commands if "command:" + cmd.name == identity), None
        )
        if command is not None:
            self.show_command(command)

    def show_command(self, command: Command) -> None:
        changed = command.name != self.selected_name
        self.selected_name = command.name
        text = display_text()
        text.append(f"/{command.name}\n", style="bold cyan")
        text.append(f"{command.description}\n\n")
        text.append("Usage\n", style="bold")
        text.append(command.usage + "\n\n")
        text.append(f"Aliases: {', '.join('/' + a for a in command.aliases) or 'none declared'}\n")
        assignment = resolve(command, self.preferences)
        text.append(f"Category: {assignment.category}\nAssigned by: {assignment.source}\n")
        text.append(f"Puppy category: {command.category or 'not supplied'}\n\n")
        text.append("Help\n", style="bold")
        text.append(
            command.detailed_help or "No detailed help declared. Usage above is from source."
        )
        text.append(f"\n\nDeclaration\n{display_declaration(command.source)}\n\n", style="dim")
        text.append(
            (
                "Advertised by this Puppy's slash picker; not an execution guarantee.\n"
                if self.snapshot
                else "Static evidence only: this command may not be loaded in your agent.\n"
            )
            + "Selection, double-click, and Enter never execute commands.",
            style="dim",
        )
        self.query_one("#details", Static).update(display_text(text))
        if changed:
            self.query_one("#details-scroll", VerticalScroll).scroll_home(animate=False)

    def action_search(self) -> None:
        self.query_one("#workspace-tabs", TabbedContent).active = "commands"
        self.query_one("#search", Input).focus()

    def action_list(self) -> None:
        self.query_one("#workspace-tabs", TabbedContent).active = "commands"
        self.query_one("#command-tree", OptionList).focus()

    def action_details(self) -> None:
        self.query_one("#workspace-tabs", TabbedContent).active = "commands"
        self.query_one("#details-scroll", VerticalScroll).focus()
