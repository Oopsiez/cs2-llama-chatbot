"""Append fake CS2 chat to a log file so the bot can be exercised without the game.

    python scripts/fake_match.py /tmp/console.log

Point the panel's console.log path at the same file, start the bot, and watch the feed.
"""

from __future__ import annotations

import argparse
import random
import time
from datetime import datetime
from pathlib import Path

LINES = [
    ("[ALL] {name}: ez", False),
    ("[ALL] {name}: who queued this map", False),
    ("[CT] {name}: rotate b, two smokes a", False),
    ("*DEAD* [ALL] {name}: gg wp", True),
    ("*DEAD* [ALL] {name}: he is behind boxes", True),
    ("[T] {name}: eco next round", False),
    ("*SPEC* {name}: nt", False),
]
NAMES = ["skelly", "b1ts", "noodle", "Pavel", "gooberr"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--interval", type=float, default=4.0)
    parser.add_argument("--count", type=int, default=0, help="0 = run forever")
    args = parser.parse_args()

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.touch()
    sent = 0
    while args.count == 0 or sent < args.count:
        template, _ = random.choice(LINES)
        line = template.format(name=random.choice(NAMES))
        stamp = datetime.now().strftime("%m/%d %H:%M:%S")
        with args.log.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  {line}\n")
        print(f"wrote: {line}")
        sent += 1
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
