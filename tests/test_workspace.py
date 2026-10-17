from textual.widgets import Button, Input, OptionList, Select, Static, TabbedContent

from doggy_drawer import preferences as prefs
from doggy_drawer.app import Drawer
from doggy_drawer.catalog import Catalog, Command


def catalog():
    return Catalog(
        tuple(
            Command(name, description, "/" + name, category=native)
            for name, description, native in [
                ("agent", "Switch agent", "core"),
                ("model", "Switch model", "config"),
                ("new-command", "Unrecognized operation", ""),
            ]
        ),
        (),
    )


def rows(app):
    options = app.query_one(OptionList)
    return [options.get_option_at_index(i) for i in range(options.option_count)]


def command_names(app):
    return [row.id.removeprefix("command:") for row in rows(app) if row.id.startswith("command:")]


def select_category(app, category):
    options = app.query_one(OptionList)
    options.highlighted = options.get_option_index("category:" + category)
    options.action_select()


async def test_dashboard_default_and_accordion_all_collapse():
    app = Drawer(catalog())
    async with app.run_test(size=(48, 38)) as pilot:
        tabs = app.query_one(TabbedContent)
        assert tabs.active == "dashboard"
        assert "3 commands" in str(app.query_one("#dashboard-summary", Static).render())
        assert not list(app.query("#title"))
        await pilot.press("ctrl+f")
        await pilot.pause()
        assert tabs.active == "commands"
        assert command_names(app) == ["agent"]
        select_category(app, "Models & Providers")
        await pilot.pause()
        assert command_names(app) == ["model"]
        assert app.expanded == {"Models & Providers"}
        select_category(app, "Models & Providers")
        await pilot.pause()
        assert command_names(app) == []
        await pilot.click("#expand-all")
        await pilot.pause()
        assert set(command_names(app)) == {"agent", "model", "new-command"}
        select_category(app, "Other & New")  # Open category closes itself, not a command.
        await pilot.pause()
        assert command_names(app) == []
        select_category(app, "Other & New")
        await pilot.pause()
        assert command_names(app) == ["new-command"]
        await pilot.click("#collapse-all")
        await pilot.pause()
        assert command_names(app) == []


async def test_category_search_auto_expands_matches_without_dispatch():
    app = Drawer(catalog(), initial_tab="commands")
    async with app.run_test(size=(42, 34)) as pilot:
        app.query_one(Input).value = "Providers"
        await pilot.pause()
        assert command_names(app) == ["model"]
        assert app.selected_name == "model"
        await pilot.press("enter", "enter", "enter")
        await pilot.pause()
        assert app.selected_name == "model"
        assert "drawer name rule" in str(app.query_one("#details", Static).render())
        app.query_one(Input).value = ""
        await pilot.pause()
        assert command_names(app) == ["agent"]


async def test_settings_persist_reorder_and_take_upstream_category(tmp_path):
    path = tmp_path / "preferences.json"
    app = Drawer(catalog(), preferences=path, initial_tab="settings")
    async with app.run_test(size=(52, 45)) as pilot:
        app.query_one("#category-mode", Select).value = "puppy"
        await pilot.pause()
        assert prefs.load(path)["category_mode"] == "puppy"
        assert set(app.grouped) == {"core", "config", "Other & New"}
        app.query_one("#order-tab", Select).value = "settings"
        app.query_one("#tab-earlier", Button).press()
        await pilot.pause()
        assert prefs.load(path)["tab_order"] == ["dashboard", "settings", "commands"]
        tabs = app.query_one(TabbedContent)
        assert tabs.get_tab("settings").region.x < tabs.get_tab("commands").region.x
        app.query_one("#tab-earlier", Button).press()
        await pilot.pause()
        assert prefs.load(path)["tab_order"] == ["settings", "dashboard", "commands"]
        assert tabs.get_tab("settings").region.x < tabs.get_tab("dashboard").region.x
    reopened = Drawer(catalog(), preferences=path)
    assert reopened.preferences["category_mode"] == "puppy"
    assert reopened.preferences["tab_order"][0] == "settings"


async def test_external_preference_command_reload_and_bad_file_preservation(tmp_path):
    path = tmp_path / "preferences.json"
    app = Drawer(catalog(), preferences=path, initial_tab="commands")
    async with app.run_test(size=(45, 35)) as pilot:
        prefs.update(path, overrides={"model": "My models"})
        app.refresh_preferences()
        await pilot.pause()
        assert "My models" in app.grouped
        path.write_text("broken")
        app.refresh_preferences()
        assert "My models" in app.grouped
        assert "last good" in app.preference_error
        app.save_preferences(category_mode="puppy")
        assert path.read_text() == "broken"
        assert "not saved" in app.preference_error
