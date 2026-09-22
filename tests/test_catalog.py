from cs2bot.hardware import Hardware
from cs2bot.llm import catalog


def choice(key: str) -> catalog.ModelChoice:
    return next(c for c in catalog.CHOICES if c.key == key)


def test_a_big_card_holds_the_big_model():
    beefy = Hardware(ram_gb=32, vram_gb=16)
    assert catalog.verdict(choice("llama3.1-8b"), beefy)[0] == catalog.FITS
    assert catalog.recommended(beefy) == "llama3.1-8b"


def test_cs2_keeps_its_share_of_a_small_card():
    # 6GB card: the 8B model would fit on paper, but not beside the game.
    small = Hardware(ram_gb=16, vram_gb=6)
    assert catalog.verdict(choice("llama3.2-3b"), small)[0] == catalog.FITS
    assert catalog.verdict(choice("llama3.1-8b"), small)[0] != catalog.FITS
    assert catalog.recommended(small) == "phi3.5-mini"


def test_no_gpu_falls_back_to_the_cpu_rather_than_refusing():
    laptop = Hardware(ram_gb=8, vram_gb=0)
    assert catalog.verdict(choice("llama3.2-1b"), laptop)[0] == catalog.CPU_ONLY
    assert catalog.verdict(choice("llama3.1-8b"), laptop)[0] == catalog.TOO_BIG
    assert catalog.recommended(laptop) == "llama3.2-1b"


def test_a_machine_it_cannot_read_is_said_to_be_unknown():
    assert catalog.verdict(choice("llama3.2-1b"), Hardware())[0] == catalog.UNKNOWN


def test_every_model_is_offered_with_its_cost():
    rows = catalog.survey(Hardware(ram_gb=16, vram_gb=8))
    assert len(rows) == len(catalog.CHOICES)
    assert all(row["download_gb"] and row["verdict"] and row["ollama"] for row in rows)
