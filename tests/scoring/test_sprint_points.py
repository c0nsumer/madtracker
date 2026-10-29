"""Points race, madison and tempo rules, each pinned to its article."""

from madtracker.scoring import sprint_points
from madtracker.scoring.actions import (
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
)
from madtracker.scoring.rules import (
    SprintPointsRules,
    madison_rules,
    points_race_rules,
    tempo_rules,
)

RIDERS = [1, 2, 3, 4, 5, 6]


def usac(sprints=4):
    return points_race_rules(sprint_count=sprints)


def ranks(standings):
    return {row.entrant_id: row.rank for row in standings.rows}


def test_sprint_tie_shares_place_and_skips_next():
    """UCI 3.2.118, USAC 2M2(f)(i): two tied for first both score 5, nobody scores 3."""
    result = sprint_points.award([[1, 2], [3], [4]], (5, 3, 2, 1))
    assert result == {1: 5, 2: 5, 3: 2, 4: 1}


def test_tie_for_second_awards_three_to_both_and_one_to_the_next():
    """UCI 3.2.118: a tie for 2nd gives 3 to both; the next rider is 4th for 1."""
    assert sprint_points.award([[1], [2, 3], [4]], (5, 3, 2, 1)) == {1: 5, 2: 3, 3: 3, 4: 1}


def test_unseen_place_awards_nobody():
    """An empty inner list is the scorer's X: that place goes unawarded."""
    assert sprint_points.award([[1], [], [3]], (5, 3, 2, 1)) == {1: 5, 3: 2}


def test_lap_gained_at_a_sprint_adds_both():
    """UCI 3.2.125, USAC 2M3(d): 20 for the lap plus the sprint points."""
    actions = [SprintResult(1, [[1], [2]]), LapGained([1], sprint_no=1)]
    standings = sprint_points.compute(usac(), RIDERS, actions)
    row = standings.by_entrant(1)
    assert row.sprint_points == (5, 0, 0, 0)
    assert row.lap_points == 20
    assert row.total_points == 25


def test_laps_are_points_only_never_a_sort_key():
    """UCI 3.2.118, USAC 2M2(f): a rider a lap down with more points wins."""
    # Rider 1 wins every sprint (25) but loses a lap (-20) for 5. Rider 2 is
    # second every time (15) on full laps. Points decide: 2 wins, 1 is second,
    # a lap down and still ahead of 3, who is on full laps with no points.
    actions = [
        SprintResult(1, [[1], [2]]),
        SprintResult(2, [[1], [2]]),
        SprintResult(3, [[1], [2]]),
        SprintResult(4, [[1], [2]]),
        LapLost([1]),
        FinishOrder([[1], [2], [3]]),
    ]
    standings = sprint_points.compute(usac(), [1, 2, 3], actions)
    assert standings.by_entrant(1).total_points == 5
    assert standings.by_entrant(1).net_laps == -1
    assert standings.by_entrant(2).total_points == 15
    assert ranks(standings) == {2: 1, 1: 2, 3: 3}


def test_tie_broken_by_full_final_order_beyond_scoring_places():
    """UCI 3.2.119, USAC 2M2(g): 5th and 6th across the line still break a tie."""
    # 5 and 6 each take one 4th place for 1 point and are tied on 1; the
    # final sprint only awards four places, so only the full line order can
    # separate them: 6 crossed 5th, 5 crossed 6th.
    actions = [
        SprintResult(1, [[1], [2], [3], [5]]),
        SprintResult(2, [[1], [2], [3], [6]]),
        SprintResult(3, [[1], [2], [3], [4]]),
        SprintResult(4, [[1], [2], [3], [4]]),
        FinishOrder([[1], [2], [3], [4], [6], [5]]),
    ]
    standings = sprint_points.compute(usac(), RIDERS, actions)
    assert standings.by_entrant(5).total_points == standings.by_entrant(6).total_points == 1
    assert standings.by_entrant(6).rank == 5
    assert standings.by_entrant(5).rank == 6
    assert standings.by_entrant(6).final_sprint_place == 5
    assert not standings.by_entrant(6).tied


def test_tie_on_points_and_final_place_shares_rank():
    """USAC 1M6(a): nothing separates them, so 1, 1, 3 rather than an arbitrary order."""
    # 1 and 2 swap first and second, then dead-heat the doubled final sprint:
    # 5+3+10 = 3+5+10 = 18, and the line could not split them either.
    actions = [
        SprintResult(1, [[1], [2], [3]]),
        SprintResult(2, [[2], [1], [3]]),
        SprintResult(3, [[3]]),
        SprintResult(4, [[1, 2], [3]]),
        FinishOrder([[1, 2], [3]]),
    ]
    standings = sprint_points.compute(usac(), [1, 2, 3], actions)
    assert standings.by_entrant(1).total_points == standings.by_entrant(2).total_points == 18
    assert ranks(standings) == {1: 1, 2: 1, 3: 3}
    assert standings.by_entrant(1).tied and standings.by_entrant(2).tied
    assert not standings.by_entrant(3).tied


def test_dnf_keeps_points_and_ranks_after_all_finishers_as_a_group():
    """UCI 3.3.012 A: riders withdrawn by the commissaires share the next rank."""
    actions = [
        SprintResult(1, [[5], [6], [1]]),
        Status(5, "DNF", "pulled"),
        Status(6, "DNF", "mishap"),
        SprintResult(2, [[1], [2]]),
        SprintResult(3, [[1], [2]]),
        SprintResult(4, [[1], [2]]),
        FinishOrder([[1], [2], [3], [4]]),
    ]
    standings = sprint_points.compute(usac(), RIDERS, actions)
    five, six = standings.by_entrant(5), standings.by_entrant(6)
    assert five.total_points == 5 and five.status == "DNF"
    assert five.rank == six.rank == 5
    assert five.tied and six.tied
    assert standings.by_entrant(4).rank == 4
    assert [r.entrant_id for r in standings.rows][-2:] == [5, 6]


def test_dns_is_never_ranked():
    """USAC 1M6(b): did not start, no place."""
    actions = [Status(6, "DNS"), SprintResult(1, [[1]])]
    standings = sprint_points.compute(usac(), RIDERS, actions)
    assert standings.by_entrant(6).rank is None
    assert standings.by_entrant(6).status == "DNS"
    assert 6 not in standings.remaining_entrants


def test_neutralized_into_last_kilometer_keeps_points_and_is_ranked():
    """UCI 3.2.020bis, USAC 2M8(a): no status, not at the line, ranked on points.

    A rider pulled by the officials is DNF (3.3.012 A) and ranks below; a
    rider whose free laps ran into the last kilometer is not marked and
    keeps the ranking the points give."""
    actions = [
        SprintResult(1, [[3], [1]]),
        SprintResult(2, [[3], [1]]),
        SprintResult(3, [[1], [2]]),
        SprintResult(4, [[1], [2]]),
        FinishOrder([[1], [2]]),
    ]
    standings = sprint_points.compute(usac(), [1, 2, 3], actions)
    three = standings.by_entrant(3)
    assert three.total_points == 10 and three.status is None
    assert ranks(standings) == {1: 1, 3: 2, 2: 3}


def test_finish_order_scores_the_final_sprint_when_no_sprint_result_given():
    """One full-order entry at the line is both the doubled sprint and the tie-break."""
    rules = usac(sprints=2)
    actions = [SprintResult(1, [[1], [2]]), FinishOrder([[2], [1], [3]])]
    standings = sprint_points.compute(rules, [1, 2, 3], actions)
    assert standings.by_entrant(2).sprint_points == (3, 10)
    assert standings.by_entrant(1).sprint_points == (5, 6)
    assert standings.is_complete


def test_final_sprint_result_wins_over_finish_order_for_points():
    """When both are entered the SprintResult scores and FinishOrder only breaks ties."""
    rules = usac(sprints=2)
    actions = [SprintResult(1, [[1]]), SprintResult(2, [[2], [1]]), FinishOrder([[2], [1]])]
    standings = sprint_points.compute(rules, [1, 2], actions)
    assert standings.by_entrant(2).sprint_points == (0, 10)
    assert standings.by_entrant(2).total_points == 10


