import hashlib
import io
import zipfile
from unittest.mock import Mock

import pytest

from doggy_drawer import herdr_setup


def test_existing_herdr_is_reused_without_network(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(herdr_setup.shutil, "which", lambda name: "existing-herdr")
    monkeypatch.setattr(herdr_setup, "run", lambda args: "herdr 0.9.5")
    fetch = Mock(side_effect=AssertionError("Network not allowed"))
    monkeypatch.setattr(herdr_setup, "fetch_asset", fetch)
    assert herdr_setup.ensure_herdr(tmp_path) == "existing-herdr"
    fetch.assert_not_called()


def test_missing_herdr_requires_explicit_download(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(herdr_setup.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="/drawer enable"):
        herdr_setup.ensure_herdr(tmp_path)


def test_hash_mismatch_rejected_before_install(monkeypatch) -> None:
    class Response(io.BytesIO):
        url = "https://github.com/release"

    monkeypatch.setattr(herdr_setup.urllib.request, "urlopen", lambda *a, **k: Response(b"bad"))
    with pytest.raises(RuntimeError, match="SHA-256"):
        herdr_setup.fetch_asset("herdr", "0" * 64)
    assert herdr_setup.fetch_asset("herdr", hashlib.sha256(b"bad").hexdigest()) == b"bad"


def test_windows_archive_does_not_extract_paths(tmp_path) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("nested/herdr.exe", b"exe")
        out.writestr("../outside.txt", b"untrusted")
    path = herdr_setup.install_asset(tmp_path / "managed", "Windows", archive.getvalue())
    assert path.read_bytes() == b"exe"
    assert not (tmp_path / "outside.txt").exists()


def test_failed_bootstrap_rolls_back_only_new_binary(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(herdr_setup.shutil, "which", lambda name: None)
    monkeypatch.setattr(herdr_setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(herdr_setup.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(herdr_setup, "fetch_asset", lambda *args: b"bad executable")
    monkeypatch.setattr(herdr_setup, "check_version", Mock(side_effect=RuntimeError("bad version")))
    with pytest.raises(RuntimeError, match="bad version"):
        herdr_setup.ensure_herdr(tmp_path, allow_download=True)
    assert not list(tmp_path.rglob("herdr"))[-1].is_file()


def test_old_version_is_not_silently_replaced(monkeypatch) -> None:
    monkeypatch.setattr(herdr_setup, "run", lambda args: "herdr 0.8.0")
    with pytest.raises(RuntimeError, match="left untouched"):
        herdr_setup.check_version("old-herdr")
