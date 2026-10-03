import asyncio
import os

from cs2bot import gpu
from cs2bot.config import LLMSettings
from cs2bot.hardware import Hardware
from cs2bot.llm import gpu_layers_for


def test_the_game_and_the_bot_are_never_offered_for_killing():
    assert gpu._is_protected("cs2.exe")
    assert gpu._is_protected("CS2 Chatbot.exe")
    assert not gpu._is_protected("ollama.exe")


def test_killing_the_bot_itself_is_refused():
    ok, detail = gpu.kill(os.getpid())
    assert not ok and "itself" in detail


def test_unload_without_a_server_reports_rather_than_raises():
    ok, detail = asyncio.run(gpu.unload_model("http://127.0.0.1:1", "x"))
    assert not ok and "x" in detail


def test_report_survives_a_machine_with_nothing_on_it():
    body = asyncio.run(gpu.report("http://127.0.0.1:1"))
    assert body["models"] == [] and "processes" in body


def test_a_model_that_does_not_fit_beside_cs2_stays_on_the_cpu(tmp_path):
    weights = tmp_path / "big.gguf"
    weights.write_bytes(b"\0" * 1024)
    os.truncate(weights, 5 * 1024**3)  # sparse 5GB file
    settings = LLMSettings(model_path=str(weights))
    assert gpu_layers_for(settings, Hardware(vram_gb=6)) == 0  # 6 - 2 reserve < 5 + 1
    assert gpu_layers_for(settings, Hardware(vram_gb=12)) == -1
    assert gpu_layers_for(settings, Hardware(vram_gb=0)) == 0
    assert gpu_layers_for(settings.model_copy(update={"gpu_auto": False}), Hardware()) == -1
