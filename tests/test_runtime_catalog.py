import json
import sys
import types

import pytest
from prompt_toolkit.completion import Completion
from textual.widgets import Input, OptionList, Static

from doggy_drawer.app import Drawer
from doggy_drawer.catalog import Catalog
from doggy_drawer.runtime_catalog import MAX_BYTES, picker_rows, publish, read_snapshot


def test_picker_uses_real_completion_entrypoint_not_handlers(monkeypatch) -> None:
    calls = []

    class Completer:
        def get_completions(self, document, event):
            calls.append(document.text)
            yield Completion("agent", display_meta="Switch agent")
            yield Completion("a", display="/a (alias for /agent)", display_meta="Switch agent")
            yield Completion("aaa-retopology", display_meta="Skill metadata")
            yield Completion("flux/new", display_meta="Custom command")

    module = types.ModuleType("code_puppy.command_line.completers")
    module.SlashCompleter = Completer
    monkeypatch.setitem(sys.modules, module.__name__, module)
    assert [row["name"] for row in picker_rows()] == ["agent", "a", "aaa-retopology", "flux/new"]
    assert calls == ["/"]


def test_snapshot_roundtrip_aliases_duplicates_errors_and_identity(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    rows = [
        {"name": "agent", "description": "Switch agent"},
        {"name": "a", "description": "Alias"},
        {"name": "agent", "description": "Duplicate"},
    ]
    publish(path, "session-1", rows, "provider failed")
    catalog = read_snapshot(path, "session-1")
    assert [command.name for command in catalog.commands] == ["a", "agent"]
    assert catalog.commands[1].description == "Switch agent"
    assert "provider failed" in catalog.diagnostics[0]
    with pytest.raises(ValueError, match="mismatch"):
        read_snapshot(path, "another-session")
    value = json.loads(path.read_text())
    value["updated_at"] = 0
    path.write_text(json.dumps(value))
    assert "stale" in read_snapshot(path).diagnostics[-1]


@pytest.mark.parametrize("value", [{}, {"schema": 99}, [], {"schema": 1, "session": "s"}])
def test_reject_invalid_snapshot(tmp_path, value) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        read_snapshot(path)


def test_snapshot_size_limit(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    path.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        read_snapshot(path)


async def test_live_refresh_preserves_search_and_last_good_catalog(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    publish(path, "s", [{"name": "agent", "description": "Switch agent"}])
    app = Drawer(Catalog((), ()), snapshot=path, session="s", initial_tab="commands")
    async with app.run_test(size=(70, 40)) as pilot:
        assert app.query_one(OptionList).option_count == 2
        app.query_one(Input).value = "skill"
        await pilot.pause()
        publish(path, "s", [{"name": "aaa-retopology", "description": "Skill metadata"}])
        app.refresh_runtime()
        await pilot.pause()
        assert app.query_one(OptionList).option_count == 2
        assert app.selected_name == "aaa-retopology"
        assert app.query_one(Input).value == "skill"
        path.write_text("broken")
        app.refresh_runtime()
        assert app.selected_name == "aaa-retopology"
        assert "Disconnected" in str(app.query_one("#scope", Static).render())
