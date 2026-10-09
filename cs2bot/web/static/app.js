const $ = (id) => document.getElementById(id);
const LOCAL_OLLAMA = "http://127.0.0.1:11434";
function isRemote(url) {
  try {
    const host = new URL(url).hostname;
    return !["127.0.0.1", "localhost", "::1", "0.0.0.0", ""].includes(host);
  } catch (_) {
    return false;
  }
}

let config = null;
let presets = {};
let saving = null;

/* id -> [config path, kind] */
const BINDINGS = {
  "persona-name": ["persona.name", "text"],
  "persona-description": ["persona.description", "text"],
  "persona-style": ["persona.style_notes", "text"],
  "persona-dead": ["persona.dead_notes", "text"],
  "persona-extra": ["persona.extra_instructions", "text"],
  "persona-banned": ["persona.banned_words", "list"],
  "persona-maxchars": ["persona.max_reply_chars", "int"],
  "persona-game-aware": ["persona.game_aware", "bool"],
  "speech-same-persona": ["speech_same_persona", "bool"],
  "speech-persona-name": ["speech_persona.name", "text"],
  "speech-persona-description": ["speech_persona.description", "text"],
  "speech-persona-style": ["speech_persona.style_notes", "text"],
  "speech-persona-extra": ["speech_persona.extra_instructions", "text"],
  "speech-persona-game-aware": ["speech_persona.game_aware", "bool"],
  "speech-model": ["llm.speech_ollama_model", "text"],
  "chat-model": ["llm.ollama_model", "text"],
  "chat-enabled": ["llm.chat_enabled", "bool"],
  "speech-enabled": ["llm.speech_enabled", "bool"],
  "poll-seconds": ["game.poll_seconds", "float"],
  "teammates-stance": ["teammates.stance", "text"],
  "teammates-custom": ["teammates.custom", "text"],

  iq: ["behavior.intelligence", "int"],
  literacy: ["behavior.literacy", "int"],
  unprompted: ["behavior.unprompted_advice", "bool"],
  "avoid-repeats": ["behavior.avoid_repeats", "bool"],
  "repeat-memory": ["behavior.repeat_memory", "int"],
  "repeat-similarity": ["behavior.repeat_similarity", "float"],
  "repeat-retries": ["behavior.repeat_retries", "int"],
  reply_probability: ["behavior.reply_probability", "float"],
  cooldown: ["behavior.cooldown_seconds", "float"],
  history_turns: ["behavior.history_turns", "int"],
  trigger_words: ["behavior.trigger_words", "list"],
  ignore_players: ["behavior.ignore_players", "list"],
  "typing-sim": ["behavior.typing_simulation", "bool"],
  "typing-speed": ["behavior.typing_delay_per_char", "float"],
  "reply-delay": ["behavior.reply_delay", "float"],
  "humanized-typing": ["behavior.humanized_typing", "bool"],
  "addressed-always": ["behavior.always_reply_when_addressed", "bool"],
  "addressed-only": ["behavior.only_reply_when_addressed", "bool"],

  "auto-sampling": ["generation.auto_from_intelligence", "bool"],
  temperature: ["generation.temperature", "float"],
  top_p: ["generation.top_p", "float"],
  top_k: ["generation.top_k", "int"],
  repeat_penalty: ["generation.repeat_penalty", "float"],
  max_tokens: ["generation.max_tokens", "int"],

  "llm-backend": ["llm.backend", "text"],
  "model-path": ["llm.model_path", "text"],
  n_ctx: ["llm.n_ctx", "int"],
  n_gpu_layers: ["llm.n_gpu_layers", "int"],
  n_threads: ["llm.n_threads", "int"],
  request_timeout: ["llm.request_timeout", "float"],
  "ollama-url": ["llm.ollama_url", "text"],
  "ollama-model": ["llm.ollama_model", "text"],
  "ollama-key": ["llm.ollama_api_key", "text"],
  "ollama-verify": ["llm.ollama_verify_tls", "bool"],

  "da-adapt": ["dead_alive.adapt_replies", "bool"],
  "da-track": ["dead_alive.track_players", "bool"],
  "da-enforce": ["dead_alive.enforce_visibility", "bool"],
  "da-reply-when-dead": ["dead_alive.reply_when_dead", "bool"],
  "da-dead-when-alive": ["dead_alive.reply_to_dead_when_alive", "bool"],
  "da-alive-when-dead": ["dead_alive.reply_to_alive_when_dead", "bool"],
  "da-warmup": ["dead_alive.treat_warmup_as_global", "bool"],
  "da-global": ["dead_alive.dead_chat_is_global", "bool"],
  "da-persona": ["dead_alive.use_dead_persona", "bool"],
  "da-assume": ["dead_alive.assume_alive_without_gsi", "bool"],

  "strat-enabled": ["strategy.enabled", "bool"],
  "strat-asked": ["strategy.answer_when_asked", "bool"],
  "strat-listen": ["strategy.listen_channel", "text"],
  "strat-reply": ["strategy.reply_channel", "text"],
  "strat-phrases": ["strategy.request_phrases", "list"],
  "strat-every-round": ["strategy.call_every_round", "bool"],
  "strat-round-start": ["strategy.round_start_only", "bool"],
  "strat-round-seconds": ["strategy.round_start_seconds", "float"],
  "strat-in-character": ["strategy.in_character", "bool"],
  "strat-max-lines": ["strategy.max_lines", "int"],
  "strat-name-players": ["strategy.name_players", "bool"],
  "strat-side": ["strategy.fallback_side", "text"],
  "strat-obey": ["strategy.obey_commands", "bool"],
  "obey-orders": ["strategy.obey_commands", "bool"],
  "obey-orders-speech": ["strategy.obey_commands", "bool"],
  "orders-listen": ["strategy.listen_channel", "text"],
  "orders-persona": ["strategy.obey_persona_commands", "bool"],
  "strat-quiet": ["strategy.quiet_seconds", "float"],
  "strat-persona-cmd": ["strategy.obey_persona_commands", "bool"],

  "snitch-enabled": ["snitch.enabled", "bool"],
  "snitch-asked": ["snitch.answer_when_asked", "bool"],
  "snitch-phrases": ["snitch.request_phrases", "list"],
  "snitch-interval": ["snitch.announce_interval", "float"],
  "snitch-channel": ["snitch.channel", "text"],
  "snitch-death": ["snitch.announce_on_death", "bool"],
  "snitch-position": ["snitch.reveal_position", "bool"],
  "snitch-health": ["snitch.reveal_health", "bool"],
  "snitch-weapon": ["snitch.reveal_weapon", "bool"],
  "snitch-bomb": ["snitch.reveal_bomb", "bool"],

  "reveal-enabled": ["reveal.enabled", "bool"],
  "initiative-enabled": ["initiative.enabled", "bool"],
  "initiative-on": ["initiative.enabled", "bool"],
  "initiative-on-speech": ["initiative.enabled", "bool"],
  "game-mode": ["behavior.game_mode", "bool"],
  "game-mode-speech": ["behavior.game_mode", "bool"],
  "initiative-channel": ["initiative.channel", "text"],
  "initiative-gap": ["initiative.min_gap_seconds", "number"],
  "initiative-chance": ["initiative.chance", "number"],
  "initiative-quiet": ["initiative.when_quiet_seconds", "number"],
  "initiative-round": ["initiative.on_round_start", "bool"],
  "initiative-death": ["initiative.on_death", "bool"],
  "reveal-message": ["reveal.message", "text"],
  "reveal-channel": ["reveal.channel", "text"],
  "reveal-mode": ["reveal.mode", "text"],
  "reveal-instructions": ["reveal.instructions", "text"],
  "reveal-link": ["reveal.link", "text"],

  "log-path": ["game.console_log_path", "text"],
  "cfg-dir": ["game.cfg_dir", "text"],
  "own-name": ["game.own_name", "text"],
  "name-aliases": ["game.name_aliases", "list"],
  "auto-detect-name": ["game.auto_detect_name", "bool"],
  "bind-key": ["game.bind_key", "text"],
  "char-limit": ["game.chat_char_limit", "int"],
  "send-delay": ["game.chat_send_delay", "float"],
  "output-backend": ["game.output_backend", "text"],
  "require-focus": ["game.require_focus", "bool"],

  "gsi-token": ["gsi.auth_token", "text"],

  "respond-to": ["respond_to", "text"],
  "voice-speak-engine": ["voice.speak_engine", "text"],
  "voice-device": ["voice.device", "text"],
  "voice-reply-with": ["voice.reply_with", "text"],
  "voice-speak-device": ["voice.speak_device", "text"],
  "voice-speak-monitor": ["voice.speak_monitor", "bool"],
  "voice-talk-key": ["voice.talk_key", "text"],
  "voice-capture": ["voice.capture", "text"],
  "voice-enabled": ["voice.enabled", "bool"],
  "voice-enabled-speech": ["voice.enabled", "bool"],
  "voice-speak-voice": ["voice.speak_voice", "text"],
  "voice-speak-rate": ["voice.speak_rate", "number"],
  "voice-model": ["voice.model", "text"],
  "voice-answer": ["voice.answer", "text"],
  "voice-triggers": ["voice.trigger_words", "list"],
  "voice-cooldown": ["voice.cooldown_seconds", "float"],
  "voice-min-words": ["voice.min_words", "int"],
  "voice-floor": ["voice.noise_floor", "float"],
};

