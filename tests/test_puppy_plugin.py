import json
from pathlib import Path
from unittest.mock import Mock

from doggy_drawer import puppy_plugin
from doggy_drawer.installation import install_plugin
from doggy_drawer.puppy_plugin import PuppyDrawer, load_config, save_config
from doggy_drawer.runtime_catalog import read_snapshot


def test_install_is_self_contained_and_preserves_activation(tmp_path) -> None:
    home = tmp_path / "doggy-drawer"
    save_config(home, {"enabled": True})
    destination = install_plugin(tmp_path, ui_python="isolated-python")
    assert (destination / "register_callbacks.py").is_file()
    assert (destination / "puppy_plugin.py").is_file()
    assert load_config(home) == {"enabled": True, "ui_python": "isolated-python"}
    install_plugin(tmp_path, ui_python="updated-python")
    assert len(list((tmp_path / "plugins").glob(".doggy-drawer-backup-*"))) == 1
    assert load_config(home)["ui_python"] == "updated-python"


def test_disabled_startup_has_no_download_or_catalog_side_effect(tmp_path, monkeypatch) -> None:
    plugin = PuppyDrawer(tmp_path)
    download = Mock(side_effect=AssertionError("Must not download"))
    picker = Mock(side_effect=AssertionError("Must not enumerate"))
    monkeypatch.setattr(puppy_plugin, "ensure_herdr", download)
    monkeypatch.setattr(puppy_plugin, "picker_rows", picker)
    plugin.startup()
    download.assert_not_called()
    picker.assert_not_called()
    assert not plugin.snapshot.exists()


def test_export_uses_picker_and_preserves_last_good_rows(tmp_path, monkeypatch) -> None:
    plugin = PuppyDrawer(tmp_path)
    monkeypatch.setattr(
        puppy_plugin, "picker_rows", lambda: [{"name": "skill", "description": "Skill"}]
    )
    plugin.export()
    assert read_snapshot(plugin.snapshot, plugin.session).commands[0].name == "skill"
    monkeypatch.setattr(puppy_plugin, "picker_rows", Mock(side_effect=RuntimeError("failure")))
    plugin.export()
    catalog = read_snapshot(plugin.snapshot)
    assert len(catalog.commands) == 1
    assert "failure" in catalog.diagnostics[0]


def test_commands_ignore_other_handlers_and_enable_is_explicit(tmp_path, monkeypatch) -> None:
    plugin = PuppyDrawer(tmp_path)
    setup = Mock(return_value="herdr")
    monkeypatch.setattr(puppy_plugin, "ensure_herdr", setup)
    monkeypatch.setattr(puppy_plugin, "in_herdr", lambda: False)
    monkeypatch.setattr(puppy_plugin, "picker_rows", lambda: [])
    monkeypatch.setattr(plugin, "message", Mock())
    assert plugin.command("/agent", "agent") is None
    setup.assert_not_called()
    assert plugin.command("/drawer enable", "drawer") is True
    assert setup.call_args_list[0].kwargs == {"allow_download": True}
    assert load_config(tmp_path)["enabled"] is True
    assert plugin.command("/drawer disable", "drawer") is True
    assert load_config(tmp_path)["enabled"] is False
    plugin.shutdown()


def test_open_pins_snapshot_and_preserves_chat_focus(tmp_path, monkeypatch) -> None:
    plugin = PuppyDrawer(tmp_path)
    save_config(tmp_path, {"enabled": True, "ui_python": "isolated-python"})
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    monkeypatch.setattr(puppy_plugin, "in_herdr", lambda: True)
    monkeypatch.setattr(puppy_plugin, "ensure_herdr", lambda *a, **k: "herdr")
    calls = []

    def run(arguments):
        calls.append(arguments)
        if "open" in arguments:
            return json.dumps({"result": {"plugin_pane": {"pane": {"pane_id": "w1:p2"}}}})
        if "list" in arguments:
            return json.dumps({"result": {"panes": [{"pane_id": "w1:p2"}]}})
        return "{}"

    monkeypatch.setattr(puppy_plugin, "run", run)
    plugin.open()
    plugin.open()
    assert sum("open" in call for call in calls) == 1
    assert "--no-focus" in calls[1]
    assert calls[1][calls[1].index("--target-pane") + 1] == "w1:p1"
    import tomllib

    manifest = tomllib.loads((plugin.snapshot.parent / "herdr-plugin.toml").read_text())
    command = manifest["panes"][0]["command"]
    assert command[0] == "isolated-python"
    assert command[-1] == plugin.session
    assert Path(command[command.index("--snapshot") + 1]) == plugin.snapshot
