import json

import pytest

from doggy_drawer import preferences as prefs
from doggy_drawer.catalog import Command
from doggy_drawer.categories import resolve
from doggy_drawer.preference_commands import handle


def cmd(name="model", category=""):
    return Command(name, "Switch model", "/" + name, category=category)


def test_policy_and_future_native_category():
    value = prefs.defaults()
    value["overrides"] = {"model": "My models"}
    assert resolve(cmd(), value).category == "My models"
    assert resolve(cmd(category="Future Puppy Category"), value).category == "My models"
    value["category_mode"] = "puppy"
    assert resolve(cmd(category="Future Puppy Category"), value).category == "Future Puppy Category"
    assert resolve(cmd(), value).category == "My models"
    value["overrides"] = {}
    assert resolve(cmd(), value).category == "Models & Providers"
    assert resolve(cmd(category="core"), value).category == "core"


def test_name_alias_description_and_unknown_rules():
    value = prefs.defaults()
    assert resolve(Command("a", "", "/a"), value).category == "Agents & Orchestration"
    assert resolve(Command("skills:custom", "", ""), value).category == "Tools & Integrations"
    assert (
        resolve(Command("future", "Inspect conversation history", ""), value).category
        == "Sessions & Context"
    )
    assert (
        resolve(Command("unfamiliar", "Nothing recognizable", ""), value).category == "Other & New"
    )
    assert (
        resolve(Command("theme", "Uses a model to choose colors", ""), value).category
        == "Settings & Appearance"
    )


def test_overrides_and_unknown_preferences_survive_upgrade(tmp_path):
    path = tmp_path / "preferences.json"
    prefs.update(path, future_option={"preserve": True})
    handle(tmp_path, ["category", "set", "/model", "My", "models"])
    handle(tmp_path, ["category", "mode", "puppy"])
    handle(tmp_path, ["tabs", "settings", "commands", "dashboard"])
    saved = prefs.load(path)
    assert saved["future_option"] == {"preserve": True}
    assert saved["overrides"]["model"] == "My models"
    assert saved["tab_order"] == ["settings", "commands", "dashboard"]
    # New metadata can take stage without destroying the user's assignment.
    assert resolve(cmd(category="models-v2"), saved).category == "models-v2"
    assert resolve(cmd(), saved).category == "My models"
    assert "My models" in handle(tmp_path, ["category", "list"])
    handle(tmp_path, ["category", "reset", "model"])
    assert prefs.load(path)["overrides"] == {}


@pytest.mark.parametrize(
    "changes",
    [
        {"category_mode": "bogus"},
        {"tab_order": ["dashboard"]},
        {"tab_order": ["dashboard", "dashboard", "settings"]},
        {"overrides": {"model": "bad\ncategory"}},
        {"overrides": {"": "Models"}},
    ],
)
def test_invalid_updates_preserve_file(tmp_path, changes):
    path = tmp_path / "preferences.json"
    prefs.update(path)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        prefs.update(path, **changes)
    assert path.read_bytes() == before


def test_unknown_schema_and_corruption_are_never_overwritten(tmp_path):
    path = tmp_path / "preferences.json"
    for content in [json.dumps({"schema": 99}), "broken"]:
        path.write_text(content)
        with pytest.raises(ValueError):
            prefs.update(path, category_mode="puppy")
        assert path.read_text() == content


def test_help_and_invalid_commands_do_not_write(tmp_path):
    assert "/drawer category mode" in handle(tmp_path, ["category"])
    assert not (tmp_path / "preferences.json").exists()
    with pytest.raises(ValueError):
        handle(tmp_path, ["tabs", "dashboard", "dashboard", "settings"])
    assert not (tmp_path / "preferences.json").exists()
