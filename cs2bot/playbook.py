"""Real strategies, one per round, for the Premier / FACEIT Active Duty pool.

These are the standard calls teams actually run - the shapes you see in pro demos and in
Metastack-style playbooks. Nothing here is generated: the model only ever rephrases a call from
this book, so a bot with a bad model still calls a real strat instead of inventing "smoke Long
from Banana".

A call is written as five jobs, one per player, because "smoke this or that" is not a strat. Each
job says where the player stands, what utility they throw, when they move and what they hold after
the plant, so the call answers who covers what and where. The bot says them as consecutive chat
lines, one player per line, using teammates' names when it knows them. `detail` is the reasoning
behind the call: it is given to the model as context and never said on its own.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
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
class Job:
    """One player's round: where they start, and what they are responsible for."""

    spot: str  # where they play it from - "palace", "banana", "heaven"
    task: str  # utility, timing, and what they hold afterwards

    @property
    def line(self) -> str:
        return f"{self.spot}: {self.task}"


@dataclass(frozen=True)
class Strategy:
    map_name: str  # "" for the calls that work anywhere
    side: Team
    name: str
    site: str  # a | b | mid | ""
    buy: str
    jobs: tuple[Job, ...] = field(default_factory=tuple)  # one per player, one chat line each
    detail: str = ""  # the reasoning, given to the model, never sent on its own

    @property
    def steps(self) -> tuple[str, ...]:
        """The jobs as plain lines, without the player names the engine puts on them."""
        return tuple(job.line for job in self.jobs)

    @property
    def call(self) -> str:
        """The whole plan as one string, for prompts and for the panel."""
        return " ".join(self.steps)


def _jobs(specs: Sequence[str]) -> tuple[Job, ...]:
    """`"palace|smoke CT, entry on the flash"` -> a job. The pipe keeps the book readable."""
    out = []
    for spec in specs:
        spot, _, task = spec.partition("|")
        out.append(Job(spot.strip(), task.strip()))
    return tuple(out)


def _t(map_name: str, name: str, site: str, buy: str, *specs: str, why: str = "") -> Strategy:
    return Strategy(map_name, Team.T, name, site, buy, _jobs(specs), why)


def _ct(map_name: str, name: str, site: str, buy: str, *specs: str, why: str = "") -> Strategy:
    return Strategy(map_name, Team.CT, name, site, buy, _jobs(specs), why)


