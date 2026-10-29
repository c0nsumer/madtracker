"""Elimination race rules: UCI 3.2.218 to 3.2.226, USAC 2E."""

from madtracker.scoring import elimination
from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    LapGained,
    OutOfFinish,
    SprintResult,
    Status,
    Withdrawn,
)
from madtracker.scoring.rules import EliminationRules, elimination_rules

RIDERS = [1, 2, 3, 4, 5, 6]


def ranks(standings):
    return {row.entrant_id: row.rank for row in standings.rows}


def test_eliminated_riders_placed_in_reverse_order():
    """UCI 3.2.223bis, USAC 2E3(e): the first rider out is placed last."""
    actions = [
        Eliminated(1, [6]),
        Eliminated(2, [5]),
        Eliminated(3, [4]),
        Eliminated(4, [3]),
        FinishOrder([[1], [2]]),
    ]
    standings = elimination.compute(elimination_rules(), RIDERS, actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
    assert standings.by_entrant(6).eliminated_at == 1
    assert standings.is_complete


def test_green_flag_eliminates_nobody():
    """UCI 3.2.223, USAC 2E3(d)(iii): no decision in time, nobody goes out."""
    actions = [Eliminated(1, [6]), Eliminated(2, []), Eliminated(3, [5])]
    standings = elimination.compute(elimination_rules(), RIDERS, actions)
    assert standings.remaining_entrants == (1, 2, 3, 4)
    assert standings.next_sprint_no == 4
    assert standings.by_entrant(6).rank == 6
    assert standings.by_entrant(5).rank == 5


def test_several_out_at_one_sprint_share_a_place():
    """UCI 3.2.223, USAC 2E3(d)(iii): one entry can name several riders the
    officials put out together, and they share the place."""
    actions = [
        Eliminated(1, [6]),
        Eliminated(2, [4, 5]),
        Eliminated(3, [3]),
        FinishOrder([[2], [1]]),
    ]
    standings = elimination.compute(elimination_rules(), RIDERS, actions)
    assert ranks(standings) == {2: 1, 1: 2, 3: 3, 4: 4, 5: 4, 6: 6}
    assert standings.by_entrant(4).tied and standings.by_entrant(5).tied


def test_survivors_placed_by_final_sprint():
    """UCI 3.2.224, USAC 2E3(f): the last two sprint for the win."""
    actions = [Eliminated(1, [3]), FinishOrder([[2], [1]])]
    standings = elimination.compute(elimination_rules(), [1, 2, 3], actions)
    assert ranks(standings) == {2: 1, 1: 2, 3: 3}
    assert standings.by_entrant(2).final_sprint_place == 1


def test_miss_and_out_to_three_survivors():
    """USAC 2E5: ride to N survivors, then a sprint judged on front wheels."""
    rules = elimination_rules(survivors=3)
    actions = [Eliminated(1, [6]), Eliminated(2, [5]), Eliminated(3, [4])]
    standings = elimination.compute(rules, RIDERS, actions)
    assert not standings.is_complete
    assert standings.remaining_entrants == (1, 2, 3)
    assert standings.by_entrant(4).rank == 4
    standings = elimination.compute(rules, RIDERS, actions + [FinishOrder([[3], [1], [2]])])
    assert ranks(standings) == {3: 1, 1: 2, 2: 3, 4: 4, 5: 5, 6: 6}


def test_last_rider_standing_wins_without_a_final_sprint():
    rules = EliminationRules(survivors=1, final_by_sprint=False)
    actions = [Eliminated(1, [3]), Eliminated(2, [2])]
    standings = elimination.compute(rules, [1, 2, 3], actions)
    assert standings.is_complete
    assert ranks(standings) == {1: 1, 2: 2, 3: 3}


def test_mid_race_ranks_count_down_from_the_field():
    """With 6 riders and 2 out, the last one out is 5th and 4 are still in."""
    actions = [Eliminated(1, [6]), Eliminated(2, [5])]
    standings = elimination.compute(elimination_rules(), RIDERS, actions)
    assert [r.entrant_id for r in standings.rows[:4]] == [1, 2, 3, 4]
    assert all(r.rank is None for r in standings.rows[:4])
    assert standings.by_entrant(5).rank == 5
    assert standings.by_entrant(6).rank == 6


def test_dnf_rider_is_out_at_that_moment_and_placed():
    """USAC 2E3(d)(i), 2E4(a)(ii), 2E4(d), UCI 3.2.223: a rider who leaves
    the race is eliminated, not DNF in the USAC 1M6 sense, so the row is
    placed in the reverse order of elimination, below whoever goes out
    next. A DNF before the first bell is the first rider out: last."""
    actions = [
        Status(4, "DNF", "crash"),
        Eliminated(1, [6]),
        Eliminated(2, [5]),
        Eliminated(3, [3]),
    ]
    standings = elimination.compute(
        elimination_rules(), RIDERS, actions + [FinishOrder([[1], [2]])]
    )
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 5: 4, 6: 5, 4: 6}
    row = standings.by_entrant(4)
    assert (row.status, row.eliminated_at, row.tied, row.placed) == ("DNF", 1, False, True)
    assert len(standings.rows) == len(RIDERS)


