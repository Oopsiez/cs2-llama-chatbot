import time

import pytest
from fastapi.testclient import TestClient

from cs2bot.config import AppConfig
from cs2bot.engine import Engine
from cs2bot.models import LifeState
from cs2bot.web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CS2BOT_CONFIG", str(tmp_path / "config.json"))
    config = AppConfig()
    config.llm.backend = "mock"
    config.game.output_backend = "dry_run"
    engine = Engine(config)
    with TestClient(create_app(engine)) as test_client:
        test_client.engine = engine
        yield test_client


def test_index_and_config(client):
    assert client.get("/").status_code == 200
    body = client.get("/api/config").json()
    assert body["config"]["llm"]["backend"] == "mock"
    assert "Cheeky Teammate" in body["presets"]


def test_toggle_enabled(client):
    status = client.post("/api/enabled", json={"enabled": True}).json()
    assert status["enabled"] is True
    assert client.engine.config.enabled is True


def test_log_endpoint_reports_a_missing_console_log(client):
    body = client.get("/api/log").json()
    assert body["log_exists"] is False
    assert body["lines"] == []


def test_log_endpoint_shows_the_lines_the_tailer_read(client, tmp_path):
    log = tmp_path / "console.log"
    log.write_text("")
    client.engine.config.game.console_log_path = str(log)

    deadline = time.monotonic() + 5
    while not client.engine.log_attached and time.monotonic() < deadline:
        time.sleep(0.05)
    log.write_text("[ALL] someone: hey\nDropped player from server\n")
    while client.engine.lines_seen < 2 and time.monotonic() < deadline:
        time.sleep(0.05)

    body = client.get("/api/log").json()
    assert body["log_exists"] is True
    assert body["lines_seen"] == 2
    assert body["lines"][0] == {"line": "[ALL] someone: hey", "chat": True}
    assert body["lines"][1]["chat"] is False


def test_parse_endpoint_reports_dead_players(client):
    results = client.post("/api/parse", json={"text": "*DEAD* [ALL] ghost: gg\nnot chat"}).json()
    assert results["results"][0]["parsed"]["sender_state"] == "dead"
    assert results["results"][1]["parsed"] is None


def test_simulate_answers_from_either_side_of_the_grave(client):
    dead_view = client.post(
        "/api/simulate", json={"line": "[ALL] enemy: ez", "local_state": "dead"}
    ).json()
    assert dead_view["would_reply"] is True

    dead_sender = client.post(
        "/api/simulate", json={"line": "[DEAD] ghost: unlucky", "local_state": "alive"}
    ).json()
    assert dead_sender["message"]["sender_state"] == "dead"
    assert dead_sender["would_reply"] is True

    alive_view = client.post(
        "/api/simulate", json={"line": "[ALL] enemy: ez", "local_state": "alive"}
    ).json()
    assert alive_view["would_reply"] is True
    assert alive_view["reply"]


def test_gsi_endpoint_updates_local_state(client):
    payload = {
        "provider": {"steamid": "76561198000000000"},
        "player": {"steamid": "76561198000000000", "name": "me", "team": "CT",
                   "state": {"health": 0}},
        "map": {"name": "de_mirage", "phase": "live", "mode": "competitive"},
        "round": {"phase": "live"},
    }
    assert client.post("/api/gsi", json=payload).status_code == 200
    assert client.engine.game_state.local_state() is LifeState.DEAD
    assert client.get("/api/status").json()["local_state"] == "dead"


def test_gsi_token_is_enforced(client):
    client.engine.config.gsi.auth_token = "secret"
    assert client.post("/api/gsi", json={"provider": {}}).status_code == 401
    assert client.post("/api/gsi", json={"auth": {"token": "secret"}}).status_code == 200


def test_persona_save_and_delete(client):
    persona = client.get("/api/personas").json()["current"]
    persona["name"] = "Test Guy"
    assert client.post("/api/personas", json={"name": "Test Guy", "persona": persona}).status_code == 200
    assert "Test Guy" in client.get("/api/personas").json()["saved"]
    assert client.delete("/api/personas/Test Guy").status_code == 200
    assert client.get("/api/personas").json()["saved"] == {}

def test_a_custom_prompt_survives_a_save_and_reload(client):
    persona = client.get("/api/personas").json()["current"]
    persona["extra_instructions"] = "you only speak in questions"
    client.post("/api/personas", json={"name": "Interrogator", "persona": persona})

    saved = client.get("/api/personas").json()["saved"]["Interrogator"]
    assert saved["extra_instructions"] == "you only speak in questions"


def test_custom_prompt_reaches_the_model(client):
    config = client.get("/api/config").json()["config"]
    config["persona"]["extra_instructions"] = "you only speak in questions"
    assert client.put("/api/config", json=config).status_code == 200

    prompt = client.post(
        "/api/simulate", json={"line": "[ALL] enemy: ez", "local_state": "alive"}
    ).json()["prompt"]
    assert "you only speak in questions" in prompt


def test_recording_a_callout_needs_gsi(client):
    assert client.post("/api/callouts", json={"name": "banana"}).status_code == 422

    client.post(
        "/api/gsi",
        json={
            "provider": {"steamid": "1"},
            "player": {"steamid": "1", "name": "me"},
            "map": {"name": "de_dust2", "phase": "live"},
        },
    )
    response = client.post("/api/callouts", json={"name": "banana"})
    assert response.status_code == 422
    assert "position" in response.json()["detail"]


def test_recording_and_deleting_a_callout(client):
    client.post(
        "/api/gsi",
        json={
            "provider": {"steamid": "1"},
            "player": {"steamid": "1", "name": "me", "position": "100.0, 200.0, 30.0"},
            "map": {"name": "de_dust2", "phase": "live"},
        },
    )
    body = client.post("/api/callouts", json={"name": "banana"}).json()
    assert body["callouts"] == [
        {"name": "banana", "x": 100.0, "y": 200.0, "z": 30.0, "radius": 400.0}
    ]

    listed = client.get("/api/callouts").json()
    assert listed["callout"] == "banana"
    assert listed["map"] == "de_dust2"

    assert client.delete("/api/callouts/de_dust2/banana").status_code == 200
    assert client.get("/api/callouts").json()["callouts"] == []
    assert client.delete("/api/callouts/de_dust2/banana").status_code == 404
