from pathlib import Path

from doggy_drawer.catalog import Command, display_declaration, scan_sources


def test_literal_metadata_without_execution(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    (tmp_path / "commands.py").write_text(
        f"raise RuntimeError('must not import')\n"
        f"open({str(marker)!r}, 'w').write('bad')\n"
        '@register_command("hello", "Say hello", usage="/hello NAME", '
        'aliases=["hi"], category="demo", detailed_help="Long help")\n'
        'def hello(): raise RuntimeError("must not call")\n',
        encoding="utf-8",
    )
    catalog = scan_sources([tmp_path])
    assert not marker.exists()
    assert len(catalog.commands) == 1
    command = catalog.commands[0]
    assert command.name == "hello"
    assert command.aliases == ("hi",)
    assert command.usage == "/hello NAME"
    assert command.detailed_help == "Long help"
    assert command.source.endswith("commands.py:3")


def test_dynamic_invalid_duplicate_and_missing(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        '@register_command("one", "First")\ndef one(): pass\n'
        '@register_command(make_name(), "Dynamic")\ndef two(): pass\n'
        '@registry.register_command("one", "Second")\ndef three(): pass\n',
        encoding="utf-8",
    )
    (tmp_path / "broken.py").write_text("def !", encoding="utf-8")
    catalog = scan_sources([tmp_path, tmp_path, tmp_path / "missing"])
    assert [cmd.description for cmd in catalog.commands] == ["First"]
    assert len(catalog.roots) == 2
    assert len(catalog.diagnostics) == 4
    assert any("dynamic" in note for note in catalog.diagnostics)
    assert any("Duplicate" in note for note in catalog.diagnostics)


def test_declaration_abbreviates_only_current_home() -> None:
    home = Path.home()
    source = str(home / "plugins" / "register_callbacks.py") + ":68"
    assert display_declaration(source) == "%USERPROFILE%" + source[len(str(home)) :]
    neighbor = str(home) + "-other/plugins/register_callbacks.py:68"
    assert display_declaration(neighbor) == neighbor
    assert display_declaration("runtime completion") == "runtime completion"
    assert display_declaration("relative/module.py:12") == "relative/module.py:12"


def test_filter_is_case_insensitive_and_matches_all_words() -> None:
    command = Command("hello", "Say greetings", "/hello", ("hi",), "demo")
    assert command.matches("HI DEMO")
    assert command.matches("greet")
    assert command.matches("")
    assert not command.matches("hi missing")


def test_nonliteral_optional_metadata_is_not_evaluated(tmp_path: Path) -> None:
    (tmp_path / "commands.py").write_text(
        '@register_command("safe", "Known", detailed_help=run_callback(), aliases=get_aliases())\n'
        "async def handler(): pass\n",
        encoding="utf-8",
    )
    command = scan_sources([tmp_path]).commands[0]
    assert command.detailed_help == ""
    assert command.aliases == ()
    assert command.usage == "/safe"
