---
name: testing-cs2bot
description: How to run and end-to-end test the CS2 llama chatbot control panel (FastAPI panel on port 8420) on a Linux box with no CS2, no Windows and no audio hardware. Covers starting the panel with a throwaway config, driving the mock LLM, proving team-vs-all chat routing from disk, exercising the Voice tab, and simulating typed chat through console.log.
---

# Testing the CS2 llama chatbot panel

The app is a local FastAPI control panel (`http://127.0.0.1:8420`) that reads CS2's
`console.log`, asks an LLM for a reply and types it back into the game. Almost everything
can be exercised on Linux without CS2, because the panel has a mock LLM backend, a
console.log tail you can write to yourself, and simulate endpoints for each input path.

## Devin Secrets Needed

None. The panel is local and unauthenticated; do not try to authenticate or use cookies.

## Starting the panel

```bash
cd /home/ubuntu/repos/cs2-llama-chatbot
rm -f /tmp/cs2bot-test.json /tmp/console.log   # clean slate: config is sticky between runs
rm -rf /tmp/cs2cfg && mkdir -p /tmp/cs2cfg
touch /tmp/console.log
CS2BOT_CONFIG=/tmp/cs2bot-test.json nohup .venv/bin/python -m cs2bot > /tmp/cs2bot.log 2>&1 &
```

Always point `CS2BOT_CONFIG` at a throwaway file and delete it first. Settings persist to
that JSON immediately on save, so a previous run's Output mode / cfg dir / reply channels
will silently change how the next run behaves.

`/tmp/cs2bot.log` is the single best evidence source: it logs every HTTP request with its
status code, so `grep -E 'HTTP/1.1" [45][0-9][0-9]' /tmp/cs2bot.log` is a cheap check for
500s, and `grep -c Traceback` catches unhandled exceptions.

## Panel conventions worth knowing

- The master **Start bot / Stop bot** button in the header runs the engine tick loop. Most
  background behaviour (log tailing, voice pumping) only happens while the bot is started.
- Nearly every control autosaves on change; there is usually no explicit Save button.
- Tabs: Personality, Intelligence, Model, Dead / alive, Strats, Voice, Snitch, Game, Test.
  Reply-channel checkboxes ("Reply in all chat" / "Reply in team chat") live at the very
  **bottom of the Intelligence tab** — you have to scroll to reach them.
- Set **Model tab -> Backend = Mock (no model)** so replies are instant and deterministic-ish.
  The mock returns canned CS2 chatter unrelated to the input, so never assert on reply
  *content*; assert that a reply happened and where it was routed.
- The mock's canned pool is small, so you will often see a `too similar, retrying: ...`
  line in the feed before the real reply. That is the anti-repetition guard working, not a bug.

## Proving chat routing (team vs all) without Windows

The default dry-run sender only shows replies in the panel, so it cannot prove *which* chat
a reply went to. To get file-based proof:

1. Game tab -> **Output = "Type into CS2 (Windows)"**
2. Game tab -> **CS2 cfg directory = `/tmp/cs2cfg`**
3. Game tab -> uncheck **"Only type when CS2 is the focused window"**

The Windows sender writes the console command to `<cfgdir>/message.cfg` *before* the
keypress fails on Linux. So after triggering a reply:

```bash
cat /tmp/cs2cfg/message.cfg     # say_team "..."  => team chat,  say "..." => all chat
```

This is far stronger evidence than the UI's "→ team chat:" label, which is hardcoded text.

## Simulating typed chat

With a console.log path configured (Game tab -> `console.log path = /tmp/console.log`),
append parser-recognised lines and the engine picks them up within a couple of seconds:

```bash
printf '01/15 12:00:01  [ALL] skelly: who queued this map\n' >> /tmp/console.log
```

The channel tag (`[ALL]`, `[CT]`, `[T]`, `[DEAD]`, `[SPEC]`) is what the parser keys on;
the leading timestamp is cosmetic. `scripts/fake_match.py /tmp/console.log` also works.