const LITERACY_DESCRIPTIONS = [
  [15, "Barely literate: a few lowercase words, no punctuation, frequent typos."],
  [35, "Careless: one short lowercase line, chat abbreviations, some typos."],
  [60, "Average: short sentences, mostly lowercase, light slang."],
  [85, "Clear: plain sentences, correct spelling, minimal slang."],
  [101, "Precise: correct grammar and punctuation, well-chosen words."],
];

const IQ_DESCRIPTIONS = [
  [15, "Clueless: no tactics, wrong callouts, reacts to the last thing said."],
  [35, "Weak game sense: vague advice, confident but usually wrong."],
  [60, "Average game sense: basic economy and callouts, no deep reads."],
  [85, "Strong: concrete callouts, economy awareness, reads the enemy."],
  [101, "Professional: map knowledge, utility, timings - and right about them."],
];

function getPath(obj, path) {
  return path.split(".").reduce((acc, key) => (acc == null ? acc : acc[key]), obj);
}

function setPath(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  const target = keys.reduce((acc, key) => (acc[key] ??= {}), obj);
  target[last] = value;
}

function readField(el, kind) {
  if (kind === "bool") return el.checked;
  if (kind === "int") return parseInt(el.value || "0", 10);
  if (kind === "float") return parseFloat(el.value || "0");
  if (kind === "list") return el.value.split(",").map((s) => s.trim()).filter(Boolean);
  return el.value;
}

function writeField(el, kind, value) {
  if (kind === "bool") el.checked = Boolean(value);
  else if (kind === "list") el.value = (value || []).join(", ");
  else el.value = value ?? "";
}

