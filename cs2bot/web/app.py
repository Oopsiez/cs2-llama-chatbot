"""FastAPI control panel: config, live activity feed and the CS2 GSI endpoint."""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..callouts import DEFAULT_RADIUS, Callout
from ..config import AppConfig, PersonaSettings, config_path, load_config, save_config
from ..elevate import relaunch_as_admin
from ..engine import Engine
from ..gamestate import install_gsi_cfg
from ..identity import detect_name_from_line
from ..llm import BACKENDS
from ..models import LifeState
from ..output import keyboard
from ..parser import parse_chat_line
from ..persona import PRESETS, build_system_prompt
from ..rules import should_reply
from ..snitch import where

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

    @app.post("/api/llm/check")
    async def llm_check() -> dict[str, str]:
        return {"status": await engine.check_llm()}

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
                detail="CS2 has not reported a position; install the GSI config and join a map",
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

    @app.post("/api/gsi/install")
    async def gsi_install() -> dict[str, str]:
        cfg_dir = engine.config.game.cfg_dir
        if not cfg_dir:
            raise HTTPException(status_code=422, detail="set the CS2 cfg directory first")
        endpoint = f"http://{engine.config.web.host}:{engine.config.web.port}/api/gsi"
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
            await ws.send_json({"kind": "snapshot", "data": {
                "status": engine.status(),
                "config": engine.config.model_dump(mode="json"),
                "events": engine.bus.history(),
            }})
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
