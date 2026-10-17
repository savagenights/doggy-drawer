from pathlib import Path

from rich.text import Text

from doggy_drawer.display import abbreviate_home, display_text


def test_home_paths_anywhere_in_prose_and_escaped_errors() -> None:
    home = str(Path.home())
    path = str(Path.home() / "settings.json")
    for value in (path, path.replace("\\", "/"), path.replace("\\", "\\\\")):
        result = abbreviate_home(f"Preferences: {value}\nError: '{value}'")
        assert result.count("%USERPROFILE%") == 2
        assert home not in result
    assert abbreviate_home(f"Home: {home}") == "Home: %USERPROFILE%"
    assert abbreviate_home(home + "-other/file") == home + "-other/file"
    assert abbreviate_home(home + "2/file") == home + "2/file"
    assert abbreviate_home("relative/file") == "relative/file"
    assert abbreviate_home("%USERPROFILE%/file") == "%USERPROFILE%/file"


def test_rich_styles_and_original_evidence_survive() -> None:
    original = Text("Help\n", style="dim")
    original.append(str(Path.home() / "help.txt"))
    original.append("\nStill bold", style="bold")
    rendered = display_text(original)
    assert "%USERPROFILE%" in rendered.plain
    assert str(Path.home()) in original.plain
    assert rendered.style == "dim"
    assert any(
        span.style == "bold" and rendered.plain[span.start : span.end] == "\nStill bold"
        for span in rendered.spans
    )
