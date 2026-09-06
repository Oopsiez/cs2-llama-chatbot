import random

import pytest

from cs2bot import playbook
from cs2bot.models import Team


def test_every_active_duty_map_has_both_sides():
    for map_name in playbook.ACTIVE_DUTY:
        for side in (Team.T, Team.CT):
            calls = playbook.strategies_for(map_name, side)
            assert calls, f"{map_name} {side.value} has no calls"
            assert all(c.map_name == map_name for c in calls)


def test_every_line_of_every_call_fits_in_a_chat_line():
    for strategy in playbook.PLAYBOOK:
        assert strategy.steps, f"{strategy.name} has no steps"
        for line in playbook.call_lines(strategy):
            assert len(line) <= 221, line


def test_a_call_is_said_over_several_lines():
    strategy = playbook.pick("de_inferno", Team.T, site="b", buy=playbook.FULL)
    assert strategy is not None
    lines = playbook.call_lines(strategy)
    assert len(lines) > 1
    assert lines[0].startswith("Inferno T:")
    assert lines[1:] == list(strategy.steps)


def test_max_lines_folds_the_tail_in_rather_than_dropping_it():
    strategy = playbook.pick("de_mirage", Team.T, site="a", buy=playbook.FULL)
    assert strategy is not None and len(strategy.steps) == 3

    lines = playbook.call_lines(strategy, max_lines=3)
    assert len(lines) == 3
    assert strategy.steps[-1] in lines[-1]  # nothing tactical is lost


def test_no_line_limit_keeps_every_step():
    strategy = playbook.pick("de_nuke", Team.T, site="a", buy=playbook.FULL)
    assert strategy is not None
    assert len(playbook.call_lines(strategy, max_lines=0)) == len(strategy.steps) + 1


@pytest.mark.parametrize(
    "given,expected",
    [
        ("de_mirage", "de_mirage"),
        ("Mirage", "de_mirage"),
        ("Dust 2", "de_dust2"),
        ("workshop/123456/de_cache", "de_cache"),
        ("de_train", ""),
        ("", ""),
    ],
)
def test_normalise_map(given, expected):
    assert playbook.normalise_map(given) == expected


def test_unknown_map_falls_back_to_the_generic_calls():
    calls = playbook.strategies_for("de_vertigo", Team.T)
    assert calls and all(not c.map_name for c in calls)


def test_pick_honours_the_asked_for_site():
    strategy = playbook.pick("de_inferno", Team.T, site="b", rng=random.Random(1))
    assert strategy is not None and strategy.site == "b"


def test_pick_avoids_the_last_call():
    first = playbook.pick("de_mirage", Team.T, rng=random.Random(3))
    assert first is not None
    again = playbook.pick("de_mirage", Team.T, avoid=[first.name], rng=random.Random(3))
    assert again is not None and again.name != first.name


def test_pick_leaves_out_pistol_and_eco_calls_on_a_full_buy():
    for _ in range(20):
        strategy = playbook.pick("de_nuke", Team.T)
        assert strategy is not None and strategy.buy in (playbook.ANY, playbook.FULL)


def test_pistol_rounds_get_a_pistol_call_where_one_exists():
    strategy = playbook.pick("de_dust2", Team.CT, buy=playbook.PISTOL, rng=random.Random(0))
    assert strategy is not None and strategy.buy in (playbook.PISTOL, playbook.ANY)


def test_no_maps_outside_the_premier_pool():
    named = {s.map_name for s in playbook.PLAYBOOK if s.map_name}
    assert named == set(playbook.ACTIVE_DUTY)
