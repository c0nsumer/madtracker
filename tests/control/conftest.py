"""A tmp store with one event and a race builder for the control tests."""

import pytest

from madtracker.scoring import rules as R
from madtracker.store import Store


class HouseRules:
    """Club-style values the session tests score under: a lap worth 10,
    10-7-5-3-2-1 doubled in the points race.

    Spelled out here because no preset holds them; a venue keeps such
    values in a stored ruleset (``madtracker.control.rulesets``).
    """

    LAP = 10
    POINTS_TABLE = (10, 7, 5, 3, 2, 1)

    @classmethod
    def points(cls, sprints: int | None = None) -> R.SprintPointsRules:
        return R.SprintPointsRules(
            sprint_count=sprints,
            intermediate_points=cls.POINTS_TABLE,
            final_points=tuple(2 * p for p in cls.POINTS_TABLE),
            lap_gained_points=cls.LAP,
            lap_lost_points=cls.LAP,
        )

    @classmethod
    def madison(cls, sprints: int | None = None) -> R.SprintPointsRules:
        return R.SprintPointsRules(
            sprint_count=sprints,
            lap_gained_points=cls.LAP,
            lap_lost_points=cls.LAP,
            scored_unit="team",
        )

    @staticmethod
    def elimination() -> R.EliminationRules:
        return R.EliminationRules()


@pytest.fixture
def house():
    return HouseRules


NAMES = {
    3: "Marcus Delgado",
    5: "Priya Okafor",
    7: "Maya Petrakis",
    8: "Tom Kowalczyk",
    9: "Ben Szymanski",
    12: "Tess Gallagher",
    19: "Omar Rahimi",
    24: "Kenji Mori",
    33: "Jack Moreau",
    36: "Nora Haddad",
    44: "Eli Brandt",
}


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "control.sqlite")
    yield s
    s.close()


@pytest.fixture
def event(store):
    """Every rider in NAMES entered in one event with that bib; returns (event_id, bib->rider_id)."""
    m = store.add_event("Test Race Night", "2026-10-10")
    ids = {}
    for bib, name in NAMES.items():
        first, last = name.split(" ")
        rider = store.add_rider(first, last)
        store.add_entry(m.event_id, rider.rider_id, bib)
        ids[bib] = rider.rider_id
    return m.event_id, ids


@pytest.fixture
def make_race(store, event):
    """Build a race: make_race(fmt, bibs, rules=None, teams=None) -> race_id.

    teams is a list of (color, bib, bib); team races enter both riders.
    """
    event_id, ids = event

    def build(fmt, bibs, rules=None, teams=None, name="Race"):
        race = store.add_race(event_id, name, fmt, rules=rules.to_dict() if rules else None)
        for bib in bibs:
            store.add_race_entry(race.race_id, ids[bib])
        for color, a, b in teams or ():
            team = store.add_team(race.race_id, color, color=color)
            store.add_team_member(team.team_id, ids[a])
            store.add_team_member(team.team_id, ids[b])
        return race.race_id

    return build
