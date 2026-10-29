"""Win-and-out family (docs/research/usac-track-formats.md): club rules."""

from madtracker.scoring import win_and_out
from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    OutOfFinish,
    SprintResult,
    Status,
    Withdrawn,
)
from madtracker.scoring.rules import WinAndOutRules

RIDERS = [1, 2, 3, 4, 5, 6, 7]


def ranks(standings):
    return {row.entrant_id: row.rank for row in standings.rows}


def test_forward_lap_winners_take_places_in_order():
    """Win-and-out: the k-th lap winner takes place k; the rest follow by the line."""
    rules = WinAndOutRules(places=3, direction="forward")
    actions = [
        SprintResult(1, [[5]]),
        SprintResult(2, [[3]]),
        SprintResult(3, [[7]]),
        FinishOrder([[2], [1], [6], [4]]),
    ]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert ranks(standings) == {5: 1, 3: 2, 7: 3, 2: 4, 1: 5, 6: 6, 4: 7}
    assert standings.is_complete


def test_reverse_belgian_fills_from_the_bottom_place_up():
    """Belgian: the first lap winner takes the lowest prize place, the last takes 1st."""
    rules = WinAndOutRules(places=3, direction="reverse")
    actions = [
        SprintResult(1, [[5]]),
        SprintResult(2, [[3]]),
        SprintResult(3, [[7]]),
        FinishOrder([[2], [1], [6], [4]]),
    ]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert ranks(standings) == {7: 1, 3: 2, 5: 3, 2: 4, 1: 5, 6: 6, 4: 7}


def test_mid_race_shows_decided_places_and_who_is_still_in():
    rules = WinAndOutRules(places=5, direction="reverse")
    actions = [SprintResult(1, [[5]]), SprintResult(2, [[3]])]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert not standings.is_complete
    assert standings.remaining_entrants == (1, 2, 4, 6, 7)
    assert standings.by_entrant(5).rank == 5
    assert standings.by_entrant(3).rank == 4
    assert standings.next_sprint_no == 3


def test_race_shortened_fills_open_places_from_the_line():
    """Ended before every place lap: the finish order fills the open places."""
    rules = WinAndOutRules(places=5, direction="reverse")
    actions = [
        SprintResult(1, [[5]]),
        SprintResult(2, [[3]]),
        FinishOrder([[1], [2], [4], [6], [7]]),
    ]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert ranks(standings) == {1: 1, 2: 2, 4: 3, 3: 4, 5: 5, 6: 6, 7: 7}


def test_dead_heat_on_a_place_lap_shares_that_place():
    """USAC 1M6(a), 1M4(b): a dead heat the officials declare is an equal
    placing that uses two places, so the next bell is for 3rd and the race
    rings one bell fewer; the fill follows the last place a bell used."""
    rules = WinAndOutRules(places=3, direction="forward")
    actions = [SprintResult(1, [[5, 3]]), SprintResult(2, [[7]])]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert ranks(standings) == {5: 1, 3: 1, 7: 3, 1: None, 2: None, 4: None, 6: None}
    assert standings.by_entrant(5).tied
    assert standings.next_sprint_no == 4, "no third bell: the places are used"
    assert win_and_out.validate(rules, RIDERS, actions, SprintResult(3, [[1]])) == [
        "Every place is decided (a dead heat takes two); the rest finish together"
    ]
    standings = win_and_out.compute(rules, RIDERS, [*actions, FinishOrder([[1], [2], [4], [6]])])
    assert ranks(standings) == {5: 1, 3: 1, 7: 3, 1: 4, 2: 5, 4: 6, 6: 7}


def test_dead_heat_in_reverse_shares_the_lower_of_the_two_places_it_uses():
    """Belgian, three places: a dead heat on the first bell (for 3rd) uses
    3rd and 2nd and is placed 2nd equal; the next bell is for 1st, and
    then the places are used."""
    rules = WinAndOutRules(places=3, direction="reverse")
    actions = [SprintResult(1, [[5, 3]])]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert ranks(standings) == {5: 2, 3: 2, 7: None, 1: None, 2: None, 4: None, 6: None}
    actions.append(SprintResult(2, [[7]]))
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert ranks(standings) == {7: 1, 5: 2, 3: 2, 1: None, 2: None, 4: None, 6: None}
    assert standings.next_sprint_no == 4
    standings = win_and_out.compute(rules, RIDERS, [*actions, FinishOrder([[1], [2], [4], [6]])])
    assert ranks(standings) == {7: 1, 5: 2, 3: 2, 1: 4, 2: 5, 4: 6, 6: 7}


