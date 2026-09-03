from cs2bot.liveness import DeathBoard
from cs2bot.models import ChatChannel, ChatMessage, LifeState


def chat(**kwargs) -> ChatMessage:
    base = {"raw": "raw", "sender": "ghost", "text": "gg", "channel": ChatChannel.ALL,
            "sender_state": LifeState.UNKNOWN}
    base.update(kwargs)
    return ChatMessage(**base)


def test_dead_tag_is_remembered_for_later_untagged_lines():
    board = DeathBoard()
    board.observe(chat(sender_state=LifeState.DEAD))
    assert board.observe(chat(text="unlucky")).sender_state is LifeState.DEAD
    assert board.dead_players == ["ghost"]


def test_an_alive_line_clears_a_stale_death():
    board = DeathBoard()
    board.observe(chat(sender_state=LifeState.DEAD))
    board.observe(chat(sender_state=LifeState.ALIVE))
    assert board.state_of("GHOST") is LifeState.ALIVE
    assert board.dead_players == []


def test_a_new_round_wipes_the_board():
    board = DeathBoard()
    board.note_phase("live")
    board.observe(chat(sender_state=LifeState.DEAD))
    board.note_phase("over")
    assert board.state_of("ghost") is LifeState.DEAD

    board.note_phase("freezetime")
    assert board.state_of("ghost") is LifeState.UNKNOWN
    assert board.observe(chat()).sender_state is LifeState.UNKNOWN


def test_spectators_do_not_join_the_dead_roster():
    board = DeathBoard()
    board.observe(chat(channel=ChatChannel.SPEC, sender_state=LifeState.DEAD))
    assert board.dead_players == []


def test_unknown_sender_is_left_alone():
    board = DeathBoard()
    assert board.observe(chat()).sender_state is LifeState.UNKNOWN