def test_tempo_scores_one_point_per_sprint_final_not_doubled():
    """UCI 3.2.262, USAC 2P2(c): the final sprint is also 1 point."""
    rules = tempo_rules(sprint_count=4)
    actions = [SprintResult(n, [[1]]) for n in range(1, 5)] + [FinishOrder([[1], [2]])]
    standings = sprint_points.compute(rules, [1, 2], actions)
    assert standings.by_entrant(1).sprint_points == (1, 1, 1, 1)
    assert standings.by_entrant(1).total_points == 4


def test_snowball_uses_per_sprint_table():
    """Snowball (docs/research/usac-track-formats.md): lap 1 awards 1, lap 2 awards 2 and 1."""
    rules = SprintPointsRules(points_by_sprint=((1,), (2, 1), (3, 2, 1)), lap_gained_points=0)
    actions = [SprintResult(1, [[1]]), SprintResult(2, [[2], [1]]), SprintResult(3, [[1], [2]])]
    standings = sprint_points.compute(rules, [1, 2], actions)
    assert standings.by_entrant(1).sprint_points == (1, 1, 3)
    assert standings.by_entrant(2).sprint_points == (0, 2, 2)
    # Complete only once the full line order is in (USAC 2M2(g)).
    assert not standings.is_complete
    standings = sprint_points.compute(rules, [1, 2], actions + [FinishOrder([[1], [2]])])
    assert standings.by_entrant(1).sprint_points == (1, 1, 3)
    assert standings.is_complete


def test_madison_scores_teams_the_same_way():
    """UCI 3.2.161, 3.2.162, USAC 2N2(g): the madison is the points race over teams."""
    rules = madison_rules(sprint_count=2)
    actions = [SprintResult(1, [[10], [11]]), LapGained([11]), SprintResult(2, [[11], [10]])]
    standings = sprint_points.compute(rules, [10, 11], actions)
    assert standings.by_entrant(11).total_points == 3 + 20 + 10
    assert standings.by_entrant(11).rank == 1


def test_no_entries_yet_means_no_ranks():
    standings = sprint_points.compute(usac(), [1, 2], [])
    assert all(row.rank is None for row in standings.rows)
    assert standings.remaining_entrants == (1, 2)


def test_re_entered_sprint_replaces_and_is_noted():
    actions = [SprintResult(1, [[1]]), SprintResult(1, [[2]])]
    standings = sprint_points.compute(usac(), [1, 2], actions)
    assert standings.by_entrant(2).total_points == 5
    assert standings.by_entrant(1).total_points == 0
    assert any("entered twice" in note for note in standings.notes)


def test_a_later_status_replaces_an_earlier_one():
    """A rider who left the race (DNF) and is then disqualified after a
    protest (USAC 1P1) reads as DQ: the last status stands, nothing is
    undone, and the rider's points leave the sheet with the DQ."""
    rules = usac()
    actions = [SprintResult(1, [[6], [2]]), Status(6, "DNF"), Status(6, "DQ")]
    standings = sprint_points.compute(rules, RIDERS, actions)
    row = standings.by_entrant(6)
    assert row.status == "DQ" and row.rank is None
    assert standings.by_entrant(2).rank == 1


def test_validate_rejects_the_usual_slips():
    rules = usac()
    actions = [SprintResult(1, [[1], [2]]), Status(6, "DNF", "pulled")]
    v = sprint_points.validate
    assert v(rules, RIDERS, actions, SprintResult(2, [[99]])) == ["Unknown entrant 99"]
    assert "Entered more than once" in v(rules, RIDERS, actions, SprintResult(2, [[1], [1]]))[0]
    assert any("already recorded" in p for p in v(rules, RIDERS, actions, SprintResult(1, [[1]])))
    assert any("beyond the 4" in p for p in v(rules, RIDERS, actions, SprintResult(5, [[1]])))
    assert any("Expected sprint 2" in p for p in v(rules, RIDERS, actions, SprintResult(3, [[1]])))
    assert any("is DNF" in p for p in v(rules, RIDERS, actions, SprintResult(2, [[6]])))
    assert any("already DNF" in p for p in v(rules, RIDERS, actions, Status(6, "DNF")))
    assert v(rules, RIDERS, actions, Status(6, "DQ")) == []
    assert any("not scored" in p for p in v(rules, RIDERS, actions, Eliminated(2, [1])))
    assert v(rules, RIDERS, actions, SprintResult(2, [[2], [3]])) == []
    assert v(rules, RIDERS, actions, LapLost([3])) == []


def test_validate_rejects_scoring_after_the_finish():
    rules = usac()
    actions = [SprintResult(1, [[1]]), FinishOrder([[1], [2]])]
    v = sprint_points.validate
    assert any("already recorded" in p for p in v(rules, RIDERS, actions, SprintResult(2, [[1]])))
    assert any("after the finish" in p for p in v(rules, RIDERS, actions, Status(2, "DNF")))
    # A DQ after the line is how a protest ends (USAC 1P1).
    assert v(rules, RIDERS, actions, Status(2, "DQ", "protest upheld")) == []


# Edge cases: the sprint count, the finish, laps, DNF and DQ.


def test_race_without_a_sprint_count_refuses_every_entry():
    """With no sprint count the engine cannot know which sprint doubles
    (UCI 3.2.118, USAC 2M2(f)), so it takes nothing rather than score the
    finish as an extra doubled sprint nobody rode."""
    rules = SprintPointsRules()
    v = sprint_points.validate
    for action in (SprintResult(1, [[1]]), FinishOrder([[1], [2]]), LapGained([1])):
        assert v(rules, [1, 2], [], action) == ["This race has no sprint count"]
    # A log written past the refusal: the finish breaks ties, scores nothing.
    actions = [SprintResult(1, [[1], [2]]), FinishOrder([[2], [1]])]
    standings = sprint_points.compute(rules, [1, 2], actions)
    assert standings.by_entrant(2).sprint_points == (3,)
    assert standings.by_entrant(1).total_points == 5


def test_finish_order_refused_while_an_earlier_sprint_is_missing():
    """The finish is the final sprint (USAC 2M2(f), UCI 3.2.118): with
    sprint 2 of 4 never entered, a finish would silently score it as zero."""
    v = sprint_points.validate
    problems = v(usac(4), RIDERS, [SprintResult(1, [[1]])], FinishOrder([[1], [2]]))
    assert problems == ["Sprint 2 of 4 has not been recorded"]
    done = [SprintResult(n, [[1]]) for n in (1, 2, 3)]
    assert v(usac(4), RIDERS, done, FinishOrder([[1], [2]])) == []


def test_last_sprint_result_alone_does_not_complete_the_race():
    """USAC 2M2(g), UCI 3.2.119: the tie-break reads the full order of
    everyone still in, so the race is complete only once the FinishOrder
    is in; the final as a SprintResult plus a FinishOrder still works."""
    actions = [SprintResult(1, [[1]]), SprintResult(2, [[2], [1]])]
    standings = sprint_points.compute(usac(2), [1, 2, 3], actions)
    assert not standings.is_complete
    assert standings.remaining_entrants == (1, 2, 3)
    standings = sprint_points.compute(usac(2), [1, 2, 3], actions + [FinishOrder([[2], [1], [3]])])
    assert standings.is_complete


def test_gain_then_lose_a_lap_nets_zero():
    """USAC 2M2(f)(ii), (iii), UCI 3.2.118: +20 for the lap gained, -20 for
    the lap lost; the rider is back to sprint points only."""
    actions = [SprintResult(1, [[1]]), LapGained([1]), LapLost([1]), SprintResult(2, [[2]])]
    row = sprint_points.compute(usac(2), [1, 2], actions).by_entrant(1)
    assert (row.laps_gained, row.laps_lost, row.lap_points) == (1, 1, 0)
    assert row.total_points == 5


def test_lap_gained_in_the_final_sprint_scores_both_then_laps_close():
    """UCI 3.2.125, USAC 2M3(d): a lap gained at the doubled final sprint is
    20 + 10. After the finish order nothing more scores (validate_common)."""
    rules = usac(2)
    actions = [SprintResult(1, [[2]]), LapGained([1], sprint_no=2), FinishOrder([[1], [2]])]
    standings = sprint_points.compute(rules, [1, 2], actions)
    assert standings.by_entrant(1).total_points == 30
    assert standings.by_entrant(1).rank == 1
    problems = sprint_points.validate(rules, [1, 2], actions, LapGained([2]))
    assert any("finish order is already recorded" in p for p in problems)