def test_dnf_ranks_after_everyone_placed():
    rules = WinAndOutRules(places=2, direction="forward")
    actions = [SprintResult(1, [[5]]), Status(6, "DNF"), SprintResult(2, [[3]]), FinishOrder([[1]])]
    standings = win_and_out.compute(rules, [1, 3, 5, 6], actions)
    assert ranks(standings) == {5: 1, 3: 2, 1: 3, 6: 4}


def test_statused_lap_winner_vacates_the_place_and_the_rest_move_up():
    """A DQ'd lap winner is not placed (USAC 1M6); the place closes up, so
    the later lap winners move up and the line fills in after the last
    place a lap decided, whichever direction the places were handed out."""
    actions = [
        SprintResult(1, [[5]]),
        SprintResult(2, [[3]]),
        SprintResult(3, [[7]]),
        Status(5, "DQ"),
        FinishOrder([[2], [1], [6], [4]]),
    ]
    forward = win_and_out.compute(WinAndOutRules(places=3, direction="forward"), RIDERS, actions)
    assert ranks(forward) == {3: 1, 7: 2, 2: 3, 1: 4, 6: 5, 4: 6, 5: None}
    reverse = win_and_out.compute(WinAndOutRules(places=3, direction="reverse"), RIDERS, actions)
    assert ranks(reverse) == {7: 1, 3: 2, 2: 3, 1: 4, 6: 5, 4: 6, 5: None}


def test_vacated_place_closes_up_before_the_finish_as_it_will_after():
    """R-WIN-1, a lap winner later marked DNF: the later places close up.
    The result so far closes them up already, so the finish confirms the
    places on the screen rather than moving them; a place a lap has yet
    to decide is not vacated and moves nobody."""
    before = [
        SprintResult(1, [[4]]),
        SprintResult(2, [[7]]),
        Status(7, "DNF"),
        SprintResult(3, [[9]]),
    ]
    entrants = [4, 7, 9, 12, 19]
    forward = WinAndOutRules(places=3, direction="forward")
    so_far = win_and_out.compute(forward, entrants, before)
    assert not so_far.is_complete
    assert ranks(so_far) == {4: 1, 9: 2, 12: None, 19: None, 7: 5}
    done = win_and_out.compute(forward, entrants, [*before, FinishOrder([[12], [19]])])
    assert ranks(done) == {4: 1, 9: 2, 12: 3, 19: 4, 7: 5}
    # Reverse: lap 1 decided 3rd, lap 2's winner left 2nd, so 3rd closes
    # up to 2nd now; 1st is still for lap 3 to decide.
    reverse = WinAndOutRules(places=3, direction="reverse")
    so_far = win_and_out.compute(reverse, entrants, before[:3])
    assert ranks(so_far) == {4: 2, 9: None, 12: None, 19: None, 7: 5}
    done = win_and_out.compute(reverse, entrants, [*before, FinishOrder([[12], [19]])])
    assert ranks(done) == {9: 1, 4: 2, 12: 3, 19: 4, 7: 5}


def test_dnf_group_follows_the_last_used_place():
    """A dead heat on the only bell of a two-place race uses both places;
    the fill starts at 3rd and the DNF group follows the last finisher."""
    rules = WinAndOutRules(places=2, direction="forward")
    actions = [
        SprintResult(1, [[5, 3]]),
        Status(6, "DNF"),
        FinishOrder([[7], [1], [2], [4]]),
    ]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert ranks(standings) == {5: 1, 3: 1, 7: 3, 1: 4, 2: 5, 4: 6, 6: 7}


