"""Getting the virtual microphone onto the machine.

VB-Audio Cable is a signed Windows audio driver, which no Python wheel can stand in for and
which we are not licensed to bundle. So the panel fetches VB-Audio's own installer and runs
it (elevated - it is a driver) when asked, and tells whether the cable is already there.
"""

from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

from .audio import loopback_missing

DOWNLOAD_URL = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip"
SETUP_NAME = "VBCABLE_Setup_x64.exe"
CABLE_MARK = "cable"  # the devices are named "CABLE Input (VB-Audio Virtual Cable)" / "CABLE Output ..."


def cable_devices() -> list[str]:
    """Names of the VB-Cable playback devices present, empty when the driver is not installed."""
    if loopback_missing():
        return []
    import soundcard as sc

    try:
        return [str(s.name) for s in sc.all_speakers() if CABLE_MARK in str(s.name).casefold()]
    except Exception:  # pragma: no cover - no audio hardware at all
        return []


def cable_input_id() -> str:
    """The id of the CABLE Input device to play into, or empty."""
    if loopback_missing():
        return ""
    import soundcard as sc

    try:
        for speaker in sc.all_speakers():
            if CABLE_MARK in str(speaker.name).casefold() and "input" in str(speaker.name).casefold():
                return str(speaker.id)
    except Exception:  # pragma: no cover
        return ""
    return ""


def download_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "cs2bot"
    base.mkdir(parents=True, exist_ok=True)
    return base


def fetch_installer(target: Path | None = None) -> Path:
    """Download VB-Audio's driver pack and unpack the 64-bit setup next to the bot's data."""
    folder = target or download_dir() / "vbcable"
    folder.mkdir(parents=True, exist_ok=True)
    setup = folder / SETUP_NAME
    if setup.exists():
        return setup
    with urllib.request.urlopen(DOWNLOAD_URL, timeout=120) as response:  # noqa: S310 - fixed https URL
        data = response.read()
    with zipfile.ZipFile(io.BytesIO(data)) as pack:
        pack.extractall(folder)
    if not setup.exists():
        raise RuntimeError(f"{SETUP_NAME} was not in the download")
    return setup


def install_cable() -> tuple[bool, str]:
    """Run VB-Cable's installer with admin rights (UAC prompt); Windows must restart afterwards."""
    if sys.platform != "win32":
        return False, "VB-Cable is a Windows driver"
    if cable_devices():
        return True, "VB-Cable is already installed"
    try:
        setup = fetch_installer()
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        return False, f"could not download VB-Cable: {exc}"
    import ctypes

    shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
    # "-i -h": install, hidden. Returns > 32 when the launch itself succeeded.
    result = shell32.ShellExecuteW(None, "runas", str(setup), "-i -h", str(setup.parent), 1)
    if int(result) <= 32:
        return False, f"Windows would not start the driver installer (code {int(result)})"
    return True, "VB-Cable installer started - accept the prompt, then restart Windows"


def driver_status() -> dict[str, object]:
    return {
        "installed": bool(cable_devices()),
        "devices": cable_devices(),
        "input_id": cable_input_id(),
        "setup_cached": (download_dir() / "vbcable" / SETUP_NAME).exists(),
    }
