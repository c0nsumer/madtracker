"""Decisions on the design's reading, kept as cases so each stays checked."""

import pytest
from test_multi_race import (
    entered,
    night,
    rider_standings,
    scratch,
)

from madtracker.control import multi_race
from madtracker.scoring import rules as R


@pytest.mark.parametrize("case", ["everyone-dns", "elimination-walkover"])
def test_q1_a_complete_result_counts_even_from_dns_marks_alone(store, riders, case):
    """A one-rider race counts. A race whose result is
    complete is a column even when every other rider is marked DNS; the rider
    left takes 1st and scores the place (the Elimination walkover's 40 in the
    Four-Race Omnium). A Scratch Race left with one rider counts once its
    finish is recorded, which needs a scorer action."""
    a, b, c = riders[:3]
    fri = night(store, riders, "Fri", "2026-10-16")
    scratch(store, fri, [a, b, c], name="Scratch")
    if case == "everyone-dns":
        live = entered(store, fri, "chase", R.placings_rules(), [b, c], name="Nobody")
    else:
        live = entered(store, fri, "elimination", R.elimination_rules(), [a, b, c], name="Walkover")
    assert live.act(b, "dns").ok and live.act(c, "dns").ok
    decided = live.race_id
    got = multi_race.compute(store, rider_standings(store, [fri], kind=multi_race.OMNIUM))
    assert got.not_yet_raced == []
    (group,) = got.groups
    assert [col.race_id for col in group.columns][-1] == decided
    rows = {r.bib: r for r in group.rows}
    if case == "elimination-walkover":
        assert rows[1].per_race == [7, 7] and rows[1].total == 14
    else:
        assert rows[1].per_race == [7, None] and rows[2].per_race == [5, None]