def test_validate_rejects_the_usual_slips():
    rules = WinAndOutRules(places=3, direction="forward")
    actions = [SprintResult(1, [[5]])]
    v = win_and_out.validate
    assert any(
        "already took a place" in p for p in v(rules, RIDERS, actions, SprintResult(2, [[5]]))
    )
    assert any("already took a place" in p for p in v(rules, RIDERS, actions, FinishOrder([[5]])))
    assert any("Expected lap 2" in p for p in v(rules, RIDERS, actions, SprintResult(3, [[1]])))
    assert any("already recorded" in p for p in v(rules, RIDERS, actions, SprintResult(1, [[1]])))
    assert any("beyond the 3" in p for p in v(rules, RIDERS, actions, SprintResult(4, [[1]])))
    assert any("No lap winner" in p for p in v(rules, RIDERS, actions, SprintResult(2, [[]])))
    assert any("not scored" in p for p in v(rules, RIDERS, actions, Eliminated(1, [1])))
    assert v(rules, RIDERS, actions, SprintResult(2, [[1]])) == []


def test_tie_in_the_finish_fill_shares_the_place_and_skips_the_next():
    """USAC 1M6(a): riders the judges cannot separate at the line share the
    place and the next is skipped, in the fill as anywhere else. The place
    across the line agrees, two places up."""
    rules = WinAndOutRules(places=2, direction="forward")
    actions = [SprintResult(1, [[1]]), SprintResult(2, [[2]]), FinishOrder([[3, 4], [5], [6]])]
    standings = win_and_out.compute(rules, [1, 2, 3, 4, 5, 6], actions)
    assert ranks(standings) == {1: 1, 2: 2, 3: 3, 4: 3, 5: 5, 6: 6}
    for eid in (3, 4, 5, 6):
        row = standings.by_entrant(eid)
        assert row.rank == row.final_sprint_place + 2


def test_tied_fill_pushes_the_dnf_group_past_the_skipped_place():
    """USAC 1M6(a), UCI 3.3.012 A: a reverse race with no lap run, a dead
    heat at the line ranks 1, 1, 3, and the DNF group follows at 4."""
    rules = WinAndOutRules(places=3, direction="reverse")
    actions = [Status(9, "DNF"), FinishOrder([[1, 2], [3]])]
    standings = win_and_out.compute(rules, [1, 2, 3, 9], actions)
    assert ranks(standings) == {1: 1, 2: 1, 3: 3, 9: 4}


def test_provisional_dnf_ranks_after_everyone_placed_or_racing_in_reverse():
    """UCI 3.3.012 A: the DNF group follows every rider placed or still in.
    Reverse, two places: the lap 1 winner holds 2nd, nobody else is in, so
    the DNF is 3rd, after the place shown; the finish closes the open 1st
    up and renumbers both."""
    rules = WinAndOutRules(places=2, direction="reverse")
    actions = [Status(7, "DNF"), SprintResult(1, [[8]])]
    standings = win_and_out.compute(rules, [7, 8], actions)
    assert ranks(standings) == {8: 2, 7: 3}


def test_provisional_dnf_follows_a_tied_pair_and_the_riders_racing():
    """UCI 3.3.012 A: a pair tied for 1st used two places and one rider
    races for 3rd, so the DNF group is 4th while the race runs."""
    rules = WinAndOutRules(places=3, direction="forward")
    actions = [SprintResult(1, [[5, 3]]), Status(6, "DNF")]
    standings = win_and_out.compute(rules, [5, 3, 6, 7], actions)
    assert ranks(standings) == {5: 1, 3: 1, 7: None, 6: 4}


def test_provisional_dnf_never_outranks_a_held_place_in_reverse():
    """UCI 3.3.012 A: in reverse the held places are the high numbers, so the
    DNF group follows the highest one, not a count of the places decided.
    Five places, 67 holds 5th and one rider races: the DNF is 6th. Four
    places, a lap 1 dead heat holds 4th and one of the pair leaves: the
    DNF is 5th, not 4th beside the rider who still holds it."""
    rules = WinAndOutRules(places=5, direction="reverse")
    standings = win_and_out.compute(rules, [67, 2, 3], [SprintResult(1, [[67]]), Status(2, "DNF")])
    assert ranks(standings) == {67: 5, 2: 6, 3: None}
    rules = WinAndOutRules(places=4, direction="reverse")
    actions = [SprintResult(1, [[65, 43]]), Status(65, "DNF")]
    standings = win_and_out.compute(rules, [65, 43, 8, 9], actions)
    # The pair used 4th and 3rd; 43 holds 3rd alone now and the DNF follows it.
    assert ranks(standings) == {43: 3, 65: 4, 8: None, 9: None}


