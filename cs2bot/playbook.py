"""Real strategies, one per round, for the Premier / FACEIT Active Duty pool.

These are the standard calls teams actually run - the shapes you see in pro demos and in
Metastack-style playbooks - written short enough to fit in one CS2 chat line. Nothing here is
generated: the model only ever rephrases a call from this book, so a bot with a bad model still
calls a real strat instead of inventing "smoke Long from Banana".

Each entry knows the map, the side, the site it hits or holds, and the buy it belongs to, so
"strat?" on an eco does not get an answer that needs five sets of utility.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

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
    call: str  # what goes into chat
    detail: str = ""  # the reasoning, given to the model, never sent on its own


def _t(map_name: str, name: str, site: str, buy: str, call: str, detail: str = "") -> Strategy:
    return Strategy(map_name, Team.T, name, site, buy, call, detail)


def _ct(map_name: str, name: str, site: str, buy: str, call: str, detail: str = "") -> Strategy:
    return Strategy(map_name, Team.CT, name, site, buy, call, detail)


PLAYBOOK: list[Strategy] = [
    # ---- Mirage ----------------------------------------------------------------
    _t("de_mirage", "Mid default", "mid", ANY,
       "default: smoke top mid + window, 2 mid 1 ladder, 1 palace 1 apps - decide the hit before "
       "ladder is taken",
       "Mirage rounds are won by defaults. Take mid, ladder and connector, but agree on the "
       "finish before the ladder player is in, or the round dies waiting."),
    _t("de_mirage", "A execute", "a", FULL,
       "A exec: smoke jungle, CT and stairs, flash over palace, 3 ramp 2 palace, trade the first "
       "entry",
       "The three-smoke A take: jungle and CT cut the rotate, stairs blinds connector. Palace and "
       "ramp enter on the same flash so the site is crossed at once."),
    _t("de_mirage", "B split through apps", "b", FULL,
       "B split: smoke market + short, molly bench, 2 through apps 2 through short, plant default",
       "Apps and short at the same time beats a single-side hold. Market smoke stops the CT "
       "spawn rotate seeing the plant."),
    _t("de_mirage", "Mid to B", "b", ANY,
       "mid to B: window smoke, take connector, then short into B - CTs are usually looking apps",
       "Once mid is yours, B through short arrives from the side the B anchor is not watching."),
    _t("de_mirage", "Pistol A rush", "a", PISTOL,
       "pistol: 4 palace 1 ramp, flash in together, spread the plant so the CT can't wipe it with "
       "one nade",
       "Numbers and armour beat utility on pistols. Palace has cover and a short walk to the "
       "default plant."),
    _ct("de_mirage", "Standard hold", "", ANY,
       "hold: AWP window, 1 connector 1 A default, apps drop + short - deny mid before it starts",
       "Window control is the whole map. Two players can hold A while the apps pair keeps Ts out "
       "of short."),
    _ct("de_mirage", "Apps aggression", "b", ANY,
       "apps: flash and swing early, then fall back to bench - don't hold the same spot twice",
       "The apps player has to alternate between pushing and holding, or the T side pre-aims and "
       "walks in for free."),
    _ct("de_mirage", "A retake", "a", ANY,
       "retake A: smoke the plant, flash from connector and stairs at the same time, one man clears "
       "sandwich",
       "Never trickle into a retake. Smoke the bomb, flash from two angles, enter together."),
    _ct("de_mirage", "Pistol stack B", "b", PISTOL,
       "pistol: 3 B, molly short, 2 hold A default and connector - B rushes lose to numbers",
       "Most pistol rounds are a B rush or a palace hit. Three in apps beats the rush; A still has "
       "a crossfire."),

    # ---- Inferno ---------------------------------------------------------------
    _t("de_inferno", "Banana control", "b", ANY,
       "banana: molly car and sandbags, flash over, take the top - we fight for banana every round",
       "Even A rounds start with banana. Owning it forces the CT rotate and opens the B execute."),
    _t("de_inferno", "B execute", "b", FULL,
       "B exec: smoke CT and coffins, molly dark and new box, flash over sandbags, 4 in 1 lurks mid",
       "The standard B take: CT smoke stops the rotate, dark and new box molly clears the two "
       "holds, entry goes on the flash."),
    _t("de_inferno", "A split", "a", FULL,
       "A split: smoke library and CT, molly pit, 3 apartments 2 short, trade off the balcony entry",
       "Apartments and short together stretch the two A defenders. Library smoke stops the "
       "rotate from B."),
    _t("de_inferno", "Fake B take A", "a", FULL,
       "fake B: 2 make noise banana with nades, 3 quiet through apps - hit A the second they rotate",
       "Inferno rotations are slow. Utility on banana reads as a full commit and drags the CTs "
       "away from A."),
    _t("de_inferno", "Eco banana stack", "b", ECO,
       "eco: 5 banana, molly car, rush the top together and plant fast - take the CT rifles",
       "On an eco you want the close fight and the guns that come with it."),
    _ct("de_inferno", "Banana denial", "b", ANY,
       "hold: early molly banana, then smoke to split them, 2 B, rotate through CT not over site",
       "Make banana cost utility every round, and never cross the open site while rotating."),
    _ct("de_inferno", "Apartments layers", "a", ANY,
       "A: 1 pit 1 short/arch, apps player alternates boiler push and balcony hold, save flashes "
       "for retake",
       "Layered A hold. The apps player is the info; pit and short trade for each other."),
    _ct("de_inferno", "B retake", "b", ANY,
       "retake B: smoke over the plant, molly the default, come from CT and banana together",
       "One-by-one retakes lose. Smoke the bomb, molly the likely plant spot, enter from two sides."),
    _ct("de_inferno", "Pistol B stack", "b", PISTOL,
       "pistol: 3 B with a molly for banana, 2 A - if they take banana, fall back and retake with "
       "the nade",
       "B is the pistol-round target on Inferno; the molly buys the time A needs to rotate."),

    # ---- Dust 2 ----------------------------------------------------------------
    _t("de_dust2", "Mid control default", "mid", ANY,
       "default: smoke doors and CT cross, 2 mid 2 long 1 short - open both sides before we pick one",
       "Breaking the mid AWP with doors and cross smokes is the whole T side; the split follows."),
    _t("de_dust2", "A split long + cat", "a", FULL,
       "A split: smoke CT and jungle, flash long doors, 3 long 2 cat, cross onto site together",
       "Long and cat at once means the A anchors cannot trade. CT smoke stops the spawn rotate."),
    _t("de_dust2", "B tunnels execute", "b", FULL,
       "B exec: smoke CT and door, flash out of upper tunnels, 4 out 1 mid lurk, plant back site",
       "Standard B take. The mid lurk stops the mid-doors rotate arriving into the plant."),
    _t("de_dust2", "Short to B", "b", ANY,
       "mid to B: doors smoke, take cat, then drop to B - the B anchor is watching tunnels",
       "Once mid is yours, B from short arrives behind the tunnel hold."),
    _t("de_dust2", "Pistol B rush", "b", PISTOL,
       "pistol: 5 tunnels, flash over, spread out on plant so one HE can't clear us",
       "Numbers into the close angles; B has the shortest path from T spawn."),
    _ct("de_dust2", "Layered A", "a", ANY,
       "A: AWP doors for the round start, long in layers - doors pick, then pit, then site",
       "Give up long in stages instead of dying to the first flash."),
    _ct("de_dust2", "B stall", "b", ANY,
       "B: keep a tunnel-exit smoke and a molly, 1 site 1 door, don't peek tunnels alone",
       "Two B players survive a rush by delaying with utility until the A player rotates."),
    _ct("de_dust2", "A retake", "a", ANY,
       "retake A: smoke the bomb, flash from cat and CT together, one clears goose",
       "Split the retake so the planter cannot hold both entries."),
    _ct("de_dust2", "Pistol mid pinch", "mid", PISTOL,
       "pistol: 2 mid, take doors early with a flash, 2 A 1 B - mid control kills their split",
       "Winning mid on the pistol denies both splits and gives the first rotation."),

    # ---- Anubis ----------------------------------------------------------------
    _t("de_anubis", "Water default", "mid", ANY,
       "default: presence in water every round, smoke top mid, 2 water 2 alley 1 palace",
       "Water control is the map. It opens connector and both sites."),
    _t("de_anubis", "A execute", "a", FULL,
       "A exec: smoke heaven and CT, flash over main, 3 main 2 connector, plant behind the pillar",
       "Heaven smoke removes the angle that holds the site; main and connector enter together."),
    _t("de_anubis", "B execute", "b", FULL,
       "B exec: smoke sniper and street, flash over gate, 4 in, second wave through palace",
       "Sniper and street smokes cut the two long holds; the palace second wave catches the retake."),
    _t("de_anubis", "Mid to A split", "a", ANY,
       "mid to A: take bridge and water, smoke off street, then split A from connector and main",
       "Once water is yours the CTs must choose which entrance to hold."),
    _t("de_anubis", "Eco water rush", "mid", ECO,
       "eco: 5 through water, flash up and take the close fights - don't cross open mid",
       "Water is the covered route: the fight happens where pistols can win."),
    _ct("de_anubis", "Fight mid", "mid", ANY,
       "hold: contest mid early with utility, 2 A heaven and tunnel, 2 B pillar and street support",
       "Giving up mid free on Anubis loses both sites at once."),
    _ct("de_anubis", "A layered hold", "a", ANY,
       "A: heaven holds the entry, second man falls back through tunnel, keep a molly for main",
       "Trade space for time; heaven is the angle that wins the first duel."),
    _ct("de_anubis", "B retake", "b", ANY,
       "retake B: smoke the plant, flash from palace and street, cross together",
       "The palace entry is the one the planter is least likely to be watching."),
    _ct("de_anubis", "Pistol A stack", "a", PISTOL,
       "pistol: 3 A with a molly for main, 2 mid - trade the entry and take the bomb fight",
       "A main is the pistol-round rush; the molly breaks the timing."),

    # ---- Ancient ---------------------------------------------------------------
    _t("de_ancient", "Patient default", "", ANY,
       "default: drain their utility first - 2 mid 2 donut 1 B ramp, no commit until nades are gone",
       "Ancient is chokepoints. Making the CTs spend utility on nothing is the strategy."),
    _t("de_ancient", "A execute", "a", FULL,
       "A exec: smoke CT lane and temple, flash both entrances, 3 main 2 donut, plant near the tree",
       "CT lane smoke isolates the site; main and donut enter on the same flash."),
    _t("de_ancient", "Fast B", "b", FULL,
       "fast B: smoke back halls, flash wave up ramp, 4 in, plant behind the pillar, 1 holds cave",
       "B is fast because rotations arrive through a single choke you can smoke."),
    _t("de_ancient", "Mid split", "mid", ANY,
       "mid: smoke elbow and cave, take mid, then split A from short and main",
       "Mid control gives you both A entrances and cuts the rotate."),
    _t("de_ancient", "Eco B rush", "b", ECO,
       "eco: 5 ramp, one flash over, take the site fight close and plant fast",
       "Close-range numbers is the eco plan on a map with short sightlines."),
    _ct("de_ancient", "Layered A", "a", ANY,
       "A: temple long hold plus a short/donut player, utility-only mid so the roamer stays free",
       "Two players and a roamer hold A if they hold different depths."),
    _ct("de_ancient", "B ramp molly", "b", ANY,
       "B: early molly ramp every round, 1 cave 1 site, rotate the roamer on the second contact",
       "The ramp molly is what stops the fast B before it starts."),
    _ct("de_ancient", "A retake", "a", ANY,
       "retake A: smoke the plant, flash from CT lane and donut, enter together not one by one",
       "Ancient retakes are lost to trickling in through the same door."),
    _ct("de_ancient", "Pistol B", "b", PISTOL,
       "pistol: 3 B with the molly on ramp, 2 A - the rush breaks on the fire and numbers",
       "The pistol-round rush is nearly always ramp."),

    # ---- Nuke ------------------------------------------------------------------
    _t("de_nuke", "Outside control", "b", ANY,
       "outside: smoke heaven and silo, take outside, then secret opens B - win outside, win the "
       "round",
       "Every good Nuke T side starts outside; secret and B follow from it."),
    _t("de_nuke", "A execute", "a", FULL,
       "A exec: smoke main and heaven, molly hut, entry squeaky and hut together, plant default",
       "Heaven smoke removes the angle that holds A; hut molly clears the anchor."),
    _t("de_nuke", "Vent drop off an A fake", "b", FULL,
       "fake A: 3 make noise in lobby and main, 2 drop vents - hit B when the rotate commits",
       "Nuke rotates in three seconds, so the vent drop only works behind real A noise."),
    _t("de_nuke", "Ramp to B", "b", ANY,
       "B: smoke and molly ramp control, take secret, then hit B from both ramp and secret",
       "Two entrances at once is the only way B falls."),
    _t("de_nuke", "Pistol A rush", "a", PISTOL,
       "pistol: 5 through lobby, flash squeaky, take the close fight and plant back site",
       "Lobby gets you into the site before the CTs can set a crossfire."),
    _ct("de_nuke", "Info chokes", "", ANY,
       "hold: play the chokes not the sites - squeaky, ramp and garage, AWP outside or main",
       "Nuke is held in the corridors; the sites are where you retake, not where you sit."),
    _ct("de_nuke", "Outside denial", "", ANY,
       "outside: contest it early with utility, then fall back to secret - never let them own it "
       "free",
       "Free outside control means B and secret are gone at the same time."),
    _ct("de_nuke", "B retake through vents", "b", ANY,
       "retake B: smoke the plant, one through vents one down ramp, rotate A player last",
       "Vents is the three-second rotate that makes the retake a crossfire."),
    _ct("de_nuke", "Pistol A stack", "a", PISTOL,
       "pistol: 3 A with a hut molly, 1 ramp 1 outside - lobby rush dies to fire and numbers",
       "The pistol rush is lobby into A almost every time."),

    # ---- Cache -----------------------------------------------------------------
    _t("de_cache", "Garage control", "b", ANY,
       "garage: take it every round - smoke CT, molly checkers, that is where the B hit starts",
       "Garage is the B lane and the mid pressure at the same time."),
    _t("de_cache", "A execute", "a", FULL,
       "A exec: smoke highway and truck, molly squeaky, hit both doors at once, plant behind quad",
       "Highway and truck smokes cut the rotate and the crossfire; both doors together beats the "
       "site hold."),
    _t("de_cache", "B execute", "b", FULL,
       "B exec: smoke heaven and CT, flash over B main, 4 in, one clears checkers, plant at "
       "sandbags",
       "Heaven smoke is the whole call - without it the B site cannot be crossed."),
    _t("de_cache", "Mid to A", "a", ANY,
       "mid: smoke white box and sandbags, take mid, boost or drop into A from squeaky",
       "Mid control opens A from the side the CTs are not holding."),
    _t("de_cache", "Eco vent B", "b", ECO,
       "eco: quiet through vents, all 5 into B, take the close fight and plant fast",
       "The vent drop is the covered route pistols can win from."),
    _ct("de_cache", "Mid AWP", "mid", ANY,
       "hold: AWP mid from white box or sandbags, 2 A crossfire, 1 B 1 garage",
       "Mid control from the CT side shuts down both executes."),
    _ct("de_cache", "A crossfire", "a", ANY,
       "A: one watches squeaky, one holds highway/truck - never both looking the same door",
       "The A hold only works as a crossfire between the two entrances."),
    _ct("de_cache", "B vent read", "b", ANY,
       "B: listen for the vent drop, molly it early, fall back to checkers and wait for the rotate",
       "The vent drop precedes most B hits, and the molly buys the rotation."),
    _ct("de_cache", "Pistol B stack", "b", PISTOL,
       "pistol: 3 B, 2 mid - deny garage early and the rush has nowhere to come from",
       "Garage denial is what breaks the pistol B rush."),

    # ---- Anywhere ---------------------------------------------------------------
    _t("", "Default", "", ANY,
       "default: spread out, take map control with utility, keep 1 lurking, decide the hit before "
       "the 45 second mark",
       "Generic T structure when the map is unknown."),
    _t("", "Eco", "", ECO,
       "eco: stack one site, all 5 together, take close fights and pick up their rifles",
       "Generic eco: numbers in one place."),
    _t("", "Force", "", ECO,
       "force: buy armour and utility, hit one site fast before their AWP is set",
       "Generic force buy plan."),
    _ct("", "Default hold", "", ANY,
       "hold: 2-1-2, contest map control early with utility, rotate on the second contact not the "
       "first",
       "Generic CT structure when the map is unknown."),
    _ct("", "Retake", "", ANY,
       "retake: smoke the bomb, flash from two sides, go together - nobody peeks alone",
       "Generic retake discipline."),
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


def call_text(strategy: Strategy) -> str:
    """The line that goes into chat."""
    return f"{strategy.name} - {strategy.call}"