function renderConfig() {
  keepChosen($("speech-model"), config.llm.speech_ollama_model);
  keepChosen($("chat-model"), config.llm.ollama_model);
  for (const [id, [path, kind]] of Object.entries(BINDINGS)) {
    const el = $(id);
    if (el) writeField(el, kind, getPath(config, path));
  }
  renderPlacement();
  renderOrderOptions();
  $("speech-persona-block").style.display = config.speech_same_persona ? "none" : "";
  const remote = isRemote(config.llm.ollama_url);
  $("use-server").checked = remote;
  $("server-block").style.display = remote ? "" : "none";
  $("reply-all").checked = config.behavior.reply_channels.includes("all");
  $("reply-team").checked = config.behavior.reply_channels.includes("team");
  renderDials();
  renderSavedPersonas();
}

function renderDials() {
  for (const [id, field, table] of [
    ["iq", "intelligence", IQ_DESCRIPTIONS],
    ["literacy", "literacy", LITERACY_DESCRIPTIONS],
  ]) {
    const value = config.behavior[field];
    $(`${id}-value`).textContent = value;
    $(`${id}-desc`).textContent = table.find(([limit]) => value < limit)[1];
  }
  $("delay-value").textContent = config.behavior.humanized_typing
    ? "typing speed"
    : `${Number(config.behavior.reply_delay).toFixed(1)}s`;
  $("reply-delay").disabled = config.behavior.humanized_typing;
}

function renderSavedPersonas() {
  renderPresetChoices();
}

