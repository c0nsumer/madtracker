"""Action payload round-trips and the guards on decoding store rows."""

import json

import pytest

from madtracker.scoring.actions import (
    ACTION_TYPES,
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    LapNotCounted,
    OutOfFinish,
    PointsAdjusted,
    RaceEnded,
    RaceShortened,
    SprintResult,
    Status,
    Withdrawn,
    decode_action,
)

SAMPLES = [
    SprintResult(sprint_no=2, places=[[1], [2, 3], [], [4]]),
    LapGained(entrant_ids=[1], sprint_no=2),
    LapLost(entrant_ids=[2, 3]),
    Eliminated(sprint_no=4, entrant_ids=[]),
    FinishOrder(places=[[1], [2]]),
    Status(entrant_id=3, status="DNF", reason="pulled"),
    OutOfFinish(entrant_id=4),
    PointsAdjusted(entrant_id=2, points=-5),
    LapNotCounted(entrant_ids=[1]),
    RaceEnded(after_sprint=3),
    RaceShortened(sprint_count=3),
    Withdrawn(entrant_id=5),
]


@pytest.mark.parametrize("action", SAMPLES, ids=lambda e: e.kind)
def test_payload_round_trips_through_json(action):
    """The store keeps (kind, schema_ver, payload); json must be enough."""
    payload = json.loads(json.dumps(action.to_payload()))
    assert decode_action(action.kind, action.SCHEMA_VER, payload) == action


def test_places_are_normalized_to_tuples():
    """Frozen actions must not carry mutable lists the UI could alter later."""
    action = SprintResult(sprint_no=1, places=[[5], [6, 7]])
    assert action.places == ((5,), (6, 7))
    assert action.to_payload() == {"sprint_no": 1, "places": [[5], [6, 7]]}


def test_every_kind_is_registered():
    assert set(ACTION_TYPES) == {e.kind for e in SAMPLES}


def test_unknown_kind_is_refused():
    with pytest.raises(ValueError, match="Unknown action kind"):
        decode_action("teleport", 1, {})


def test_newer_schema_is_refused():
    """A payload from newer code is not guessed at; the replay must be exact."""
    with pytest.raises(ValueError, match="newer than this code"):
        decode_action("status", Status.SCHEMA_VER + 1, {"entrant_id": 1, "status": "DNF"})


def test_status_code_is_checked():
    """USAC 1M6 codes plus the CSV's DNP; anything else is a typo."""
    with pytest.raises(ValueError):
        Status(entrant_id=1, status="ABD")