An unaddressed line like the above is *not* urgent, so it is subject to the Intelligence-tab
cooldown — handy for testing cooldown behaviour, annoying otherwise. Set **Intelligence ->
Cooldown (seconds) = 0** and **Reply probability = 1** with **Trigger words blank** when you
just want every line answered.

## Voice tab on a box without audio

`soundcard` and `faster-whisper` are optional extras and are normally absent. Expected,
correct behaviour: the Voice status box reads
`cannot listen here: soundcard is not installed (No module named 'soundcard')`, the device
dropdown holds only "default speakers", and nothing 500s.

**Observability trap:** the status box renders `!supported` first, so it shows the same
"cannot listen here" text whether or not a listener was ever attempted. To tell "never
started" from "tried and failed", open `http://127.0.0.1:8420/api/voice` in a browser tab
and read `status.error`:

- `error: ""` -> the listener was never started.
- `error: "RuntimeError: soundcard is not installed ..."` -> start was attempted and failed.

`status.running` should be `false` whenever `error` is set; `running: true` alongside an
error means a listener thread is stuck. Cross-check with:

```bash
for t in /proc/$(pgrep -f "python -m cs2bot" | head -1)/task/*; do cat $t/comm; done | sort -u
```

No `cs2bot-voice-*` thread names should survive after a failed start or a stop.

### Simulating speech

Voice tab -> "Say this out loud" box -> **"Pretend somebody said this"** posts to
`/api/voice/simulate`, which runs the real `handle_voice` path. Note it **bypasses
`_tick`/`pump_voice` and the listener threads entirely**, so it proves reply/routing logic
but proves nothing about listener startup or thread lifecycle — test those via `/api/voice`.

Gotchas:
- Clear **"Only answer speech containing"** (trigger words), otherwise transcripts are ignored.
- Keep the transcript above the **"Ignore speech shorter than (words)"** threshold.
- Blank/whitespace input is rejected with HTTP 422 and the panel shows `nothing was said`.
- Voice replies are always team-only by design — they must still produce `say_team` even
  with reply channels set to all-chat only.
- The Live feed tags voice input `[voice]` rather than `[all]`/`[team]`.

### Separate cooldown clocks

Voice and typed chat keep independent pacing clocks. To test, set Intelligence cooldown to
60 and Voice "Wait between answers" to 0, then run this 4-step sequence:

1. Simulate a voice line -> replies.
2. Immediately append a typed line -> should still reply (voice must not spend the typed clock).
3. Immediately append a second typed line -> should be skipped with `cooling down`
   (this step is essential; without it step 2 proves nothing, since a broken cooldown also passes).
4. Immediately simulate a second voice line -> should reply (typed must not spend the voice clock).

## Strats regression

Do **not** test `strat?` through the Test tab's "Try a reply" box. That endpoint
(`/api/simulate`) calls `generate_reply` directly and deliberately skips the strat caller,
so it returns an ordinary persona reply and looks like a regression when it is not.

Test it through the real chat path instead — append `[ALL] someone: strat?` (or any of the
Strats tab "Ask phrases", e.g. `whats the plan`) to console.log with the bot started. The
feed then shows a `strat →` entry.

With **"Say it in the persona's voice"** ON and the mock backend, the strat is rewritten into
a single canned mock line. Turn that checkbox **off** to see the raw playbook output and
confirm the strat content is real — you should get a header plus P1–P5 role lines.

## Suggested assertion checklist

- Panel loads, all 9 tabs render their controls.
- Voice tab explains why it cannot listen; `/api/voice` distinguishes never-started vs failed.
- Settings survive F5 and match the JSON on disk.
- Voice simulate replies, is tagged `[voice]`, and writes `say_team` to message.cfg.
- Same holds with reply channels = all only.
- Blank transcript -> 422 / `nothing was said`, no feed entry.
- Restart listening -> 200, status re-renders, still not running.
- `grep -E 'HTTP/1.1" 5[0-9][0-9]' /tmp/cs2bot.log` empty; browser console clean.