function renderPresetChoices() {
  const option = (name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`;
  const saved = Object.keys(config.saved_personas || {});
  $("preset").innerHTML =
    '<option value="">— choose a preset —</option>' +
    `<optgroup label="Built in">${Object.keys(presets).map(option).join("")}</optgroup>` +
    (saved.length ? `<optgroup label="Your personas">${saved.map(option).join("")}</optgroup>` : "");
}

function scheduleSave() {
  clearTimeout(saving);
  saving = setTimeout(saveConfig, 350);
}

async function saveConfig() {
  const response = await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    pushEvent({ kind: "error", data: { message: `saving settings failed (${response.status})` } });
    return;
  }
  config = await response.json();
}

function bindInputs() {
  for (const [id, [path, kind]] of Object.entries(BINDINGS)) {
    const el = $(id);
    if (!el) continue;
    el.addEventListener("input", () => {
      setPath(config, path, readField(el, kind));
      for (const [other, [otherPath]] of Object.entries(BINDINGS))
        if (other !== id && otherPath === path && $(other)) writeField($(other), kind, readField(el, kind));
      if (["iq", "literacy", "reply-delay", "humanized-typing"].includes(id)) renderDials();
      if (path === "strategy.obey_commands") renderOrderOptions();
      scheduleSave();
    });
  }
  for (const [id, channel] of [["reply-all", "all"], ["reply-team", "team"]]) {
    $(id).addEventListener("input", () => {
      const channels = new Set(config.behavior.reply_channels);
      $(id).checked ? channels.add(channel) : channels.delete(channel);
      config.behavior.reply_channels = [...channels];
      scheduleSave();
    });
  }
}

function placementOf(llm) {
  if (llm.cpu_only) return "cpu";
  if (!llm.gpu_auto && llm.n_gpu_layers >= 0) return "split";
  return "gpu";
}

function applyPlacement(mode) {
  const llm = config.llm;
  if (mode === "cpu") {
    llm.cpu_only = true;
  } else if (mode === "split") {
    llm.cpu_only = false;
    llm.gpu_auto = false;
    llm.n_gpu_layers = Math.max(1, Number($("split-layers").value || 16));
  } else {
    llm.cpu_only = false;
    llm.gpu_auto = true;
    llm.n_gpu_layers = -1;
  }
  renderPlacement();
}

function renderPlacement() {
  const mode = placementOf(config.llm);
  $("llm-placement").value = mode;
  $("split-layers-label").style.display = mode === "split" ? "" : "none";
  if (mode === "split") $("split-layers").value = config.llm.n_gpu_layers;
  else if (!$("split-layers").value) $("split-layers").value = 16;
  $("n_gpu_layers").value = config.llm.cpu_only ? 0 : config.llm.n_gpu_layers;
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      document.querySelectorAll(".panel").forEach((panel) => {
        panel.dataset.active = String(panel.dataset.panel === tab.dataset.tab);
      });
      if (tab.dataset.tab === "speech") renderVoice();
      if (tab.dataset.tab === "advanced") renderGpu();
    });
  });
}

/* ---------- live feed ---------- */

function line(text, className, meta) {
  const feed = $("feed");
  const stick = feed.scrollTop + feed.clientHeight > feed.scrollHeight - 60;
  const row = document.createElement("div");
  row.className = `event ${className}`;
  row.innerHTML = text + (meta ? `<span class="meta">${meta}</span>` : "");
  feed.appendChild(row);
  while (feed.childElementCount > 400) feed.removeChild(feed.firstChild);
  if (stick) feed.scrollTop = feed.scrollHeight;
}

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function chatClass(message) {
  const classes = ["chat"];
  if (message.sender_state === "dead") classes.push("dead");
  if (message.sender_team === "CT") classes.push("ct");
  if (message.sender_team === "T") classes.push("t");
  if (message.addressed_to_me) classes.push("mention");
  return classes.join(" ");
}

function pushEvent(event) {
  const data = event.data || {};
  if (event.kind === "chat") {
    const tag =
      data.source === "voice"
        ? "[voice]"
        : `[${data.channel}]${data.sender_state === "dead" ? " *DEAD*" : ""}`;
    line(
      `${escapeHtml(tag)} <span class="who">${escapeHtml(data.sender)}</span>: ${escapeHtml(data.text)}`,
      chatClass(data),
      data.addressed_to_me ? escapeHtml(`→ you (${data.mention_reason})`) : "",
    );
  } else if (event.kind === "reply") {
    line(
      `<span class="who">bot →</span> ${escapeHtml(data.text)}`,
      `reply ${data.delivered ? "" : "failed"}`,
      `${data.latency_ms}ms · ${escapeHtml(data.reason)}`,
    );
  } else if (event.kind === "reveal") {
    line(
      `<span class="who">reveal →</span> ${escapeHtml(data.text)}`,
      `reply ${data.delivered ? "" : "failed"}`,
      escapeHtml(data.reason),
    );
  } else if (event.kind === "strategy") {
    line(
      `<span class="who">strat →</span> ${escapeHtml(data.text)}`,
      `reply ${data.delivered ? "" : "failed"}`,
      escapeHtml(
        [data.map, data.side, data.strategy].filter(Boolean).join(" ") + ` · ${data.reason}`,
      ),
    );
  } else if (event.kind === "command") {
    const orders = {
      quiet: `${escapeHtml(data.by)} told the bot to be quiet`,
      talk: `${escapeHtml(data.by)} told the bot to talk again`,
      persona: `${escapeHtml(data.by)} made the bot ${escapeHtml(data.to || "")}`,
    };
    line(
      orders[data.kind] || escapeHtml(data.kind),
      "gamestate",
      data.kind === "quiet" ? escapeHtml(`for ${data.for}s`) : "",
    );
  } else if (event.kind === "snitch") {
    line(
      `<span class="who">snitch →</span> ${escapeHtml(data.text)}`,
      `reply ${data.delivered ? "" : "failed"}`,
      escapeHtml(data.reason),
    );
  } else if (event.kind === "skipped") {
    line(`skipped ${escapeHtml(data.message.sender)}`, "skipped", escapeHtml(data.reason));
  } else if (event.kind === "repeat") {
    line(
      `too similar, retrying: ${escapeHtml(data.text)}`,
      "skipped",
      escapeHtml(`echoes "${data.echoed}" · attempt ${data.attempt}/${data.attempts}`),
    );
  } else if (event.kind === "error") {
    line(escapeHtml(data.message), "error");
  } else if (event.kind === "identity") {
    line(`your name looks like "${escapeHtml(data.name)}"`, "gamestate", escapeHtml(data.source));
  } else if (event.kind === "gamestate") {
    const extra = [data.map_name, data.round_phase].filter(Boolean).join(" · ");
    $("gamestate-line").textContent =
      data.state === "unknown" || !data.state
        ? "game state: unknown (CS2 is not sending game state - check the GSI setup on the Game tab)"
        : `game state: ${data.state}${data.health != null ? ` (${data.health} hp)` : ""}${extra ? ` - ${extra}` : ""}`;
  }
}

function renderStatus(status) {
  const setPill = (id, text, cls) => {
    const el = $(id);
    el.textContent = text;
    el.className = `pill ${cls || ""}`;
  };
  setPill("pill-state", `you: ${status.local_state}`, status.local_state === "dead" ? "bad" : "good");
  setPill("pill-gsi", status.gsi_connected ? "gsi: connected" : "gsi: waiting", status.gsi_connected ? "good" : "warn");
  setPill("pill-log", status.log_attached ? "log: attached" : "log: detached", status.log_attached ? "good" : "warn");
  setPill(
    "pill-llm",
    `llm: ${status.llm_backend}`,
    status.llm_status.startsWith("error") ? "bad" : status.llm_status === "not checked" ? "" : "good",
  );
  setPill("pill-sender", `output: ${status.sender}`);
  if (status.pull_status) $("pull-note").textContent = status.pull_status;
  setPill(
    "pill-name",
    `you: ${status.own_name || "unknown"}`,
    status.own_name ? "good" : "warn",
  );
  $("pill-name").title = `name source: ${status.name_source}`;
  $("version").textContent = status.version ? `v${status.version}` : "";
  const toggle = $("toggle");
  toggle.dataset.on = String(status.enabled);
  toggle.textContent = status.enabled ? "Stop bot" : "Start bot";
  $("feed-note").textContent = status.last_error || status.log_path || "";
}

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (raw) => {
    const event = JSON.parse(raw.data);
    if (event.kind === "snapshot") {
      renderStatus(event.data.status);
      event.data.events.forEach(pushEvent);
      return;
    }
    if (event.kind === "status") return renderStatus(event.data);
    if (event.kind === "config") {
      config = event.data;
      return;
    }
    pushEvent(event);
  };
  ws.onclose = () => setTimeout(connect, 1500);
}

/* ---------- actions ---------- */

function bindActions() {
  $("toggle").addEventListener("click", async () => {
    const enabled = $("toggle").dataset.on !== "true";
    const response = await fetch("/api/enabled", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    renderStatus(await response.json());
  });

  $("clear-feed").addEventListener("click", () => ($("feed").innerHTML = ""));

  $("preset").addEventListener("change", () => {
    const name = $("preset").value;
    const preset = (config.saved_personas || {})[name] || presets[name];
    if (!preset) return;
    config.persona = structuredClone(preset);
    renderConfig();
    scheduleSave();
  });

  $("refresh-models").addEventListener("click", renderModels);
  fillSpeechModels();
  $("pull-speech-model").addEventListener("click", async () => {
    const tag = $("speech-model").value || config.llm.ollama_model;
    $("pull-note").textContent = `installing ${tag}…`;
    const body = await (await fetch("/api/llm/pull", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: tag }) })).json();
    $("pull-note").textContent = body.status;
  });
  $("speech-same-persona").addEventListener("change", () => {
    $("speech-persona-block").style.display = $("speech-same-persona").checked ? "none" : "";
  });
  $("refresh-gpu").addEventListener("click", renderGpu);

  $("use-remote").addEventListener("click", async () => {
    $("use-server").checked = true;
    $("server-block").style.display = "";
    let host = $("remote-host").value.trim();
    if (!host) return;
    if (!/^https?:\/\//.test(host)) host = `http://${host}`;
    if (!/:\d+$/.test(host)) host = `${host}:11434`;
    config.llm.backend = "ollama";
    config.llm.ollama_url = host;
    config.llm.cpu_only = false;
    $("llm-backend").value = "ollama";
    $("ollama-url").value = host;
    $("remote-note").textContent = "checking…";
    await saveConfig();
    const response = await fetch("/api/llm/check", { method: "POST" });
    $("remote-note").textContent = (await response.json()).status;
  });

  $("check-llm").addEventListener("click", async () => {
    $("llm-note").textContent = "checking…";
    await saveConfig();
    const response = await fetch("/api/llm/check", { method: "POST" });
    $("llm-note").textContent = (await response.json()).status;
  });

  $("persona-save").addEventListener("click", async () => {
    const name = ($("persona-save-name").value || config.persona.name).trim();
    if (!name) return;
    await saveConfig();
    const response = await fetch("/api/personas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, persona: config.persona }),
    });
    if (!response.ok) {
      $("persona-note").textContent = "could not save";
      return;
    }
    config.saved_personas[name] = structuredClone(config.persona);
    $("persona-save-name").value = "";
    renderSavedPersonas();
    $("preset").value = name;
    $("persona-note").textContent = `saved "${name}" - it is in the Preset list`;
  });

  $("persona-delete").addEventListener("click", async () => {
    const name = $("preset").value;
    if (!(name in (config.saved_personas || {}))) {
      $("persona-note").textContent = "pick one of your personas in the Preset list first";
      return;
    }
    if (!confirm(`Delete persona "${name}"?`)) return;
    await fetch(`/api/personas/${encodeURIComponent(name)}`, { method: "DELETE" });
    delete config.saved_personas[name];
    renderSavedPersonas();
    $("persona-note").textContent = `deleted "${name}"`;
  });

  $("callout-add").addEventListener("click", async () => {
    const name = $("callout-name").value.trim();
    if (!name) return;
    const response = await fetch("/api/callouts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) {
      $("callout-output").textContent = (await response.json()).detail;
      return;
    }
    $("callout-name").value = "";
    renderCallouts();
  });

  $("callout-refresh").addEventListener("click", renderCallouts);

  $("voice-test").addEventListener("click", async () => {
    await saveConfig();
    $("voice-output").textContent = "listening…";
    const response = await fetch("/api/voice/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("voice-say").value }),
    });
    const body = await response.json();
    if (!response.ok) {
      $("voice-output").textContent = body.detail;
      return;
    }
    $("voice-output").textContent = body.replied
      ? `heard "${body.heard}" → team chat: ${body.reply.text}`
      : `heard "${body.heard}" — said nothing back`;
  });

  $("voice-cable-install").addEventListener("click", async () => {
    $("voice-cable-status").textContent = "downloading VB-Cable… accept the Windows prompt when it appears";
    const body = await (await fetch("/api/voice/cable/install", { method: "POST" })).json();
    $("voice-cable-status").textContent = body.detail;
  });
  $("voice-cable-use").addEventListener("click", async () => {
    const body = await (await fetch("/api/voice/cable")).json();
    if (!body.input_id) {
      $("voice-cable-status").textContent = "no CABLE Input device found - install VB-Cable and restart Windows first";
      return;
    }
    config.voice.speak_device = body.input_id;
    await renderVoice();
    $("voice-cable-status").textContent = "playing into CABLE Input - now set CS2's microphone to CABLE Output and save";
  });
  $("voice-speak-engine").addEventListener("change", async () => {
    config.voice.speak_engine = $("voice-speak-engine").value;
    config.voice.speak_voice = "";
    await renderVoice();
  });
  $("llm-placement").addEventListener("change", () => applyPlacement($("llm-placement").value));
  $("split-layers").addEventListener("change", () => applyPlacement("split"));
  $("check-updates").addEventListener("click", () => checkServerVersion(true));
  $("update-badge").addEventListener("click", () => {
    document.querySelector('[data-tab="server"]').click();
  });
  $("test-server").addEventListener("click", async () => {
    $("server-test-note").textContent = "testing the server…";
    await saveConfig();
    const response = await fetch("/api/llm/check", { method: "POST" });
    $("server-test-note").textContent = (await response.json()).status;
    await checkServerVersion();
  });
  $("use-server").addEventListener("change", async () => {
    const on = $("use-server").checked;
    $("server-block").style.display = on ? "" : "none";
    if (!on) {
      config.llm.ollama_url = LOCAL_OLLAMA;
      $("ollama-url").value = LOCAL_OLLAMA;
      $("server-test-note").textContent = "back to this PC";
      await saveConfig();
    }
  });
  $("update-server").addEventListener("click", async () => {
    $("server-version").textContent = "asking the server to update…";
    $("update-server").hidden = true;
    $("update-badge").hidden = true;
    const response = await fetch("/api/server/update", { method: "POST" });
    const data = await response.json();
    $("server-version").textContent = data.error
      ? data.error
      : `${data.status} - it downloads and installs on its own; test again in a few minutes`;
  });
  $("voice-preview").addEventListener("click", async () => {
    const voice = $("voice-speak-voice").value;
    $("voice-speak-output").textContent = "fetching the voice if needed, then playing on your speakers…";
    const body = await (
      await fetch("/api/voice/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice,
          engine: $("voice-speak-engine").value,
          rate: Number($("voice-speak-rate").value || 0),
        }),
      })
    ).json();
    $("voice-speak-output").textContent = body.detail;
    await renderVoice();
  });
  $("voice-talk-key-detect").addEventListener("click", async () => {
    $("voice-talk-key-note").textContent = "reading CS2's keybinds…";
    const body = await (await fetch("/api/voice/talk-key")).json();
    if (body.key) {
      config.voice.talk_key = body.key;
      $("voice-talk-key").value = body.key;
      $("voice-talk-key-note").textContent = `detected "${body.key}" in ${body.where}`;
      await saveConfig();
    } else {
      $("voice-talk-key-note").textContent = body.where;
    }
  });
  $("voice-speak-test").addEventListener("click", async () => {
    $("voice-speak-output").textContent = "speaking…";
    const response = await fetch("/api/voice/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "mic check, this is the bot" }),
    });
    const body = await response.json();
    $("voice-speak-output").textContent = body.spoken
      ? "spoken - did your team hear it?"
      : `could not speak: ${body.detail}`;
  });
  $("voice-restart").addEventListener("click", async () => {
    await saveConfig();
    await fetch("/api/voice/restart", { method: "POST" });
    renderVoice();
  });

  $("install-gsi").addEventListener("click", async () => {
    await saveConfig();
    const response = await fetch("/api/gsi/install", { method: "POST" });
    const body = await response.json();
    $("gsi-note").textContent = response.ok ? `written to ${body.path} — restart CS2` : body.detail;
  });

  $("gsi-check").addEventListener("click", async () => {
    const body = await (await fetch("/api/gsi/status")).json();
    const lines = [
      body.connected
        ? `connected — CS2 posted ${body.seconds_since_post}s ago`
        : "not connected",
      `endpoint: ${body.endpoint}`,
      ...body.problems.map((problem) => `• ${problem}`),
    ];
    if (body.connected) {
      lines.push(
        `map: ${body.map || "—"} (${body.mode || "—"}) · side: ${body.team} · round ${body.round_number} ${body.round_phase}`,
        `position: ${body.has_position ? "reported" : "not reported"}`,
      );
    }
    lines.push(body.note);
    $("gsi-result").textContent = lines.join("\n");
  });

  $("name-detect").addEventListener("click", async () => {
    await saveConfig();
    $("name-note").textContent = "asking CS2…";
    const body = await (await fetch("/api/name/detect", { method: "POST" })).json();
    // The name arrives a moment later, in the console line CS2 prints in answer.
    await new Promise((done) => setTimeout(done, 1500));
    const status = await (await fetch("/api/status")).json();
    $("name-note").textContent = body.asked
      ? `you are ${status.own_name || "still unknown"} (${status.name_source})`
      : body.detail;
  });

  $("output-test").addEventListener("click", async () => {
    await saveConfig();
    $("output-note").textContent = "pressing the key…";
    const body = await (await fetch("/api/output/test", { method: "POST" })).json();
    $("output-note").textContent = body.confirmed ? "the game ran it" : "no answer from the game";
    $("output-result").textContent = [body.advice, "", body.detail, JSON.stringify(body, null, 2)]
      .join("\n");
  });

  $("run-as-admin").addEventListener("click", async () => {
    $("output-note").textContent = "asking Windows…";
    const body = await (await fetch("/api/restart-as-admin", { method: "POST" })).json();
    // On success this panel dies with the process; the new one comes up on the same address.
    $("output-note").textContent = body.detail;
  });

  $("log-refresh").addEventListener("click", renderLog);

  $("parse-run").addEventListener("click", async () => {
    const response = await fetch("/api/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("parse-input").value }),
    });
    const { results, own_name, name_source } = await response.json();
    const header = `your name: ${own_name || "unknown"} (${name_source})`;
    $("parse-output").textContent = [header]
      .concat(
        results.map(({ line, parsed, detected_name }) => {
          if (detected_name) return `name detected: ${detected_name}`;
          if (!parsed) return `not chat: ${line}`;
          const aimed = parsed.addressed_to_me ? ` | TO YOU (${parsed.mention_reason})` : "";
          return `${parsed.channel} | ${parsed.sender} | ${parsed.sender_state} | ${parsed.sender_team} | "${parsed.text}"${aimed}`;
        }),
      )
      .join("\n");
  });

  $("sim-run").addEventListener("click", async () => {
    $("sim-output").textContent = "generating…";
    await saveConfig();
    const response = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ line: $("sim-line").value, local_state: $("sim-state").value }),
    });
    const body = await response.json();
    if (!response.ok) {
      $("sim-output").textContent = body.detail;
      return;
    }
    const aimed = body.message.addressed_to_me ? ` (talking to you: ${body.message.mention_reason})` : "";
    $("sim-output").textContent = body.would_reply
      ? `reply: ${body.reply}${aimed}`
      : `no reply — ${body.reason}${aimed}`;
  });
}

