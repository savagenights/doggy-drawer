import sys
import types

import pytest

from doggy_drawer import picker_export
from doggy_drawer.runtime_catalog import picker_rows, publish, read_snapshot


def test_termflow_and_native_alias_categories_after_plugin_discovery(monkeypatch):
    registered = []

    class Completer:
        def get_completions(self, document, event):
            assert document.text_before_cursor == "/"
            registered.append(
                types.SimpleNamespace(
                    name="agent", aliases=["a"], hidden_aliases=["hidden"], category="session"
                )
            )
            for name in ("agent", "a", "hidden", "custom/command"):
                yield types.SimpleNamespace(text=name, display="/" + name, display_meta="Help")

    completers = types.ModuleType("code_puppy.command_line.completers")
    completers.SlashCompleter = Completer
    registry = types.ModuleType("code_puppy.command_line.command_registry")
    registry.get_unique_commands = lambda: registered
    monkeypatch.setitem(sys.modules, completers.__name__, completers)
    monkeypatch.setitem(sys.modules, registry.__name__, registry)
    rows = picker_rows()
    assert [row["category"] for row in rows] == ["session", "session", "session", ""]
    assert all(row["description"] == "Help" for row in rows)


def test_discovery_snapshot_never_claims_live_connection(tmp_path):
    path = tmp_path / "catalog.json"
    publish(path, "discovery-test", [{"name": "agent", "description": "Help"}], origin="discovery")
    catalog = read_snapshot(path)
    assert "not this chat's live session" in catalog.diagnostics[0]


def test_empty_discovery_does_not_replace_snapshot(tmp_path, monkeypatch):
    # Stub registration imports: the standalone UI/test environment needs no Puppy.
    puppy = types.ModuleType("code_puppy")
    command_line = types.ModuleType("code_puppy.command_line")
    handler = types.ModuleType("code_puppy.command_line.command_handler")
    puppy.command_line = command_line
    command_line.command_handler = handler
    for module in (puppy, command_line, handler):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(picker_export, "picker_rows", lambda: [])
    path = tmp_path / "catalog.json"
    path.write_text("keep existing snapshot")
    with pytest.raises(ValueError, match="no commands"):
        picker_export.export_picker(path, "discovery-test")
    assert path.read_text() == "keep existing snapshot"
