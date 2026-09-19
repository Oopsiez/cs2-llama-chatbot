"""Hearing the team's voice comms.

CS2 puts nothing about voice in the console log, so the only honest way to hear a teammate
without touching the game is to listen to what the speakers are playing: Windows can hand back
its own output mix (WASAPI loopback), and a local Whisper model turns that into text. Nothing is
read out of the game and no microphone is opened.

What that costs: the loopback mix is *everything* - voices, gunfire, the bomb - so transcripts
are rougher than chat, and there is no way to tell who spoke. The bot answers in team chat,
because voice comms are team-only.
"""

from __future__ import annotations

from .listener import Utterance, VoiceListener
from .segment import Segmenter
from .transcribe import Transcriber, WhisperTranscriber, model_is_cached, whisper_missing

__all__ = [
    "Segmenter",
    "Transcriber",
    "Utterance",
    "VoiceListener",
    "WhisperTranscriber",
    "model_is_cached",
    "whisper_missing",
]