async function renderLog() {
  const body = await (await fetch("/api/log")).json();
  const size = body.log_exists ? `${body.log_size} bytes, last written ${body.log_modified}` : "missing";
  $("log-note").textContent = `${body.path || "no path set"} — ${size}`;
  if (!body.log_exists) {
    $("log-output").textContent =
      "CS2 has not created this file. Add -condebug to the launch options and restart the game.";
    return;
  }
  if (!body.lines.length) {
    $("log-output").textContent = body.attached
      ? "watching, but CS2 has not written a line since the bot started"
      : "not reading the log yet — press Start bot";
    return;
  }
  $("log-output").textContent = body.lines
    .map(({ line, chat }) => `${chat ? "chat  " : "      "}${line}`)
    .join("\n");
}

function renderOrderOptions() {
  for (const id of ["obey-options", "obey-options-speech"])
    $(id).style.display = config.strategy.obey_commands ? "" : "none";
}

async function renderVoice() {
  const body = await (await fetch("/api/voice")).json();
  const select = $("voice-device");
  select.innerHTML =
    '<option value="">default speakers</option>' +
    body.devices
      .map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`)
      .join("");
  select.value = config.voice.device;
  const out = $("voice-speak-device");
  out.innerHTML =
    '<option value="">default speakers (your team will not hear it)</option>' +
    body.devices
      .map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`)
      .join("");
  out.value = config.voice.speak_device;
  if (body.devices_error) $("voice-speak-output").textContent = `no output devices listed: ${body.devices_error}`;
  const voices = $("voice-speak-voice");
  const engine = config.voice.speak_engine || "piper";
  $("voice-speak-engine").value = engine;
  const tts = body.status.tts || { voices: [] };
  const kokoro = body.status.kokoro || { voices: [] };
  let options = "";
  if (engine === "piper")
    options = tts.voices
      .map((v) => {
        const note = v.ready ? "" : v.downloading ? " (downloading…)" : ` (${v.size_mb} MB download)`;
        return `<option value="${escapeHtml(v.id)}">${escapeHtml(v.label)}${note}</option>`;
      })
      .join("");
  else if (engine === "kokoro") {
    const note = kokoro.ready ? "" : kokoro.downloading ? " (downloading…)" : ` (${kokoro.size_mb} MB download, once)`;
    options = kokoro.voices
      .map((v) => `<option value="${escapeHtml(v.id)}">${escapeHtml(v.label)}${note}</option>`)
      .join("");
  } else
    options =
      '<option value="">Windows default</option>' +
      (body.voices || []).map((v) => `<option value="windows:${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
  voices.innerHTML = options;
  const known = [...voices.options].some((o) => o.value === config.voice.speak_voice);
  voices.value = known ? config.voice.speak_voice : voices.options[0] ? voices.options[0].value : "";
  config.voice.speak_voice = voices.value;
  const status = body.status;
  fetch("/api/voice/cable")
    .then((r) => r.json())
    .then((cable) => {
      $("voice-cable-status").textContent = cable.installed
        ? `virtual microphone installed: ${cable.devices.join(", ")}`
        : "virtual microphone not installed yet";
    })
    .catch(() => {});
  if (status.speak_error) $("voice-speak-output").textContent = `could not speak: ${status.speak_error}`;
  else if (!status.speak_supported)
    $("voice-speak-output").textContent = `cannot talk here: ${status.speak_unsupported_reason}`;
  else if (status.said)
    $("voice-speak-output").textContent = `said ${status.said} line${status.said === 1 ? "" : "s"}, last: "${status.last_said}"`;
  const lines = [];
  if (status.error) lines.push(`stopped: ${status.error}`);
  else if (!status.supported) lines.push(`cannot listen here: ${status.unsupported_reason}`);
  else if (status.downloading) lines.push(`downloading the ${status.model} speech model…`);
  else if (status.running) lines.push("listening");
  else if (status.enabled) lines.push("starting…");
  else lines.push("not listening");
  lines.push(
    `speech model: ${status.model} (${status.model_ready ? "ready" : "downloads on first use"})`,
    `heard ${status.heard} time${status.heard === 1 ? "" : "s"}${status.last_text ? `, last: "${status.last_text}"` : ""}`,
  );
  $("voice-status").textContent = lines.join("\n");
}

async function renderCallouts() {
  const body = await (await fetch("/api/callouts")).json();
  const head = body.map
    ? `${body.map}${body.callout ? ` - you are at ${body.callout}` : ""}`
    : "no map yet (is GSI connected?)";
  const where = body.position
    ? `position ${body.position.x.toFixed(0)}, ${body.position.y.toFixed(0)}, ${body.position.z.toFixed(0)}`
    : "CS2 is not reporting a position";
  const recorded = body.callouts.length
    ? body.callouts.map((c) => `  ${c.name} (${c.x.toFixed(0)}, ${c.y.toFixed(0)}, ${c.z.toFixed(0)})`)
    : ["  nothing recorded for this map yet"];
  $("callout-output").textContent = [head, where, "recorded:"].concat(recorded).join("\n");
}

const VERDICT_CLASS = { fits: "fits", tight: "tight", "cpu only": "cpu", "too big": "no", unknown: "no" };

async function fillSpeechModels() {
  const body = await (await fetch("/api/catalog")).json();
  fillSpeechModelOptions(body.models);
}

const TIERS = [["best", "Best"], ["better", "Better"], ["good", "Good"]];

function optionsFor(models) {
  return models.map((m) => `<option value="${escapeHtml(m.ollama)}">${escapeHtml(m.label)}</option>`).join("");
}

function keepChosen(select, chosen) {
  if (chosen && ![...select.options].some((o) => o.value === chosen)) {
    select.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(chosen)}">${escapeHtml(chosen)}</option>`);
  }
  select.value = chosen;
}

