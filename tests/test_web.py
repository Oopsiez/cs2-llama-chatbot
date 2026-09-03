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