def test_out_of_finish_is_not_scored_in_a_win_and_out():
    """Club rule: the places are decided by bell laps and the line, with no
    points to place a rider on; the entry is refused."""
    rules = WinAndOutRules(places=2)
    assert win_and_out.validate(rules, [1, 2, 3], [], OutOfFinish(1)) == [
        "Out of the finish is scored in a Points Race, Madison, or Tempo Race only"
    ]


def test_dns_is_taken_after_a_lap_is_decided_for_a_rider_with_no_lap():
    """USAC 1M6(b): the lap winner started; a rider with nothing recorded may be DNS."""
    rules = WinAndOutRules(places=2)
    v = win_and_out.validate
    actions = [SprintResult(1, [[1]])]
    assert v(rules, [1, 2, 3], actions, Status(2, "DNS")) == []
    assert v(rules, [1, 2, 3], actions, Status(1, "DNS")) == [
        "Entrant 1 has a result and cannot be marked DNS"
    ]
    standings = win_and_out.compute(rules, [1, 2, 3], [*actions, Status(2, "DNS")])
    assert standings.by_entrant(2).status == "DNS" and standings.by_entrant(2).rank is None
    assert standings.remaining_entrants == (3,)


def test_withdrawn_is_not_scored_in_a_win_and_out():
    """Club rule with no word on a pulled rider: the scorer marks them as the
    officials call it, and the placing entry is refused."""
    assert win_and_out.validate(WinAndOutRules(places=2), [1, 2, 3], [], Withdrawn(1)) == [
        "Withdrawn is scored in a race placed at the line, a Points Race, a Madison,"
        " or a Tempo Race only"
    ]


def test_a_dead_heat_on_the_last_bell_in_reverse_shares_first():
    """Belgian, three places: two bells take 3rd and 2nd, and a dead heat
    on the third bell (USAC 1M4(b), re-ridden for the win) shares 1st
    rather than reaching past it."""
    rules = WinAndOutRules(places=3, direction="reverse")
    actions = [SprintResult(1, [[5]]), SprintResult(2, [[3]]), SprintResult(3, [[7, 1]])]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert standings.by_entrant(7).rank == standings.by_entrant(1).rank == 1
    assert standings.by_entrant(7).tied
    assert standings.next_sprint_no == 4


def test_the_next_bell_is_due_until_the_last_place_is_decided():
    """A two-place race rings its second bell after the first, and none after that."""
    rules = WinAndOutRules(places=2, direction="forward")
    standings = win_and_out.compute(rules, RIDERS, [SprintResult(1, [[5]])])
    assert standings.next_sprint_no == 2
    standings = win_and_out.compute(rules, RIDERS, [SprintResult(1, [[5]]), SprintResult(2, [[3]])])
    assert standings.next_sprint_no == 3


def test_a_dnf_with_nobody_placed_or_racing_ranks_first():
    """Every rider out before the first bell: the DNF group follows no place, so it is 1st."""
    rules = WinAndOutRules(places=2, direction="reverse")
    actions = [Status(1, "DQ"), Status(2, "DNF")]
    standings = win_and_out.compute(rules, [1, 2], actions)
    assert ranks(standings) == {2: 1, 1: None}


def test_a_lap_result_carries_no_lap_ruling():
    """Laps do not count in a Win-and-Out, so no row says a lap was struck."""
    rules = WinAndOutRules(places=2, direction="forward")
    actions = [SprintResult(1, [[5]]), SprintResult(2, [[3]]), FinishOrder([[1], [2]])]
    standings = win_and_out.compute(rules, RIDERS, actions)
    assert not any(row.laps_not_counted for row in standings.rows)
    assert not standings.ended
