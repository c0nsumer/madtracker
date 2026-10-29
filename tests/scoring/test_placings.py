"""Placings engine: scratch, chase, chariot and finals ranked at the line."""

from madtracker.scoring import placings
from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    LapNotCounted,
    OutOfFinish,
    PointsAdjusted,
    SprintResult,
    Status,
    Withdrawn,
)
from madtracker.scoring.replay import compute_for_format
from madtracker.scoring.rules import PlacingsRules, placings_rules

RIDERS = [1, 2, 3, 4, 5]


def ranks(standings):
    return {row.entrant_id: row.rank for row in standings.rows}


def test_laps_gained_sort_ahead_of_finish_order():
    """USAC 2C5, UCI 3.2.178: a rider a lap up wins even if last across the line."""
    actions = [LapGained([5]), FinishOrder([[1], [2], [3], [4], [5]])]
    standings = placings.compute(placings_rules(), RIDERS, actions)
    assert ranks(standings) == {5: 1, 1: 2, 2: 3, 3: 4, 4: 5}
    assert standings.by_entrant(5).final_sprint_place == 5


def test_usac_lapped_rider_who_stays_is_placed_by_laps_down():
    """USAC 2C4: not removed, so placed by laps down then finish position."""
    actions = [LapLost([2]), FinishOrder([[2], [1], [3], [4], [5]])]
    standings = placings.compute(placings_rules(), RIDERS, actions)
    assert ranks(standings) == {1: 1, 3: 2, 4: 3, 5: 4, 2: 5}
    assert standings.by_entrant(2).status is None


def test_uci_lapped_rider_ranks_with_the_withdrawn():
    """UCI 3.2.177: a lapped rider must leave; if recorded, DNF after the finishers."""
    actions = [LapLost([2]), FinishOrder([[2], [1], [3], [4], [5]])]
    rules = PlacingsRules(lapped_riders_placed_by_laps=False)
    standings = placings.compute(rules, RIDERS, actions)
    two = standings.by_entrant(2)
    assert two.status == "DNF" and two.rank == 5
    assert "3.2.177" in two.notes[0]


