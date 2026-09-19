"""Build `CS2 Chatbot.exe`: one file, no Python installation needed on the target machine.

    python scripts/build_exe.py

Run it on Windows - PyInstaller freezes the interpreter it is running on, so a Linux build
produces a Linux binary. CI does this on a Windows runner and attaches the result to the release.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "CS2 Chatbot"
# Voice comms: native libraries and data files PyInstaller cannot infer from the imports.
# `soundcard` reads C headers shipped beside it, `faster_whisper` carries the voice-detection
# model, and `ctranslate2`/`onnxruntime` are DLLs loaded by name at runtime.
VOICE_PACKAGES = ("soundcard", "faster_whisper", "ctranslate2", "onnxruntime", "av")


def installed(package: str) -> bool:
    try:
        return importlib.util.find_spec(package) is not None
    except ModuleNotFoundError:  # a package whose own import machinery is incomplete
        return False


def main() -> int:
    if shutil.which("pyinstaller") is None:
        print("PyInstaller is missing. Install it with:  pip install pyinstaller")
        return 1

    static = ROOT / "cs2bot" / "web" / "static"
    separator = ";" if sys.platform == "win32" else ":"
    command = [
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        NAME,
        # The panel is HTML served off disk, so it has to travel inside the executable.
        "--add-data",
        f"{static}{separator}cs2bot/web/static",
        # Pull the package in from the checkout: an editable install hides the real files behind a
        # finder that PyInstaller cannot follow, and the launcher only imports one module by name.
        "--paths",
        str(ROOT),
        "--collect-submodules",
        "cs2bot",
        # uvicorn loads these by name at runtime, so static analysis cannot see them.
        "--hidden-import",
        "uvicorn.protocols.http.h11_impl",
        "--hidden-import",
        "uvicorn.protocols.websockets.websockets_impl",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "uvicorn.loops.asyncio",
        *[arg for pkg in VOICE_PACKAGES if installed(pkg) for arg in ("--collect-all", pkg)],
        # Freeze the launcher, not `cs2bot/__main__.py`: PyInstaller runs its entry script as a
        # package-less `__main__`, where the package's relative imports blow up on startup.
        str(ROOT / "scripts" / "launcher.py"),
    ]
    missing = [pkg for pkg in VOICE_PACKAGES if not installed(pkg)]
    if missing:
        # Not fatal: the build works, it just cannot hear anything. Say so, because the panel
        # will then report voice as unsupported on a machine that looks fully installed.
        print(f"warning: building without voice support, missing {', '.join(missing)}")
        print("         install it with:  pip install '.[voice]'")

    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        return result.returncode

    built = ROOT / "dist" / (f"{NAME}.exe" if sys.platform == "win32" else NAME)
    print(f"\nBuilt {built}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
