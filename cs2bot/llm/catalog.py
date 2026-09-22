"""Models worth pointing the bot at, and whether this machine can run them.

Chat replies are one or two sentences, so a small instruct model is not a big compromise here -
the 8B models are better at banter, not necessary for it. Sizes are the 4-bit quant download and
are approximate; the VRAM figures are what it takes to keep the whole model on the card next to
CS2, which is why the panel also says what runs on the CPU instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..hardware import Hardware


@dataclass(frozen=True)
class ModelChoice:
    key: str
    label: str
    ollama: str  # tag to pull with `ollama pull`
    gguf: str  # Hugging Face repo holding the GGUF for llama.cpp
    params: str
    download_gb: float
    vram_gb: float  # to keep it entirely on the GPU beside CS2
    ram_gb: float  # to run it on the CPU instead
    note: str


CHOICES: tuple[ModelChoice, ...] = (
    ModelChoice(
        key="llama3.2-1b",
        label="Llama 3.2 1B Instruct (Q4_K_M)",
        ollama="llama3.2:1b-instruct-q4_K_M",
        gguf="bartowski/Llama-3.2-1B-Instruct-GGUF",
        params="1B",
        download_gb=0.8,
        vram_gb=1.5,
        ram_gb=4.0,
        note="Runs on anything, including no GPU at all. Short, blunt replies.",
    ),
    ModelChoice(
        key="qwen2.5-1.5b",
        label="Qwen2.5 1.5B Instruct (Q4_K_M)",
        ollama="qwen2.5:1.5b-instruct-q4_K_M",
        gguf="bartowski/Qwen2.5-1.5B-Instruct-GGUF",
        params="1.5B",
        download_gb=1.0,
        vram_gb=2.0,
        ram_gb=4.0,
        note="Better sentences than the 1B for about the same cost.",
    ),
    ModelChoice(
        key="llama3.2-3b",
        label="Llama 3.2 3B Instruct (Q4_K_M)",
        ollama="llama3.2:3b-instruct-q4_K_M",
        gguf="bartowski/Llama-3.2-3B-Instruct-GGUF",
        params="3B",
        download_gb=2.0,
        vram_gb=3.5,
        ram_gb=8.0,
        note="The sweet spot on a 6GB card next to CS2.",
    ),
    ModelChoice(
        key="phi3.5-mini",
        label="Phi-3.5 Mini Instruct (Q4_K_M)",
        ollama="phi3.5:3.8b-mini-instruct-q4_0",
        gguf="bartowski/Phi-3.5-mini-instruct-GGUF",
        params="3.8B",
        download_gb=2.2,
        vram_gb=4.0,
        ram_gb=8.0,
        note="Follows the persona instructions closely; a bit prim for trash talk.",
    ),
    ModelChoice(
        key="mistral-7b",
        label="Mistral 7B Instruct v0.3 (Q4_K_M)",
        ollama="mistral:7b-instruct-q4_K_M",
        gguf="bartowski/Mistral-7B-Instruct-v0.3-GGUF",
        params="7B",
        download_gb=4.4,
        vram_gb=6.5,
        ram_gb=16.0,
        note="Loosest tongue of the mid-size models.",
    ),
    ModelChoice(
        key="llama3.1-8b",
        label="Llama 3.1 8B Instruct (Q4_K_M)",
        ollama="llama3.1:8b-instruct-q4_K_M",
        gguf="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
        params="8B",
        download_gb=4.7,
        vram_gb=7.0,
        ram_gb=16.0,
        note="Best banter here, but wants an 8GB+ card with CS2 already on it.",
    ),
)

FITS, TIGHT, CPU_ONLY, TOO_BIG, UNKNOWN = "fits", "tight", "cpu only", "too big", "unknown"


def verdict(choice: ModelChoice, hardware: Hardware) -> tuple[str, str]:
    """`(verdict, why)` for running this model on this machine."""
    spare = hardware.vram_for_model_gb
    if hardware.vram_gb and spare >= choice.vram_gb:
        return FITS, f"{choice.vram_gb:g}GB of the card, with CS2's share left alone"
    if hardware.vram_gb and spare >= choice.vram_gb * 0.6:
        return TIGHT, "part of it spills into system memory - slower, but it runs"
    if not hardware.ram_gb:
        return UNKNOWN, "could not read this machine's memory"
    if hardware.ram_gb >= choice.ram_gb:
        reason = "no GPU headroom, so it runs on the CPU - seconds per reply, not milliseconds"
        return CPU_ONLY, reason
    return TOO_BIG, f"wants about {choice.ram_gb:g}GB of RAM to run without a GPU"


def recommended(hardware: Hardware) -> str:
    """The biggest model this machine can hold on the GPU, or the smallest one otherwise."""
    for choice in reversed(CHOICES):
        if verdict(choice, hardware)[0] == FITS:
            return choice.key
    return CHOICES[0].key


def survey(hardware: Hardware) -> list[dict[str, str | float]]:
    """The catalogue with this machine's verdict attached, for the panel."""
    rows: list[dict[str, str | float]] = []
    for choice in CHOICES:
        state, why = verdict(choice, hardware)
        rows.append(
            {
                "key": choice.key,
                "label": choice.label,
                "ollama": choice.ollama,
                "gguf": choice.gguf,
                "params": choice.params,
                "download_gb": choice.download_gb,
                "vram_gb": choice.vram_gb,
                "ram_gb": choice.ram_gb,
                "note": choice.note,
                "verdict": state,
                "why": why,
            }
        )
    return rows