function fillSpeechModelOptions(models) {
  const groups = TIERS.filter(([tier]) => models.some((m) => m.speech_tier === tier))
    .map(([tier, name]) => `<optgroup label="${name}">${optionsFor(models.filter((m) => m.speech_tier === tier))}</optgroup>`)
    .join("");
  $("speech-model").innerHTML = `<option value="">Same as the chat model</option>` + groups;
  keepChosen($("speech-model"), config.llm.speech_ollama_model);
  $("chat-model").innerHTML = optionsFor(models);
  keepChosen($("chat-model"), config.llm.ollama_model);
}

const UPDATE_POLL_MS = 4 * 60 * 60 * 1000;

async function checkServerVersion(byHand = false) {
  if (byHand) $("server-version").textContent = "checking…";
  let data;
  try {
    data = await (await fetch("/api/updates")).json();
  } catch (error) {
    $("server-version").textContent = `could not check: ${error}`;
    return;
  }
  const server = data.server || {};
  const latest = data.latest || {};
  const lines = [`you: ${data.client}`];
  if (server.error) lines.push(`server: unknown - ${server.error}`);
  else if (server.updating) lines.push(`server: updating (${(server.log || []).slice(-1)[0] || "…"})`);
  else lines.push(`server: ${server.version}${data.server_behind ? " - OUT OF DATE" : data.in_sync ? " - same as you" : ""}`);
  lines.push(latest.error ? `latest release: unknown - ${latest.error}` : `latest release: ${latest.version}`);
  if (data.client_behind) lines.push(`a newer client is out - get it at ${latest.url}`);
  $("server-version").textContent = lines.join("\n");
  const serverStale = data.server_behind && !server.updating && !server.error;
  $("update-server").hidden = !serverStale;
  $("update-badge").hidden = !serverStale;
  $("update-badge").textContent = serverStale ? `server out of date (${server.version})` : "";
}

