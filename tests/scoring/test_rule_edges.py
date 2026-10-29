"""Edges of the rules that no golden sheet reaches.

Each test pins a behavior the register cites that the sheets never
exercise: the refusals at the numbering's edges, the ruling that takes
back one lap of two, the notes and fields the sheet prints, and the
omnium tie-break walk. A change to any of these that keeps the goldens
green fails here.
"""

import pytest

from madtracker.scoring import aggregate, elimination, placings, sprint_points, win_and_out
from madtracker.scoring._common import place_map
from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    LapGained,
    LapNotCounted,
    PointsAdjusted,
    SprintResult,
    Status,
)
from madtracker.scoring.result import Standing, Standings
from madtracker.scoring.rules import (
    AggregateRules,
    WinAndOutRules,
    elimination_rules,
    placings_rules,
    points_race_rules,
    team_omnium_rules,
    usac_omnium_rules,
)

RIDERS = [1, 2, 3, 4, 5, 6]


def usac(sprints=4):
    return points_race_rules(sprint_count=sprints)


def ranks(standings):
    return {row.entrant_id: row.rank for row in standings.rows}


def race(*rows, complete=True):
    """(entrant, rank, total[, status[, final place]]), as in test_aggregate."""
    built = []
    for spec in rows:
        eid, rank, total = spec[:3]
        status = spec[3] if len(spec) > 3 else None
        final = spec[4] if len(spec) > 4 else None
        built.append(
            Standing(
                entrant_id=eid,
                rank=rank,
                total_points=total,
                status=status,
                final_sprint_place=final,
            )
        )
    return Standings(rows=tuple(built), is_complete=complete)


# Points Race, Madison, Tempo (sprint_points)


def test_sprint_zero_is_refused():
    """Sprint numbers start at 1 (R-POINTS-1): sprint 0 is a slip, not the first sprint."""
    problems = sprint_points.validate(usac(), RIDERS, [], SprintResult(0, [[1], [2]]))
    assert "Sprint numbers start at 1" in problems


def test_a_lap_gained_at_the_final_sprint_number_is_accepted():
    """USAC 2M3(d), UCI 3.2.125 (R-POINTS-3): a lap gained at the last sprint scores both,
    so the entry naming the final sprint's number is taken; one past it is not."""
    log = [SprintResult(n, [[1], [2]]) for n in (1, 2, 3)]
    assert sprint_points.validate(usac(4), RIDERS, log, LapGained([3], sprint_no=4)) == []
    problems = sprint_points.validate(usac(4), RIDERS, log, LapGained([3], sprint_no=5))
    assert problems == ["Sprint 5 is beyond the 4 sprints in this race"]


def test_one_point_back_with_no_penalty_is_refused():
    """USAC 8D5(b) (R-POINTS-7): nothing awards points, so +1 with no penalty standing is refused."""
    problems = sprint_points.validate(usac(), RIDERS, [], PointsAdjusted(entrant_id=1, points=1))
    assert problems == ["Entrant 1 has no penalty to give back"]


def test_next_sprint_number_follows_the_highest_sprint_recorded():
    """The surface's Record Sprint number comes from the engine: 1 before any sprint,
    then one past the highest recorded, whatever order the log holds them in."""
    assert sprint_points.compute(usac(), RIDERS, []).next_sprint_no == 1
    log = [SprintResult(2, [[1]]), SprintResult(1, [[2]])]
    assert sprint_points.compute(usac(), RIDERS, log).next_sprint_no == 3


def test_a_sprint_entered_twice_is_noted_once_and_a_single_entry_not_at_all():
    """A re-entered sprint shows on the sheet as a note; a clean log carries none."""
    clean = sprint_points.compute(usac(), RIDERS, [SprintResult(1, [[1]])])
    assert clean.notes == ()
    twice = sprint_points.compute(usac(), RIDERS, [SprintResult(1, [[1]]), SprintResult(1, [[2]])])
    assert twice.notes == ("Sprint 1 was entered twice; the later entry counts",)
    assert twice.by_entrant(2).sprint_points[0] == 5


def test_rows_before_any_entry_are_neither_ranked_nor_tied():
    """A field with nothing recorded is a start list: no rank and no tie on any row."""
    standings = sprint_points.compute(usac(), [1, 2, 3], [])
    assert all(row.rank is None and not row.tied for row in standings.rows)


def test_a_lap_not_counted_takes_back_one_lap_of_two():
    """USAC 8D5(b) (R-LAP-4): the ruling strikes one lap gained, and the other stands."""
    log = [LapGained([1]), LapGained([1]), LapNotCounted([1])]
    row = sprint_points.compute(usac(), RIDERS, log).by_entrant(1)
    assert row.laps_gained == 1
    assert row.lap_points == 20
    assert row.laps_not_counted == 1