def test_dnf_on_fifteen_points_ranks_behind_a_finisher_on_zero():
    """UCI 3.3.012 A: the DNF group ranks after every finisher, whatever
    the points; the DNF keeps its 15 on the sheet."""
    actions = [SprintResult(n, [[3]]) for n in (1, 2, 3)]
    actions += [Status(3, "DNF", "crash"), SprintResult(4, [[1], [2]])]
    actions.append(FinishOrder([[1], [2], [4]]))
    standings = sprint_points.compute(usac(4), [1, 2, 3, 4], actions)
    assert standings.by_entrant(4).total_points == 0
    assert ranks(standings) == {1: 1, 2: 2, 4: 3, 3: 4}
    assert standings.by_entrant(3).total_points == 15


def test_dq_after_the_finish_moves_everyone_up_and_passes_no_points_on():
    """USAC 1M6 and glossary: a DQ is not placed, so the others move up a
    rank. The points a DQ'd rider took stay unawarded unless the officials
    correct the sprint; the program records, it does not re-award
    (docs/scoring-rules.md, "What is deliberately not enforced")."""
    actions = [SprintResult(1, [[1], [2], [3]]), FinishOrder([[1], [2], [3]])]
    actions.append(Status(1, "DQ", "protest upheld"))
    standings = sprint_points.compute(usac(2), [1, 2, 3], actions)
    assert ranks(standings) == {2: 1, 3: 2, 1: None}
    assert standings.by_entrant(2).sprint_points == (3, 6)
    assert standings.by_entrant(3).sprint_points == (2, 4)


def test_a_final_sprint_dead_heat_for_first_awards_both_first_place_points_and_shares_first():
    """USAC 2M2(f)(i): two tied for first in a points sprint both score first
    place's points and there is no second place. The final sprint is a points
    sprint, so the specific rule governs it over 1M4(b)'s re-ride (USAC 1K1(d)):
    riders level on points after it share first, and no re-ride is entered."""
    actions = [SprintResult(1, [[3], [4], [1, 2]]), FinishOrder([[1, 2], [3], [4]])]
    standings = sprint_points.compute(usac(2), [1, 2, 3, 4], actions)
    assert ranks(standings) == {1: 1, 2: 1, 3: 3, 4: 4}
    assert standings.by_entrant(1).tied and standings.by_entrant(2).tied
    assert standings.by_entrant(1).sprint_points == (2, 10)
    assert standings.by_entrant(2).sprint_points == (2, 10)
    assert standings.by_entrant(3).sprint_points == (5, 4)
    assert standings.is_complete


def test_a_tempo_dead_heat_awards_both_riders_the_one_point():
    """USAC 2P2(c) with 2M2(f)(i): the Tempo sprint's one point goes to both
    riders the judges cannot separate."""
    standings = sprint_points.compute(
        tempo_rules(sprint_count=3), [1, 2, 3], [SprintResult(1, [[1, 2]])]
    )
    assert standings.by_entrant(1).total_points == 1
    assert standings.by_entrant(2).total_points == 1
    assert standings.by_entrant(3).total_points == 0


def test_dnf_is_refused_on_a_rider_who_never_started():
    """USAC 1M6(b): a DNS rider took no start, so there is no race to fail
    to finish. The wrong mark is undone instead; a DQ may still follow."""
    actions = [Status(1, "DNS")]
    assert sprint_points.validate(usac(2), [1, 2, 3], actions, Status(1, "DNF")) == [
        "Entrant 1 is DNS and never started; it cannot be marked DNF"
    ]
    assert sprint_points.validate(usac(2), [1, 2, 3], actions, Status(1, "DQ")) == []
    assert sprint_points.validate(usac(2), [1, 2, 3], [Status(1, "DNP")], Status(1, "DNF")) == [
        "Entrant 1 is DNP and never started; it cannot be marked DNF"
    ]


def test_level_on_points_and_both_missing_from_the_finish_share_the_rank():
    """USAC 2M2(g), UCI 3.2.119 break a tie by the final sprint; with
    neither placed in it nothing separates them (USAC 1M6(a) equal placing)."""
    # Tied for second in sprint 1, both 3; the final is its own entry so
    # the finish order only breaks ties.
    actions = [SprintResult(1, [[1], [3, 4]]), SprintResult(2, [[1], [2]])]
    actions.append(FinishOrder([[1], [2]]))
    standings = sprint_points.compute(usac(2), [1, 2, 3, 4], actions)
    assert standings.by_entrant(3).total_points == standings.by_entrant(4).total_points == 3
    assert ranks(standings)[3] == ranks(standings)[4] == 3
    assert standings.by_entrant(3).tied


def test_negative_totals_order_below_zero():
    """USAC 2M2(f)(iii), UCI 3.2.118: -20 per lap lost and totals may go
    negative; two laps down (-40) ranks above three down (-60), both below
    a rider on 0."""
    actions = [LapLost([1]), LapLost([1]), LapLost([2]), LapLost([2]), LapLost([2])]
    actions += [SprintResult(1, [[3]]), FinishOrder([[3], [2], [1]])]
    standings = sprint_points.compute(usac(1), [1, 2, 3], actions)
    assert standings.by_entrant(1).total_points == -40
    assert standings.by_entrant(2).total_points == -60
    assert ranks(standings) == {3: 1, 1: 2, 2: 3}


def test_one_rider_field_ranks_first():
    """USAC 2M2(f): the only rider takes every sprint and is first."""
    actions = [SprintResult(1, [[1]]), FinishOrder([[1]])]
    standings = sprint_points.compute(usac(2), [1], actions)
    assert ranks(standings) == {1: 1}
    assert standings.by_entrant(1).total_points == 15


def test_tempo_lap_gained_on_the_last_lap_scores_twenty_one():
    """USAC 2P2(c), (d), UCI 3.2.262: the final sprint is 1 point, not
    doubled, and a lap gained there adds 20 (UCI 3.2.125 via 3.2.260)."""
    rules = tempo_rules(sprint_count=3)
    actions = [SprintResult(1, [[2]]), SprintResult(2, [[2]])]
    actions += [LapGained([1], sprint_no=3), FinishOrder([[1], [2]])]
    standings = sprint_points.compute(rules, [1, 2], actions)
    assert standings.by_entrant(1).total_points == 21
    assert standings.by_entrant(1).sprint_points == (0, 0, 1)


def test_tempo_tie_broken_by_the_last_sprint_order():
    """USAC 2P2(a), UCI 3.2.260 apply the points race tie-break
    (USAC 2M2(g), UCI 3.2.119): level on 2, the better place at the line wins."""
    rules = tempo_rules(sprint_count=4)
    actions = [SprintResult(1, [[1]]), SprintResult(2, [[2]]), SprintResult(3, [[1]])]
    actions.append(FinishOrder([[2], [1]]))
    standings = sprint_points.compute(rules, [1, 2], actions)
    assert standings.by_entrant(1).total_points == standings.by_entrant(2).total_points == 2
    assert ranks(standings) == {2: 1, 1: 2}


def test_madison_team_dnf_keeps_its_points_in_the_dnf_group():
    """UCI 3.3.012 A: a team withdrawn or with a mishap keeps its points
    and ranks in the DNF group after every finishing team."""
    rules = madison_rules(sprint_count=2)
    actions = [SprintResult(1, [[30], [10]]), Status(30, "DNF", "crash")]
    actions += [SprintResult(2, [[20], [10]]), FinishOrder([[20], [10]])]
    standings = sprint_points.compute(rules, [10, 20, 30], actions)
    team = standings.by_entrant(30)
    assert (team.status, team.total_points, team.rank) == ("DNF", 5, 3)
    # 20 on 10 (the doubled final), 10 on 3 + 6, then the DNF team.
    assert ranks(standings) == {20: 1, 10: 2, 30: 3}