def test_chariot_ignores_laps():
    """A chariot or keirin final is the line only; no lap can be gained."""
    rules = PlacingsRules(laps_count_for_ranking=False)
    actions = [LapGained([5]), FinishOrder([[1], [2], [3], [4], [5]])]
    standings = placings.compute(rules, RIDERS, actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


def test_group_the_judges_cannot_separate_shares_a_rank():
    """USAC 1M6(a): a tied inner list shares its place, the next place is skipped."""
    actions = [FinishOrder([[1], [2, 3], [4]])]
    standings = placings.compute(placings_rules(), [1, 2, 3, 4], actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 2, 4: 4}
    assert standings.by_entrant(2).tied


def test_riders_left_out_of_the_finish_order_share_the_next_rank():
    """USAC 1M6(a): the judges place as many as they can; the rest place equally."""
    actions = [FinishOrder([[1], [2]])]
    standings = placings.compute(placings_rules(), RIDERS, actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 3, 5: 3}
    assert "Shared place" in standings.by_entrant(3).notes[0]


def test_non_finishers_follow_the_finishers():
    """UCI 3.3.012 A: DNF group ranked next; DQ and DNS unranked, listed last."""
    actions = [
        Status(3, "DNF", "mishap"),
        Status(4, "DQ", "dangerous riding"),
        Status(5, "DNS"),
        FinishOrder([[1], [2]]),
    ]
    standings = placings.compute(placings_rules(), RIDERS, actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: None, 5: None}
    assert [r.entrant_id for r in standings.rows] == [1, 2, 3, 4, 5]


def test_before_the_finish_everyone_is_unranked_and_remaining():
    standings = placings.compute(placings_rules(), RIDERS, [LapGained([1])])
    assert not standings.is_complete
    assert standings.remaining_entrants == (1, 2, 3, 4, 5)
    assert all(r.rank is None for r in standings.rows)
    assert standings.by_entrant(1).laps_gained == 1


def test_validate_rejects_sprints_eliminations_and_a_second_finish():
    rules = placings_rules()
    v = placings.validate
    assert any("not scored" in p for p in v(rules, RIDERS, [], SprintResult(1, [[1]])))
    assert any("not scored" in p for p in v(rules, RIDERS, [], Eliminated(1, [1])))
    done = [FinishOrder([[1], [2]])]
    assert any("already recorded" in p for p in v(rules, RIDERS, done, FinishOrder([[2], [1]])))
    assert v(rules, RIDERS, [], FinishOrder([[1], [2], [3]])) == []
    assert v(rules, RIDERS, [], FinishOrder([])) == ["The finish order is empty"]
    assert v(rules, RIDERS, [Status(2, "DNS")], FinishOrder([[2]])) == [
        "Entrant 2 is DNS and cannot be placed"
    ]


def test_lapped_gained_and_dq_after_the_line_under_both_switches():
    """USAC 2C4, 2C5, UCI 3.2.177, 3.2.178, USAC 1M6: 2 gained a lap and
    wins from second across the line; 1 crossed first and is DQ'd on
    protest, so is not placed and the rest move up. 5 is a lap down:
    placed last by laps down under USAC 2C4, or the DNF group under the
    UCI switch, which takes the same next rank (UCI 3.3.012 A)."""
    actions = [
        LapGained([2]),
        LapLost([5]),
        FinishOrder([[5], [1], [2], [3], [4]]),
        Status(1, "DQ", "protest upheld"),
    ]
    usac = placings.compute(placings_rules(), RIDERS, actions)
    assert ranks(usac) == {2: 1, 3: 2, 4: 3, 5: 4, 1: None}
    assert usac.by_entrant(5).status is None
    uci = placings.compute(PlacingsRules(lapped_riders_placed_by_laps=False), RIDERS, actions)
    assert ranks(uci) == {2: 1, 3: 2, 4: 3, 5: 4, 1: None}
    assert uci.by_entrant(5).status == "DNF"
    assert uci.by_entrant(1).status == "DQ"


def test_dead_heat_for_first_is_a_shared_first_until_re_ridden():
    """USAC 1M4(b): a dead heat for first is re-ridden and the re-ride
    decides the place. The engine has no re-ride input: until the re-ride
    is entered the two share first (USAC 1M6(a)), and the scorer enters
    the re-ride by voiding this finish order and entering the new one,
    which the engine then scores on its own."""
    heat = [FinishOrder([[1, 2], [3]])]
    standings = placings.compute(placings_rules(), [1, 2, 3], heat)
    assert ranks(standings) == {1: 1, 2: 1, 3: 3}
    assert standings.by_entrant(1).tied and standings.by_entrant(2).tied
    # The void leaves only the re-entered order in the live log.
    re_ridden = [FinishOrder([[2], [1], [3]])]
    standings = placings.compute(placings_rules(), [1, 2, 3], re_ridden)
    assert ranks(standings) == {2: 1, 1: 2, 3: 3}
    assert not standings.by_entrant(1).tied


def test_handicap_is_placed_as_a_scratch_race():
    """USAC 2D5: a handicap race "shall be run as a scratch race" after
    the start, so laps gained sort first and then the order at the line,
    exactly as the scratch format places the same race."""
    actions = [LapGained([4]), FinishOrder([[1], [2], [3], [4], [5]])]
    handicap = compute_for_format("handicap", placings_rules(), RIDERS, actions)
    scratch = compute_for_format("scratch", placings_rules(), RIDERS, actions)
    assert ranks(handicap) == {4: 1, 1: 2, 2: 3, 3: 4, 5: 5}
    assert handicap == scratch


def test_out_of_finish_is_not_scored_in_a_placings_race():
    """USAC 2C5(b): a rider who cannot return before the last kilometer
    "will not appear in the final placings"; there are no points to place
    them on, so the entry is refused and the scorer marks the rider."""
    rules = PlacingsRules()
    assert placings.validate(rules, RIDERS, [], OutOfFinish(1)) == [
        "Out of the finish is scored in a Points Race, Madison, or Tempo Race only"
    ]


def test_dns_is_taken_while_the_rider_has_nothing_recorded_and_refused_after():
    """USAC 1M6(b): a lap on the rider says they started; other riders' laps do not."""
    rules = PlacingsRules()
    v = placings.validate
    actions = [LapGained([1]), LapLost([2])]
    assert v(rules, RIDERS, actions, Status(3, "DNS")) == []
    assert v(rules, RIDERS, actions, Status(1, "DNS")) == [
        "Entrant 1 has a result and cannot be marked DNS"
    ]
    assert v(rules, RIDERS, actions, Status(2, "DNS")) == [
        "Entrant 2 has a result and cannot be marked DNS"
    ]


def test_a_lap_not_counted_drops_the_lap_from_the_ranking():
    """A lap wrongly recorded in a Scratch Race is the same fix: with it,
    5 wins from last across the line (USAC 2C5); without it, 5 is last."""
    actions = [LapGained([5]), FinishOrder([[1], [2], [3], [4], [5]])]
    assert placings.validate(placings_rules(), RIDERS, actions, LapNotCounted([5])) == []
    standings = placings.compute(placings_rules(), RIDERS, [*actions, LapNotCounted([5])])
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    assert standings.by_entrant(5).net_laps == 0
    assert placings.validate(placings_rules(), RIDERS, actions, LapNotCounted([1])) == [
        "Entrant 1 has no lap gained to cancel"
    ]


def test_points_rulings_and_laps_where_they_do_not_count_are_refused():
    assert placings.validate(placings_rules(), RIDERS, [], PointsAdjusted(1, -5)) == [
        "A points penalty is scored in a Points Race, Madison, or Tempo Race only"
    ]
    chariot = PlacingsRules(laps_count_for_ranking=False)
    assert placings.validate(chariot, RIDERS, [LapGained([1])], LapNotCounted([1])) == [
        "Laps do not count in this race"
    ]


def test_pulled_riders_named_last_take_the_places_after_the_finishers():
    """USAC 1M6(d): when the Chief Referee has the pulled riders placed by
    their positions when withdrawn, the scorer names them at the end of the
    finish order, earliest pulled first, and they take those places as
    places, not as DNF (R-NF-3)."""
    actions = [FinishOrder(places=[[1], [2], [3], [4], [6], [5]])]
    standings = placings.compute(placings_rules(), [1, 2, 3, 4, 5, 6], actions)
    assert {r.entrant_id: r.rank for r in standings.rows} == {1: 1, 2: 2, 3: 3, 4: 4, 6: 5, 5: 6}
    assert all(r.status is None for r in standings.rows)


def test_withdrawn_riders_follow_the_finishers_by_the_moment_whatever_their_laps():
    """USAC 1M6(d): pulled riders the Chief Referee has placed rank "by their
    relative positions when withdrawn", after the finishers (R-NF-3); USAC
    2O3(e) gives the same rank in the omnium's Scratch Race. 4 was
    withdrawn first with a lap in hand, 5 later: 5 ranks above 4, and
    neither takes a place from a rider who finished. The rank shows from
    the moment on, and the finish order names the field without them."""
    actions = [LapGained([4]), Withdrawn(4), Withdrawn(5)]
    running = placings.compute(placings_rules(), RIDERS, actions)
    assert ranks(running) == {1: None, 2: None, 3: None, 5: 4, 4: 5}
    assert running.remaining_entrants == (1, 2, 3)
    assert placings.validate(placings_rules(), RIDERS, actions, FinishOrder([[1], [4]])) == [
        "Entrant 4 is withdrawn and cannot be placed"
    ]
    done = placings.compute(placings_rules(), RIDERS, [*actions, FinishOrder([[3], [1], [2]])])
    assert ranks(done) == {3: 1, 1: 2, 2: 3, 5: 4, 4: 5}
    assert done.by_entrant(4).withdrawn and done.by_entrant(4).placed
    assert done.by_entrant(4).laps_gained == 1 and done.is_complete
    assert [r.entrant_id for r in done.rows] == [3, 1, 2, 5, 4]


def test_a_withdrawn_rider_a_lap_down_keeps_the_rank_under_the_uci_lapped_switch():
    """UCI 3.2.177 turns a lapped rider still recorded at the line into a
    DNF; a withdrawn rider is placed by the moment of the entry (R-NF-3),
    which laps never reorder, so the switch leaves them with that rank."""
    rules = PlacingsRules(laps_count_for_ranking=True, lapped_riders_placed_by_laps=False)
    actions = [LapLost([3]), Withdrawn(3), FinishOrder([[1], [2]])]
    standings = placings.compute(rules, [1, 2, 3], actions)
    three = standings.by_entrant(3)
    assert (three.rank, three.status, three.withdrawn) == (3, None, True)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3}


