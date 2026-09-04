"""How a reply gets from the bot into the game's chat box."""

from __future__ import annotations

import abc


class ChatSender(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def send(self, text: str, team_only: bool = False) -> tuple[bool, str]:
        """Return `(delivered, detail)`."""

    async def run_command(self, command: str) -> tuple[bool, str]:
        """Make the game run a console command. Return `(ran, detail)`."""
        return False, f"{self.name} cannot run console commands"

    def describe(self) -> str:
        return self.name


def chunk_message(text: str, limit: int) -> list[str]:
    """Split a reply into pieces CS2 will not truncate, preferring word boundaries."""
    if limit <= 0 or len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        split_at = window.rfind(" ")
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return [c for c in chunks if c]


def sanitize_for_console(text: str) -> str:
    """Make a reply safe to embed in a `say "..."` console command."""
    cleaned = text.replace('"', "''").replace("\n", " ").replace("\r", " ")
    cleaned = cleaned.replace(";", ",")  # `;` would end the console command
    return " ".join(cleaned.split())