def test_madison_lap_gained_at_a_sprint_scores_the_lap_and_the_sprint():
    """USAC 2N3(h), UCI 3.2.167: a team that gains a lap at the moment of
    a sprint scores 20 for the lap plus its points in that sprint."""
    rules = madison_rules(sprint_count=3)
    actions = [SprintResult(1, [[10], [20]]), LapGained([10], sprint_no=1)]
    team = sprint_points.compute(rules, [10, 20], actions).by_entrant(10)
    assert team.sprint_points == (5, 0, 0)
    assert team.lap_points == 20
    assert team.total_points == 25


def test_madison_teams_level_on_points_split_by_the_final_sprint():
    """USAC 2N2(h), UCI 3.2.162: teams level on points are separated by
    their places in the final sprint, even a place that scored nothing."""
    rules = madison_rules(sprint_count=3)
    teams = [10, 20, 30, 40, 50]
    # Team 10 wins sprints 1 and 2 (10); team 20 wins the doubled final
    # (10). Team 10 is fifth in the final, outside the points.
    actions = [SprintResult(1, [[10]]), SprintResult(2, [[10]])]
    actions.append(FinishOrder([[20], [30], [40], [50], [10]]))
    standings = sprint_points.compute(rules, teams, actions)
    assert standings.by_entrant(10).total_points == standings.by_entrant(20).total_points == 10
    assert ranks(standings) == {20: 1, 10: 2, 30: 3, 40: 4, 50: 5}
    assert not standings.by_entrant(10).tied


def test_tempo_every_lap_after_the_first_four_is_a_one_point_sprint():
    """USAC 2P2(b), UCI 3.2.261: after the first four laps every lap is a
    sprint. The engine counts sprints, not laps, so a 10-lap tempo is six
    sprints, each awarding 1 to the first rider, and a seventh is refused."""
    laps = 10
    rules = tempo_rules(sprint_count=laps - 4)
    assert [rules.points_for_sprint(n) for n in range(1, 7)] == [(1,)] * 6
    actions = [SprintResult(n, [[1 + n % 2]]) for n in range(1, 6)]
    actions.append(FinishOrder([[1], [2]]))
    standings = sprint_points.compute(rules, [1, 2], actions)
    assert standings.by_entrant(1).sprint_points == (0, 1, 0, 1, 0, 1)
    assert standings.by_entrant(2).sprint_points == (1, 0, 1, 0, 1, 0)
    assert sprint_points.validate(rules, [1, 2], actions[:-1], SprintResult(7, [[1]])) == [
        "Sprint 7 is beyond the 6 sprints in this race"
    ]


def test_tempo_rulebook_points_are_exact_and_an_announced_variation_scores_as_set():
    """USAC 2P3: inside an omnium the tempo follows USAC 2P1 and 2P2
    exactly, which is the rulebook preset (1 point a sprint, final not
    doubled, 20 a lap). Outside one, a promoter may announce a variation;
    a ruleset that awards 2 a sprint scores exactly that."""
    exact = tempo_rules(sprint_count=3)
    assert (exact.intermediate_points, exact.final_points) == ((1,), (1,))
    assert (exact.lap_gained_points, exact.lap_lost_points) == (20, 20)
    announced = SprintPointsRules(sprint_count=3, intermediate_points=(2,), final_points=(2,))
    actions = [SprintResult(1, [[1]]), SprintResult(2, [[1]]), FinishOrder([[1], [2]])]
    assert sprint_points.compute(exact, [1, 2], actions).by_entrant(1).total_points == 3
    assert sprint_points.compute(announced, [1, 2], actions).by_entrant(1).total_points == 6


# ----- out of the finish: a mishap in the last kilometer ---------------------

MISHAP_LOG = [
    SprintResult(1, [[3], [1]]),
    SprintResult(2, [[3], [1]]),
    SprintResult(3, [[1], [2]]),
]


def test_out_of_finish_ranks_on_points_and_laps_held_before_the_mishap():
    """USAC 2M7(b), 2M8(a): 3 cannot return before the last kilometer and
    "shall appear in the final placings depending on the points and laps
    accumulated prior to the mishap". The entry gives the same table as
    the unmarked rider of R-POINTS-5 (the same log without it), and the
    row says why there is no final-sprint place."""
    unmarked = sprint_points.compute(
        usac(), [1, 2, 3], [*MISHAP_LOG, SprintResult(4, [[1], [2]]), FinishOrder([[1], [2]])]
    )
    marked = sprint_points.compute(
        usac(),
        [1, 2, 3],
        [*MISHAP_LOG, OutOfFinish(3), SprintResult(4, [[1], [2]]), FinishOrder([[1], [2]])],
    )
    assert ranks(marked) == ranks(unmarked) == {1: 1, 3: 2, 2: 3}
    three = marked.by_entrant(3)
    assert (three.total_points, three.status, three.final_sprint_place) == (10, None, None)
    assert three.out_of_finish and three.placed
    assert not marked.by_entrant(1).out_of_finish
    assert [r.total_points for r in marked.rows] == [r.total_points for r in unmarked.rows]
    assert marked.is_complete


def test_out_of_finish_with_a_lap_keeps_the_lap_points():
    """USAC 2M7(b): "points and laps accumulated prior to the mishap"."""
    actions = [SprintResult(1, [[2], [1]]), LapGained([3]), OutOfFinish(3), FinishOrder([[1], [2]])]
    standings = sprint_points.compute(usac(sprints=2), [1, 2, 3], actions)
    assert standings.by_entrant(3).total_points == 20
    assert ranks(standings) == {3: 1, 1: 2, 2: 3}


def test_out_of_finish_leaves_the_rider_out_of_the_field_the_finish_must_name():
    """Before the finish the rider is placed already: not in remaining_entrants,
    so the surface's final sprint completes with the others."""
    before = sprint_points.compute(usac(), [1, 2, 3], MISHAP_LOG)
    assert before.remaining_entrants == (1, 2, 3)
    after = sprint_points.compute(usac(), [1, 2, 3], [*MISHAP_LOG, OutOfFinish(3)])
    assert after.remaining_entrants == (1, 2)
    assert not after.is_complete
    # 1 holds 11 to 3's 10 going into the final sprint.
    assert after.by_entrant(3).out_of_finish and after.by_entrant(3).rank == 2


def test_out_of_finish_is_taken_only_during_the_final_sprint():
    """USAC 2M7(a), 2M7(b): the rider may still return on free laps until the
    last kilometer, so the entry waits for every earlier sprint. Then it is
    refused twice, for a rider with a status, and for one placed in the
    final sprint; the finish order may not name the rider."""
    rules = usac()
    v = sprint_points.validate
    early = MISHAP_LOG[:2]
    assert v(rules, RIDERS, early, OutOfFinish(3)) == [
        "Out of the finish applies during the final sprint; sprint 3 of 4 has not been recorded"
    ]
    assert v(rules, RIDERS, MISHAP_LOG, OutOfFinish(3)) == []
    marked = [*MISHAP_LOG, OutOfFinish(3)]
    assert v(rules, RIDERS, marked, OutOfFinish(3)) == ["Entrant 3 is already out of the finish"]
    assert v(rules, RIDERS, [*MISHAP_LOG, Status(3, "DNF")], OutOfFinish(3)) == [
        "Entrant 3 is DNF and cannot be placed"
    ]
    assert v(rules, RIDERS, marked, FinishOrder([[1], [3], [2]])) == [
        "Entrant 3 is out of the finish and cannot be placed in it"
    ]
    assert v(rules, RIDERS, marked, SprintResult(4, [[3], [1]])) == [
        "Entrant 3 is out of the finish and cannot be placed in it"
    ]
    placed = [*MISHAP_LOG, SprintResult(4, [[3], [1]])]
    assert v(rules, RIDERS, placed, OutOfFinish(3)) == ["Entrant 3 is placed in the final sprint"]
    assert v(rules, RIDERS, [*marked, FinishOrder([[1], [2]])], OutOfFinish(2)) == [
        "The finish order is already recorded; void it before entering more"
    ]
    assert v(rules, RIDERS, [], OutOfFinish(99)) == [
        "Unknown entrant 99",
        "Out of the finish applies during the final sprint; sprint 1 of 4 has not been recorded",
    ]


