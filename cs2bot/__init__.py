"""CS2 chatbot: local Llama 3 replies to in-game chat, driven from a web panel."""

# Keep in step with `version` in pyproject.toml and the tag the release workflow builds from;
# tests/test_version.py fails if they drift.
__version__ = "1.9.0"

try:
    from ._release import RELEASE  # written by the release workflow from the git tag
except ImportError:  # a source checkout or a local build
    RELEASE = f"v{__version__}"