def test_dnf_after_the_last_sprint_ranks_right_behind_the_survivors():
    """USAC 2E4(d): the rider is the next one out, so they place after the
    survivors and ahead of the field."""
    actions = [Eliminated(1, [6]), Eliminated(2, [5]), Eliminated(3, [3]), Status(4, "DNF")]
    standings = elimination.compute(elimination_rules(), RIDERS, actions)
    assert not standings.is_complete
    assert ranks(standings) == {1: None, 2: None, 4: 3, 3: 4, 5: 5, 6: 6}
    standings = elimination.compute(
        elimination_rules(), RIDERS, actions + [FinishOrder([[2], [1]])]
    )
    assert ranks(standings) == {2: 1, 1: 2, 4: 3, 3: 4, 5: 5, 6: 6}


def test_status_on_a_rider_already_out_gives_one_row():
    """UCI 3.2.223: an eliminated rider who stays on the track may be
    disqualified. The DQ row replaces the placed row (USAC 1M6: a DQ is not
    placed) and the others move up; a DNF on a rider already out only adds
    the mark. Either way the rider appears once."""
    actions = [Eliminated(1, [6]), Eliminated(2, [5]), Status(6, "DQ", "stayed on track")]
    standings = elimination.compute(elimination_rules(), RIDERS, actions)
    assert [r.entrant_id for r in standings.rows].count(6) == 1
    assert ranks(standings) == {1: None, 2: None, 3: None, 4: None, 5: 5, 6: None}
    assert standings.by_entrant(6).status == "DQ"

    actions = [Eliminated(1, [6]), Status(6, "DNF", "crash")]
    standings = elimination.compute(elimination_rules(), RIDERS, actions)
    assert [r.entrant_id for r in standings.rows].count(6) == 1
    row = standings.by_entrant(6)
    assert (row.rank, row.status, row.eliminated_at, row.placed) == (6, "DNF", 1, True)


def test_a_later_status_takes_the_place_a_dnf_gave_back():
    """USAC 1M6, UCI 3.2.223: a later status replaces an earlier one, and a
    DQ, DNS, or DNP is never placed. A rider the DNF put out between bells
    who is then marked DQ, DNS, or DNP holds no place, and the others are
    placed as if the DNF had never been marked."""
    before = [Eliminated(1, [6]), Status(4, "DNF", "crash"), Eliminated(2, [5])]
    after = [Eliminated(3, [3]), FinishOrder([[2], [1]])]
    for later in ("DQ", "DNS", "DNP"):
        standings = elimination.compute(
            elimination_rules(), RIDERS, [*before, Status(4, later), *after]
        )
        assert ranks(standings) == {2: 1, 1: 2, 3: 3, 5: 4, 6: 5, 4: None}, later
        row = standings.by_entrant(4)
        assert (row.status, row.eliminated_at, row.placed) == (later, None, False), later
        assert [r.entrant_id for r in standings.rows].count(4) == 1
        unmarked = [Eliminated(1, [6]), Eliminated(2, [5]), Status(4, later), *after]
        assert standings == elimination.compute(elimination_rules(), RIDERS, unmarked), later


def test_lap_gains_do_not_count():
    """UCI 3.2.225, USAC 2E3(g)."""
    rules = elimination_rules()
    problems = elimination.validate(rules, RIDERS, [], LapGained([1]))
    assert any("Laps do not count" in p for p in problems)


def test_validate_rejects_the_usual_slips():
    rules = elimination_rules()
    actions = [Eliminated(1, [6]), Eliminated(2, [5])]
    v = elimination.validate
    assert any("already eliminated" in p for p in v(rules, RIDERS, actions, Eliminated(3, [6])))
    assert any("before the last" in p for p in v(rules, RIDERS, actions, Eliminated(1, [4])))
    assert v(rules, RIDERS, actions, Eliminated(3, [99])) == ["Unknown entrant 99"]
    assert any("leave nobody" in p for p in v(rules, RIDERS, actions, Eliminated(3, [1, 2, 3, 4])))
    assert any("not scored" in p for p in v(rules, RIDERS, actions, SprintResult(1, [[1]])))
    assert any("still in" in p for p in v(rules, RIDERS, actions, FinishOrder([[1], [2]])))
    assert any("was eliminated" in p for p in v(rules, RIDERS, actions, FinishOrder([[6], [2]])))
    assert v(rules, RIDERS, actions, Eliminated(3, [])) == []
    assert v(rules, RIDERS, actions, Eliminated(3, [4, 3])) == []
    done = actions + [Eliminated(3, [4]), Eliminated(4, [3])]
    assert v(rules, RIDERS, done, FinishOrder([[2], [1]])) == []


