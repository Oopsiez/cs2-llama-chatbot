"""FastAPI control panel: config, live activity feed and the CS2 GSI endpoint."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import AppConfig, PersonaSettings, config_path, load_config, save_config
from ..engine import Engine
from ..gamestate import install_gsi_cfg
from ..llm import BACKENDS
from ..models import LifeState
from ..parser import parse_chat_line
from ..persona import PRESETS

STATIC_DIR = Path(__file__).parent / "static"


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

    @app.post("/api/parse")
    async def parse_lines(payload: dict[str, Any]) -> dict[str, Any]:
        """Paste raw console.log lines and see exactly what the bot makes of them."""
        text = str(payload.get("text") or "")
        own_name = engine.config.game.own_name or engine.game_state.player.name
        results = []
        for line in text.splitlines():
            if not line.strip():
                continue
            message = parse_chat_line(line, own_name)
            results.append(
                {
                    "line": line,
                    "parsed": message.model_dump(mode="json") if message else None,
                }
            )
        return {"results": results}

    @app.post("/api/simulate")
    async def simulate(payload: dict[str, Any]) -> dict[str, Any]:
        """Generate a reply for a made-up message without touching the game."""
        line = str(payload.get("line") or "")
        message = parse_chat_line(line, engine.config.game.own_name)
        if message is None:
            raise HTTPException(status_code=422, detail="line is not recognised as CS2 chat")
        state_override = payload.get("local_state")
        local_state = (
            LifeState(state_override)
            if state_override in {s.value for s in LifeState}
            else engine.game_state.local_state(engine.config.dead_alive.assume_alive_without_gsi)
        )
        from ..rules import should_reply

        allowed, reason = should_reply(engine.config, message, local_state, engine.game_state.player)
        result: dict[str, Any] = {
            "message": message.model_dump(mode="json"),
            "local_state": local_state.value,
            "would_reply": allowed,
            "reason": reason,
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