# Shared helpers (_common) seen through the placings engine


def test_place_map_skips_a_place_for_a_tie_and_for_an_unseen_place():
    """USAC 1M6(a) (R-TIE-1): two tied for first are followed by third; an empty
    group is a place the judges did not call, and it is skipped too."""
    assert place_map([[3, 4], [2]]) == {3: 1, 4: 1, 2: 3}
    assert place_map([[], [1], [2]]) == {1: 2, 2: 3}
    standings = placings.compute(placings_rules(), [1, 2, 3], [FinishOrder([[], [1], [2]])])
    assert standings.by_entrant(1).final_sprint_place == 2
    assert standings.by_entrant(2).final_sprint_place == 3


def test_unranked_statuses_list_dnp_then_dq_then_dns():
    """The unranked tail has one order on every sheet: DNP, then DQ, then DNS."""
    log = [
        Status(entrant_id=2, status="DNS"),
        Status(entrant_id=3, status="DQ"),
        Status(entrant_id=4, status="DNP"),
        FinishOrder([[1]]),
    ]
    standings = placings.compute(placings_rules(), [1, 2, 3, 4], log)
    assert [row.entrant_id for row in standings.rows] == [1, 4, 3, 2]
    assert [row.status for row in standings.rows] == [None, "DNP", "DQ", "DNS"]


def test_riders_the_judges_left_out_carry_the_shared_place_note_and_nobody_else_does():
    """USAC 1M6(a) (R-CHASE-1): the note sits on the riders not separated, only them."""
    standings = placings.compute(placings_rules(), [1, 2, 3, 4], [FinishOrder([[1], [2]])])
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 3}
    note = "Shared place: not separated by the judges"
    assert standings.by_entrant(3).notes == (note,)
    assert standings.by_entrant(4).notes == (note,)
    assert standings.by_entrant(1).notes == ()
    assert standings.by_entrant(2).notes == ()


def test_a_row_the_engine_does_not_touch_keeps_zero_work():
    """A scratch race row shows no lap points, no penalty, no laps struck, no mishap:
    the exact row, so every default the sheet prints is pinned."""
    standings = placings.compute(placings_rules(), [1, 2], [FinishOrder([[1], [2]])])
    row = standings.by_entrant(1)
    assert (row.rank, row.final_sprint_place) == (1, 1)
    assert (row.lap_points, row.adjust_points, row.laps_not_counted, row.total_points) == (
        0,
        0,
        0,
        0,
    )
    assert row.tied is False and row.out_of_finish is False and row.status is None
    assert Standings().next_sprint_no == 1 and Standings().is_complete is False


def test_the_first_sprint_or_lap_is_expected_before_a_later_one():
    """Sequence by number: with nothing recorded, sprint 2 (or lap 2) names the gap, and
    the finish order names the first sprint not yet in."""
    problems = sprint_points.validate(usac(), RIDERS, [], SprintResult(2, [[1]]))
    assert "Expected sprint 1, got 2" in problems
    problems = sprint_points.validate(usac(), RIDERS, [], FinishOrder([[1], [2]]))
    assert "Sprint 1 of 4 has not been recorded" in problems
    rules = WinAndOutRules(places=3, direction="forward")
    assert "Expected lap 1, got 2" in win_and_out.validate(
        rules, RIDERS, [], SprintResult(2, [[1]])
    )


# Elimination


def test_two_bells_may_carry_the_same_sprint_number():
    """USAC 2E3(d)(i), UCI 3.2.223 (R-ELIM-3): several riders go out at one sprint,
    entered as separate bells with the same number; an earlier number is refused."""
    log = [Eliminated(1, [6])]
    assert elimination.validate(elimination_rules(), RIDERS, log, Eliminated(1, [5])) == []
    problems = elimination.validate(
        elimination_rules(), RIDERS, [Eliminated(2, [6])], Eliminated(1, [5])
    )
    assert problems == ["Sprint 1 is before the last recorded sprint 2"]


def test_the_field_may_be_eliminated_down_to_one_rider():
    """USAC 2E5 (R-ELIM-5): a miss-and-out to the last rider; only emptying the race is refused."""
    log = [Eliminated(1, [3])]
    assert elimination.validate(elimination_rules(), [1, 2, 3], log, Eliminated(2, [2])) == []
    problems = elimination.validate(elimination_rules(), [1, 2, 3], log, Eliminated(2, [1, 2]))
    assert problems == ["Eliminating them would leave nobody in the race"]


