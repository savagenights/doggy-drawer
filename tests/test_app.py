from textual.containers import VerticalScroll
from textual.widgets import Input, OptionList, Static

from doggy_drawer.app import Drawer
from doggy_drawer.catalog import Catalog, Command


def sample_catalog() -> Catalog:
    return Catalog(
        tuple(
            Command(
                f"cmd{i:02}", f"Description {i}", f"/cmd{i:02}", detailed_help="Help line\n" * 60
            )
            for i in range(35)
        ),
        (),
    )


async def test_list_shows_only_names_and_details_keep_descriptions() -> None:
    app = Drawer(sample_catalog(), initial_tab="commands")
    async with app.run_test(size=(60, 40)) as pilot:
        options = app.query_one(OptionList)
        assert [options.get_option_at_index(i).prompt.plain.strip() for i in range(1, 36)] == [
            f"/cmd{i:02}" for i in range(35)
        ]
        assert "Description 0" in str(app.query_one("#details", Static).render())
        app.query_one(Input).value = "Description 12"
        await pilot.pause()
        assert options.option_count == 2
        assert options.get_option_at_index(1).prompt.plain.strip() == "/cmd12"
        assert "Description 12" in str(app.query_one("#details", Static).render())


async def test_home_abbreviation_across_tabs_help_and_errors(tmp_path) -> None:
    from pathlib import Path

    from textual.widgets import TabbedContent

    home = str(Path.home())
    path = str(Path.home() / "example.json")
    command = Command(
        "example",
        f"Description: {path}",
        f"/example {path}",
        detailed_help=f"Read '{path}'",
        source=path,
    )
    app = Drawer(
        Catalog((command,), (), (f"Could not read '{path}'",)),
        preferences=tmp_path / "preferences.json",
        initial_tab="commands",
    )
    async with app.run_test(size=(80, 40)) as pilot:
        # Exercise settings/error output without writing anything in the real home.
        app.preferences_path = Path(path)
        app.preference_error = f"Invalid preferences: '{path}'"
        app.update_dashboard()
        for tab, selector in (
            ("commands", "#details"),
            ("dashboard", "#dashboard-summary"),
            ("settings", "#settings-status"),
        ):
            app.query_one(TabbedContent).active = tab
            await pilot.pause()
            rendered = str(app.query_one(selector, Static).render())
            assert home not in rendered
            assert "%USERPROFILE%" in rendered
        app.snapshot = Path(path)
        app.refresh_runtime()
        scope = str(app.query_one("#scope", Static).render())
        assert home not in scope
        assert "%USERPROFILE%" in scope
        assert app.catalog.commands[0] == command
        assert app.preferences_path == Path(path)


async def test_compact_controls_and_home_declaration() -> None:
    from pathlib import Path

    source = str(Path.home() / "plugins" / "commands.py") + ":68"
    command = Command("example", "Example", "/example", source=source)
    app = Drawer(Catalog((command,), ()), initial_tab="commands")
    async with app.run_test(size=(60, 40)) as pilot:
        details = str(app.query_one("#details", Static).render())
        assert "%USERPROFILE%" in details
        assert source not in details
        for selector in ("#search", "#tree-controls", "#expand-all", "#collapse-all"):
            control = app.query_one(selector)
            assert control.styles.margin.top == 0
            assert control.styles.margin.bottom == 0
            assert control.size.height == 1
            assert control.content_size.height == 1
        await pilot.click("#expand-all")
        assert app.all_expanded
        await pilot.click("#collapse-all")
        assert not app.all_expanded
        await pilot.press("ctrl+f")
        await pilot.press("e", "x")
        assert app.query_one(Input).value == "ex"
        assert [cmd.name for cmd in app.filtered_commands] == ["example"]


async def test_search_navigation_focus_and_empty_results() -> None:
    app = Drawer(sample_catalog(), initial_tab="commands")
    async with app.run_test(size=(60, 40)) as pilot:
        assert app.focused is app.query_one(Input)
        await pilot.press("c", "m", "d", "0", "3")
        assert [cmd.name for cmd in app.filtered_commands] == ["cmd03"]
        await pilot.press("enter")
        assert app.focused is app.query_one(OptionList)
        assert app.selected_name == "cmd03"
        await pilot.press("enter", "enter")  # Selection only, never dispatch.
        assert app.selected_name == "cmd03"
        await pilot.press("f2")
        assert app.focused is app.query_one("#details-scroll", VerticalScroll)
        await pilot.press("pagedown")
        await pilot.pause()
        assert app.query_one("#details-scroll", VerticalScroll).scroll_y > 0
        assert app.query_one(OptionList).scroll_y == 0
        await pilot.press("ctrl+f")
        app.query_one(Input).value = "does-not-exist"
        await pilot.pause()
        assert not app.filtered_commands
        assert app.selected_name is None
        assert "No matching" in str(app.query_one("#details", Static).render())


async def test_mouse_selection_and_narrow_layout() -> None:
    app = Drawer(sample_catalog(), initial_tab="commands")
    async with app.run_test(size=(38, 30)) as pilot:
        await pilot.press("escape", "down")
        assert app.selected_name == "cmd01"
        # First command follows the category header inside the list border.
        await pilot.click("#command-tree", offset=(3, 2))
        await pilot.pause()
        assert app.selected_name == "cmd00"
        assert app.query_one("#details-scroll").region.bottom <= app.query_one("#search").region.y
        await pilot.resize_terminal(28, 24)
        await pilot.pause()
        assert app.query_one("#command-tree").size.height >= 4
        assert app.query_one("#search").region.bottom <= 24


async def test_list_scroll_does_not_scroll_details_or_steal_hover_focus() -> None:
    app = Drawer(sample_catalog(), initial_tab="commands")
    async with app.run_test(size=(60, 30)) as pilot:
        search = app.query_one(Input)
        await pilot.hover("#command-tree")
        assert app.focused is search
        await pilot.press("escape", "end")
        await pilot.pause()
        assert app.query_one(OptionList).scroll_y > 0
        assert app.query_one("#details-scroll", VerticalScroll).scroll_y == 0
        assert app.selected_name == "cmd34"
        await pilot.press("ctrl+f")
        search.value = "cmd34"
        await pilot.pause()
        search.value = ""
        await pilot.pause()
        assert app.selected_name == "cmd34"
        assert app.query_one(OptionList).option_count == 36


async def test_empty_catalog_has_actionable_message() -> None:
    app = Drawer(Catalog((), (), ("Source directory not found: example",)))
    async with app.run_test(size=(50, 30)):
        assert app.query_one(OptionList).option_count == 0
        assert "--source" in str(app.query_one("#details", Static).render())