def test_dnf_with_four_or_fewer_left_is_out_at_that_moment():
    """UCI 3.2.226, USAC 2E4(d): with four or fewer riders left there is no
    neutralization and a rider who does not finish is eliminated at that
    moment, so it places below the next rider out instead of sharing. The
    sheet prints the number, not DNF."""
    actions = [
        Eliminated(1, [5]),
        Status(4, "DNF", "crash"),
        Eliminated(2, [3]),
        FinishOrder([[1], [2]]),
    ]
    standings = elimination.compute(elimination_rules(), [1, 2, 3, 4, 5], actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    assert standings.by_entrant(4).status == "DNF"
    assert not standings.by_entrant(4).tied
    assert standings.by_entrant(4).placed
    assert [r.placed for r in standings.rows] == [True] * 5


def test_two_out_at_one_bell_share_and_a_dnf_after_them_is_the_next_out():
    """UCI 3.2.223, USAC 2E3(d)(i), 2E4(a)(ii): two out at one bell share a
    place; a rider who leaves with six left is out at that moment, in a
    group of their own, so the next bell's rider places above them. (The
    book's abandon-by-choice reading would have them share the next
    sprint's place; the program takes the mishap reading for every DNF,
    docs/scoring-rules.md "Where the program decides".)"""
    riders = [1, 2, 3, 4, 5, 6, 7, 8]
    actions = [
        Eliminated(1, [8, 7]),
        Status(6, "DNF", "mechanical"),
        Eliminated(2, [5]),
        Eliminated(3, [4]),
        Eliminated(4, [3]),
        FinishOrder([[1], [2]]),
    ]
    standings = elimination.compute(elimination_rules(), riders, actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 7}


def test_final_sprint_dead_heat_shares_first():
    """USAC 1M6(a): a group the judges cannot separate shares the place.
    USAC 1M4(b) has a dead heat for first re-ridden; the scorer records the
    re-ride by voiding this finish order and entering the new one."""
    actions = [Eliminated(1, [3]), FinishOrder([[1, 2]])]
    standings = elimination.compute(elimination_rules(), [1, 2, 3], actions)
    assert ranks(standings) == {1: 1, 2: 1, 3: 3}
    assert standings.by_entrant(1).tied


def test_dnf_after_dns_is_refused_so_a_no_show_never_takes_a_place():
    """USAC 1M6(b): a rider who never started cannot leave the race, so the
    DNF that would put them out at that moment, and give them a place, is
    refused; a wrong DNS is undone instead."""
    actions = [Status(2, "DNS"), Eliminated(1, [3])]
    assert elimination.validate(elimination_rules(), [1, 2, 3], actions, Status(2, "DNF")) == [
        "Entrant 2 is DNS and never started; it cannot be marked DNF"
    ]


def test_out_of_finish_is_not_scored_in_an_elimination():
    """USAC 2E4(a)(ii): a rider who cannot rejoin is eliminated at that
    moment, which the scorer records as DNF; the points-race entry is refused."""
    rules = EliminationRules()
    assert elimination.validate(rules, RIDERS, [], OutOfFinish(1)) == [
        "Out of the finish is scored in a Points Race, Madison, or Tempo Race only"
    ]


def test_a_no_show_found_after_riders_are_out_is_dns_and_the_places_close_up():
    """USAC 1M6(b), 2E3(e): 6 and 5 are out when 4 is found never to have
    started. 4 is DNS, never placed, and the riders out take the places
    counted from the three who did start: 5 is 3rd, 6 is 4th. DNS is
    refused for 6, who has an elimination recorded."""
    rules = EliminationRules()
    actions = [Eliminated(1, [6]), Eliminated(2, [5])]
    v = elimination.validate
    assert v(rules, RIDERS, actions, Status(4, "DNS")) == []
    assert v(rules, RIDERS, actions, Status(6, "DNS")) == [
        "Entrant 6 has a result and cannot be marked DNS"
    ]
    standings = elimination.compute(
        rules, [1, 2, 3, 4, 5, 6], [*actions, Status(4, "DNS"), Eliminated(3, [3])]
    )
    assert standings.remaining_entrants == (1, 2)
    assert [(r.entrant_id, r.rank, r.status) for r in standings.rows] == [
        (1, None, None),
        (2, None, None),
        (3, 3, None),
        (5, 4, None),
        (6, 5, None),
        (4, None, "DNS"),
    ]
    done = elimination.compute(
        rules, [1, 2, 3, 4, 5, 6], [*actions, Status(4, "DNS"), FinishOrder([[2], [1], [3]])]
    )
    assert [(r.entrant_id, r.rank) for r in done.rows] == [
        (2, 1), (1, 2), (3, 3), (5, 4), (6, 5), (4, None)
    ]  # fmt: skip


def test_withdrawn_is_not_scored_in_an_elimination():
    """USAC 2E4(a)(ii), 2E4(d): a rider who leaves is eliminated at that
    moment and clicked out; the placing entry of 2O3(e) is refused."""
    assert elimination.validate(EliminationRules(), RIDERS, [], Withdrawn(1)) == [
        "Withdrawn is scored in a race placed at the line, a Points Race, a Madison,"
        " or a Tempo Race only"
    ]