def test_a_bell_on_a_dnf_rider_is_only_the_mark():
    """USAC 2E3(d)(i) (R-ELIM-6): a DNF rider is out at that moment, so the bell naming
    them is taken as the mark; the finish order still cannot place them."""
    log = [Status(entrant_id=3, status="DNF")]
    assert elimination.validate(elimination_rules(), [1, 2, 3], log, Eliminated(1, [3])) == []
    problems = elimination.validate(elimination_rules(), [1, 2, 3], log, FinishOrder([[3], [1]]))
    assert "Entrant 3 is DNF and cannot be placed" in problems


def test_next_sprint_number_is_one_before_any_bell():
    assert elimination.compute(elimination_rules(), RIDERS, []).next_sprint_no == 1
    assert (
        elimination.compute(elimination_rules(), RIDERS, [Eliminated(2, [6])]).next_sprint_no == 3
    )


# Win-and-Out


def test_lap_zero_and_a_lap_without_a_winner_are_refused():
    rules = WinAndOutRules(places=3, direction="forward")
    assert "Lap numbers start at 1" in win_and_out.validate(
        rules, RIDERS, [], SprintResult(0, [[1]])
    )
    assert "No lap winner entered" in win_and_out.validate(
        rules, RIDERS, [], SprintResult(1, [[], [1]])
    )


def test_next_lap_follows_the_highest_lap_recorded():
    rules = WinAndOutRules(places=3, direction="forward")
    assert win_and_out.compute(rules, RIDERS, []).next_sprint_no == 1
    assert win_and_out.compute(rules, RIDERS, [SprintResult(1, [[3]])]).next_sprint_no == 2


def test_a_lone_lap_winner_is_not_tied():
    """R-WIN-1: one rider took the place; the riders still in are unranked, not tied with anyone."""
    rules = WinAndOutRules(places=3, direction="forward")
    standings = win_and_out.compute(rules, [1, 2, 3], [SprintResult(1, [[3]])])
    assert standings.by_entrant(3).rank == 1
    assert not standings.by_entrant(3).tied
    assert standings.by_entrant(1).rank is None


# Aggregates (Team Omnium, omnium tables)


def test_the_higher_total_wins_before_any_count_of_firsts():
    """USAC 2B19(e) (R-TEAM-3): firsts break a tie on the total, never beat a higher total."""
    races = [race((1, 2, 50), (2, 1, 40)), race((1, 2, 30), (2, 1, 20))]
    standings = aggregate.compute(team_omnium_rules(), [1, 2], races)
    assert ranks(standings) == {1: 1, 2: 2}


def test_a_tie_below_first_place_shares_the_rank():
    """USAC 2B19(e): identical records anywhere in the table share the rank, not only at the top."""
    races = [race((3, 1, 0), (2, 2, 0), (4, 2, 0)), race((3, 1, 0), (2, 2, 0), (4, 2, 0))]
    standings = aggregate.compute(usac_omnium_rules(), [2, 3, 4], races)
    assert ranks(standings) == {3: 1, 2: 2, 4: 2}
    assert standings.by_entrant(2).tied and standings.by_entrant(4).tied


def test_a_team_absent_from_a_race_under_must_finish_all_is_out_as_dnf():
    """USAC 2O2(c), 2O3(d) (R-OMNI-4): missing a race is leaving the omnium; the row is
    marked DNF and listed after the finishers, and an absent row is not a crash."""
    rules = AggregateRules(points_by_place=(5, 3), must_finish_all=True)
    races = [race((1, 1, 0), (2, 2, 0)), race((2, 1, 0))]
    standings = aggregate.compute(rules, [1, 2], races)
    assert standings.by_entrant(1).status == "DNF"
    assert standings.by_entrant(1).rank is None
    assert ranks(standings)[2] == 1


def test_no_tie_break_shares_a_level_total_whatever_the_final_sprint():
    """With tie_break 'none' the rule stops at the total; the final sprint is not consulted."""
    rules = AggregateRules(points_by_place=(5, 3), tie_break="none")
    races = [
        race((1, 1, 0, None, 2), (2, 2, 0, None, 1)),
        race((2, 1, 0, None, 2), (1, 2, 0, None, 1)),
    ]
    standings = aggregate.compute(rules, [1, 2], races)
    assert standings.by_entrant(1).total_points == standings.by_entrant(2).total_points == 8
    assert ranks(standings) == {1: 1, 2: 1}


