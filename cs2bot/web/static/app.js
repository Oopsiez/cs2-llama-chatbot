const $ = (id) => document.getElementById(id);

let config = null;
let presets = {};
let saving = null;

/* id -> [config path, kind] */
const BINDINGS = {
  "persona-name": ["persona.name", "text"],
  "persona-description": ["persona.description", "text"],
  "persona-style": ["persona.style_notes", "text"],
  "persona-dead": ["persona.dead_notes", "text"],
  "persona-banned": ["persona.banned_words", "list"],
  "persona-maxchars": ["persona.max_reply_chars", "int"],

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

  "gsi-port": ["gsi.port", "int"],
  "gsi-token": ["gsi.auth_token", "text"],
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
  for (const [id, [path, kind]] of Object.entries(BINDINGS)) {
    const el = $(id);
    if (el) writeField(el, kind, getPath(config, path));
  }
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
  const select = $("persona-saved");
  const names = Object.keys(config.saved_personas || {});
  select.innerHTML = names.length
    ? names.map((n) => `<option value="${n}">${n}</option>`).join("")
    : '<option value="">(nothing saved)</option>';
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
      if (["iq", "literacy", "reply-delay", "humanized-typing"].includes(id)) renderDials();
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

function bindTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      document.querySelectorAll(".panel").forEach((panel) => {
        panel.dataset.active = String(panel.dataset.panel === tab.dataset.tab);
      });
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
    const tag = `[${data.channel}]${data.sender_state === "dead" ? " *DEAD*" : ""}`;
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
    line(
      `game state: ${escapeHtml(data.state)}${data.health != null ? ` (${data.health} hp)` : ""}`,
      "gamestate",
      escapeHtml([data.map_name, data.round_phase].filter(Boolean).join(" · ")),
    );
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
  setPill(
    "pill-name",
    `you: ${status.own_name || "unknown"}`,
    status.own_name ? "good" : "warn",
  );
  $("pill-name").title = `name source: ${status.name_source}`;
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
    const preset = presets[$("preset").value];
    if (!preset) return;
    config.persona = structuredClone(preset);
    renderConfig();
    scheduleSave();
  });

  $("check-llm").addEventListener("click", async () => {
    $("llm-note").textContent = "checking…";
    await saveConfig();
    const response = await fetch("/api/llm/check", { method: "POST" });
    $("llm-note").textContent = (await response.json()).status;
  });

  $("persona-save").addEventListener("click", async () => {
    const name = prompt("Save persona as:", config.persona.name);
    if (!name) return;
    await fetch("/api/personas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, persona: config.persona }),
    });
    config.saved_personas[name] = structuredClone(config.persona);
    renderSavedPersonas();
  });

  $("persona-load").addEventListener("click", () => {
    const saved = config.saved_personas[$("persona-saved").value];
    if (!saved) return;
    config.persona = structuredClone(saved);
    renderConfig();
    scheduleSave();
  });

  $("persona-delete").addEventListener("click", async () => {
    const name = $("persona-saved").value;
    if (!name || !confirm(`Delete persona "${name}"?`)) return;
    await fetch(`/api/personas/${encodeURIComponent(name)}`, { method: "DELETE" });
    delete config.saved_personas[name];
    renderSavedPersonas();
  });

  $("install-gsi").addEventListener("click", async () => {
    await saveConfig();
    const response = await fetch("/api/gsi/install", { method: "POST" });
    const body = await response.json();
    $("gsi-note").textContent = response.ok ? `written to ${body.path} — restart CS2` : body.detail;
  });

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

async function init() {
  const response = await fetch("/api/config");
  const body = await response.json();
  config = body.config;
  presets = body.presets;
  $("preset").innerHTML =
    '<option value="">— choose a preset —</option>' +
    Object.keys(presets).map((name) => `<option value="${name}">${name}</option>`).join("");
  renderConfig();
  bindInputs();
  bindTabs();
  bindActions();
  connect();
}

init();
