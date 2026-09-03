"""Build `CS2 Chatbot.exe`: one file, no Python installation needed on the target machine.

    python scripts/build_exe.py

Run it on Windows - PyInstaller freezes the interpreter it is running on, so a Linux build
produces a Linux binary. CI does this on a Windows runner and attaches the result to the release.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "CS2 Chatbot"


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
        # uvicorn loads these by name at runtime, so static analysis cannot see them.
        "--hidden-import",
        "uvicorn.protocols.http.h11_impl",
        "--hidden-import",
        "uvicorn.protocols.websockets.websockets_impl",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "uvicorn.loops.asyncio",
        str(ROOT / "cs2bot" / "__main__.py"),
    ]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        return result.returncode

    built = ROOT / "dist" / (f"{NAME}.exe" if sys.platform == "win32" else NAME)
    print(f"\nBuilt {built}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