@pytest.mark.parametrize("first, second, winner", [(None, 2, 2), (2, None, 1)])
def test_uci_tie_break_a_final_sprint_place_beats_none(first, second, winner):
    """UCI 3.2.252, USAC 2O3(g) (R-OMNI-3): level on the total, the rider with a place in
    the final sprint ranks ahead of one without, whichever side of the pair has it."""
    rules = AggregateRules(points_by_place=(5, 3), tie_break="last_race_final_sprint")
    races = [race((1, 1, 0), (2, 2, 0)), race((2, 1, 0, None, second), (1, 2, 0, None, first))]
    standings = aggregate.compute(rules, [1, 2], races)
    assert ranks(standings)[winner] == 1
    assert ranks(standings)[3 - winner] == 2


def test_level_in_every_count_and_neither_placed_in_the_last_race_shares_the_rank():
    """USAC 2B19(e) (R-TEAM-3): the walk back skips the last race when neither placed, and
    a tie in the race before it is where the rule stops."""
    races = [race((1, 1, 0), (2, 1, 0)), race((1, None, 0, "DNS"), (2, None, 0, "DNS"))]
    standings = aggregate.compute(usac_omnium_rules(), [1, 2], races)
    assert ranks(standings) == {1: 1, 2: 1}


def test_a_place_past_the_table_still_counts_in_the_most_places_walk():
    """USAC 2B19(e) "the most first place finishes or, if still tied, the most second
    place finishes, etc.": the walk runs to the worst place anyone took, even one
    past the scoring table, before the last race decides."""
    # 1: 1st, 6th, 2nd = 7 + 0 + 5. 2: 2nd, absent, 1st = 5 + 0 + 7. One first and one
    # second each; 1 has a sixth and 2 has none, so 1 ranks ahead, and the last race
    # (where 2 won) is never reached.
    races = [race((1, 1, 0), (2, 2, 0)), race((1, 6, 0)), race((2, 1, 0), (1, 2, 0))]
    standings = aggregate.compute(usac_omnium_rules((7, 5, 3, 2, 1)), [1, 2], races)
    assert standings.by_entrant(1).total_points == standings.by_entrant(2).total_points == 12
    assert ranks(standings) == {1: 1, 2: 2}


def test_aggregate_validate_names_each_problem_exactly():
    """Every check in aggregate.validate, by its exact text and race number."""
    races = [race((1, 1, 0), (2, 2, 0)), race((1, 1, 0), (2, 2, 0), complete=False)]
    rules = AggregateRules(points_by_place=(5, 3), multipliers=(1, 2), sum_total_races=(1,))
    assert aggregate.validate(rules, [1, 2], races) == ["Race 2 is not complete"]
    rules = AggregateRules(points_by_place=(5, 3), multipliers=(1,), sum_total_races=(2,))
    assert aggregate.validate(rules, [1, 2], races) == [
        "2 races but 1 multipliers; missing ones count 1",
        "sum_total_races names race 2 but only 2 were given",
        "Race 2 is not complete",
    ]
    # No multipliers at all is the common case and must not be read as too few.
    assert aggregate.validate(AggregateRules(points_by_place=(5, 3)), [1, 2], races[:1]) == []


def test_the_lower_total_wins_under_low_before_any_count_of_firsts():
    """USAC 7C3(f) (R-OMNI-7): lowest total wins; firsts only break a tie on it."""
    rules = AggregateRules(points_by_place=tuple(range(1, 25)), direction="low")
    races = [race((1, 2, 0), (2, 1, 0)), race((1, 2, 0), (2, 5, 0))]
    standings = aggregate.compute(rules, [1, 2], races)
    assert standings.by_entrant(1).total_points == 4
    assert standings.by_entrant(2).total_points == 6
    assert ranks(standings) == {1: 1, 2: 2}


def test_in_the_last_race_a_rider_who_placed_beats_one_who_was_absent():
    """USAC 2B19(e) (R-TEAM-3): level on total and on every count, the last race decides,
    and being placed there at all beats not riding it."""
    # 1: 6th, 1st, absent. 2: absent, 1st, 6th. Both 7 on 7-5-3-2-1, one first and one
    # sixth each; in the last race 2 placed and 1 did not.
    races = [race((1, 6, 0)), race((1, 1, 0), (2, 1, 0)), race((2, 6, 0))]
    standings = aggregate.compute(usac_omnium_rules((7, 5, 3, 2, 1)), [1, 2], races)
    assert standings.by_entrant(1).total_points == standings.by_entrant(2).total_points == 7
    assert ranks(standings) == {2: 1, 1: 2}
    standings = aggregate.compute(usac_omnium_rules((7, 5, 3, 2, 1)), [2, 1], races)
    assert ranks(standings) == {2: 1, 1: 2}
