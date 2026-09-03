"""Post-processing that makes a reply look like it was typed by a human of a given skill level.

Two dials, deliberately independent: *literacy* is how well the bot writes and *game IQ* is how
good its Counter-Strike thinking is, so a well-spoken fool and a sharp player who types like a
goblin are both reachable. Models are stubbornly articulate, so the low end of literacy is
enforced here as well: shorter replies, lowercase, dropped punctuation, chat abbreviations and
keyboard-neighbour typos.
"""

from __future__ import annotations

import random
import re

_ADJACENT = {
    "a": "sq", "b": "vn", "c": "xv", "d": "sf", "e": "wr", "f": "dg", "g": "fh", "h": "gj",
    "i": "uo", "j": "hk", "k": "jl", "l": "k", "m": "n", "n": "bm", "o": "ip", "p": "o",
    "q": "wa", "r": "et", "s": "ad", "t": "ry", "u": "yi", "v": "cb", "w": "qe", "x": "zc",
    "y": "tu", "z": "x",
}

_ABBREVIATIONS = {
    "you": "u", "your": "ur", "you're": "ur", "are": "r", "okay": "ok", "please": "pls",
    "thanks": "ty", "thank": "ty", "because": "cuz", "people": "ppl", "probably": "prob",
    "really": "rly", "about": "abt", "with": "w", "though": "tho", "right": "rite",
    "what": "wat", "want": "wanna", "going": "gonna", "yes": "ya", "know": "kno",
}


def sampling_for(literacy: int, intelligence: int) -> dict[str, float | int]:
    """Sampling knobs: low game IQ rambles hotter, low literacy answers shorter."""
    iq = max(0, min(100, intelligence)) / 100
    lit = max(0, min(100, literacy)) / 100
    return {
        "temperature": round(1.35 - 0.65 * iq, 3),
        "top_p": round(0.85 + 0.13 * iq, 3),
        "top_k": int(round(20 + 60 * iq)),
        "repeat_penalty": round(1.25 - 0.15 * iq, 3),
        "max_tokens": int(round(24 + 96 * lit)),
    }


def literacy_directive(literacy: int) -> str:
    """The prompt fragment describing how well the bot writes."""
    level = max(0, min(100, literacy))
    if level < 15:
        return (
            "Write like a barely-literate player: 3-8 words, all lowercase, no punctuation, "
            "frequent typos, simple words only."
        )
    if level < 35:
        return (
            "Write like a casual player who does not care: one short lowercase sentence, chat "
            "abbreviations, occasional typos."
        )
    if level < 60:
        return "Write like an average player: one short sentence, mostly lowercase, light slang."
    if level < 85:
        return "Write clearly: one or two plain sentences, correct spelling, minimal slang."
    return (
        "Write precisely: correct grammar and punctuation, well-chosen words, still no longer "
        "than two sentences."
    )


def game_iq_directive(intelligence: int) -> str:
    """The prompt fragment describing how good the bot's Counter-Strike thinking is."""
    level = max(0, min(100, intelligence))
    if level < 15:
        return (
            "You barely understand the game: no tactics, wrong callouts, react to whatever was "
            "said last and nothing else."
        )
    if level < 35:
        return "Your game sense is weak: vague advice, confident but usually wrong about tactics."
    if level < 60:
        return "Your game sense is average: basic economy and callout knowledge, no deep reads."
    if level < 85:
        return (
            "Your game sense is strong: concrete callouts, economy awareness, reasoning about "
            "what the enemy is doing."
        )
    return (
        "Your game sense is professional: specific map knowledge, utility usage, timings and "
        "economy, and you are right."
    )


def _typo(word: str, rng: random.Random) -> str:
    if len(word) < 3:
        return word
    index = rng.randrange(len(word))
    char = word[index].lower()
    roll = rng.random()
    if roll < 0.4 and char in _ADJACENT:
        replacement = rng.choice(_ADJACENT[char])
        return word[:index] + replacement + word[index + 1 :]
    if roll < 0.7:  # swap with the next character
        if index + 1 < len(word):
            return word[:index] + word[index + 1] + word[index] + word[index + 2 :]
        return word
    return word[:index] + word[index + 1 :]  # dropped key


def humanize(text: str, literacy: int, max_chars: int, seed: int | None = None) -> str:
    """Apply the literacy-dependent degradation and trim to the chat limit."""
    rng = random.Random(seed)
    level = max(0, min(100, literacy))
    result = re.sub(r"\s+", " ", text).strip().strip('"')

    # Models love to prefix replies with the speaker's name or stage directions.
    result = re.sub(r"^\s*\*[^*]{0,60}\*\s*", "", result)
    result = re.sub(r"^[A-Za-z0-9_\-\[\]]{1,24}\s*:\s+", "", result)

    if level < 60:
        words = result.split(" ")
        result = " ".join(_ABBREVIATIONS.get(w.lower().strip(".,!?"), w) for w in words)
    if level < 70:
        result = result.lower()
    if level < 40:
        result = re.sub(r"[.,;:!?]+", "", result)
        result = re.sub(r"\s+", " ", result).strip()

    typo_rate = 0.0 if level >= 70 else (70 - level) / 70 * 0.18
    if typo_rate > 0:
        words = result.split(" ")
        result = " ".join(_typo(w, rng) if rng.random() < typo_rate else w for w in words)

    word_cap = max(3, int(round(4 + level * 0.26)))
    words = result.split(" ")
    if len(words) > word_cap:
        result = " ".join(words[:word_cap])

    if max_chars > 0 and len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0]
    return result.strip()
