"""Rule presets: the one rulebook, its aliases, and what is not built in."""

import pytest

from madtracker.scoring.rules import (
    PRESETS,
    UCI_OMNIUM_PLACE_POINTS,
    AggregateRules,
    EliminationRules,
    PlacingsRules,
    SprintPointsRules,
    WinAndOutRules,
    elimination_rules,
    madison_rules,
    placings_rules,
    points_race_rules,
    rules_from_dict,
    tempo_rules,
    uci_omnium_rules,
    win_and_out_rules,
)


def test_the_final_sprint_is_the_one_numbered_sprint_count():
    """USAC 2M2(f), UCI 3.2.118: the last sprint awards double, the others 5-3-2-1."""
    rules = SprintPointsRules(sprint_count=5)
    assert rules.points_for_sprint(5) == (10, 6, 4, 2)
    assert rules.points_for_sprint(4) == (5, 3, 2, 1)
    assert rules.points_for_sprint(6) == (5, 3, 2, 1)  # never final
    assert SprintPointsRules().sprint_count is None
    with pytest.raises(ValueError, match="at least 1"):
        SprintPointsRules(sprint_count=0)


def test_tempo_one_point_per_sprint_final_not_doubled():
    """UCI 3.2.261, 3.2.262, USAC 2P2: every sprint awards 1, the last one too."""
    rules = tempo_rules(sprint_count=36)
    assert rules.sprint_count == 36
    assert rules.points_for_sprint(36) == (1,)
    assert rules.points_for_sprint(1) == (1,)
    assert rules.lap_gained_points == 20


def test_one_rulebook_is_built_in():
    """USAC and UCI score every format alike; a venue's house values live
    in a stored ruleset, never in a preset."""
    assert PRESETS == ("rulebook",)
    assert points_race_rules(" Rulebook ") == points_race_rules()
    for name in ("madtrack", "usac", "uci"):
        with pytest.raises(ValueError, match="preset must be one of"):
            points_race_rules(name)


def test_rulebook_presets_use_twenty_per_lap():
    """USAC 2M2(f)(ii), UCI 3.2.118: 20 points per lap, 5-3-2-1 doubled, by team in a madison."""
    rules = points_race_rules(sprint_count=10)
    assert rules.lap_gained_points == rules.lap_lost_points == 20
    assert rules.intermediate_points == (5, 3, 2, 1)
    assert rules.final_points == (10, 6, 4, 2)
    madison = madison_rules(sprint_count=8)
    assert madison.scored_unit == "team"
    assert madison.lap_gained_points == 20
    assert madison.sprint_count == 8


def test_rulebook_placings_elimination_and_win_and_out():
    """USAC 2C4 places a lapped rider who stays in; USAC 2E3(f), UCI 3.2.224
    ride the final between two; the win-and-out awards three places forward."""
    assert placings_rules().lapped_riders_placed_by_laps is True
    assert elimination_rules().survivors == 2
    assert elimination_rules(survivors=1).final_by_sprint is False
    assert (win_and_out_rules().places, win_and_out_rules().direction) == (3, "forward")


def test_uci_omnium_table():
    """UCI 3.2.250: 40, 38, ... 2 for places 1 to 20, then 1."""
    assert UCI_OMNIUM_PLACE_POINTS[:3] == (40, 38, 36)
    assert UCI_OMNIUM_PLACE_POINTS[-1] == 2
    assert len(UCI_OMNIUM_PLACE_POINTS) == 20
    assert uci_omnium_rules().points_beyond_table == 1


@pytest.mark.parametrize(
    "rules",
    [
        PlacingsRules(lapped_riders_placed_by_laps=False),
        SprintPointsRules(sprint_count=4, scored_unit="team"),
        SprintPointsRules(points_by_sprint=((1,), (2, 1), (3, 2, 1))),
        EliminationRules(survivors=3),
        WinAndOutRules(places=5, direction="reverse"),
        AggregateRules(points_by_place=(7, 5, 3, 2, 1), multipliers=(1, 2.5)),
    ],
    ids=lambda r: type(r).__name__,
)
def test_rules_round_trip_through_dict(rules):
    """The race stores its rules as JSON; the replay must rebuild them exactly."""
    assert rules_from_dict(rules.to_dict()) == rules


def test_bad_option_values_are_refused():
    with pytest.raises(ValueError):
        SprintPointsRules(tie_break="coin")
    with pytest.raises(ValueError):
        WinAndOutRules(direction="sideways")
    with pytest.raises(ValueError):
        AggregateRules(direction="middle")
    with pytest.raises(ValueError):
        points_race_rules("fifa")