def test_the_shared_place_note_goes_only_to_riders_who_share_an_unplaced_rank():
    """USAC 1M6(a): riders the judges could not place share a rank and say
    so; a rider left out alone on their lap shares nothing, and a placed
    rider never carries the note."""
    actions = [LapGained([3]), FinishOrder([[1], [2]])]
    standings = placings.compute(placings_rules(), RIDERS, actions)
    assert ranks(standings) == {3: 1, 1: 2, 2: 3, 4: 4, 5: 4}
    notes = {row.entrant_id: row.notes for row in standings.rows}
    assert notes[3] == () and notes[1] == () and notes[2] == ()
    assert all("Shared place" in n for n in notes[4] + notes[5])
    assert len(notes[4]) == len(notes[5]) == 1


def test_a_plain_result_carries_no_tie_ruling_or_early_end():
    """Before the finish and at it, no row is tied without a shared place,
    no lap is struck without a ruling, and the race is not ended early, so
    the sheet and the board print nothing beside a name or the state."""
    for actions in ([], [Status(5, "DNF"), FinishOrder([[1], [2], [3], [4]])]):
        standings = placings.compute(placings_rules(), RIDERS, actions)
        assert not standings.ended
        assert not any(row.tied for row in standings.rows)
        assert not any(row.laps_not_counted for row in standings.rows)
