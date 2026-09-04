"""Sender used off-Windows and while testing: records instead of typing."""

from __future__ import annotations

from .base import ChatSender


class DryRunSender(ChatSender):
    name = "dry_run"

    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []
        self.commands: list[str] = []

    async def send(self, text: str, team_only: bool = False) -> tuple[bool, str]:
        self.sent.append((text, team_only))
        return True, "dry run (not typed into the game)"

    async def run_command(self, command: str) -> tuple[bool, str]:
        self.commands.append(command)
        return False, "dry run (the game was not asked anything)"

    def describe(self) -> str:
        return "dry run - replies are shown in the web UI only"