def test_out_of_finish_rider_may_be_disqualified_but_not_marked_dns_or_dnf():
    """USAC 2M8(a) places the rider, so DNS or DNF would contradict it; a DQ
    after a protest (USAC 1P1) still applies, and then the status wins."""
    rules = usac()
    v = sprint_points.validate
    marked = [*MISHAP_LOG, OutOfFinish(3)]
    assert v(rules, RIDERS, marked, Status(3, "DNF")) == [
        "Entrant 3 is out of the finish and placed on points; it cannot be marked DNF"
    ]
    assert v(rules, RIDERS, marked, Status(3, "DNS")) == [
        "Entrant 3 has a result and cannot be marked DNS",
        "Entrant 3 is out of the finish and placed on points; it cannot be marked DNS",
    ]
    assert v(rules, RIDERS, marked, Status(3, "DQ")) == []
    standings = sprint_points.compute(
        rules, [1, 2, 3], [*marked, FinishOrder([[1], [2]]), Status(3, "DQ")]
    )
    three = standings.by_entrant(3)
    assert (three.status, three.rank, three.out_of_finish) == ("DQ", None, False)
    assert ranks(standings) == {1: 1, 2: 2, 3: None}


def test_madison_team_out_of_finish_keeps_its_points():
    """USAC 2N6(c), 2N7(a): a team entitled to free laps in the final kilometer
    is placed on the laps and points held at the mishap."""
    rules = madison_rules(sprint_count=2)
    actions = [SprintResult(1, [[20], [10]]), OutOfFinish(20), FinishOrder([[10], [30]])]
    standings = sprint_points.compute(rules, [10, 20, 30], actions)
    # 10: 3 + 10; 30: 6 in the doubled final; 20 keeps the 5 of sprint 1.
    assert ranks(standings) == {10: 1, 30: 2, 20: 3}
    assert standings.by_entrant(20).total_points == 5
    assert standings.by_entrant(20).out_of_finish and standings.by_entrant(20).placed


def test_tempo_rider_out_of_finish_keeps_the_sprints_won():
    """USAC 2P2(a): the Points Race rules apply, 2M7(b) and 2M8(a) included."""
    rules = tempo_rules(sprint_count=3)
    actions = [
        SprintResult(1, [[2]]),
        SprintResult(2, [[2]]),
        OutOfFinish(2),
        FinishOrder([[1], [3]]),
    ]
    standings = sprint_points.compute(rules, [1, 2, 3], actions)
    assert ranks(standings) == {2: 1, 1: 2, 3: 3}
    assert standings.by_entrant(2).total_points == 2


def test_dns_is_refused_once_the_rider_has_a_result():
    """USAC 1M6(b): DNS is a rider who "fail[s] to take the start line". A
    sprint place or a lap says the rider started, so DNS is refused for
    them and still taken for a rider with nothing recorded, however far
    the race has gone."""
    rules = usac()
    v = sprint_points.validate
    actions = [SprintResult(1, [[1], [2]]), LapGained([4]), SprintResult(2, [[1]])]
    assert v(rules, RIDERS, actions, Status(1, "DNS")) == [
        "Entrant 1 has a result and cannot be marked DNS"
    ]
    assert v(rules, RIDERS, actions, Status(4, "DNS")) == [
        "Entrant 4 has a result and cannot be marked DNS"
    ]
    assert v(rules, RIDERS, actions, Status(3, "DNS")) == []
    assert v(rules, RIDERS, actions, Status(1, "DNF")) == [], "a DNF is for a rider who raced"
    standings = sprint_points.compute(rules, RIDERS, [*actions, Status(3, "DNS")])
    assert standings.by_entrant(3).status == "DNS" and standings.by_entrant(3).rank is None


# ----- the officials' rulings: a points penalty, a lap not counted ----------


def test_a_points_penalty_comes_off_the_total_and_ranks_by_it():
    """USAC 8D5(b): "loss of points"; the glossary's relegation is "a loss of
    position, points or time". Rider 1 wins both sprints (5 + 10) but loses
    10; rider 2 is second twice (3 + 6) and now leads 9 to 5."""
    actions = [
        SprintResult(1, [[1], [2]]),
        PointsAdjusted(entrant_id=1, points=-10),
        SprintResult(2, [[1], [2]]),
    ]
    standings = sprint_points.compute(usac(2), [1, 2, 3], actions)
    row = standings.by_entrant(1)
    assert row.sprint_points == (5, 10) and row.adjust_points == -10 and row.total_points == 5
    assert standings.by_entrant(2).adjust_points == 0
    assert ranks(standings) == {2: 1, 1: 2, 3: 3}


def test_a_penalty_is_taken_after_the_finish_order_and_the_race_stays_complete():
    """A ruling follows a protest (USAC 1P1), after the line; the finish
    order stops scoring entries, not rulings."""
    actions = [SprintResult(1, [[1], [2]]), FinishOrder([[1], [2], [3]])]
    rules = usac(2)
    penalty = PointsAdjusted(entrant_id=1, points=-20)
    assert sprint_points.validate(rules, [1, 2, 3], actions, penalty) == []
    standings = sprint_points.compute(rules, [1, 2, 3], [*actions, penalty])
    assert standings.is_complete
    # 1 held 5 + 10, now -5; 2 has 3 + 6 = 9 and 3 has 4: 2, 3, 1.
    assert standings.by_entrant(1).total_points == -5
    assert ranks(standings) == {2: 1, 3: 2, 1: 3}


def test_points_come_back_only_down_to_the_penalty_standing():
    """A positive PointsAdjusted lowers the penalty (the officials reversed
    it, or it went on the wrong rider); it may not exceed the penalty
    standing, so a total never rises above what the riding earned, and
    with no penalty there is nothing to give back."""
    from madtracker.scoring._common import penalty_of

    rules = usac(2)
    actions = [SprintResult(1, [[1], [2]]), PointsAdjusted(entrant_id=1, points=-5)]
    assert penalty_of(actions, 1) == 5 and penalty_of(actions, 2) == 0
    assert sprint_points.validate(
        rules, [1, 2, 3], actions, PointsAdjusted(entrant_id=2, points=5)
    ) == ["Entrant 2 has no penalty to give back"]
    assert sprint_points.validate(
        rules, [1, 2, 3], actions, PointsAdjusted(entrant_id=1, points=6)
    ) == ["Entrant 1's penalty is 5 points; 6 cannot come back"]
    lowered = PointsAdjusted(entrant_id=1, points=3)
    assert sprint_points.validate(rules, [1, 2, 3], actions, lowered) == []
    standings = sprint_points.compute(rules, [1, 2, 3], [*actions, lowered])
    assert standings.by_entrant(1).adjust_points == -2 and standings.by_entrant(1).total_points == 3
    assert penalty_of([*actions, lowered], 1) == 2
    off = PointsAdjusted(entrant_id=1, points=2)
    assert sprint_points.validate(rules, [1, 2, 3], [*actions, lowered], off) == []
    assert penalty_of([*actions, lowered, off], 1) == 0


def test_a_tie_on_total_after_a_penalty_still_breaks_by_the_final_sprint():
    """USAC 2M2(g): 1 wins sprint 1 (5) and sprint 2 (10) for 15, less 10 is
    5; 2 takes 3 + 6 = 9, less a penalty of 4, so both are on 5, and 1,
    first in the final sprint, ranks ahead."""
    actions = [
        SprintResult(1, [[1], [2]]),
        FinishOrder([[1], [2], [3]]),
        PointsAdjusted(entrant_id=1, points=-10),
        PointsAdjusted(entrant_id=2, points=-4),
    ]
    standings = sprint_points.compute(usac(2), [1, 2, 3], actions)
    assert standings.by_entrant(1).total_points == standings.by_entrant(2).total_points == 5
    assert ranks(standings) == {1: 1, 2: 2, 3: 3}
    assert not standings.by_entrant(1).tied


