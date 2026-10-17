import pytest

from doggy_drawer import preferences


@pytest.fixture(autouse=True)
def isolated_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "preferences_path", lambda: tmp_path / "preferences.json")
