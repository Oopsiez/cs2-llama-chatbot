from cs2bot.models import ChatChannel, LifeState, Team
from cs2bot.parser import parse_chat_line


def test_all_chat_with_timestamp():
    message = parse_chat_line("07/02 17:35:36  [ALL] someguy\u200e: hey there")
    assert message is not None
    assert message.sender == "someguy"
    assert message.text == "hey there"
    assert message.channel is ChatChannel.ALL
    assert message.sender_state is LifeState.ALIVE


def test_team_chat_tag_sets_team():
    message = parse_chat_line("[CT] rifler: rotate b")
    assert message is not None
    assert message.channel is ChatChannel.TEAM
    assert message.sender_team is Team.CT


def test_dead_prefix_before_channel_tag():
    message = parse_chat_line("*DEAD* [ALL] ghost: gg")
    assert message is not None
    assert message.sender == "ghost"
    assert message.sender_state is LifeState.DEAD
    assert message.channel is ChatChannel.ALL


def test_dead_prefix_after_channel_tag():
    message = parse_chat_line("[ALL] *DEAD* ghost: gg")
    assert message is not None
    assert message.sender_state is LifeState.DEAD


def test_legacy_dead_team_tag():
    message = parse_chat_line("*DEAD*(Terrorist) player one : nice one")
    assert message is not None
    assert message.sender == "player one"
    assert message.sender_state is LifeState.DEAD
    assert message.sender_team is Team.T
    assert message.channel is ChatChannel.TEAM


def test_spectator_chat():
    message = parse_chat_line("*SPEC* watcher: nt")
    assert message is not None
    assert message.channel is ChatChannel.SPEC
    assert message.sender_team is Team.SPECTATOR


def test_srcds_say_team():
    message = parse_chat_line('"Tester<3><[U:1:1234]><CT>" say_team "b split"')
    assert message is not None
    assert message.sender == "Tester"
    assert message.channel is ChatChannel.TEAM
    assert message.sender_team is Team.CT
    assert message.text == "b split"


def test_own_message_flagged():
    message = parse_chat_line("[ALL] Me: hello", own_name="me")
    assert message is not None
    assert message.is_self


def test_console_noise_is_ignored():
    assert parse_chat_line("Redownloading all lightmaps") is None
    assert parse_chat_line("07/02 17:35:36  Host_Error: something: bad") is None
    assert parse_chat_line("") is None
