"""Turn the raw world coordinates GSI reports into a name a human would say in chat.

CS2's Game State Integration gives the local player's position as three world-space numbers and
nothing else - no callout, no region name. Valve does not publish the callout volumes, and
guessing them per map would be inventing data, so the map is learned instead: stand somewhere in
game, name it in the panel, and that point is remembered for that map. A position then resolves
to the nearest recorded point within its radius.

Coordinates are compared with the vertical axis scaled down, because two floors of the same site
are far apart in the way that matters even when `z` differs by less than the radius.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

# One unit is roughly an inch; ~400 covers a callout-sized area without swallowing the next one.
DEFAULT_RADIUS = 400.0
# A staircase is a short horizontal distance but a different callout, so height counts for more.
HEIGHT_WEIGHT = 2.0


class Callout(BaseModel):
    """A named spot on a map, recorded by standing there."""

    name: str
    x: float
    y: float
    z: float
    radius: float = DEFAULT_RADIUS


class Position(BaseModel):
    x: float
    y: float
    z: float

    @classmethod
    def parse(cls, value: object) -> Position | None:
        """GSI sends `"1234.00, -567.00, 128.03"`; anything else is not a position."""
        if isinstance(value, str):
            parts = value.split(",")
        elif isinstance(value, (list, tuple)):
            parts = [str(part) for part in value]
        else:
            return None
        if len(parts) != 3:
            return None
        try:
            x, y, z = (float(str(part).strip()) for part in parts)
        except ValueError:
            return None
        return cls(x=x, y=y, z=z)

    def distance_to(self, callout: Callout) -> float:
        return math.sqrt(
            (self.x - callout.x) ** 2
            + (self.y - callout.y) ** 2
            + (HEIGHT_WEIGHT * (self.z - callout.z)) ** 2
        )


class CalloutBook(BaseModel):
    """Recorded callouts, keyed by map name (`de_dust2`)."""

    maps: dict[str, list[Callout]] = Field(default_factory=dict)

    def for_map(self, map_name: str) -> list[Callout]:
        return self.maps.get(map_name.strip().casefold(), [])

    def record(self, map_name: str, callout: Callout) -> None:
        """Add a callout, replacing any earlier one with the same name on that map."""
        key = map_name.strip().casefold()
        kept = [c for c in self.maps.get(key, []) if c.name.casefold() != callout.name.casefold()]
        self.maps[key] = kept + [callout]

    def forget(self, map_name: str, name: str) -> bool:
        key = map_name.strip().casefold()
        existing = self.maps.get(key, [])
        remaining = [c for c in existing if c.name.casefold() != name.casefold()]
        if len(remaining) == len(existing):
            return False
        if remaining:
            self.maps[key] = remaining
        else:
            del self.maps[key]
        return True

    def resolve(self, map_name: str, position: Position | None) -> str:
        """The name of the spot the player is standing in, or "" when nothing is close."""
        if position is None:
            return ""
        nearest = ""
        best = math.inf
        for callout in self.for_map(map_name):
            distance = position.distance_to(callout)
            if distance <= callout.radius and distance < best:
                nearest, best = callout.name, distance
        return nearest
