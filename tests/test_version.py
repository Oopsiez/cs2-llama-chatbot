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