def test_a_penalty_on_a_dns_or_dq_rider_is_refused_and_on_a_dnf_rider_stands():
    rules = usac(2)
    marked = [
        SprintResult(1, [[1], [2], [3]]),
        Status(entrant_id=2, status="DNS"),
        Status(entrant_id=3, status="DQ"),
        Status(entrant_id=4, status="DNF"),
    ]
    assert sprint_points.validate(rules, RIDERS, marked, PointsAdjusted(2, -5)) == [
        "Entrant 2 is DNS and has no result to change"
    ]
    assert sprint_points.validate(rules, RIDERS, marked, PointsAdjusted(3, -5)) == [
        "Entrant 3 is DQ and has no result to change"
    ]
    assert sprint_points.validate(rules, RIDERS, marked, PointsAdjusted(4, -5)) == []
    assert sprint_points.validate(rules, RIDERS, marked, PointsAdjusted(1, 0)) == [
        "No points entered"
    ]
    assert sprint_points.validate(rules, RIDERS, marked, PointsAdjusted(99, -5)) == [
        "Unknown entrant 99"
    ]
    # A DNF keeps the points shown (UCI 3.3.012 A), less the penalty.
    standings = sprint_points.compute(rules, RIDERS, [*marked, PointsAdjusted(4, -5)])
    assert standings.by_entrant(4).total_points == -5 and standings.by_entrant(4).status == "DNF"


def test_a_lap_not_counted_takes_back_the_lap_and_its_points():
    """USAC 8D5(b) "loss of ... laps illegally gained", 8D5(c) and 2N3(e) for
    a relay: the gain never happened, unlike a lap lost, which is a second
    event and leaves both in the net count."""
    rules = usac(2)
    gained = [SprintResult(1, [[1], [2]]), LapGained([1])]
    before = sprint_points.compute(rules, [1, 2], gained)
    assert before.by_entrant(1).laps_gained == 1 and before.by_entrant(1).total_points == 25
    assert sprint_points.validate(rules, [1, 2], gained, LapNotCounted([1])) == []
    after = sprint_points.compute(rules, [1, 2], [*gained, LapNotCounted([1])])
    row = after.by_entrant(1)
    assert (row.laps_gained, row.laps_lost, row.net_laps, row.lap_points) == (0, 0, 0, 0)
    assert row.total_points == 5
    # The ruling is counted on the row, so the sheet can note it beside the name.
    assert row.laps_not_counted == 1 and after.by_entrant(2).laps_not_counted == 0
    # The same ride with a lap lost instead keeps both laps on the sheet.
    lost = sprint_points.compute(rules, [1, 2], [*gained, LapLost([1])]).by_entrant(1)
    assert (lost.laps_gained, lost.laps_lost, lost.net_laps, lost.lap_points) == (1, 1, 0, 0)


def test_a_lap_not_counted_with_no_lap_to_cancel_is_refused():
    rules = usac(2)
    assert sprint_points.validate(rules, [1, 2], [], LapNotCounted([1])) == [
        "Entrant 1 has no lap gained to cancel"
    ]
    one = [LapGained([1]), LapNotCounted([1])]
    assert sprint_points.validate(rules, [1, 2], one, LapNotCounted([1])) == [
        "Entrant 1 has no lap gained to cancel"
    ]
    # A lap lost is not a lap gained: nothing to cancel.
    assert sprint_points.validate(rules, [1, 2], [LapLost([1])], LapNotCounted([1])) == [
        "Entrant 1 has no lap gained to cancel"
    ]
    # Two gained, one cancelled: one left to cancel, and the floor holds
    # in a log written past the check.
    two = [LapGained([1]), LapGained([1]), LapNotCounted([1])]
    assert sprint_points.validate(rules, [1, 2], two, LapNotCounted([1])) == []
    over = [LapGained([1]), LapNotCounted([1]), LapNotCounted([1])]
    assert sprint_points.compute(rules, [1, 2], over).by_entrant(1).laps_gained == 0


def test_a_lap_not_counted_is_allowed_after_the_finish_order():
    actions = [SprintResult(1, [[1], [2]]), LapGained([2]), FinishOrder([[1], [2]])]
    assert sprint_points.validate(usac(2), [1, 2], actions, LapNotCounted([2])) == []
    standings = sprint_points.compute(usac(2), [1, 2], [*actions, LapNotCounted([2])])
    assert standings.is_complete and ranks(standings) == {1: 1, 2: 2}


def test_a_race_ended_after_eighty_percent_stands_on_the_sprints_ridden():
    """USAC 2M6, 2N5: "Race stopped after 80%: Let results stand". Two of
    three sprints ridden; the race is complete on them, with no doubled
    final sprint and no final-sprint place, so riders level on points
    share the rank (USAC 1M6(a))."""
    actions = [
        SprintResult(1, [[1], [2], [3], [4]]),
        SprintResult(2, [[2], [1], [3], [4]]),
        RaceEnded(after_sprint=2),
    ]
    standings = sprint_points.compute(usac(3), [1, 2, 3, 4], actions)
    assert standings.is_complete and standings.ended
    assert standings.remaining_entrants == ()
    assert ranks(standings) == {1: 1, 2: 1, 3: 3, 4: 4}
    assert standings.by_entrant(1).tied and standings.by_entrant(2).tied
    assert standings.by_entrant(1).sprint_points == (5, 3)
    assert standings.by_entrant(2).sprint_points == (3, 5)
    assert standings.by_entrant(1).final_sprint_place is None
    assert standings.by_entrant(3).sprint_points == (2, 2), "two columns, no empty final"


def test_a_race_ended_takes_no_more_scoring_entries_but_rulings_still_apply():
    """After the end only the officials' calls move: a DQ or a penalty
    follows a protest, while a sprint, a lap, a DNF, or a second end is
    refused until the end is undone."""
    actions = [SprintResult(1, [[1], [2], [3]]), RaceEnded(after_sprint=1)]
    rules = usac(3)
    assert sprint_points.validate(rules, RIDERS, actions, SprintResult(2, [[1]])) == [
        "The race has ended with its results standing; undo that first"
    ]
    assert sprint_points.validate(rules, RIDERS, actions, LapGained(entrant_ids=(2,))) == [
        "The race has ended with its results standing; undo that first"
    ]
    assert sprint_points.validate(rules, RIDERS, actions, Status(2, "DNF")) == [
        "Entrant 2 cannot be marked DNF after the race's end"
    ]
    assert sprint_points.validate(rules, RIDERS, actions, RaceEnded(after_sprint=1)) == [
        "The race has already ended with its results standing"
    ]
    assert sprint_points.validate(rules, RIDERS, actions, Status(2, "DQ")) == []
    assert sprint_points.validate(rules, RIDERS, actions, PointsAdjusted(1, -2)) == []


def test_ending_a_race_needs_a_sprint_and_not_a_finish():
    """Nothing stands before a sprint is ridden; once the final sprint is in
    the race is complete as ridden; and the entry names the sprint it
    stopped after, so the log reads back where the race ended."""
    rules = usac(2)
    assert sprint_points.validate(rules, RIDERS, [], RaceEnded(after_sprint=0)) == [
        "No sprint is recorded, so no result can stand"
    ]
    one = [SprintResult(1, [[1], [2]])]
    assert sprint_points.validate(rules, RIDERS, one, RaceEnded(after_sprint=2)) == [
        "The last sprint recorded is 1, not 2"
    ]
    assert sprint_points.validate(rules, RIDERS, one, RaceEnded(after_sprint=1)) == []
    two = [*one, SprintResult(2, [[2], [1]])]
    assert sprint_points.validate(usac(3), RIDERS, two, RaceEnded(after_sprint=1)) == [
        "The last sprint recorded is 2, not 1"
    ]
    assert sprint_points.validate(usac(3), RIDERS, two, RaceEnded(after_sprint=2)) == []
    done = [*one, FinishOrder([[1], [2], [3], [4], [5], [6]])]
    assert sprint_points.validate(rules, RIDERS, done, RaceEnded(after_sprint=1)) == [
        "The final sprint is recorded; the race is complete as ridden"
    ]


def test_results_stand_is_a_points_race_or_madison_entry_only():
    """USAC 2P5 restarts or reruns a stopped Tempo Race, and the other
    formats' tables say rerun or restart, so the entry is refused there."""
    from madtracker.scoring.replay import validate_for_format
    from madtracker.scoring.rules import elimination_rules, placings_rules, win_and_out_rules

    refusal = ["Only a Points Race or Madison can end early with its result as-is"]
    one = [SprintResult(1, [[1], [2]])]
    assert (
        validate_for_format("tempo", tempo_rules(sprint_count=3), RIDERS, one, RaceEnded(1))
        == refusal
    )
    assert validate_for_format("points", usac(3), RIDERS, one, RaceEnded(1)) == []
    assert (
        validate_for_format("madison", madison_rules(sprint_count=3), RIDERS, one, RaceEnded(1))
        == []
    )
    assert validate_for_format("scratch", placings_rules(), RIDERS, [], RaceEnded(0)) == refusal
    assert (
        validate_for_format("elimination", elimination_rules(), RIDERS, [], RaceEnded(0)) == refusal
    )
    assert (
        validate_for_format("win_and_out", win_and_out_rules(), RIDERS, [], RaceEnded(0)) == refusal
    )


