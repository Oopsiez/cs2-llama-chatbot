# CS2 Chatbot

A Counter-Strike 2 chat bot that reads in-game chat from `console.log`, generates a reply with a
**local quantized Llama 3 8B**, and types it back into the game. Everything is driven from a web
control panel: personality, how well it writes, how well it plays, and what it is allowed to answer.

Same premise as the original character.ai-based bot, rebuilt around a local model, a browser UI,
and rules that understand who is alive and who is dead.

## Features

- **Local model.** llama.cpp (GGUF, e.g. `Meta-Llama-3-8B-Instruct.Q4_K_M`) or Ollama. No API keys,
  no account, nothing leaves the machine. A `mock` backend lets you try the UI with no model at all.
- **Personality.** Editable system prompt (character, style rules, a separate "when dead" voice),
  presets, and named personas you can save and reload. Presets: Cheeky Teammate, Calm IGL, Silver
  Enjoyer, Deadpan Bot, **Coach** (volunteers pointers), **Gaming Therapist** (counsels you through
  being bad at the game) and **Angry and Toxic**.
- **Two dials, 0-100.** *Literacy* is how well it writes (spelling, punctuation, sentence length,
  typos, abbreviations); *Game IQ* is how good its Counter-Strike thinking is (callouts, economy,
  utility, timings). They are independent, so a smart player who types like a goblin - or a
  well-spoken fool - are both one slider apart. Sampling follows the dials, or can be set by hand.
- **Unsolicited advice.** A toggle that makes the bot volunteer a pointer instead of only answering
  what was said; pair it with the Coach preset.
- **No repeating itself.** Recent replies are fed back into the prompt as "don't say these again",
  and a reply too similar to a recent one is thrown away and regenerated (limit and retries are
  configurable). If every attempt is a rerun, it stays quiet.
- **Reply timing.** A delay slider for how fast or slow it answers, or a checkbox to bypass it and
  take realistically long: read the message, then type it out at the configured typing speed.
- **Dead vs alive.** `[DEAD]` senders are read straight off the log and remembered for the rest of
  the round, and CS2 Game State Integration reports whether *you* are alive. Each of the four
  combinations gets its own instruction in the prompt, so a corpse gets a different answer than a
  teammate mid-fight (see below).
- **Knows who you are.** Your in-game name is taken from the panel, or read from Game State
  Integration and the console log, and is handed to the model as prompt context.
- **Knows when it is being spoken to.** `you: gg`, `@you`, your name inside a sentence, nickname
  aliases and follow-ups to the bot's own last line are flagged as directed at you; those can jump
  the trigger-word filter, cooldown and reply-chance roll, or be the only thing the bot answers.
- **Live panel.** Streaming feed of chat, replies, and every skip reason; parser tester for pasting
  real log lines; reply simulator that needs no game running.

## Requirements

- Python 3.10+
- CS2 launched with `-condebug` (writes `console.log`)
- In CS2: `bind p "exec message.cfg"` (any key; set the same key in the panel)
- For real replies: a GGUF Llama 3 8B Instruct file, or `ollama pull llama3:8b-instruct-q4_K_M`
- Typing into the game requires Windows (`pip install "cs2bot[windows]"`). Elsewhere the bot runs in
  dry-run mode and shows replies in the panel only.

## Install

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -e ".[llama,windows]"   # or: pip install -e .  for the Ollama/mock backends
cs2bot
```

Then open <http://127.0.0.1:8420>.

## Setup checklist

1. **Game tab** - point `console.log` at
   `.../Counter-Strike Global Offensive/game/csgo/console.log` and the cfg directory at
   `.../game/csgo/cfg` (both are auto-detected when Steam is installed in a standard location).
   Set the bind key. Leave *Your in-game name* blank to auto-detect it; add aliases if people
   shorten your name.
2. **Model tab** - pick a backend, set the GGUF path or Ollama model, press *Check model*.
3. **Game tab → Install GSI config** - writes `gamestate_integration_cs2bot.cfg` into the cfg
   directory so CS2 reports your alive/dead state. Restart CS2 afterwards.
4. Press **Start bot**.

## How the dead/alive logic works

CS2 prefixes a dead player's chat with `[DEAD]` (some servers use `*DEAD*`). The parser reads that
tag, and because only the tagged lines carry it, the bot also remembers who died until the round
resets - so an untagged line from a player already seen dead still counts as coming from the grave.
Pair that with your own state from GSI and the prompt gets one of four instructions:

| Bot is | Sender is | How it answers |
| ------ | --------- | -------------- |
| alive  | alive     | quick line you could realistically type mid-round |
| alive  | dead      | treats them as a backseat voice; it is the one still playing |
| dead   | alive     | one short, useful line - they are in a fight |
| dead   | dead      | spectator talk: react to the round, second-guess the living |

Nothing is filtered out by default: everyone sees everyone's chat. For servers that split the
audience so the living cannot read dead chat, turn on *Skip messages the bot could not have seen*
on the *Dead / alive* tab and the old visibility rules apply. Without GSI the bot assumes it is
alive.

## How it knows your name

In priority order: the name typed into the *Game* tab, the player name reported by GSI, then the
console log (`"name" = "..."`, `name "..."`, rename notices). The resolved name and its source are
shown in the status bar. A message counts as directed at you when it starts with your name, uses
`@name`, contains your name or one of your aliases (accents, leetspeak and clan tags are ignored),
or uses "you" shortly after the bot spoke. When visibility enforcement is on, it still wins - being
named never makes the bot answer chat it should not be able to see.

## Trying it without CS2

```bash
python scripts/fake_match.py /tmp/console.log      # writes fake chat lines
CS2BOT_CONFIG=/tmp/cs2bot.json cs2bot              # point the log path at /tmp/console.log
```

The *Test* tab also parses pasted log lines and generates one-off replies with no game involved.

## Project layout

| Path | Purpose |
| ---- | ------- |
| `cs2bot/logtail.py` | incremental `console.log` follower (handles append, truncate, relaunch) |
| `cs2bot/identity.py` | your name: detection, aliases, and "is this aimed at me?" |
| `cs2bot/parser.py` | chat line → `ChatMessage` (channel, sender, dead/alive, team) |
| `cs2bot/gamestate.py` | CS2 Game State Integration listener + cfg generator |
| `cs2bot/liveness.py` | per-round memory of who is dead, learned from `[DEAD]` tags |
| `cs2bot/rules.py` | who may be answered, and why not |
| `cs2bot/persona.py` | prompt construction (persona + dials + live game context) |
| `cs2bot/humanize.py` | literacy / game IQ dials → sampling and post-processing |
| `cs2bot/novelty.py` | similarity check that keeps replies from repeating |
| `cs2bot/llm/` | llama.cpp / Ollama / mock backends |
| `cs2bot/output/` | delivery: Windows `message.cfg` + keypress, or dry run |
| `cs2bot/web/` | FastAPI panel and static UI |

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

Settings live in `config.json` under the per-user config directory (override with `CS2BOT_CONFIG`).

## Can I be banned for this?

The bot never touches the game process: it reads a log file CS2 writes itself and sends a keystroke
that runs a normal console command. That is the same approach the original project used.
