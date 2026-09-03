# CS2 Chatbot

A Counter-Strike 2 chat bot that reads in-game chat from `console.log`, generates a reply with a
**local quantized Llama 3 8B**, and types it back into the game. Everything is driven from a web
control panel: personality, how smart the bot sounds, and what it is allowed to answer.

Same premise as the original character.ai-based bot, rebuilt around a local model, a browser UI,
and rules that understand who is alive and who is dead.

## Features

- **Local model.** llama.cpp (GGUF, e.g. `Meta-Llama-3-8B-Instruct.Q4_K_M`) or Ollama. No API keys,
  no account, nothing leaves the machine. A `mock` backend lets you try the UI with no model at all.
- **Personality.** Editable system prompt (character, style rules, a separate "when dead" voice),
  four presets, and named personas you can save and reload.
- **Intelligence dial (0-100).** Controls how articulate the bot sounds: prompt directives, sampling
  (temperature / top-p / top-k / length), plus post-processing that adds chat abbreviations, lowercase
  and typos at the low end. Sampling can also be set by hand.
- **Dead vs alive.** `*DEAD*` senders are detected from the log, and CS2 Game State Integration
  reports whether *you* are alive. The bot will not answer messages a living player could not have
  seen, and will not type into chat that nobody alive can read (see below).
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
   Set your in-game name and the bind key.
2. **Model tab** - pick a backend, set the GGUF path or Ollama model, press *Check model*.
3. **Game tab → Install GSI config** - writes `gamestate_integration_cs2bot.cfg` into the cfg
   directory so CS2 reports your alive/dead state. Restart CS2 afterwards.
4. Press **Start bot**.

## How the dead/alive logic works

CS2 splits the chat audience: a dead player's messages are only rendered for other dead players and
spectators. That gives two rules, both toggleable on the *Dead / alive* tab:

| Bot is | Sender is | Default | Why |
| ------ | --------- | ------- | --- |
| alive  | alive     | reply   | normal case |
| alive  | dead      | skip    | a living player is not supposed to see dead chat |
| dead   | dead      | reply   | both are in the dead audience |
| dead   | alive     | skip    | the reply would be invisible to them |

Warmup, deathmatch and `sv_deadtalk` servers merge the audiences again; the *treat warmup as one
shared chat* and *global dead chat* toggles cover those. Without GSI the bot assumes it is alive.

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
| `cs2bot/parser.py` | chat line → `ChatMessage` (channel, sender, dead/alive, team) |
| `cs2bot/gamestate.py` | CS2 Game State Integration listener + cfg generator |
| `cs2bot/rules.py` | who may be answered, and why not |
| `cs2bot/persona.py` | prompt construction (persona + intelligence + live game context) |
| `cs2bot/humanize.py` | intelligence dial → sampling and post-processing |
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
