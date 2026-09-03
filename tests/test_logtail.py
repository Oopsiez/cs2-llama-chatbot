from cs2bot.logtail import LogTailer


def test_reads_only_new_lines(tmp_path):
    log = tmp_path / "console.log"
    log.write_text("old line\n", encoding="utf-8")

    tailer = LogTailer(log)
    assert list(tailer.read_lines()) == []

    with log.open("a", encoding="utf-8") as handle:
        handle.write("first\nsecond\n")
    assert list(tailer.read_lines()) == ["first", "second"]
    assert list(tailer.read_lines()) == []


def test_partial_line_is_buffered(tmp_path):
    log = tmp_path / "console.log"
    log.write_text("", encoding="utf-8")
    tailer = LogTailer(log)
    list(tailer.read_lines())

    with log.open("a", encoding="utf-8") as handle:
        handle.write("half a li")
    assert list(tailer.read_lines()) == []

    with log.open("a", encoding="utf-8") as handle:
        handle.write("ne\n")
    assert list(tailer.read_lines()) == ["half a line"]


def test_truncation_restarts_from_the_top(tmp_path):
    log = tmp_path / "console.log"
    log.write_text("a\nb\nc\n", encoding="utf-8")
    tailer = LogTailer(log)
    list(tailer.read_lines())

    log.write_text("x\n", encoding="utf-8")  # -conclearlog on relaunch shrinks the file
    assert list(tailer.read_lines()) == ["x"]


def test_missing_file_is_not_fatal(tmp_path):
    tailer = LogTailer(tmp_path / "nope.log")
    assert list(tailer.read_lines()) == []
    assert not tailer.is_open