def test_a_shortened_race_doubles_its_new_last_sprint_with_the_finish():
    """USAC 1G4(b), 2M2(f): a race set for 4 sprints and shortened to 3
    rides to a new finish. Sprint 3 is the final sprint: the finish order
    scores it doubled, the race is complete on it, and the table has the
    three columns ridden."""
    actions = [
        SprintResult(1, [[1], [2], [3], [4]]),
        SprintResult(2, [[2], [1], [3], [4]]),
        RaceShortened(sprint_count=3),
    ]
    rules = usac(4)
    running = sprint_points.compute(rules, [1, 2, 3, 4], actions)
    assert running.sprint_count == 3 and not running.is_complete
    assert running.by_entrant(1).sprint_points == (5, 3, 0)
    done = sprint_points.compute(rules, [1, 2, 3, 4], [*actions, FinishOrder([[3], [4], [1], [2]])])
    assert done.is_complete and done.sprint_count == 3 and not done.ended
    assert done.by_entrant(3).sprint_points == (2, 2, 10)
    assert done.by_entrant(4).sprint_points == (1, 1, 6)
    assert done.by_entrant(1).sprint_points == (5, 3, 4)
    assert done.by_entrant(2).sprint_points == (3, 5, 2)
    assert done.by_entrant(3).final_sprint_place == 1


def test_a_shortened_race_breaks_a_tie_on_its_new_final_sprint():
    """USAC 2M2(g): riders level on points are split by the final sprint,
    which in a shortened race is the last sprint under the new count."""
    actions = [
        SprintResult(1, [[1], [2]]),
        RaceShortened(sprint_count=2),
        FinishOrder([[2], [1], [3]]),
    ]
    standings = sprint_points.compute(usac(4), [1, 2, 3], actions)
    assert standings.by_entrant(1).total_points == 11
    assert standings.by_entrant(2).total_points == 13
    level = [
        SprintResult(1, [[1], [2], [3]]),
        RaceShortened(sprint_count=2),
        FinishOrder([[3], [2], [1]]),
    ]
    standings = sprint_points.compute(points_race_rules(sprint_count=4), [1, 2, 3], level)
    # 1: 5 + 4 = 9; 2: 3 + 6 = 9; 3: 2 + 10 = 12. Rider 2 beat rider 1 in
    # the new final, so takes 2nd on the tie.
    assert ranks(standings) == {3: 1, 2: 2, 1: 3}
    assert not standings.by_entrant(1).tied


def test_a_second_shortening_lowers_the_count_again():
    """The latest entry is the count in force."""
    actions = [SprintResult(1, [[1], [2]]), RaceShortened(4), RaceShortened(3)]
    standings = sprint_points.compute(usac(5), [1, 2], actions)
    assert standings.sprint_count == 3
    assert len(standings.by_entrant(1).sprint_points) == 3
    assert sprint_points.validate(usac(5), [1, 2], actions, SprintResult(4, [[1]])) == [
        "Sprint 4 is beyond the 3 sprints in this race"
    ]
    assert sprint_points.validate(usac(5), [1, 2], actions, RaceShortened(2)) == []


def test_the_count_in_force_is_the_rules_count_until_a_shortening():
    assert sprint_points.compute(usac(4), [1, 2], []).sprint_count == 4
    assert sprint_points.compute(SprintPointsRules(), [1, 2], []).sprint_count is None


def test_a_shortened_race_takes_its_finish_once_the_sprints_before_the_new_final_are_in():
    """The finish order is the final sprint; under the new count it needs
    only the sprints before the new final."""
    actions = [SprintResult(1, [[1], [2]]), SprintResult(2, [[2], [1]])]
    finish = FinishOrder([[1], [2]])
    assert sprint_points.validate(usac(4), [1, 2], actions, finish) == [
        "Sprint 3 of 4 has not been recorded"
    ]
    shortened = [*actions, RaceShortened(3)]
    assert sprint_points.validate(usac(4), [1, 2], shortened, finish) == []
    assert sprint_points.validate(usac(4), [1, 2], shortened, SprintResult(3, [[1]])) == []


def test_shortening_is_below_the_count_and_above_every_sprint_ridden():
    """A count at or below the sprints ridden is a race stopped, which is
    End Race's entry; at or above the count in force is no shortening."""
    two = [SprintResult(1, [[1], [2]]), SprintResult(2, [[2], [1]])]
    rules = usac(4)
    assert sprint_points.validate(rules, RIDERS, two, RaceShortened(4)) == [
        "The race has 4 sprints; shorten it to fewer"
    ]
    assert sprint_points.validate(rules, RIDERS, two, RaceShortened(5)) == [
        "The race has 4 sprints; shorten it to fewer"
    ]
    assert sprint_points.validate(rules, RIDERS, two, RaceShortened(2)) == [
        "Sprint 2 is recorded; shorten to at least Sprint 3"
    ]
    assert sprint_points.validate(rules, RIDERS, two, RaceShortened(1)) == [
        "Sprint 2 is recorded; shorten to at least Sprint 3"
    ]
    assert sprint_points.validate(rules, RIDERS, two, RaceShortened(3)) == []
    assert sprint_points.validate(rules, RIDERS, [], RaceShortened(0)) == [
        "A race has at least one sprint"
    ]
    assert sprint_points.validate(rules, RIDERS, [], RaceShortened(1)) == []
    assert sprint_points.validate(SprintPointsRules(), RIDERS, [], RaceShortened(1)) == [
        "This race has no sprint count"
    ]


def test_shortening_is_refused_once_the_finish_is_in_or_the_race_ended():
    rules = usac(3)
    done = [SprintResult(1, [[1], [2]]), FinishOrder([[1], [2], [3], [4], [5], [6]])]
    assert sprint_points.validate(usac(2), RIDERS, done, RaceShortened(1)) == [
        "The final sprint is recorded; the race is complete as ridden"
    ]
    final_in = [SprintResult(1, [[1]]), SprintResult(2, [[2]]), SprintResult(3, [[3]])]
    assert sprint_points.validate(rules, RIDERS, final_in[:2], RaceShortened(2)) == [
        "Sprint 2 is recorded; shorten to at least Sprint 3"
    ]
    assert sprint_points.validate(usac(4), RIDERS, final_in, RaceShortened(3)) == [
        "Sprint 3 is recorded; shorten to at least Sprint 4"
    ]
    shortened_final = [*final_in[:2], RaceShortened(3), final_in[2]]
    assert sprint_points.validate(usac(5), RIDERS, shortened_final, RaceShortened(3)) == [
        "The final sprint is recorded; the race is complete as ridden"
    ]
    ended = [SprintResult(1, [[1]]), RaceEnded(after_sprint=1)]
    assert sprint_points.validate(rules, RIDERS, ended, RaceShortened(2)) == [
        "The race has ended with its results standing; undo that first"
    ]


def test_a_shortened_race_may_still_end_with_its_results_standing():
    """A shortened race stopped again after 80 percent (USAC 2M6): the
    sprints ridden stand, with no doubled final."""
    actions = [SprintResult(1, [[1], [2]]), RaceShortened(3), SprintResult(2, [[2], [1]])]
    assert sprint_points.validate(usac(4), [1, 2], actions, RaceEnded(after_sprint=2)) == []
    standings = sprint_points.compute(usac(4), [1, 2], [*actions, RaceEnded(after_sprint=2)])
    assert standings.ended and standings.by_entrant(1).sprint_points == (5, 3)


