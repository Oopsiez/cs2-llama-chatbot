"""CS2 Game State Integration: authoritative source for whether *we* are alive.

The console log tells us whether the *sender* of a message was dead (`*DEAD*`), but it says
nothing about the local player. GSI does: CS2 POSTs a JSON snapshot whenever state changes, and
`player.state.health == 0` means we are dead and our chat only reaches other dead players.

While spectating, `player` describes the observed player, so we only trust it when
`player.steamid == provider.steamid`.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .callouts import Position
from .models import LifeState, LocalPlayer, Team

GSI_CFG_NAME = "gamestate_integration_cs2bot.cfg"

_TEAMS = {"CT": Team.CT, "T": Team.T}


class GameStateStore:
    """Holds the latest local player snapshot posted by CS2."""

    def __init__(self) -> None:
        self.player = LocalPlayer()
        self.last_payload: dict[str, Any] | None = None

    def update(self, payload: dict[str, Any]) -> LocalPlayer:
        self.last_payload = payload
        provider = payload.get("provider") or {}
        player = payload.get("player") or {}
        round_info = payload.get("map") or {}
        round_state = payload.get("round") or {}
        bomb = payload.get("bomb") or {}

        snapshot = LocalPlayer(
            name=self.player.name,
            steam_id=str(provider.get("steamid") or self.player.steam_id),
            team=self.player.team,
            state=self.player.state,
            health=self.player.health,
            round_phase=str(round_state.get("phase") or ""),
            map_phase=str(round_info.get("phase") or ""),
            map_name=str(round_info.get("name") or ""),
            mode=str(round_info.get("mode") or ""),
            position=self.player.position,
            active_weapon=self.player.active_weapon,
            bomb=str(bomb.get("state") or round_state.get("bomb") or ""),
            round_number=int(round_info.get("round") or 0),
            updated_at=time.time(),
        )

        is_local = bool(player) and (
            not provider.get("steamid") or str(player.get("steamid")) == str(provider.get("steamid"))
        )
        if is_local:
            snapshot.name = str(player.get("name") or snapshot.name)
            snapshot.team = _TEAMS.get(str(player.get("team") or ""), Team.SPECTATOR)
            health = (player.get("state") or {}).get("health")
            if health is None:
                snapshot.state = LifeState.UNKNOWN
            else:
                snapshot.health = int(health)
                snapshot.state = LifeState.ALIVE if int(health) > 0 else LifeState.DEAD
            snapshot.position = Position.parse(player.get("position")) or snapshot.position
            snapshot.active_weapon = _active_weapon(player) or snapshot.active_weapon

        self.player = snapshot
        return snapshot

    def local_state(self, assume_alive_without_gsi: bool = True) -> LifeState:
        if self.player.is_stale or self.player.state is LifeState.UNKNOWN:
            return LifeState.ALIVE if assume_alive_without_gsi else LifeState.UNKNOWN
        return self.player.state


def _active_weapon(player: dict[str, Any]) -> str:
    """The weapon currently in the player's hands, out of the `weapon_0`/`weapon_1`/... map."""
    weapons = player.get("weapons")
    if not isinstance(weapons, dict):
        return ""
    for weapon in weapons.values():
        if isinstance(weapon, dict) and weapon.get("state") == "active":
            name = str(weapon.get("name") or "")
            return name.removeprefix("weapon_")
    return ""


def render_gsi_cfg(endpoint: str, auth_token: str = "") -> str:
    """The `gamestate_integration_*.cfg` CS2 needs in order to POST state to us."""
    auth_block = ""
    if auth_token:
        auth_block = f'    "auth"\n    {{\n        "token" "{auth_token}"\n    }}\n'
    return (
        '"cs2bot"\n'
        "{\n"
        f'    "uri" "{endpoint}"\n'
        '    "timeout" "5.0"\n'
        '    "buffer" "0.1"\n'
        '    "throttle" "0.1"\n'
        '    "heartbeat" "10.0"\n'
        f"{auth_block}"
        '    "data"\n'
        "    {\n"
        '        "provider" "1"\n'
        '        "map" "1"\n'
        '        "round" "1"\n'
        '        "player_id" "1"\n'
        '        "player_state" "1"\n'
        '        "player_weapons" "1"\n'
        '        "player_position" "1"\n'
        '        "bomb" "1"\n'
        '        "player_match_stats" "1"\n'
        "    }\n"
        "}\n"
    )


def gsi_endpoint(port: int) -> str:
    """Where CS2 posts state. Always loopback: CS2 posts from the same machine, and a panel
    bound to 0.0.0.0 so a phone can reach it must not put 0.0.0.0 in the game's config."""
    return f"http://127.0.0.1:{port}/api/gsi"


def inspect_gsi_cfg(cfg_dir: str | Path, endpoint: str, auth_token: str = "") -> list[str]:
    """Everything wrong with the GSI configs on disk, in the order worth fixing.

    An empty list means CS2 has been told to post to us; it says nothing about whether it has.
    """
    problems: list[str] = []
    if not str(cfg_dir).strip():
        return ["the CS2 cfg directory is not set on the Game tab"]

    directory = Path(cfg_dir)
    if not directory.is_dir():
        return [f"{directory} does not exist - point the cfg directory at .../game/csgo/cfg"]
    if directory.name != "cfg" or directory.parent.name != "csgo":
        problems.append(
            f"{directory} is not .../game/csgo/cfg - CS2 only reads GSI configs from that folder"
        )

    ours = directory / GSI_CFG_NAME
    if not ours.is_file():
        others = sorted(p.name for p in directory.glob("gamestate_integration_*.cfg"))
        problems.append(
            f"{GSI_CFG_NAME} is not installed"
            + (f" (found {', '.join(others)} instead)" if others else "")
        )
        return problems

    text = ours.read_text(encoding="utf-8", errors="replace")
    if endpoint not in text:
        problems.append(
            f"{ours.name} does not point at {endpoint} - the panel's port changed since it was "
            "installed, so reinstall it"
        )
    if auth_token and f'"{auth_token}"' not in text:
        problems.append(f"{ours.name} carries a different auth token - reinstall it")
    return problems


def install_gsi_cfg(cfg_dir: str | Path, endpoint: str, auth_token: str = "") -> Path:
    directory = Path(cfg_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / GSI_CFG_NAME
    target.write_text(render_gsi_cfg(endpoint, auth_token), encoding="utf-8")
    return target
