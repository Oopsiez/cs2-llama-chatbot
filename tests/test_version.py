import re
from pathlib import Path

from cs2bot import __version__
from cs2bot.engine import Engine

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_the_package_and_the_project_metadata_agree():
    # Read rather than import the metadata: tomllib only exists from 3.11 and this runs on 3.10.
    declared = re.search(r'^version = "(.+)"$', PYPROJECT.read_text(), re.MULTILINE)
    assert declared is not None
    assert declared.group(1) == __version__


def test_the_panel_can_show_which_version_is_running():
    assert Engine().status()["version"] == __version__


def test_the_server_counts_as_behind_only_when_its_release_is_older():
    from cs2bot.server_update import agent_url, behind

    assert behind("v1.9.0-rc22", "v1.9.0-rc24")
    assert behind("1.9.0-rc22", "v1.9.0")
    assert not behind("v1.9.0", "v1.9.0-rc24")
    assert not behind("v1.9.0-rc24", "v1.9.0-rc24")
    assert not behind("unknown", "v1.9.0-rc24")
    assert agent_url("http://192.168.0.70:11434") == "http://192.168.0.70:11435"


def test_switching_a_model_off_stops_that_kind_of_reply():
    from cs2bot.config import AppConfig
    from cs2bot.models import ChatChannel, ChatMessage

    engine = Engine(AppConfig())
    message = ChatMessage(raw="x", sender="mate", text="rush b?", channel=ChatChannel.TEAM)
    typed, spoken = engine._reply_modes(message)
    engine.config.llm.chat_enabled = False
    engine.config.llm.speech_enabled = False
    assert engine._reply_modes(message) == (False, False)
    assert engine.answers_text is False
    assert (typed, spoken) != (False, False)


def test_update_report_flags_a_stale_server_and_an_old_client():
    from cs2bot.server_update import parse_release, update_report

    latest = parse_release({"tag_name": "v1.10.9", "html_url": "https://x/r"})
    assert latest == {"version": "1.10.9", "url": "https://x/r"}
    report = update_report("v1.10.9", {"version": "v1.9.0-rc24"}, latest)
    assert report["server_behind"] and not report["client_behind"] and not report["in_sync"]
    report = update_report("v1.10.8", {"version": "1.10.8"}, latest)
    assert report["in_sync"] and report["client_behind"] and not report["server_behind"]
    report = update_report("v1.10.8", {"error": "no agent"}, {"error": "offline"})
    assert not report["in_sync"] and not report["server_behind"] and not report["client_behind"]
