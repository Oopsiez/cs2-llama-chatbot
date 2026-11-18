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


def test_no_handle_is_kept_between_polls(tmp_path, monkeypatch):
    import cs2bot.logtail as logtail

    opened = []
    real = logtail.open_shared

    def spy(path):
        handle = real(path)
        opened.append(handle)
        return handle

    monkeypatch.setattr(logtail, "open_shared", spy)
    log = tmp_path / "console.log"
    log.write_text("", encoding="utf-8")
    tailer = LogTailer(log)
    list(tailer.read_lines())
    with log.open("a", encoding="utf-8") as handle:
        handle.write("hi\n")
    assert list(tailer.read_lines()) == ["hi"]
    assert opened and all(handle.closed for handle in opened)
    assert tailer.is_open


def test_replaced_file_is_read_from_the_top(tmp_path):
    log = tmp_path / "console.log"
    log.write_text("a\n", encoding="utf-8")
    tailer = LogTailer(log)
    list(tailer.read_lines())

    log.unlink()
    assert list(tailer.read_lines()) == []
    assert not tailer.is_open
    log.write_text("new session line\nmore\n", encoding="utf-8")
    assert list(tailer.read_lines()) == ["new session line", "more"]


def test_split_utf8_character_is_kept_whole(tmp_path):
    log = tmp_path / "console.log"
    log.write_bytes(b"")
    tailer = LogTailer(log)
    list(tailer.read_lines())
    data = "caf\u00e9\n".encode()
    with log.open("ab") as handle:
        handle.write(data[:4])
    assert list(tailer.read_lines()) == []
    with log.open("ab") as handle:
        handle.write(data[4:])
    assert list(tailer.read_lines()) == ["caf\u00e9"]


def test_cs2_can_delete_the_log_while_the_bot_reads_it(tmp_path):
    from cs2bot.logtail import open_shared

    log = tmp_path / "console.log"
    log.write_text("x\n", encoding="utf-8")
    with open_shared(log) as handle:
        log.unlink()
        assert handle.read() == b"x\n"
    assert not log.exists()