async function renderModels() {
  $("hardware-note").textContent = "looking…";
  const body = await (await fetch("/api/models")).json();
  const hw = body.hardware;
  const card = hw.vram_gb
    ? `${hw.gpu || "GPU"}: ${hw.vram_gb}GB, about ${hw.vram_for_model_gb}GB free once CS2 has taken ${hw.cs2_reserve_gb}GB`
    : "no GPU memory reported - the model would run on the CPU";
  const ram = hw.ram_gb ? `${hw.ram_gb}GB system RAM` : "system RAM unknown";
  $("hardware-note").textContent = `${card}\n${ram}`;
  fillSpeechModelOptions(body.models);
  $("model-picks").innerHTML = body.models
    .map((model) => {
      const tag = model.key === body.recommended ? " · best fit here" : "";
      return `<div class="pick">
        <div class="top">
          <span class="name">${escapeHtml(model.label)}${escapeHtml(tag)}</span>
          <span class="verdict ${VERDICT_CLASS[model.verdict] || "no"}">${escapeHtml(model.verdict)}</span>
        </div>
        <div class="why">${escapeHtml(model.why)} — ${escapeHtml(model.note)}</div>
        <div class="specs">${model.params} · ${model.download_gb}GB download · ${model.vram_gb}GB VRAM or ${model.ram_gb}GB RAM · ${escapeHtml(model.ollama)}</div>
        <div class="actions"><button class="action" data-use-model="${escapeHtml(model.key)}">Use this one</button></div>
      </div>`;
    })
    .join("");
  for (const button of $("model-picks").querySelectorAll("[data-use-model]")) {
    const model = body.models.find((m) => m.key === button.dataset.useModel);
    button.addEventListener("click", () => {
      config.llm.backend = "ollama";
      config.llm.ollama_model = model.ollama;
      keepChosen($("chat-model"), model.ollama);
      renderConfig();
      scheduleSave();
      $("llm-note").textContent = `set to ${model.ollama} - pull it with: ollama pull ${model.ollama}`;
    });
  }
}

