"""Entry point for the frozen build.

PyInstaller runs its entry script as a top-level `__main__` with no package around it, so freezing
`cs2bot/__main__.py` directly makes its `from .config import ...` fail before anything is drawn.
This imports the package properly instead.

It also keeps the console open when something goes wrong: a double-clicked exe that crashes
otherwise vanishes with the error, and the user has nothing to report.
"""

from __future__ import annotations

import sys
import traceback

from cs2bot.__main__ import main


def run() -> int:
    try:
        main()
    except KeyboardInterrupt:
        return 0
    except Exception:
        traceback.print_exc()
        print("\nCS2 Chatbot could not start. Copy the error above into a GitHub issue:")
        print("https://github.com/Oopsiez/cs2-llama-chatbot/issues")
        if hasattr(sys, "frozen"):
            input("\nPress Enter to close this window. ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
