# CS2 Chatbot

A Counter-Strike 2 teammate that actually talks. It reads in-game chat, thinks with a **local
Llama 3 8B** running on your own machine, and types replies back into the game. You control who it
is, how smart it sounds, and what it is allowed to say from a control panel in your browser.

No account, no API key, no subscription. Nothing you type leaves your computer.

---

## Just want to use it?

**[Download the latest release](https://github.com/Oopsiez/cs2-llama-chatbot/releases/latest)** →
grab **`CS2 Chatbot Setup.exe`** → run it → click **Install**. You get a Start Menu and desktop
shortcut; open it and your browser lands on the control panel. No Python, no admin password, no
commands. Uninstall it like any other program from Add/Remove Programs.

Windows will warn that the publisher is unknown (the installer is not code-signed) - click *More
info* → *Run anyway*.

Prefer not to install anything? The same release also has a standalone **`CS2 Chatbot.exe`** you can
double-click from anywhere. Or download this repository as a ZIP (green **Code** button →
*Download ZIP*), unzip it, and double-click **`Start CS2 Chatbot.bat`**, which sets Python up for you
on first run.

### Then, three things inside CS2

1. **Add `-condebug` to the launch options.** Steam → right-click Counter-Strike 2 → Properties →
   Launch Options → type `-condebug`. This makes CS2 write the chat log the bot reads.
2. **Bind a key.** Open the developer console in CS2 and paste: `bind p "exec message.cfg"`
   (any key works - just set the same one in the panel).
3. **Press *Install GSI config*** on the panel's Game tab, then restart CS2. That is what lets the
   bot know whether you are alive, what round it is, and where you are standing. CS2 only reads
   that config when it starts, so the restart is not optional. **Check GSI** on the same tab says
   what is wrong if the header still reads *gsi: waiting*.

Press **Start bot** and play. The panel shows every message it sees, every reply, and the reason it
stayed quiet when it did.

### Which brain to use

| Option | What you need | Notes |
| ------ | ------------- | ----- |
| **Mock** | nothing | Canned replies. Good for trying the panel out. |
| **Ollama** | [Ollama](https://ollama.com) + `ollama pull llama3:8b-instruct-q4_K_M` | Easiest real option. Can run on **another computer** - see below. |
| **llama.cpp** | a `.gguf` model file | Fastest, no extra program running. |

---

## What it can do

- **Be anyone.** Presets for Cheeky Teammate, Calm IGL, Silver Enjoyer, Deadpan Bot, **Coach**
  (volunteers pointers), **Gaming Therapist** (counsels you through being bad at the game) and
  **Angry and Toxic** - plus a **Custom prompt** box you can type into mid-match and save under
  any name for next time.
- **Two dials, 0-100.** *Literacy* is how well it writes; *Game IQ* is how good its Counter-Strike
  thinking is. They are independent, so a smart player who types like a goblin - or a well-spoken
  fool - are both one slider apart.
- **Know who is dead.** It reads the `[DEAD]` tag on chat, remembers who died for the rest of the
  round, and knows whether *you* are alive. All four combinations get a different kind of reply.
- **Know when you are being talked to.** Your name at the start of a line, `@name`, a nickname, or
  a "you" right after it spoke - all count, and can jump the queue past the cooldown.
- **Know who you are, on any account.** Leave *Your in-game name* blank and it asks CS2 itself -
  it runs the `name` command every couple of minutes and reads the answer out of the console - so
  a different Steam account, or a rename mid-session, is picked up on its own. *Ask CS2 my name
  now* on the **Game** tab does it immediately.
- **Snitch on you.** Ask "where are you?" in chat and it answers honestly with your callout, health,
  weapon or the bomb state. It can also drop your position on a timer or when you die. It only ever
  describes **you** - see [Is this a cheat?](#is-this-a-cheat) below.
- **Call an actual strat.** Type `strat?` (or `!strat b`) in chat and it answers with a real call
  for the map and side you are on - see [Calling strats](#calling-strats).
- **Never repeat itself.** A reply too close to a recent one is thrown away and regenerated; if
  every attempt is a rerun, it stays quiet instead.
- **Answer at human speed.** A delay slider, or a checkbox that makes it read the message and then
  take as long as actually typing the reply would.
- **Own up at the end.** When the final scoreboard appears it admits it was a bot and links the
  project. One line, once per match; editable, and switch-off-able, on the Snitch tab.

## Calling strats

Ask for a plan in chat and the bot answers with a genuine call - an execute, a default or a CT
setup - chosen for the map you are on and the side you are playing, off a fixed playbook built from
how the round is actually played at a high level. The model never invents tactics: it is handed the
call and, at most, allowed to say it in its own voice, so the utility and the site it names are the
ones written down.

Every call is five jobs, one per player: where you start, what you throw, who you entry or trade,
who plants and what you hold after it. Nobody is told to "smoke something" - the line has a name on
it. A strat does not fit in CS2's ~220 character chat line, so it goes out one player per line:

```
Mirage T: A execute
Gavin ramp: smoke jungle, entry ramp on the palace flash, take ticket
kenny ramp: trade the ramp entry, molly stairs, then clear triple and sandwich
P3 palace: smoke CT and stairs, flash over palace on the count
P4 palace: entry from palace behind the flash, plant default at ticket
P5 connector: hold connector against the mid rotate, fall back to jungle post-plant
```

The names come from your team chat - anyone who has talked there this map is a teammate, newest
voice first - and everyone else is `P3`, `P4`, `P5`. All chat is ignored for this on purpose:
putting an enemy's name on a job is worse than a slot number.

The **Strats** tab in the panel controls it:

| Setting | What it does |
| --- | --- |
| *Take orders from* | All chat, team chat, or both. Separate from where it chats normally, so it can banter in all chat but only take orders from your team. |
| *Call in* | Team chat, all chat, or wherever it was asked. |
| *Call every round* | Off by default. On, it calls one strat in freezetime, once per round, without being asked. |
| *Only near round start* | Ignores strat requests once the round is underway. |
| *Chat lines per strat* | How many lines it is allowed to spend. Six - a header plus five players - says all of it; anything that does not fit is folded into the last line rather than dropped. |
| *Give the jobs to teammates by name* | On by default. Off, everyone is `P1`-`P5`. |
| *Ask phrases* | The words it listens for. `strat`, `strats`, `what's the plan`, `call it`, `what do we do` by default. |

In chat:

- `strat?`, `strats`, `what's the plan`, `call it` - give me a call.
- `!strat a`, `!strat b`, `!strat mid` - a call for that site, if the map has one.
- `!quiet` - shut up for two minutes. `!talk` - come back.

The map and side come from Game State Integration, so install the GSI config (**Game** tab) or it
falls back to the side you picked in the panel and to map-agnostic calls. GSI is Valve's own API
and works in Premier and other official matches: it reports your map, side, round phase and health,
which is everything the strats and the dead-chat rules need. The one thing official matches hold
back is your position - CS2 only sends that while you are spectating - so callouts fill in after
you die rather than while you are alive. Covered maps are the
current Premier and FACEIT active duty pool: **Mirage, Inferno, Dust 2, Anubis, Ancient, Nuke,
Cache**. Anything else - workshop maps, deathmatch servers - gets calls that hold on any map.

## Teaching it callouts

CS2 tells the bot your coordinates, not that you are standing in banana. So you teach it once per
map: stand somewhere, type the name on the **Snitch** tab, and press *Record where I am standing*.
Anything within about 400 units of that point is then called by that name. Until you record
something it just says it does not know the callout - health and bomb state still work.

## Running the model on another computer

The model is the only heavy part, so it can live on a different machine - a desktop with a GPU, a
home server, anything reachable over the network. On that machine run Ollama with
`OLLAMA_HOST=0.0.0.0 ollama serve`, then on the **Model** tab set the Ollama URL to
`http://that-machine:11434`. If it sits behind a reverse proxy with a password, put the token in
*Ollama API key*; for a self-signed HTTPS certificate, untick *Verify TLS certificate*.

## Is this a cheat?

**No, and deliberately so.** The bot never touches the game's memory or process. It reads a log file
CS2 writes itself, receives the official Game State Integration feed Valve provides, and sends a
keystroke that runs an ordinary console command.

The snitch feature only ever reveals **your own** position, because that is the only thing Game
State Integration reports while you are playing. Wiring in a memory-reading tool to see other
players was considered and rejected - that would make this a cheat client and get you VAC-banned.

## Trying it without CS2

```bash
python scripts/fake_match.py /tmp/console.log      # writes fake chat lines
CS2BOT_CONFIG=/tmp/cs2bot.json cs2bot              # point the log path at /tmp/console.log
```

The *Test* tab also parses pasted log lines and generates one-off replies with no game involved.

## It is not seeing any chat

Open the *Test* tab and press **Refresh log**. It shows the path, whether the file is growing, and
every line the bot has read, with the ones it understood as chat marked.

- Nothing at all, or the file is missing: CS2 is not writing that file - check `-condebug` is in
  the launch options, restart the game, and make sure the path on the *Game* tab is the
  `console.log` next to your CS2 install.
- Lines appear but none are marked as chat: that is a parsing gap - open an issue with a couple of
  those lines.

## It writes a reply but nothing is said in game

Focus CS2, then press **Test typing into CS2** on the *Game* tab. It makes the game echo a word and
watches the console log for it, so the three failures look different:

- *the keypress did not leave Windows*: input is being refused. Usually CS2 runs as administrator
  and the bot does not - **Restart as administrator** next to the test fixes that.
- *CS2 did not run it*: the keypress landed but the key is not bound. In the game console run
  `bind "p" "exec message.cfg"` (or whichever key the panel is set to).
- *the game ran it*: delivery works, so a missing reply is the bot deciding not to speak - the
  activity feed says which rule stopped it.

---

## For developers

```bash
pip install -e ".[dev]"        # add [llama] for llama.cpp
cs2bot                         # panel on http://127.0.0.1:8420
pytest -q && ruff check . && mypy cs2bot
python scripts/build_exe.py    # one-file executable (run this on Windows)
iscc /DAppVersion=1.3.2 installer\cs2-chatbot.iss   # then wrap it in the installer
```

Settings live in `config.json` in the per-user config directory (override with `CS2BOT_CONFIG`).

| Path | Purpose |
| ---- | ------- |
| `cs2bot/engine.py` | the loop: read chat, decide, generate, send |
| `cs2bot/logtail.py` | incremental `console.log` follower (append, truncate, relaunch) |
| `cs2bot/parser.py` | chat line → `ChatMessage` (channel, sender, dead/alive, team) |
| `cs2bot/identity.py` | your name: detection, aliases, and "is this aimed at me?" |
| `cs2bot/echo.py` | recognises the bot's own lines coming back, so it cannot talk to itself |
| `cs2bot/gamestate.py` | Game State Integration listener + cfg generator |
| `cs2bot/liveness.py` | per-round memory of who is dead |
| `cs2bot/rules.py` | who may be answered, and why not |
| `cs2bot/persona.py` | prompt construction (persona + dials + live game context) |
| `cs2bot/humanize.py` | dials → sampling and post-processing |
| `cs2bot/novelty.py` | similarity check that keeps replies from repeating |
| `cs2bot/snitch.py` | what the bot is willing to give away about you |
| `cs2bot/callouts.py` | recorded map positions and nearest-spot lookup |
| `cs2bot/llm/` | llama.cpp / Ollama / mock backends |
| `cs2bot/output/` | delivery: Windows `message.cfg` + keypress, or dry run |
| `cs2bot/web/` | FastAPI panel and static UI |
