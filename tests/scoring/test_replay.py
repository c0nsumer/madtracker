"""Replay dispatch and recomputation after a void."""

import pytest

from madtracker.scoring import (
    RULES_VERSION,
    actions_from_rows,
    compute_for_format,
    validate_for_format,
)
from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    LapNotCounted,
    PointsAdjusted,
    SprintResult,
    Status,
)
from madtracker.scoring.replay import FORMAT_ENGINE, engine_for
from madtracker.scoring.rules import (
    elimination_rules,
    placings_rules,
    points_race_rules,
    rules_from_dict,
    win_and_out_rules,
)


def test_rules_version_is_a_string_the_store_can_record():
    assert RULES_VERSION == "2026.10.1"


def test_every_format_key_maps_to_an_engine():
    for key in FORMAT_ENGINE:
        assert engine_for(key).compute


def test_unknown_format_and_mismatched_rules_are_refused():
    with pytest.raises(ValueError, match="Unknown race format"):
        compute_for_format("kabaddi", placings_rules(), [1], [])
    with pytest.raises(TypeError, match="cannot score"):
        compute_for_format("points", elimination_rules(), [1], [])
    with pytest.raises(TypeError):
        validate_for_format("elimination", placings_rules(), [1], [], Eliminated(1, [1]))


def test_store_rows_replay_to_the_same_standings():
    """The store hands over (kind, schema_ver, payload) rows and the rules JSON."""
    rules = points_race_rules(sprint_count=3)
    actions = [
        SprintResult(1, [[35], [12], [18]]),
        LapLost([22]),
        SprintResult(2, [[35], [18], [12]]),
        FinishOrder([[35], [18], [12], [22]]),
    ]
    rows = [(e.kind, e.SCHEMA_VER, e.to_payload()) for e in actions]
    replayed = actions_from_rows(rows)
    assert replayed == actions
    direct = compute_for_format("points", rules, [12, 35, 18, 22], actions)
    again = compute_for_format(
        "points", rules_from_dict(rules.to_dict()), [12, 35, 18, 22], replayed
    )
    assert again == direct


def test_voiding_an_action_recomputes_the_standings():
    """Undo is a void row the store drops from the live list; the engine is
    stateless so the standings simply come out as if it never happened."""
    rules = elimination_rules()
    riders = [1, 2, 3, 4]
    actions = [Eliminated(1, [4]), Eliminated(2, [2]), Eliminated(3, [3])]
    before = compute_for_format("elimination", rules, riders, actions)
    # One rider left is the winner outright; no final sprint is needed.
    assert before.is_complete
    assert before.by_entrant(1).rank == 1
    assert before.by_entrant(2).rank == 3
    # The scorer voids the second elimination (it was rider 3, not 2).
    live = [actions[0], actions[2]]
    after = compute_for_format("elimination", rules, riders, live)
    assert after.remaining_entrants == (1, 2)
    assert after.by_entrant(2).rank is None
    assert after.by_entrant(3).rank == 3
    assert after.next_sprint_no == 4


def test_validate_for_format_dispatches():
    rules = placings_rules()
    problems = validate_for_format("chase", rules, [1, 2], [Status(2, "DNF")], FinishOrder([[2]]))
    assert problems == ["Entrant 2 is DNF and cannot be placed"]


def test_rulings_replay_through_the_format_dispatch():
    """A penalty and a lap not counted, stored as rows, score the same as
    the actions, and are validated by the format's engine."""
    rules = points_race_rules(sprint_count=2)
    live = [
        SprintResult(1, [[1], [2]]),
        LapGained([2]),
        FinishOrder([[2], [1]]),
        PointsAdjusted(entrant_id=2, points=-20),
        LapNotCounted([2]),
    ]
    rows = [(a.kind, a.SCHEMA_VER, a.to_payload()) for a in live]
    standings = compute_for_format("points", rules, [1, 2], actions_from_rows(rows))
    assert standings == compute_for_format("points", rules, [1, 2], live)
    row = standings.by_entrant(2)
    # 3 + 10 from the sprints, the lap and its 20 gone, 20 off: -7.
    assert (row.sprint_points, row.laps_gained, row.adjust_points) == ((3, 10), 0, -20)
    assert row.total_points == -7 and standings.by_entrant(1).rank == 1
    assert validate_for_format("points", rules, [1, 2], live, LapNotCounted([2])) == [
        "Entrant 2 has no lap gained to cancel"
    ]
    assert validate_for_format(
        "elimination", elimination_rules(), [1, 2], [], PointsAdjusted(1, -1)
    ) == [  # fmt: skip
        "A points penalty is scored in a Points Race, Madison, or Tempo Race only"
    ]
    laps = [LapGained([1])]
    assert validate_for_format(
        "win_and_out", win_and_out_rules(2), [1, 2], laps, LapNotCounted([1])
    ) == [  # fmt: skip
        "Laps do not count in a Win-and-Out"
    ]