PLAYBOOK: list[Strategy] = [
    # ---- Mirage ----------------------------------------------------------------
    _t("de_mirage", "Mid default", "mid", ANY,
       "top mid|smoke top mid, hold the smoke with the AWP, never peek window dry",
       "ladder|flash yourself over the smoke, take ladder, call how many are in connector",
       "under ladder|trade the ladder man, molly connector if they push back",
       "palace|hold palace with a flash ready, entry A the second the call comes",
       "apps|make noise in apps and molly bench so B cannot rotate early",
       why="Mirage rounds are won by defaults. Take mid, ladder and connector, but agree on the "
           "finish before the ladder player is in, or the round dies waiting."),
    _t("de_mirage", "A execute", "a", FULL,
       "ramp|smoke jungle, entry ramp on the palace flash, take ticket",
       "ramp|trade the ramp entry, molly stairs, then clear triple and sandwich",
       "palace|smoke CT and stairs, flash over palace on the count",
       "palace|entry from palace behind the flash, plant default at ticket",
       "connector|hold connector against the mid rotate, fall back to jungle post-plant",
       why="The three-smoke A take: jungle and CT cut the rotate, stairs blinds connector. Palace "
           "and ramp enter together so the site is crossed at once."),
    _t("de_mirage", "B split through apps", "b", FULL,
       "apps|smoke short from apps, flash in, entry through the door first",
       "apps|trade the apps entry, clear van, anchor van after the plant",
       "short|smoke market and molly bench, swing short on the apps flash",
       "short|second man short, plant default behind the boxes",
       "mid|lurk connector, call the rotate, molly connector as the plant goes down",
       why="Apps and short at the same time beats a single-side hold. The market smoke stops the "
           "CT spawn rotate from seeing the plant."),
    _t("de_mirage", "Mid to B", "b", ANY,
       "window|smoke window first, then AWP mid once the smoke lands",
       "connector|take connector on a flash, call how many rotate off B",
       "short|drop short with the second man and entry into B",
       "short|trade the entry in, fast plant behind the boxes",
       "market|watch market for the CT spawn rotate and molly it on the plant",
       why="Once mid is yours, B through short arrives from the side the B anchor is not "
           "watching."),
    _t("de_mirage", "Pistol A rush", "a", PISTOL,
       "palace|first out palace, flash over yourself, take ticket",
       "palace|second out, trade instantly, clear sandwich",
       "palace|third out, plant at ticket while the others clear",
       "palace|hold palace behind the plant for the CT retake",
       "ramp|flash from ramp on the count, clear stairs and jungle",
       why="Numbers and armour beat utility on pistols. Palace has cover and a short walk to the "
           "default plant."),
    _ct("de_mirage", "Standard hold", "", ANY,
       "window|AWP window, smoke or molly top mid the moment you hear it, fall back connector",
       "connector|hold connector, trade the window man, rotate B through CT only",
       "A site|play ticket and sandwich cross, molly palace on contact, never peek ramp dry",
       "apps|hold apps door with a flash, alternate pushing it and falling back to bench",
       "B site|anchor van, molly short on the first noise, hold until apps trades you",
       why="Window control is the whole map. Two players hold A while the apps pair keeps Ts out "
           "of short."),
    _ct("de_mirage", "Apps aggression", "b", ANY,
       "apps|flash and swing apps early off the buy, then fall straight back to bench",
       "bench|hold bench and trade apps, molly short if you hear mid go",
       "market|watch market and cut the flank, rotate to site on contact",
       "connector|hold connector for the mid read, drop to B on the second contact",
       "A site|solo anchor A, play retake angles, no dry peeks at palace",
       why="The apps player has to alternate between pushing and holding, or the T side pre-aims "
           "and walks in for free."),
    _ct("de_mirage", "A retake", "a", ANY,
       "connector|smoke on top of the bomb from connector, flash on the count",
       "connector|enter with the smoke, clear sandwich first, defuse under it",
       "stairs|flash from stairs at the same time as connector, clear triple",
       "CT|hold CT for the palace flank, do not enter until both flashes land",
       "jungle|cover jungle and trade whoever goes in first, nobody peeks alone",
       why="Never trickle into a retake. Smoke the bomb, flash from two angles, enter together."),
    _ct("de_mirage", "Pistol stack B", "b", PISTOL,
       "apps|hold apps door, molly short on the first sound",
       "bench|hold bench, trade the apps man, do not chase into apps",
       "van|anchor van for the short entry, save the flash for the retake",
       "A site|hold ticket with a flash, rotate B if it is quiet by 40 seconds",
       "connector|hold connector for the mid read and call the rotate early",
       why="Most pistol rounds are a B rush or a palace hit. Three in apps beats the rush; A "
           "still has a crossfire."),

    # ---- Inferno ---------------------------------------------------------------
    _t("de_inferno", "Banana control", "b", ANY,
       "banana|molly car and sandbags, then take the top of banana first",
       "banana|flash your pair over the top, trade the first man, hold logs",
       "mid|hold mid for the short flank, molly boiler if you hear it",
       "apps|take apps quiet, call whether they are stacked A or rotating",
       "second mid|hold second mid, cut CT rotates once banana is ours",
       why="Even A rounds start with banana. Owning it forces the CT rotate and opens the B "
           "execute."),
    _t("de_inferno", "B execute", "b", FULL,
       "banana|smoke CT from banana, flash over sandbags for the entry",
       "banana|entry first through the smoke, clear new box, plant for banana",
       "banana|trade the entry, molly dark, then hold coffins",
       "banana|smoke coffins, molly new box, second man in, cover the CT smoke as it fades",
       "mid|lurk mid for the rotate and cut anyone coming back through second mid",
       why="The standard B take: CT smoke stops the rotate, dark and new box molly clears the two "
           "holds, entry goes on the flash."),
    _t("de_inferno", "A split", "a", FULL,
       "apps|smoke library from apps, flash out of balcony for your entry",
       "apps|entry off balcony, take the drop, get traded, plant graveyard",
       "apps|trade the balcony entry, then hold apps behind the plant",
       "short|smoke CT and molly pit, swing short on the balcony flash",
       "short|second man short, clear arch, watch library as the smoke opens",
       why="Apartments and short together stretch the two A defenders. The library smoke stops "
           "the rotate from B."),
    _t("de_inferno", "Fake B take A", "a", FULL,
       "banana|molly car, flash and spray into banana - make it sound like five",
       "banana|throw the second molly, hold banana after the fake so the flank is closed",
       "apps|walk quiet through apps, wait at balcony for the rotate call",
       "apps|entry balcony the second the CTs commit to B, take the drop",
       "short|trade the balcony entry through short, plant at graveyard",
       why="Inferno rotations are slow. Utility on banana reads as a full commit and drags the "
           "CTs away from A."),
    _t("de_inferno", "Eco banana stack", "b", ECO,
       "banana|molly car, first up banana, take the close fight",
       "banana|right behind him, trade instantly, pick up his rifle if he drops one",
       "banana|third man, swing wide of the smoke, plant fast",
       "banana|fourth, hold logs behind the plant for the CT push",
       "mid|watch mid so the retake does not come in behind you",
       why="On an eco you want the close fight and the guns that come with it."),
    _ct("de_inferno", "Banana denial", "b", ANY,
       "banana|molly banana early every round, then fall back to logs, never fight dry",
       "B site|anchor coffins, trade banana, smoke to split them when they commit",
       "second mid|hold second mid, rotate B through CT not across the open site",
       "pit|hold pit on A, save the flash for the retake",
       "apps|watch apps and short, call the split the moment you hear the drop",
       why="Make banana cost utility every round, and never cross the open site while rotating."),
    _ct("de_inferno", "Apartments layers", "a", ANY,
       "pit|hold pit, molly balcony on contact, fall back to graveyard when traded",
       "short|hold short or arch, trade pit, watch the library flank",
       "apps|alternate the boiler push and the balcony hold, give the info and get out",
       "banana|molly banana early, play for the trade and rotate on the second contact",
       "CT|play CT spawn as the retake man, keep your utility for the retake",
       why="Layered A hold. The apps player is the info; pit and short trade for each other."),
    _ct("de_inferno", "B retake", "b", ANY,
       "CT|smoke over the plant from CT, molly the default spot before anyone enters",
       "CT|enter with the smoke, clear new box, defuse under it",
       "banana|come down banana on the same count, clear coffins",
       "banana|trade the banana man, watch dark for the lurk",
       "second mid|cut the T rotate through second mid so the retake is five on four",
       why="One-by-one retakes lose. Smoke the bomb, molly the likely plant spot, enter from two "
           "sides."),
    _ct("de_inferno", "Pistol B stack", "b", PISTOL,
       "banana|molly car on the first sound, fall back to logs, do not fight top banana",
       "B site|anchor new box, trade banana, hold for the retake not the frag",
       "coffins|hold coffins, cover the plant, save the flash",
       "pit|hold pit on A, rotate B on the first contact",
       "short|hold short, watch apps, rotate with the pit man together",
       why="The pistol round B rush is the most common opening on Inferno."),

    # ---- Dust 2 ----------------------------------------------------------------
    _t("de_dust2", "Mid control default", "mid", ANY,
       "mid|smoke CT cross and xbox, hold mid behind the smoke, do not peek the AWP",
       "mid|flash for the mid man, take xbox, call whether mid is held",
       "long|molly the corner of long, hold pit with a flash ready",
       "long|second long, trade the pit man, no dry peek on the AWP",
       "short|hold short with a flash, take cat once mid gives, then call the side",
       why="Breaking the mid AWP with doors and cross smokes is the whole T side; the split "
           "follows."),
    _t("de_dust2", "A split long + cat", "a", FULL,
       "long|smoke CT from long, molly goose, entry through pit on the flash",
       "long|trade the long entry, clear the corner, plant long side",
       "long|third man long, hold pit behind the plant for the CT rotate",
       "cat|smoke jungle, flash over the boxes, drop into site on the long entry",
       "cat|trade the cat man, clear ninja and hold short after the plant",
       why="A single-side A take loses to the CT crossfire; long and cat together does not."),
    _t("de_dust2", "B tunnels execute", "b", FULL,
       "upper tunnels|smoke B doors, flash out of tunnels for the entry",
       "upper tunnels|entry first, clear the corner, plant behind the double stack",
       "upper tunnels|molly back plat and the corner, trade the entry in",
       "upper tunnels|fourth man, hold tunnels behind the plant",
       "mid|lurk mid, molly window, cut the CT spawn rotate",
       why="B is a tight take: the doors smoke stops the CT spawn rotate and the mollies clear "
           "the two anchor spots."),
    _t("de_dust2", "Short to B", "b", ANY,
       "short|flash and take cat first, call whether short is held",
       "short|trade him into cat, then drop through the doors into B",
       "short|second into B, plant fast on the side they do not watch",
       "tunnels|hold upper tunnels so the tunnel rotate walks into you",
       "mid|hold mid, molly window and watch for the CT spawn rotate",
       why="Coming into B from cat arrives behind the tunnel hold."),
    _t("de_dust2", "Pistol B rush", "b", PISTOL,
       "upper tunnels|first out, flash over yourself, take the close fight",
       "upper tunnels|second out, trade instantly, clear the back plat",
       "upper tunnels|third, plant behind the double stack while they clear",
       "upper tunnels|hold tunnels behind the plant for the rotate",
       "mid|watch mid doors so the CT spawn rotate is called",
       why="Two CTs cannot hold B against five with flashes on the pistol round."),
    _ct("de_dust2", "Default 2-1-2", "", ANY,
       "long|hold long from pit or corner, molly long on the double doors, fall back to site",
       "goose|anchor goose, trade long, never leave the site to chase",
       "mid|AWP mid, contest early with a flash, fall back to CT on contact",
       "B site|anchor the double stack, molly tunnels on the first noise",
       "B doors|hold doors, trade the anchor, rotate A through CT on confirmed contact",
       why="The standard hold. Mid control decides which rotate is possible."),
    _ct("de_dust2", "Long aggression", "a", ANY,
       "long|flash and take pit early, get the info, do not hold pit twice in a row",
       "goose|trade the pit man from goose, molly long when he falls back",
       "mid|hold mid for the cat rotate, smoke mid if they commit long",
       "B site|anchor B alone, play for the retake and call the numbers",
       "CT|play CT spawn, be the rotate for whichever side breaks",
       why="Free long control is how T sides get their A executes for nothing."),
    _ct("de_dust2", "B retake", "b", ANY,
       "CT|smoke the plant from CT, enter on the count and defuse under it",
       "CT|molly the double stack, follow him in and trade",
       "tunnels|come through tunnels on the same count, clear the back plat",
       "doors|hold doors so nobody leaves, cut the tunnel reinforcement",
       "mid|watch mid for the lurk and call anyone rotating back",
       why="Retaking B one at a time through doors is how B rounds are lost."),
    _ct("de_dust2", "Pistol A long stack", "a", PISTOL,
       "long|molly long the moment the double doors go, fall back to pit",
       "goose|anchor goose, trade long, hold for the retake",
       "CT|hold CT for the cat entry and the ninja defuse",
       "B site|anchor B, hold the double stack, do not push tunnels",
       "mid|hold mid doors, rotate A on the first contact",
       why="Pistol long takes fold to numbers and a molly."),

    # ---- Anubis ----------------------------------------------------------------
    _t("de_anubis", "Water default", "mid", ANY,
       "water|smoke top mid, take water behind it, do not swim dry",
       "water|flash for the water man, trade him, hold the connector door",
       "alley|hold alley, molly heaven if they show, call the rotate",
       "alley|second alley, ready to entry B the moment water is ours",
       "palace|hold palace with a flash, entry A on the call",
       why="Water control is the map. It opens connector and both sites."),
    _t("de_anubis", "A execute", "a", FULL,
       "palace|smoke connector, flash over palace, entry first onto site",
       "palace|trade the palace entry, clear the boxes, plant back site",
       "palace|molly the corner behind the boxes, third in, hold palace post-plant",
       "water|smoke heaven from water, cross on the same flash",
       "water|second through water, hold the water flank after the plant",
       why="The A take needs the connector smoke or the CT rotate arrives before the plant."),
    _t("de_anubis", "B execute", "b", FULL,
       "canals|smoke bridge, entry through canals on the flash",
       "canals|trade the entry, molly the back corner, plant behind the pillar",
       "canals|third through canals, hold the pillar side after the plant",
       "street|smoke connector from street, come in the same second as canals",
       "water|hold water for the mid rotate and call anyone crossing",
       why="B is taken from canals with the bridge cut off - otherwise the rotate is instant."),
    _t("de_anubis", "Mid to B split", "b", ANY,
       "water|take water first with a smoke, then hold connector once it is ours",
       "connector|drop from connector into B on the street count, entry first",
       "street|smoke bridge, come through street with the connector man, trade him",
       "street|second street, fast plant behind the pillar",
       "connector|hold connector after the plant against the rotate",
       why="Connector control turns any B hit into a split."),
    _t("de_anubis", "Pistol B rush", "b", PISTOL,
       "canals|first through canals, flash over yourself, take the close fight",
       "canals|trade him in, clear the pillar",
       "canals|third in, plant behind the pillar while they clear",
       "canals|hold bridge behind the plant for the rotate",
       "water|watch water so the mid rotate does not arrive unseen",
       why="Anubis pistol rounds reward the fast site take with numbers."),
    _ct("de_anubis", "Water denial", "", ANY,
       "mid|molly water early every round, smoke top mid when they commit, play for info",
       "A site|anchor A back site, molly palace on contact, hold for the retake",
       "heaven|hold heaven, trade the A anchor, watch connector",
       "B site|anchor behind the pillar, molly canals on the first sound",
       "bridge|hold bridge, cut the connector drop, rotate on the second contact",
       why="If the T side gets water for free they get the whole map for free."),
    _ct("de_anubis", "A layered hold", "a", ANY,
       "heaven|hold heaven, molly palace instead of peeking it, fall back when traded",
       "A site|play back site, trade heaven, keep the flash for the retake",
       "mid|hold mid for the water read, rotate A as the retake man",
       "connector|watch connector, molly the drop, do not die on site",
       "B site|anchor B alone and call the numbers early",
       why="A is too open to hold from the front; layers and a retake win it."),
    _ct("de_anubis", "B retake", "b", ANY,
       "bridge|smoke the bomb from bridge, molly the pillar, enter on the count",
       "bridge|follow him in, defuse under the smoke",
       "connector|drop from connector at the same time, clear the back corner",
       "connector|trade the connector man, watch canals for reinforcements",
       "mid|hold water so the retake is not flanked",
       why="Bridge alone is a one-by-one retake and loses."),
    _ct("de_anubis", "Pistol stack B", "b", PISTOL,
       "canals|molly canals on the first sound, fall back to site",
       "B site|anchor the pillar, trade the canals man",
       "bridge|hold bridge, cover the plant, save your utility",
       "A site|anchor A alone, rotate on the first contact",
       "mid|hold water, call the rotate, do not duel",
       why="The canals rush is the standard Anubis pistol."),

    # ---- Ancient ---------------------------------------------------------------
    _t("de_ancient", "Patient default", "", ANY,
       "mid|smoke mid, take space slowly, make them spend utility on nothing",
       "mid|trade the mid man, hold the boost side, call what they throw",
       "donut|hold donut, molly CT when they show, do not commit",
       "B ramp|make noise on ramp, molly the top, pull the rotate",
       "cave|hold cave quiet as the lurk, call the execute with 30 seconds left",
       why="Ancient is chokepoints. Making the CTs spend utility on nothing is the strategy."),
    _t("de_ancient", "A execute", "a", FULL,
       "main|smoke CT from main, flash over the boxes, entry first",
       "main|trade the entry, molly the temple corner, plant behind temple",
       "main|smoke donut, third in, clear the back of site",
       "main|fourth man, hold donut after the plant",
       "mid|hold mid for the rotate and cut the CT spawn flank",
       why="A main is a death trap without the CT smoke and the corner molly."),
    _t("de_ancient", "B split from cave and ramp", "b", FULL,
       "ramp|smoke CT from ramp, flash for your entry",
       "ramp|entry up ramp on the flash, plant at the pillar",
       "ramp|trade the ramp entry, hold the ramp flank post-plant",
       "cave|smoke heaven, molly the back of site, come in on the ramp flash",
       "cave|second out of cave, clear the back corner, hold cave after the plant",
       why="Ramp alone is held by one man with utility; cave at the same time is not."),
    _t("de_ancient", "Mid control into B", "b", ANY,
       "mid|smoke mid, take it first, do not trade the AWP dry",
       "mid|trade the mid man, then push through to cave",
       "cave|drop into B out of cave, entry first, fast plant",
       "cave|trade the cave entry, hold the CT rotate angle",
       "ramp|hold ramp so the rotate cannot come back down it",
       why="Mid is the fastest route to B and the one CTs watch last."),
    _t("de_ancient", "Eco A rush", "a", ECO,
       "main|first through main, flash over, take the close fight",
       "main|trade him instantly, clear temple",
       "main|third in, plant behind temple",
       "main|hold donut behind the plant",
       "mid|watch mid so the rotate is called before it lands",
       why="Main is short - an eco rush arrives before the utility does."),
    _ct("de_ancient", "Chokepoint hold", "", ANY,
       "A site|hold main with utility not your body, molly it early, fall back to temple",
       "donut|hold donut, trade the A anchor, rotate late through CT",
       "mid|contest mid with a flash, fall back to donut, never cross the open site",
       "B site|anchor the pillar, molly ramp on the first noise",
       "cave|hold cave, trade the B anchor, watch the ramp flank",
       why="Both site entrances are narrow; utility holds them cheaper than players do."),
    _ct("de_ancient", "Mid denial", "mid", ANY,
       "mid|molly and flash mid early, then fall back to donut - give mid, not yourself",
       "donut|trade the mid man, hold donut for the A rotate",
       "A site|anchor temple, molly main on contact",
       "B site|anchor the pillar, hold for the retake",
       "cave|hold cave, cut the mid-to-cave drop",
       why="Losing mid is survivable; losing the mid player is not."),
    _ct("de_ancient", "B retake", "b", ANY,
       "CT|smoke the plant from CT, molly the pillar, enter on the count",
       "CT|follow in and defuse under the smoke",
       "cave|come out of cave at the same time, clear the back corner",
       "cave|trade the cave man, watch ramp for reinforcements",
       "mid|cut mid so the retake is not flanked",
       why="B has two ways in for the retake - use both or do not retake."),
    _ct("de_ancient", "Pistol A stack", "a", PISTOL,
       "A site|molly main on the first contact, hold temple",
       "donut|hold donut, trade the anchor, do not chase into main",
       "main|hold the main angle with a flash, fall back once you have the info",
       "B site|anchor B alone, call the numbers",
       "mid|hold mid, rotate A on the first contact",
       why="The A main rush is the standard Ancient pistol."),

    # ---- Nuke ------------------------------------------------------------------
    _t("de_nuke", "Outside control", "b", ANY,
       "outside|smoke heaven and the silo angle, take outside first",
       "outside|molly the corner of garage, trade the first man out",
       "outside|hold the silo side, call how many are outside",
       "lobby|hold lobby, make noise, keep the A players home",
       "lobby|second lobby, ready to hit secret or ramp once outside is ours",
       why="Every good Nuke T side starts outside; secret and B follow from it."),
    _t("de_nuke", "A execute", "a", FULL,
       "squeaky|smoke heaven, entry through squeaky on the count",
       "squeaky|trade the squeaky entry, plant default, hold heaven post-plant",
       "hut|smoke main, molly hut, entry hut at the same time as squeaky",
       "hut|trade the hut man, clear the back of site",
       "ramp|hold ramp so the rotate does not come up behind the plant",
       why="The heaven smoke removes the angle that holds A; the hut molly clears the anchor."),
    _t("de_nuke", "Vent drop off an A fake", "a", FULL,
       "main|molly and flash main, spray it - sound like the whole team",
       "main|second man on the fake, then hold main so the flank is closed",
       "vents|drop through vents as the CTs commit to main, take the site from behind",
       "vents|second through vents, trade him, plant default",
       "outside|hold outside for the rotate coming back through ramp",
       why="Nuke defenders read main utility as the commit and turn away from vents."),
    _t("de_nuke", "B through secret", "b", FULL,
       "secret|smoke ramp, entry out of secret on the flash",
       "secret|trade the secret entry, molly double doors, plant back site",
       "secret|third through secret, hold secret after the plant",
       "outside|hold outside so the ramp rotate is cut off",
       "outside|second outside, watch the silo angle and call the rotate",
       why="Secret arrives behind the ramp hold, which is where B defenders look."),
    _t("de_nuke", "Pistol A rush", "a", PISTOL,
       "squeaky|first through squeaky, flash over yourself, take the close fight",
       "squeaky|trade him, clear heaven",
       "lobby|third through lobby, plant default",
       "hut|clear hut, then hold it behind the plant",
       "ramp|watch ramp for the rotate",
       why="Pistol A takes work because heaven has no utility to stop five players."),
    _ct("de_nuke", "Standard A hold", "a", ANY,
       "heaven|hold heaven, molly squeaky on contact, never drop to site early",
       "hut|anchor hut, trade heaven, hold for the retake",
       "ramp|hold ramp with a molly, rotate down ramp not across the site",
       "outside|contest outside early with a smoke, fall back on contact",
       "lobby|hold lobby, cut the squeaky push, rotate with the outside man",
       why="Nuke is held above the site; outside pressure decides the round."),
    _ct("de_nuke", "Outside pressure", "", ANY,
       "outside|AWP the silo angle, flash and fall back on contact - do not over-hold",
       "outside|trade the AWP, reset together, never lose two outside",
       "heaven|hold heaven for the A drop, cover the rotate",
       "ramp|hold ramp, molly it early, call the B commit",
       "hut|anchor A, keep your utility for the retake",
       why="Cheap outside pressure is what stops the whole T side plan."),
    _ct("de_nuke", "B retake from ramp and vents", "b", ANY,
       "ramp|smoke the plant from ramp, molly the back corner, enter on the count",
       "ramp|follow him down, defuse under the smoke",
       "vents|drop through vents at the same time, clear the back site",
       "vents|trade the vents man, watch secret for reinforcements",
       "outside|cut outside so the retake is not flanked",
       why="A ramp-only retake on B is a one-by-one and loses."),
    _ct("de_nuke", "Pistol lobby denial", "a", PISTOL,
       "lobby|push lobby with a flash, get the info, fall back to squeaky",
       "lobby|trade the lobby man, then hold squeaky",
       "heaven|hold heaven, cover the site, do not drop",
       "hut|anchor hut, hold for the retake",
       "ramp|hold ramp, rotate on the first contact",
       why="Lobby pressure breaks the pistol rush before it reaches the site."),

    # ---- Cache -----------------------------------------------------------------
    _t("de_cache", "Mid to A default", "a", ANY,
       "mid|smoke CT, take mid boost or mid box, do not peek highway dry",
       "mid|flash for the mid man, trade him, hold the mid box",
       "A main|hold main with a flash ready, entry once mid is ours",
       "A main|second main, trade the entry, plant at truck",
       "squeaky|hold squeaky for the B rotate and call it early",
       why="Cache A takes are mid takes; main alone walks into the crossfire."),
    _t("de_cache", "A execute", "a", FULL,
       "A main|smoke highway, flash into main, entry first",
       "A main|trade the entry, molly the truck corner, plant at truck",
       "A main|third through main, hold quad after the plant",
       "mid|smoke CT and quad, come in with the main flash",
       "mid|second from mid, clear the back and hold highway post-plant",
       why="The four-utility A take: quad and CT smokes cut both rotates."),
    _t("de_cache", "B execute from checkers", "b", FULL,
       "checkers|smoke CT, flash over checkers, entry first",
       "checkers|trade the entry, molly the back of site, plant behind the boxes",
       "checkers|smoke squeaky, third in, hold the heaven angle",
       "checkers|fourth man, clear the corner, hold checkers post-plant",
       "mid|lurk mid, cut the rotate, call anyone coming through",
       why="B is taken from checkers with heaven and CT cut off, or the rotate is instant."),
    _t("de_cache", "Sunroom split", "b", FULL,
       "sunroom|smoke heaven, drop into sunroom, entry on the checkers count",
       "sunroom|trade the sunroom man, hold the vent side after the plant",
       "checkers|flash over checkers, entry at the same second as sunroom",
       "checkers|trade the checkers entry, fast plant behind the boxes",
       "mid|hold mid so the CT rotate is cut off",
       why="Sunroom and checkers together beats a single-entrance B take."),
    _t("de_cache", "Pistol A rush", "a", PISTOL,
       "A main|first through main, flash over yourself, take the close fight",
       "A main|trade him instantly, clear quad",
       "A main|third in, plant at truck",
       "A main|hold quad behind the plant",
       "mid|watch mid so the rotate is called",
       why="Numbers through main beat the two-man pistol hold."),
    _ct("de_cache", "Standard hold", "", ANY,
       "quad|hold quad, molly main on contact, fall back to truck when traded",
       "truck|anchor truck, trade quad, rotate through CT only",
       "mid|contest mid early with utility, then play back and give the info",
       "heaven|hold heaven on B, cover checkers, keep the flash for the retake",
       "B site|anchor the boxes, molly checkers on the first noise",
       why="Mid decides both sites on Cache; deny it and both takes get harder."),
    _ct("de_cache", "Mid aggression", "mid", ANY,
       "mid|flash and take mid boost early, fall back before their utility lands",
       "quad|trade the mid man from quad, molly main if they commit",
       "truck|anchor A, hold for the retake, no dry peeks",
       "heaven|hold heaven, call the B numbers early",
       "B site|anchor the boxes, molly checkers on the first sound",
       why="Free mid is a free A execute for the T side."),
    _ct("de_cache", "B retake", "b", ANY,
       "heaven|smoke the plant from heaven, molly the boxes, drop on the count",
       "heaven|follow him down, defuse under the smoke",
       "CT|come from CT at the same time, clear the corner",
       "CT|trade the CT man, watch checkers for reinforcements",
       "mid|cut mid so the retake is not flanked",
       why="Heaven alone is a one-by-one retake."),
    _ct("de_cache", "Pistol B stack", "b", PISTOL,
       "checkers|molly checkers on the first sound, fall back to site",
       "B site|anchor the boxes, trade checkers",
       "heaven|hold heaven, cover the plant, save the flash",
       "quad|anchor A alone, call the numbers",
       "mid|hold mid, rotate B on the first contact",
       why="The checkers rush is the standard Cache pistol."),

    # ---- Anywhere ---------------------------------------------------------------
    _t("", "Default", "", ANY,
       "entry|take the first duel on the flash, do not go without one",
       "support|throw the flash and trade the entry, every time",
       "utility|smoke the rotate off, molly the anchor spot",
       "lurk|hold the flank quiet, call the rotate, do not fight it alone",
       "AWP|hold the map control angle, then hold it again after the plant",
       why="Generic T structure when the map is unknown."),
    _t("", "Eco", "", ECO,
       "entry|first in, flash over yourself, take the close fight",
       "support|trade him instantly and take his rifle if he drops it",
       "third|plant while the first two clear",
       "anchor|hold the flank behind the plant",
       "watch|call the rotate before it arrives",
       why="Generic eco: numbers in one place."),
    _t("", "Force", "", ECO,
       "entry|armour and a flash, hit the site before their AWP is set",
       "support|trade the entry, no one dies alone",
       "utility|smoke the rotate, molly the anchor",
       "plant|plant fast and hold the angle they rotate into",
       "flank|watch the flank so the round is not lost from behind",
       why="Generic force buy plan."),
    _ct("", "Default hold", "", ANY,
       "site A|anchor A, molly the entrance on contact, hold for the retake",
       "support A|trade the A anchor, never chase",
       "mid|contest mid early with utility, then fall back and give info",
       "site B|anchor B, molly the entrance on the first noise",
       "support B|trade the B anchor, rotate on the second contact",
       why="Generic CT structure when the map is unknown."),
    _ct("", "Retake", "", ANY,
       "smoke|smoke the bomb, then enter on the count",
       "defuse|go in under the smoke and defuse, nobody peeks alone",
       "flash|flash from the other side at the same time",
       "trade|enter behind the flash and trade the first man",
       "flank|cut the flank so the retake is five on four",
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


def assign(strategy: Strategy, names: Sequence[str] = ()) -> list[str]:
    """Each job with somebody's name on it - teammates we know, then P2, P3, ... for the rest.

    The names are whoever has spoken in team chat, so the call reads as orders to real people
    instead of "one man does this". Slots past the names we have still say a position, which is
    what makes the call actionable at all.
    """
    lines = []
    for index, job in enumerate(strategy.jobs):
        who = names[index] if index < len(names) else f"P{index + 1}"
        lines.append(f"{who} {job.line}")
    return lines


def call_lines(strategy: Strategy, max_lines: int = 6, names: Sequence[str] = ()) -> list[str]:
    """The strat as consecutive chat lines: a header, then one player's job per line."""
    header = strategy.name
    if label := map_label(strategy.map_name):
        header = f"{label} {strategy.side.value}: {strategy.name}"
    steps = assign(strategy, names)
    if max_lines > 0 and len(steps) > max_lines - 1:
        # Everything that will not fit joins the last line rather than being dropped.
        keep = max(max_lines - 2, 0)
        steps = steps[:keep] + [" ".join(steps[keep:])]
    return [header, *steps]


def call_text(strategy: Strategy, names: Sequence[str] = ()) -> str:
    """The whole call on one line, for the panel and the model."""
    return " | ".join(call_lines(strategy, max_lines=0, names=names))