def test_a_shortened_tempo_race_finishes_sooner_and_keeps_its_points():
    """USAC 2P2: every sprint is one point to the winner, the final one
    too; shortened, the race's finish is the new last sprint."""
    actions = [SprintResult(1, [[1]]), SprintResult(2, [[2]]), RaceShortened(3)]
    rules = tempo_rules(sprint_count=5)
    standings = sprint_points.compute(rules, [1, 2, 3], [*actions, FinishOrder([[3], [1], [2]])])
    assert standings.is_complete and standings.sprint_count == 3
    assert standings.by_entrant(3).sprint_points == (0, 0, 1)
    assert ranks(standings) == {3: 1, 1: 2, 2: 3}


def test_shorten_race_is_a_sprint_points_entry_only():
    """Scratch, Elimination, and Win-and-Out carry no sprint count, so a
    shortened one is entered as it is ridden and the entry is refused."""
    from madtracker.scoring.replay import SHORTEN_FORMATS, validate_for_format
    from madtracker.scoring.rules import elimination_rules, placings_rules, win_and_out_rules

    refusal = ["Shorten Race is scored in a Points Race, Madison, or Tempo Race only"]
    assert {"points", "madison", "tempo"} <= SHORTEN_FORMATS
    assert not {"scratch", "elimination", "win_and_out"} & SHORTEN_FORMATS
    one = [SprintResult(1, [[1], [2]])]
    shorten = RaceShortened(2)
    assert validate_for_format("tempo", tempo_rules(sprint_count=3), RIDERS, one, shorten) == []
    assert validate_for_format("points", usac(3), RIDERS, one, shorten) == []
    assert validate_for_format("madison", madison_rules(sprint_count=3), RIDERS, one, shorten) == []
    assert validate_for_format("scratch", placings_rules(), RIDERS, [], shorten) == refusal
    assert validate_for_format("elimination", elimination_rules(), RIDERS, [], shorten) == refusal
    assert validate_for_format("win_and_out", win_and_out_rules(), RIDERS, [], shorten) == refusal
    from madtracker.scoring import elimination, placings, win_and_out

    assert placings.validate(placings_rules(), RIDERS, [], shorten) == refusal
    assert elimination.validate(elimination_rules(), RIDERS, [], shorten) == refusal
    assert win_and_out.validate(win_and_out_rules(), RIDERS, [], shorten) == refusal


def test_withdrawn_riders_rank_after_every_finisher_by_the_moment_latest_highest():
    """USAC 2O3(e): a withdrawn rider "will be allocated the next available
    rank determined by the number of riders remaining on the track at this
    moment", so of two withdrawn the later ranks higher, whatever their
    points. 2 won sprint 1 and was withdrawn first; 3 won nothing and was
    withdrawn later. The points stay as figures and the rows print a number
    (R-OMNI-5, R-NF-3)."""
    rules = tempo_rules(sprint_count=4)
    actions = [
        SprintResult(1, [[2]]),
        Withdrawn(2),
        SprintResult(2, [[1]]),
        Withdrawn(3),
        SprintResult(3, [[4]]),
        FinishOrder([[4], [1]]),
    ]
    standings = sprint_points.compute(rules, [1, 2, 3, 4], actions)
    assert ranks(standings) == {4: 1, 1: 2, 3: 3, 2: 4}
    two, three = standings.by_entrant(2), standings.by_entrant(3)
    assert two.withdrawn and three.withdrawn and two.placed and three.placed
    assert (two.status, two.total_points, two.tied) == (None, 1, False)
    assert three.total_points == 0
    assert not standings.by_entrant(1).withdrawn
    assert standings.is_complete


def test_a_withdrawn_rider_holds_the_rank_from_the_moment_on_before_the_finish():
    """USAC 2O3(e): the rank is the moment's, so it shows while the race runs:
    with four still racing the withdrawn rider is 5th. The finish order
    names the field without them."""
    actions = [SprintResult(1, [[1], [2]]), Withdrawn(5)]
    standings = sprint_points.compute(usac(), [1, 2, 3, 4, 5], actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 3, 5: 5}
    assert standings.remaining_entrants == (1, 2, 3, 4)
    assert not standings.is_complete


def test_a_withdrawn_rider_takes_no_later_entry_and_no_status_but_a_dq():
    """USAC 2O3(e): classified from the moment, so no later sprint, lap, or
    finish names the rider, and a second entry would move the moment. The
    rule places them, so DNS and DNF are refused; a DQ after a protest
    (USAC 1P1) applies and wins. A ruling on points still reaches the row."""
    rules = usac()
    v = sprint_points.validate
    log = [SprintResult(1, [[3], [1]]), Withdrawn(3)]
    assert v(rules, RIDERS, log, SprintResult(2, [[3], [2]])) == [
        "Entrant 3 is withdrawn and cannot be placed"
    ]
    assert v(rules, RIDERS, log, LapGained([3])) == ["Entrant 3 is withdrawn and cannot be placed"]
    assert v(rules, RIDERS, log, Withdrawn(3)) == ["Entrant 3 is already withdrawn"]
    assert v(rules, RIDERS, log, Status(3, "DNF")) == [
        "Entrant 3 is withdrawn and placed by the rule; it cannot be marked DNF"
    ]
    assert v(rules, RIDERS, log, Status(3, "DNS")) == [
        "Entrant 3 has a result and cannot be marked DNS",
    ]
    assert v(rules, RIDERS, log, Status(3, "DQ")) == []
    assert v(rules, RIDERS, log, PointsAdjusted(3, -2)) == []
    full = [*log, SprintResult(2, [[1], [2]]), SprintResult(3, [[1], [2]])]
    assert v(rules, RIDERS, full, FinishOrder([[1], [2], [3]])) == [
        "Entrant 3 is withdrawn and cannot be placed"
    ]
    standings = sprint_points.compute(
        rules, [1, 2, 3], [*full, FinishOrder([[1], [2]]), Status(3, "DQ")]
    )
    three = standings.by_entrant(3)
    assert (three.status, three.rank, three.withdrawn) == ("DQ", None, False)


def test_withdrawn_and_out_of_the_finish_exclude_each_other():
    """USAC 2M8(a) places a rider out of the finish on points; USAC 2O3(e)
    places a withdrawn rider by the moment. One rider takes one of them."""
    rules = usac()
    v = sprint_points.validate
    assert v(rules, RIDERS, [*MISHAP_LOG, OutOfFinish(3)], Withdrawn(3)) == [
        "Entrant 3 is out of the finish and placed on points"
    ]
    assert v(rules, RIDERS, [*MISHAP_LOG, Withdrawn(3)], OutOfFinish(3)) == [
        "Entrant 3 is withdrawn and cannot be placed"
    ]


def test_a_withdrawn_rider_ranks_below_a_rider_out_of_the_finish_and_above_the_dnf_group():
    """A rider out of the finish is a finisher on points (USAC 2M8(a)); a
    withdrawn rider follows every finisher (USAC 2O3(e)); a DNF is not
    placed (USAC 2M8(a)) and is listed after them."""
    actions = [
        SprintResult(1, [[4], [3]]),
        Withdrawn(4),
        SprintResult(2, [[1], [2]]),
        SprintResult(3, [[1], [2]]),
        OutOfFinish(3),
        Status(5, "DNF"),
        FinishOrder([[2], [1]]),
    ]
    standings = sprint_points.compute(usac(), [1, 2, 3, 4, 5], actions)
    assert [r.entrant_id for r in standings.rows] == [2, 1, 3, 4, 5]
    assert ranks(standings) == {2: 1, 1: 2, 3: 3, 4: 4, 5: 5}
    assert standings.by_entrant(5).status == "DNF"
    assert standings.by_entrant(4).placed and not standings.by_entrant(5).placed


def test_madison_team_withdrawn_is_placed_by_the_moment_with_its_points_as_figures():
    """USAC 1M6(d) through 2N: a team the Chief Referee has placed when
    withdrawn ranks after the finishing teams, its points and laps kept."""
    rules = madison_rules(sprint_count=2)
    actions = [
        SprintResult(1, [[20], [10]]),
        LapGained([20]),
        Withdrawn(20),
        FinishOrder([[30], [10]]),
    ]
    standings = sprint_points.compute(rules, [10, 20, 30], actions)
    assert ranks(standings) == {30: 1, 10: 2, 20: 3}
    twenty = standings.by_entrant(20)
    assert twenty.withdrawn and twenty.placed and twenty.laps_gained == 1
    assert twenty.total_points == 5 + rules.lap_gained_points
