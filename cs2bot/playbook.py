"""Real strategies, one per round, for the Premier / FACEIT Active Duty pool.

These are the standard calls teams actually run - the shapes you see in pro demos and in
Metastack-style playbooks. Nothing here is generated: the model only ever rephrases a call from
this book, so a bot with a bad model still calls a real strat instead of inventing "smoke Long
from Banana".

A real call does not fit in one CS2 chat line, so each strategy is written as an ordered set of
steps - utility, then the movement, then what happens after the plant or on the retake - and the
bot says them as consecutive lines. `detail` is the reasoning behind the call: it is given to the
model as context and never said on its own.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .models import Team

# Premier / FACEIT Active Duty as of Season 5 (Cache replaced Overpass in July 2026).
ACTIVE_DUTY = {
    "de_mirage": "Mirage",
    "de_inferno": "Inferno",
    "de_dust2": "Dust 2",
    "de_anubis": "Anubis",
    "de_ancient": "Ancient",
    "de_nuke": "Nuke",
    "de_cache": "Cache",
}

# Buys a call is written for. `any` fits whatever the round is.
ANY, PISTOL, ECO, FULL = "any", "pistol", "eco", "full"


@dataclass(frozen=True)
class Strategy:
    map_name: str  # "" for the calls that work anywhere
    side: Team
    name: str
    site: str  # a | b | mid | ""
    buy: str
    steps: tuple[str, ...] = field(default_factory=tuple)  # said one chat line at a time
    detail: str = ""  # the reasoning, given to the model, never sent on its own

    @property
    def call(self) -> str:
        """The whole plan as one string, for prompts and for the panel."""
        return " ".join(self.steps)


def _t(map_name: str, name: str, site: str, buy: str, *steps: str, why: str = "") -> Strategy:
    return Strategy(map_name, Team.T, name, site, buy, tuple(steps), why)


def _ct(map_name: str, name: str, site: str, buy: str, *steps: str, why: str = "") -> Strategy:
    return Strategy(map_name, Team.CT, name, site, buy, tuple(steps), why)


PLAYBOOK: list[Strategy] = [
    # ---- Mirage ----------------------------------------------------------------
    _t("de_mirage", "Mid default", "mid", ANY,
       "util: smoke top mid and window, flash over for the ladder man",
       "setup: 2 mid, 1 ladder, 1 palace, 1 apps - trade the mid duel, don't lose it for free",
       "then: call the hit before ladder is taken - A off connector, or short into B",
       why="Mirage rounds are won by defaults. Take mid, ladder and connector, but agree on the "
           "finish before the ladder player is in, or the round dies waiting."),
    _t("de_mirage", "A execute", "a", FULL,
       "util: smoke jungle, CT and stairs - one flash over palace on the count",
       "go: 3 ramp, 2 palace, both sides cross on the same flash and trade the entry",
       "then: plant default, one holds jungle, one CT, one back in palace for the retake",
       why="The three-smoke A take: jungle and CT cut the rotate, stairs blinds connector. Palace "
           "and ramp enter together so the site is crossed at once."),
    _t("de_mirage", "B split through apps", "b", FULL,
       "util: smoke market and short, molly bench, flash into apps",
       "go: 2 through apps, 2 through short at the same time - one lurks mid for the rotate",
       "then: plant default behind the boxes, hold apps and van for the retake",
       why="Apps and short at the same time beats a single-side hold. The market smoke stops the "
           "CT spawn rotate from seeing the plant."),
    _t("de_mirage", "Mid to B", "b", ANY,
       "util: window smoke first, then take connector before anything else",
       "go: through short into B - the anchor is looking apps, not short",
       "then: fast plant, one man back in short so the rotate walks into a crossfire",
       why="Once mid is yours, B through short arrives from the side the B anchor is not "
           "watching."),
    _t("de_mirage", "Pistol A rush", "a", PISTOL,
       "go: 4 palace, 1 ramp, flashes in together and swing as a group",
       "then: spread the plant so one nade can't clear it, one man palace for the retake",
       why="Numbers and armour beat utility on pistols. Palace has cover and a short walk to the "
           "default plant."),
    _ct("de_mirage", "Standard hold", "", ANY,
       "setup: AWP window, 1 connector, 1 A default, 2 on B - apps drop and short",
       "util: deny mid before it starts - smoke or molly top mid the moment you hear it",
       "then: rotate on the second contact, not the first, and always through CT",
       why="Window control is the whole map. Two players hold A while the apps pair keeps Ts out "
           "of short."),
    _ct("de_mirage", "Apps aggression", "b", ANY,
       "setup: apps player flashes and swings early, second man holds bench",
       "then: never hold the same spot twice in a row - alternate push and fall back",
       why="The apps player has to alternate between pushing and holding, or the T side pre-aims "
           "and walks in for free."),
    _ct("de_mirage", "A retake", "a", ANY,
       "util: smoke on top of the bomb, flash from connector and stairs at the same time",
       "go: enter together, one man clears sandwich and triple, nobody peeks alone",
       why="Never trickle into a retake. Smoke the bomb, flash from two angles, enter together."),
    _ct("de_mirage", "Pistol stack B", "b", PISTOL,
       "setup: 3 B, molly short on the first noise, 2 hold A default and connector",
       "then: if it is quiet on B by 40 seconds, send one to connector for the A rotate",
       why="Most pistol rounds are a B rush or a palace hit. Three in apps beats the rush; A "
           "still has a crossfire."),

    # ---- Inferno ---------------------------------------------------------------
    _t("de_inferno", "Banana control", "b", ANY,
       "util: molly car and sandbags, flash over the top for the first man",
       "go: take the top of banana as a pair and hold it - we fight for banana every round",
       "then: with banana ours, either execute B or send 3 to apps while 2 hold it",
       why="Even A rounds start with banana. Owning it forces the CT rotate and opens the B "
           "execute."),
    _t("de_inferno", "B execute", "b", FULL,
       "util: smoke CT and coffins, molly dark and new box",
       "go: flash over sandbags, 4 in together, 1 lurks mid for the rotate",
       "then: plant for banana, hold coffins and the CT smoke as it fades",
       why="The standard B take: CT smoke stops the rotate, dark and new box molly clears the two "
           "holds, entry goes on the flash."),
    _t("de_inferno", "A split", "a", FULL,
       "util: smoke library and CT, molly pit, flash into balcony",
       "go: 3 through apartments, 2 short - the balcony entry gets traded immediately",
       "then: plant at graveyard, one man back in apps, one watching library as it opens",
       why="Apartments and short together stretch the two A defenders. The library smoke stops "
           "the rotate from B."),
    _t("de_inferno", "Fake B take A", "a", FULL,
       "go: 2 make noise on banana - molly, flash, a few shots, nothing more",
       "then: 3 walk quiet through apps and hit A the second the CTs rotate to B",
       why="Inferno rotations are slow. Utility on banana reads as a full commit and drags the "
           "CTs away from A."),
    _t("de_inferno", "Eco banana stack", "b", ECO,
       "go: all 5 banana, molly car, rush the top together and take the close fight",
       "then: plant fast and pick up their rifles - the guns are the point of the round",
       why="On an eco you want the close fight and the guns that come with it."),
    _ct("de_inferno", "Banana denial", "b", ANY,
       "util: early molly banana every round, then smoke to split them when they commit",
       "setup: 2 on B, rotate through CT and never across the open site",
       why="Make banana cost utility every round, and never cross the open site while rotating."),
    _ct("de_inferno", "Apartments layers", "a", ANY,
       "setup: 1 pit, 1 short or arch, 1 apps alternating boiler push and balcony hold",
       "then: save flashes for the retake - do not spend them holding",
       why="Layered A hold. The apps player is the info; pit and short trade for each other."),
    _ct("de_inferno", "B retake", "b", ANY,
       "util: smoke over the plant, molly the default spot before you enter",
       "go: come from CT and banana at the same time, not one after the other",
       why="One-by-one retakes lose. Smoke the bomb, molly the likely plant spot, enter from two "
           "sides."),
    _ct("de_inferno", "Pistol B stack", "b", PISTOL,
       "setup: 3 B with a molly for car, 2 A holding pit and short",
       "then: the A pair rotates on the first contact - pistol B takes are all-in",
       why="The pistol round B rush is the most common opening on Inferno."),

    # ---- Dust 2 ----------------------------------------------------------------
    _t("de_dust2", "Mid control default", "mid", ANY,
       "util: smoke doors and CT cross, flash for the mid man",
       "setup: 2 mid, 2 long, 1 short - open both sides before we pick one",
       "then: whichever side gives first, commit 4 there and lurk the other",
       why="Breaking the mid AWP with doors and cross smokes is the whole T side; the split "
           "follows."),
    _t("de_dust2", "A split long + cat", "a", FULL,
       "util: smoke CT and jungle, molly goose and the corner of long",
       "go: 3 long, 2 cat, cross on the same flash so the site is hit from both sides",
       "then: plant long side, one man cat, one holding CT as the smoke fades",
       why="A single-side A take loses to the CT crossfire; long and cat together does not."),
    _t("de_dust2", "B tunnels execute", "b", FULL,
       "util: smoke B doors and window, molly the back plat and the corner",
       "go: flash into upper tunnels and swing out as a group of 4, 1 lurks mid",
       "then: plant behind the double stack, hold tunnels and car",
       why="B is a tight take: the doors smoke stops the CT spawn rotate and the mollies clear "
           "the two anchor spots."),
    _t("de_dust2", "Short to B", "b", ANY,
       "go: take cat with a flash, then drop into B through the doors, not tunnels",
       "then: the B anchor is watching tunnels - plant fast and hold the angle they rotate into",
       why="Coming into B from cat arrives behind the tunnel hold."),
    _t("de_dust2", "Pistol B rush", "b", PISTOL,
       "go: 5 upper tunnels, flashes over, swing together and take the trade fights",
       "then: spread the plant, one man holds tunnels for the CT rotate",
       why="Two CTs cannot hold B against five with flashes on the pistol round."),
    _ct("de_dust2", "Default 2-1-2", "", ANY,
       "setup: 2 A (long and goose), 1 mid with the AWP, 2 B",
       "util: contest long and mid early with utility, then fall back to the site",
       "then: rotate through CT spawn on confirmed contact only",
       why="The standard hold. Mid control decides which rotate is possible."),
    _ct("de_dust2", "Long aggression", "a", ANY,
       "setup: long player takes the pit early with a flash, second man in goose to trade",
       "then: if long is quiet, fall back - do not hold pit twice in a row",
       why="Free long control is how T sides get their A executes for nothing."),
    _ct("de_dust2", "B retake", "b", ANY,
       "util: smoke the plant from CT, molly the double stack",
       "go: enter from tunnels and doors together, trade the first man",
       why="Retaking B one at a time through doors is how B rounds are lost."),
    _ct("de_dust2", "Pistol A long stack", "a", PISTOL,
       "setup: 3 A holding long, goose and CT, 2 B with a mid rotate",
       "then: molly long the moment you hear the double doors go",
       why="Pistol long takes fold to numbers and a molly."),

    # ---- Anubis ----------------------------------------------------------------
    _t("de_anubis", "Water default", "mid", ANY,
       "util: smoke top mid, flash for the water man",
       "setup: 2 water, 2 alley, 1 palace - presence in water every round",
       "then: water into connector opens both sites - call the hit once it is ours",
       why="Water control is the map. It opens connector and both sites."),
    _t("de_anubis", "A execute", "a", FULL,
       "util: smoke connector and heaven, molly the corner behind the boxes",
       "go: 3 through palace, 2 through water, flash and cross together",
       "then: plant back site, hold palace and the water flank",
       why="The A take needs the connector smoke or the CT rotate arrives before the plant."),
    _t("de_anubis", "B execute", "b", FULL,
       "util: smoke bridge and connector, molly the back corner",
       "go: 4 through canals and street, 1 holds water for the mid rotate",
       "then: plant behind the pillar, one man watches bridge",
       why="B is taken from canals with the bridge cut off - otherwise the rotate is instant."),
    _t("de_anubis", "Mid to B split", "b", ANY,
       "go: take water and connector first, then hit B from connector and street together",
       "then: fast plant, hold connector against the rotate",
       why="Connector control turns any B hit into a split."),
    _t("de_anubis", "Pistol B rush", "b", PISTOL,
       "go: 5 through canals with flashes, take the close fights on site",
       "then: spread the plant and hold from two sides",
       why="Anubis pistol rounds reward the fast site take with numbers."),
    _ct("de_anubis", "Water denial", "", ANY,
       "util: molly water early every round, smoke top mid when they commit",
       "setup: 2 A, 1 mid, 2 B - the mid man is info, not a duel",
       why="If the T side gets water for free they get the whole map for free."),
    _ct("de_anubis", "A layered hold", "a", ANY,
       "setup: 1 heaven, 1 back site, palace watched with a molly not a body",
       "then: fall back and retake with the mid player rather than dying on site",
       why="A is too open to hold from the front; layers and a retake win it."),
    _ct("de_anubis", "B retake", "b", ANY,
       "util: smoke the bomb, molly the pillar",
       "go: come from bridge and connector at the same time",
       why="Bridge alone is a one-by-one retake and loses."),
    _ct("de_anubis", "Pistol stack B", "b", PISTOL,
       "setup: 3 B, 2 A - molly canals on the first sound",
       why="The canals rush is the standard Anubis pistol."),

    # ---- Ancient ---------------------------------------------------------------
    _t("de_ancient", "Patient default", "", ANY,
       "setup: 2 mid, 2 donut, 1 B ramp - take space, do not commit",
       "then: drain their utility first, no site hit until the nades are gone",
       "finally: call the execute with 30 seconds left, not 90",
       why="Ancient is chokepoints. Making the CTs spend utility on nothing is the strategy."),
    _t("de_ancient", "A execute", "a", FULL,
       "util: smoke CT and donut, molly the temple corner, flash over the boxes",
       "go: 4 through main on the flash, 1 holds mid for the rotate",
       "then: plant behind temple, hold donut and CT",
       why="A main is a death trap without the CT smoke and the corner molly."),
    _t("de_ancient", "B split from cave and ramp", "b", FULL,
       "util: smoke CT and heaven, molly the back of site",
       "go: 3 ramp, 2 cave, both in on the same flash",
       "then: plant at the pillar, hold cave and the ramp flank",
       why="Ramp alone is held by one man with utility; cave at the same time is not."),
    _t("de_ancient", "Mid control into B", "b", ANY,
       "go: smoke mid, take it with 3, then drop into B from cave",
       "then: fast plant and hold the CT rotate from the side",
       why="Mid is the fastest route to B and the one CTs watch last."),
    _t("de_ancient", "Eco A rush", "a", ECO,
       "go: 5 through main, flashes over, take the close fight on site",
       why="Main is short - an eco rush arrives before the utility does."),
    _ct("de_ancient", "Chokepoint hold", "", ANY,
       "setup: 2 A, 1 mid, 2 B - hold main and ramp with utility, not with bodies",
       "then: rotate late through CT, never across the open middle of the site",
       why="Both site entrances are narrow; utility holds them cheaper than players do."),
    _ct("de_ancient", "Mid denial", "mid", ANY,
       "util: molly and flash mid early, then fall back to donut",
       "then: give mid up rather than lose the man who holds the A rotate",
       why="Losing mid is survivable; losing the mid player is not."),
    _ct("de_ancient", "B retake", "b", ANY,
       "util: smoke the plant, molly the pillar and the back corner",
       "go: enter from CT and cave together",
       why="B has two ways in for the retake - use both or do not retake."),
    _ct("de_ancient", "Pistol A stack", "a", PISTOL,
       "setup: 3 A holding main and donut, 2 B - molly main on the first contact",
       why="The A main rush is the standard Ancient pistol."),

    # ---- Nuke ------------------------------------------------------------------
    _t("de_nuke", "Outside control", "b", ANY,
       "util: smoke heaven and the silo angle, molly the corner of garage",
       "setup: 3 outside, 2 lobby - take outside before anything else",
       "then: outside gives B, secret and the ramp flank - pick one once it is ours",
       why="Every good Nuke T side starts outside; secret and B follow from it."),
    _t("de_nuke", "A execute", "a", FULL,
       "util: smoke main and heaven, molly hut",
       "go: entry squeaky and hut at the same time, trade the first man",
       "then: plant default, one man holds heaven and one watches ramp",
       why="The heaven smoke removes the angle that holds A; the hut molly clears the anchor."),
    _t("de_nuke", "Vent drop off an A fake", "a", FULL,
       "go: 2 make noise in A main with utility, 3 quiet through vents",
       "then: drop as the CTs commit to main, take the site from behind",
       why="Nuke defenders read main utility as the commit and turn away from vents."),
    _t("de_nuke", "B through secret", "b", FULL,
       "util: smoke ramp and the back of B, molly the double doors",
       "go: 3 secret, 2 hold outside so the ramp rotate is cut",
       "then: plant back site and hold secret",
       why="Secret arrives behind the ramp hold, which is where B defenders look."),
    _t("de_nuke", "Pistol A rush", "a", PISTOL,
       "go: 5 through lobby and squeaky, flashes in, take the close fights",
       why="Pistol A takes work because heaven has no utility to stop five players."),
    _ct("de_nuke", "Standard A hold", "a", ANY,
       "setup: 1 heaven, 1 hut, 1 ramp, 2 outside or lobby",
       "util: molly and smoke outside early - never let them set up for free",
       "then: rotate down through ramp, not across the site",
       why="Nuke is held above the site; outside pressure decides the round."),
    _ct("de_nuke", "Outside pressure", "", ANY,
       "setup: 2 outside with an AWP on the silo angle, flash and fall back on contact",
       "then: trade out and reset - do not lose two players outside",
       why="Cheap outside pressure is what stops the whole T side plan."),
    _ct("de_nuke", "B retake from ramp and vents", "b", ANY,
       "util: smoke the plant, molly the back corner",
       "go: come down ramp and through vents at the same time",
       why="A ramp-only retake on B is a one-by-one and loses."),
    _ct("de_nuke", "Pistol lobby denial", "a", PISTOL,
       "setup: 3 A holding hut, heaven and squeaky, 2 in lobby with flashes",
       why="Lobby pressure breaks the pistol rush before it reaches the site."),

    # ---- Cache -----------------------------------------------------------------
    _t("de_cache", "Mid to A default", "a", ANY,
       "util: smoke CT and highway, flash for the mid man",
       "setup: 2 mid, 2 A main, 1 squeaky - take mid boost or mid box first",
       "then: A main and mid together once mid is ours",
       why="Cache A takes are mid takes; main alone walks into the crossfire."),
    _t("de_cache", "A execute", "a", FULL,
       "util: smoke CT, highway and quad, molly the truck corner",
       "go: 3 A main, 2 mid, in on the same flash",
       "then: plant at truck, hold quad and highway for the retake",
       why="The four-utility A take: quad and CT smokes cut both rotates."),
    _t("de_cache", "B execute from checkers", "b", FULL,
       "util: smoke CT and squeaky, molly the back of site and the corner",
       "go: 4 through checkers on the flash, 1 lurks mid",
       "then: plant behind the boxes, hold checkers and the heaven angle",
       why="B is taken from checkers with heaven and CT cut off, or the rotate is instant."),
    _t("de_cache", "Sunroom split", "b", FULL,
       "go: 2 into sunroom, 3 checkers, hit B from both at the same time",
       "then: fast plant and hold the vent side",
       why="Sunroom and checkers together beats a single-entrance B take."),
    _t("de_cache", "Pistol A rush", "a", PISTOL,
       "go: 5 through A main with flashes, swing as a group and trade",
       why="Numbers through main beat the two-man pistol hold."),
    _ct("de_cache", "Standard hold", "", ANY,
       "setup: 2 A (quad and truck), 1 mid, 2 B (heaven and site)",
       "util: contest mid early with utility, then play the site",
       "then: rotate through CT on the second contact",
       why="Mid decides both sites on Cache; deny it and both takes get harder."),
    _ct("de_cache", "Mid aggression", "mid", ANY,
       "go: flash and take mid boost early, then fall back before their utility lands",
       why="Free mid is a free A execute for the T side."),
    _ct("de_cache", "B retake", "b", ANY,
       "util: smoke the plant, molly the boxes",
       "go: come from heaven and CT together",
       why="Heaven alone is a one-by-one retake."),
    _ct("de_cache", "Pistol B stack", "b", PISTOL,
       "setup: 3 B holding checkers and heaven, 2 A with a mid rotate",
       why="The checkers rush is the standard Cache pistol."),

    # ---- Anywhere ---------------------------------------------------------------
    _t("", "Default", "", ANY,
       "setup: spread out, take map control with utility, keep 1 lurking",
       "then: decide the hit before the 45 second mark and go together",
       why="Generic T structure when the map is unknown."),
    _t("", "Eco", "", ECO,
       "go: stack one site, all 5 together, take the close fights",
       "then: pick up their rifles before you plant",
       why="Generic eco: numbers in one place."),
    _t("", "Force", "", ECO,
       "go: armour and utility, hit one site fast before their AWP is set",
       why="Generic force buy plan."),
    _ct("", "Default hold", "", ANY,
       "setup: 2-1-2, contest map control early with utility",
       "then: rotate on the second contact, not the first",
       why="Generic CT structure when the map is unknown."),
    _ct("", "Retake", "", ANY,
       "util: smoke the bomb, flash from two sides",
       "go: enter together - nobody peeks alone",
       why="Generic retake discipline."),
]


def normalise_map(name: str) -> str:
    """`Mirage`, `de_mirage`, `workshop/123/de_mirage` -> `de_mirage`."""
    cleaned = name.strip().lower().rsplit("/", 1)[-1]
    if cleaned in ACTIVE_DUTY:
        return cleaned
    squashed = cleaned.replace(" ", "")
    if f"de_{squashed}" in ACTIVE_DUTY:
        return f"de_{squashed}"
    return ""


def map_label(map_name: str) -> str:
    return ACTIVE_DUTY.get(normalise_map(map_name), "")


def strategies_for(map_name: str, side: Team) -> list[Strategy]:
    """Every call for a map and side, falling back to the map-agnostic ones."""
    key = normalise_map(map_name)
    on_map = [s for s in PLAYBOOK if s.map_name == key and s.side is side] if key else []
    return on_map or [s for s in PLAYBOOK if not s.map_name and s.side is side]


def pick(
    map_name: str,
    side: Team,
    site: str = "",
    buy: str = ANY,
    avoid: list[str] | None = None,
    rng: random.Random | None = None,
) -> Strategy | None:
    """The call to make: the asked-for site and buy where possible, and not the last one used."""
    options = strategies_for(map_name, side)
    if not options:
        return None
    if site:
        options = [s for s in options if s.site == site] or options
    if buy != ANY:
        # A pistol or eco round rules out the calls that need a full set of utility.
        options = [s for s in options if s.buy in (buy, ANY)] or options
    else:
        options = [s for s in options if s.buy in (ANY, FULL)] or options
    fresh = [s for s in options if s.name not in (avoid or [])]
    return (rng or random).choice(fresh or options)


def call_lines(strategy: Strategy, max_lines: int = 4) -> list[str]:
    """The strat as consecutive chat lines: a header, then a step per line."""
    header = strategy.name
    if label := map_label(strategy.map_name):
        header = f"{label} {strategy.side.value}: {strategy.name}"
    steps = list(strategy.steps)
    if max_lines > 0 and len(steps) > max_lines - 1:
        # Everything that will not fit joins the last line rather than being dropped.
        keep = max(max_lines - 2, 0)
        steps = steps[:keep] + [" ".join(steps[keep:])]
    return [header, *steps]


def call_text(strategy: Strategy) -> str:
    """The whole call on one line, for the panel and the model."""
    return " | ".join(call_lines(strategy, max_lines=0))