async function gpuAction(path, body) {
  const result = await (await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })).json();
  $("gpu-note").textContent = result.detail;
  await renderGpu();
}

async function renderGpu() {
  const body = await (await fetch("/api/gpu")).json();
  const card = body.vram_gb ? `${body.gpu}: ${body.vram_gb}GB` : "no GPU memory reported";
  const used = body.nvidia_smi
    ? `${(body.used_mb / 1024).toFixed(1)}GB in use by ${body.processes.length} process(es)`
    : "nvidia-smi not found - per-process use is only readable on NVIDIA cards";
  $("gpu-note").textContent = `${card}\n${used}`;
  $("gpu-models").innerHTML = body.models.length
    ? body.models
        .map(
          (m) => `<div class="pick"><div class="top">
            <span class="name">${escapeHtml(m.name)}</span>
            <span class="specs">${m.vram_gb}GB on the card of ${m.size_gb}GB</span></div>
            <div class="actions"><button class="action" data-unload="${escapeHtml(m.name)}">Unload</button></div>
          </div>`
        )
        .join("")
    : '<div class="note">nothing loaded (or Ollama is not running)</div>';
  $("gpu-processes").innerHTML = body.processes.length
    ? body.processes
        .map(
          (p) => `<div class="pick"><div class="top">
            <span class="name">${escapeHtml(p.name)} <span class="specs">pid ${p.pid}</span></span>
            <span class="specs">${(p.used_mb / 1024).toFixed(1)}GB</span></div>
            <div class="actions">${
              p.protected
                ? '<span class="note">kept - the game or the bot needs it</span>'
                : `<button class="action" data-kill="${p.pid}">End process</button>`
            }</div>
          </div>`
        )
        .join("")
    : '<div class="note">nothing to show</div>';
  for (const button of $("gpu-models").querySelectorAll("[data-unload]")) {
    button.addEventListener("click", () => gpuAction("/api/gpu/unload", { model: button.dataset.unload }));
  }
  for (const button of $("gpu-processes").querySelectorAll("[data-kill]")) {
    button.addEventListener("click", () => gpuAction("/api/gpu/kill", { pid: Number(button.dataset.kill) }));
  }
}

async function init() {
  const response = await fetch("/api/config");
  const body = await response.json();
  config = body.config;
  presets = body.presets;
  renderPresetChoices();
  checkServerVersion();
  setInterval(checkServerVersion, UPDATE_POLL_MS);
  renderConfig();
  bindInputs();
  bindTabs();
  bindActions();
  connect();
}

init();
