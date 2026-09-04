"""Restart the panel as administrator, which is what CS2 needs when it is elevated itself."""

from __future__ import annotations

import ctypes
import os
import sys

SW_SHOWNORMAL = 1
# ShellExecuteW returns a fake HINSTANCE; anything above this means it started something.
SHELL_SUCCESS = 32


def command_line() -> tuple[str, str]:
    """The program to start again and its arguments, frozen exe or `python -m cs2bot` alike."""
    if getattr(sys, "frozen", False):
        return sys.executable, " ".join(f'"{a}"' for a in sys.argv[1:])
    args = " ".join(f'"{a}"' for a in sys.argv)
    return sys.executable, args


def relaunch_as_admin() -> tuple[bool, str]:
    """Ask Windows to start this program again, elevated. Returns `(started, detail)`.

    The caller is expected to shut down afterwards: two panels cannot hold the same port.
    """
    try:
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
    except AttributeError:
        return False, "restarting as administrator only works on Windows"
    program, args = command_line()
    result = shell32.ShellExecuteW(None, "runas", program, args, os.getcwd(), SW_SHOWNORMAL)
    if result > SHELL_SUCCESS:
        return True, "starting again as administrator - this window will close"
    return False, "the administrator prompt was refused"
