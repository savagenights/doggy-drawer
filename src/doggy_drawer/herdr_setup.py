"""Pinned, hash-checked, user-local herdr bootstrap. No shell installers."""

from __future__ import annotations

import hashlib
import io
import os
import platform
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.9.5"
RELEASE = f"https://github.com/herdrdev/herdr/releases/download/v{VERSION}/"
# GitHub release asset SHA-256 digests, verified against the v0.9.5 release API.
ASSETS = {
    ("Windows", "x86_64"): (
        "herdr-windows-x86_64.zip",
        "d2c6c9c971c43a0bfdde8c692a9a1a7a45c3e4807cd01ae45662b4734fac1cbf",
    ),
    ("Linux", "x86_64"): (
        "herdr-linux-x86_64",
        "14d9e8bc8b4a9e0118d77c32266f76d461f09b40342eb23752960bd89f59929d",
    ),
    ("Linux", "aarch64"): (
        "herdr-linux-aarch64",
        "17d7536f2da50859523680ef279dffcac8e4a235f4e46fe8da6c2ec44141897c",
    ),
    ("Darwin", "x86_64"): (
        "herdr-macos-x86_64",
        "5fb0a908ec7f6745e3e245738b06bfad56c46391c391ab3c0955fbead01f1369",
    ),
    ("Darwin", "aarch64"): (
        "herdr-macos-aarch64",
        "fb77c2232a05a8035421382c894392f4174e4e38a18e48af3dd0290157c3a7e2",
    ),
}
LIMIT = 250 * 1024 * 1024


def run(arguments: list[str]) -> str:
    result = subprocess.run(
        arguments, capture_output=True, text=True, encoding="utf-8", timeout=30, check=True
    )
    return result.stdout


def check_version(executable: str | Path) -> str:
    output = run([str(executable), "--version"])
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", output)
    if not match or tuple(map(int, match.groups())) < (0, 9, 5):
        raise RuntimeError("doggy-drawer requires herdr >= 0.9.5; existing install left untouched")
    return str(executable)


def fetch_asset(name: str, digest: str) -> bytes:
    request = urllib.request.Request(RELEASE + name, headers={"User-Agent": "doggy-drawer"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if not response.url.startswith("https://"):
            raise RuntimeError("Refusing non-HTTPS release download")
        chunks = []
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > LIMIT:
                raise RuntimeError("herdr download exceeds size limit")
            chunks.append(chunk)
    data = b"".join(chunks)
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError("herdr SHA-256 mismatch; download will not be executed")
    return data


def install_asset(directory: Path, system: str, data: bytes) -> Path:
    executable = directory / ("herdr.exe" if system == "Windows" else "herdr")
    if system == "Windows":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            matches = [
                item for item in archive.infolist() if Path(item.filename).name == "herdr.exe"
            ]
            if len(matches) != 1 or matches[0].file_size > LIMIT:
                raise RuntimeError("Unexpected herdr archive layout")
            # Read only the executable; never extract archive-controlled paths.
            data = archive.read(matches[0])
    directory.mkdir(parents=True, exist_ok=True)
    temporary = executable.with_suffix(".download")
    try:
        temporary.write_bytes(data)
        temporary.chmod(0o755)
        temporary.replace(executable)
    finally:
        temporary.unlink(missing_ok=True)
    return executable


def ensure_herdr(data_dir: Path, *, allow_download: bool = False) -> str:
    if existing := shutil.which("herdr"):
        return check_version(existing)
    system = platform.system()
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    directory = data_dir / "herdr" / VERSION / f"{system}-{machine}"
    executable = directory / ("herdr.exe" if system == "Windows" else "herdr")
    if executable.is_file():
        return check_version(executable)
    if not allow_download:
        raise RuntimeError("herdr is missing. Run /drawer enable to install the pinned release.")
    asset = ASSETS.get((system, machine))
    if asset is None:
        raise RuntimeError(f"No verified herdr release for {system}/{machine}")
    name, digest = asset
    executable = install_asset(directory, system, fetch_asset(name, digest))
    try:
        return check_version(executable)
    except (OSError, subprocess.SubprocessError, RuntimeError):
        # Only this bootstrap's newly downloaded file is rolled back.
        executable.unlink(missing_ok=True)
        raise


def in_herdr() -> bool:
    return bool(os.environ.get("HERDR_PANE_ID") and os.environ.get("HERDR_SOCKET_PATH"))
