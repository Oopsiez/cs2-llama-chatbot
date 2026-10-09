"""FastAPI control panel: config, live activity feed and the CS2 GSI endpoint."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import RELEASE, gpu, server_update
from ..callouts import DEFAULT_RADIUS, Callout
from ..config import AppConfig, PersonaSettings, config_path, load_config, save_config
from ..elevate import relaunch_as_admin
from ..engine import Engine
from ..gamestate import gsi_endpoint, inspect_gsi_cfg, install_gsi_cfg
from ..hardware import CS2_VRAM_RESERVE_GB, probe
from ..identity import detect_name_from_line
from ..llm import BACKENDS
from ..llm.catalog import recommended, survey
from ..models import LifeState
from ..output import keyboard
from ..parser import parse_chat_line
from ..persona import PRESETS, build_system_prompt
from ..rules import should_reply
from ..snitch import where
from ..voice import cable, tts
from ..voice.audio import output_devices
from ..voice.binds import detect_voice_key
from ..voice.speak import installed_voices, play, render

STATIC_DIR = Path(__file__).parent / "static"
# Long enough for the browser to receive the answer before the process goes away.
RESTART_GRACE_SECONDS = 1.0


def create_app(engine: Engine | None = None) -> FastAPI:
    engine = engine or Engine(load_config())

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        await engine.start()
        yield
        await engine.stop()

    app = FastAPI(title="CS2 Llama Chatbot", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return engine.status()

    @app.get("/api/log")
    async def log_view() -> dict[str, Any]:
        """Every line the tailer has read, chat or not, newest last."""
        return {
            "path": engine.config.game.console_log_path,
            "attached": engine.log_attached,
            "lines_seen": engine.lines_seen,
            "lines": list(engine.recent_lines),
            **engine.log_file_state(),
        }

    @app.get("/api/config")
    async def get_config() -> dict[str, Any]:
        return {
            "config": engine.config.model_dump(mode="json"),
            "backends": list(BACKENDS),
            "presets": {name: preset.model_dump(mode="json") for name, preset in PRESETS.items()},
            "config_path": str(config_path()),
        }

    @app.put("/api/config")
    async def put_config(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            config = AppConfig.model_validate(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await engine.apply_config(config)
        return engine.config.model_dump(mode="json")

    @app.post("/api/enabled")
    async def set_enabled(payload: dict[str, Any]) -> dict[str, Any]:
        config = engine.config.model_copy(update={"enabled": bool(payload.get("enabled"))})
        await engine.apply_config(config)
        return engine.status()

    @app.get("/api/models")
    async def list_models() -> dict[str, Any]:
        hardware = probe()
        return {
            "hardware": {
                "ram_gb": hardware.ram_gb,
                "vram_gb": hardware.vram_gb,
                "gpu": hardware.gpu,
                "vram_for_model_gb": hardware.vram_for_model_gb,
                "cs2_reserve_gb": CS2_VRAM_RESERVE_GB,
            },
            "recommended": recommended(hardware),
            "models": survey(hardware),
        }

    @app.post("/api/llm/check")
    async def llm_check() -> dict[str, str]:
        return {"status": await engine.check_llm()}

    @app.get("/api/server/version")
    async def server_version_report() -> dict[str, Any]:
        """What the LAN server's update agent says is installed there, against this client."""
        server = await server_update.server_version(engine.config.llm.ollama_url)
        return {
            "client": RELEASE,
            "server": server,
            "behind": server_update.behind(str(server.get("version", "")), RELEASE),
        }

    @app.post("/api/server/update")
    async def server_update_request() -> dict[str, Any]:
        return await server_update.request_update(engine.config.llm.ollama_url, RELEASE)

    @app.get("/api/gpu")
    async def gpu_report() -> dict[str, Any]:
        llm = engine.config.llm
        return await gpu.report(llm.ollama_url, llm.ollama_api_key, llm.ollama_verify_tls)

    @app.post("/api/gpu/kill")
    async def gpu_kill(body: dict[str, int]) -> dict[str, Any]:
        ok, detail = gpu.kill(int(body.get("pid", 0)))
        return {"ok": ok, "detail": detail}

    @app.post("/api/gpu/unload")
    async def gpu_unload(body: dict[str, str]) -> dict[str, Any]:
        llm = engine.config.llm
        ok, detail = await gpu.unload_model(
            llm.ollama_url, body.get("model", ""), llm.ollama_api_key, llm.ollama_verify_tls
        )
        return {"ok": ok, "detail": detail}

    @app.get("/api/personas")
    async def list_personas() -> dict[str, Any]:
        return {
            "presets": {name: p.model_dump(mode="json") for name, p in PRESETS.items()},
            "saved": {name: p.model_dump(mode="json") for name, p in engine.config.saved_personas.items()},
            "current": engine.config.persona.model_dump(mode="json"),
        }

    @app.post("/api/personas")
    async def save_persona(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            persona = PersonaSettings.model_validate(payload.get("persona") or {})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        name = (payload.get("name") or persona.name).strip()
        if not name:
            raise HTTPException(status_code=422, detail="persona name is required")
        saved = dict(engine.config.saved_personas)
        saved[name] = persona
        await engine.apply_config(engine.config.model_copy(update={"saved_personas": saved}))
        return {"saved": sorted(saved)}

    @app.delete("/api/personas/{name}")
    async def delete_persona(name: str) -> dict[str, Any]:
        saved = dict(engine.config.saved_personas)
        if name not in saved:
            raise HTTPException(status_code=404, detail="unknown persona")
        del saved[name]
        await engine.apply_config(engine.config.model_copy(update={"saved_personas": saved}))
        return {"saved": sorted(saved)}

    @app.get("/api/callouts")
    async def list_callouts() -> dict[str, Any]:
        player = engine.game_state.player
        return {
            "map": player.map_name,
            "position": player.position.model_dump() if player.position else None,
            "callout": where(player, engine.config.callouts),
            "callouts": [c.model_dump() for c in engine.config.callouts.for_map(player.map_name)],
            "maps": {name: len(v) for name, v in engine.config.callouts.maps.items()},
        }

    @app.post("/api/callouts")
    async def record_callout(payload: dict[str, Any]) -> dict[str, Any]:
        """Name the spot the player is standing in right now, as reported by GSI."""
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="callout name is required")
        player = engine.game_state.player
        map_name = str(payload.get("map") or player.map_name).strip()
        if not map_name:
            raise HTTPException(status_code=422, detail="no map yet - is GSI connected?")
        if player.position is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "CS2 has not reported a position. Official matches only send it while you "
                    "are spectating, so record callouts from a spectator slot, a private server "
                    "or after you die - or press Check GSI if it never arrives at all."
                ),
            )
        book = engine.config.callouts.model_copy(deep=True)
        book.record(
            map_name,
            Callout(
                name=name,
                x=player.position.x,
                y=player.position.y,
                z=player.position.z,
                radius=float(payload.get("radius") or DEFAULT_RADIUS),
            ),
        )
        await engine.apply_config(engine.config.model_copy(update={"callouts": book}))
        return {"map": map_name, "callouts": [c.model_dump() for c in book.for_map(map_name)]}

    @app.delete("/api/callouts/{map_name}/{name}")
    async def delete_callout(map_name: str, name: str) -> dict[str, Any]:
        book = engine.config.callouts.model_copy(deep=True)
        if not book.forget(map_name, name):
            raise HTTPException(status_code=404, detail="unknown callout")
        await engine.apply_config(engine.config.model_copy(update={"callouts": book}))
        return {"map": map_name, "callouts": [c.model_dump() for c in book.for_map(map_name)]}

    @app.post("/api/parse")
    async def parse_lines(payload: dict[str, Any]) -> dict[str, Any]:
        """Paste raw console.log lines and see exactly what the bot makes of them."""
        text = str(payload.get("text") or "")
        aliases = engine.config.game.name_aliases
        results = []
        for line in text.splitlines():
            if not line.strip():
                continue
            message = parse_chat_line(line, engine.own_name, aliases)
            results.append(
                {
                    "line": line,
                    "parsed": engine.annotate(message).model_dump(mode="json") if message else None,
                    "detected_name": detect_name_from_line(line, engine.own_name),
                }
            )
        return {"results": results, "own_name": engine.own_name, "name_source": engine.name_source}

    @app.post("/api/name/detect")
    async def detect_own_name() -> dict[str, Any]:
        """Ask CS2 what the player is called right now, for a new account or a rename."""
        ran, detail = await engine.ask_game_for_name()
        return {
            "asked": ran,
            "detail": detail,
            "own_name": engine.own_name,
            "name_source": engine.name_source,
        }

    @app.post("/api/output/test")
    async def output_test() -> dict[str, Any]:
        """Prove the whole delivery chain: keypress, keybind, cfg, console log."""
        return await engine.self_test()

    @app.post("/api/restart-as-admin")
    async def restart_as_admin() -> dict[str, Any]:
        """Start the panel again elevated, which is what an elevated CS2 will accept input from."""
        if keyboard.is_elevated():
            return {"started": False, "detail": "the bot already runs as administrator"}
        started, detail = relaunch_as_admin()
        if started:
            asyncio.get_running_loop().call_later(RESTART_GRACE_SECONDS, os._exit, 0)
        return {"started": started, "detail": detail}

    @app.get("/api/voice")
    async def voice_status() -> dict[str, Any]:
        """Whether the bot can hear voice comms here, and what it last heard."""
        return {
            "status": engine.voice_status(),
            "devices": output_devices(),
            "settings": engine.config.voice.model_dump(mode="json"),
            "voices": await asyncio.to_thread(installed_voices),
        }

    @app.get("/api/voice/talk-key")
    async def voice_talk_key() -> dict[str, Any]:
        """CS2's own push-to-talk bind, read from Steam's userdata."""
        key, where = await asyncio.to_thread(detect_voice_key, engine.config.game.cfg_dir)
        return {"key": key, "where": where}

    @app.get("/api/voice/cable")
    async def voice_cable() -> dict[str, Any]:
        """Whether the virtual microphone driver is installed."""
        return await asyncio.to_thread(cable.driver_status)

    @app.post("/api/voice/cable/install")
    async def voice_cable_install() -> dict[str, Any]:
        """Download VB-Audio Cable and run its installer (UAC prompt follows)."""
        ok, detail = await asyncio.to_thread(cable.install_cable)
        status = await asyncio.to_thread(cable.driver_status)
        return {"ok": ok, "detail": detail, **status}

    @app.get("/api/voice/voices")
    async def voice_voices() -> dict[str, Any]:
        """The natural (Piper) voices and the Windows voices the bot can talk with."""
        return {"voices": await asyncio.to_thread(installed_voices), **tts.status()}

    @app.post("/api/voice/voices/fetch")
    async def voice_fetch(payload: dict[str, Any]) -> dict[str, Any]:
        """Download a Piper voice now instead of on the first reply."""
        voice_id = str(payload.get("voice") or tts.DEFAULT_VOICE)
        if tts.find(voice_id) is None:
            return {"ok": False, "detail": f"unknown voice {voice_id}", **tts.status()}
        try:
            await asyncio.to_thread(tts.download, voice_id)
        except OSError as exc:
            return {"ok": False, "detail": f"download failed: {exc}", **tts.status()}
        return {"ok": True, "detail": f"{voice_id} ready", **tts.status()}

    @app.post("/api/voice/preview")
    async def voice_preview(payload: dict[str, Any]) -> dict[str, Any]:
        """Play a line on the default speakers - no push-to-talk, no cable - to audition a voice."""
        text = str(payload.get("text") or "rotate B now, they are all on A").strip()
        voice_id = str(payload.get("voice") or engine.config.voice.speak_voice)
        rate = int(payload.get("rate") or engine.config.voice.speak_rate)
        tts_engine = str(payload.get("engine") or engine.config.voice.speak_engine)
        try:
            samples, rate_hz = await asyncio.to_thread(render, text, voice_id, rate, tts_engine)
            await asyncio.to_thread(play, samples, rate_hz, "")
        except Exception as exc:
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
        return {"ok": True, "detail": f"played {len(samples) / rate_hz:.1f}s"}

    @app.post("/api/voice/speak")
    async def voice_speak(payload: dict[str, Any]) -> dict[str, Any]:
        """Say a line over push-to-talk now - the test for the virtual-microphone setup."""
        text = str(payload.get("text") or "mic check, this is the bot").strip()
        spoken, detail = await engine.speak(text)
        return {"spoken": spoken, "detail": detail, "status": engine.speaker.status()}

    @app.post("/api/voice/restart")
    async def voice_restart() -> dict[str, Any]:
        """Try the sound card again after a failure, without touching the settings."""
        engine.voice.restart()
        return engine.voice_status()

    @app.post("/api/voice/simulate")
    async def voice_simulate(payload: dict[str, Any]) -> dict[str, Any]:
        """Put words in a teammate's mouth: run a transcript through the voice path.

        This is how the reply, and the fact that it goes to team chat, can be checked without a
        microphone, a match or a working sound card.
        """
        heard = str(payload.get("text") or "").strip()
        if not heard:
            raise HTTPException(status_code=422, detail="nothing was said")
        reply = await engine.handle_voice(heard)
        return {
            "heard": heard,
            "replied": reply is not None,
            "reply": reply.model_dump(mode="json") if reply else None,
        }

    @app.post("/api/simulate")
    async def simulate(payload: dict[str, Any]) -> dict[str, Any]:
        """Generate a reply for a made-up message without touching the game."""
        line = str(payload.get("line") or "")
        parsed = parse_chat_line(line, engine.own_name, engine.config.game.name_aliases)
        if parsed is None:
            raise HTTPException(status_code=422, detail="line is not recognised as CS2 chat")
        message = engine.annotate(engine.flag_own_echo(engine.track_state(parsed)))
        state_override = payload.get("local_state")
        local_state = (
            LifeState(state_override)
            if state_override in {s.value for s in LifeState}
            else engine.game_state.local_state(engine.config.dead_alive.assume_alive_without_gsi)
        )
        allowed, reason = should_reply(engine.config, message, local_state, engine.game_state.player)
        result: dict[str, Any] = {
            "message": message.model_dump(mode="json"),
            "local_state": local_state.value,
            "would_reply": allowed,
            "reason": reason,
            "prompt": build_system_prompt(
                engine.config, engine.game_state.player, local_state, message, engine.own_name
            ),
        }
        if allowed and payload.get("generate", True):
            result["reply"] = await engine.generate_reply(message, local_state)
        return result

    @app.post("/api/gsi")
    async def gsi(request: Request) -> JSONResponse:
        payload = await request.json()
        expected = engine.config.gsi.auth_token
        if expected and (payload.get("auth") or {}).get("token") != expected:
            raise HTTPException(status_code=401, detail="bad GSI token")
        player = engine.game_state.update(payload)
        engine.bus.publish("gamestate", player.model_dump(mode="json"))
        return JSONResponse({"ok": True})

    @app.get("/api/gsi/status")
    async def gsi_status() -> dict[str, Any]:
        """Why GSI is not connected: the config on disk, and whether CS2 has ever posted."""
        config = engine.config
        endpoint = gsi_endpoint(config.web.port)
        problems = inspect_gsi_cfg(config.game.cfg_dir, endpoint, config.gsi.auth_token)
        player = engine.game_state.player
        posted = player.updated_at > 0
        if not problems and not posted:
            problems.append(
                "the config is installed but CS2 has never posted - restart CS2, since it only "
                "reads GSI configs at startup"
            )
        elif not problems and player.is_stale:
            problems.append(
                f"CS2 last posted {int(time.time() - player.updated_at)}s ago - it is closed, or "
                "the panel was restarted on a different port"
            )
        return {
            "connected": not player.is_stale,
            "endpoint": endpoint,
            "problems": problems,
            "seconds_since_post": round(time.time() - player.updated_at, 1) if posted else None,
            "map": player.map_name,
            "mode": player.mode,
            "team": player.team.value,
            "round_phase": player.round_phase,
            "round_number": player.round_number,
            "has_position": player.position is not None,
            "note": (
                "In Premier and other official matches CS2 reports your map, side, round phase "
                "and health, which is everything strats and dead chat need. Position is only "
                "sent while spectating, so callouts fill in once you die."
            ),
        }

    @app.post("/api/gsi/install")
    async def gsi_install() -> dict[str, str]:
        cfg_dir = engine.config.game.cfg_dir
        if not cfg_dir:
            raise HTTPException(status_code=422, detail="set the CS2 cfg directory first")
        endpoint = gsi_endpoint(engine.config.web.port)
        try:
            path = install_gsi_cfg(cfg_dir, endpoint, engine.config.gsi.auth_token)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"path": str(path), "endpoint": endpoint}

    @app.websocket("/ws")
    async def websocket(ws: WebSocket) -> None:
        await ws.accept()
        queue = engine.bus.subscribe()
        try:
            await ws.send_json(
                {
                    "kind": "snapshot",
                    "data": {
                        "status": engine.status(),
                        "config": engine.config.model_dump(mode="json"),
                        "events": engine.bus.history(),
                    },
                }
            )
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    await ws.send_json({"kind": "status", "data": engine.status()})
                    continue
                await ws.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            engine.bus.unsubscribe(queue)

    return app


def run() -> None:
    import uvicorn

    config = load_config()
    save_config(config)
    engine = Engine(config)
    uvicorn.run(
        create_app(engine),
        host=config.web.host,
        port=config.web.port,
        log_level="info",
    )
