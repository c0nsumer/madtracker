"""The fixed card grid: one card per entrant, in bib order, until the result completes.

A click that places, puts out, or marks an entrant turns the card done
in its slot. A click on a done card is refused with one sentence and
records nothing, the done card's menu is its result row's, and Undo
turns the card live again in the same slot. Bibs are the conftest's
invented riders.
"""

import pytest

from madtracker.control.race import STAGED_KEY, LiveRace, Outcome
from madtracker.control.race_words import DONE_MARKS
from madtracker.scoring import rules as R

TEAMS = [("Blue", 3, 24), ("Red", 5, 36), ("Orange", 8, 12)]


@pytest.fixture
def ids(event):
    return event[1]


def ok(outcome):
    assert outcome.ok, outcome.message
    return outcome


def bib_order(live):
    return sorted(live.roster.ids, key=live._sort_key)


def kept(live):
    """What a refused click leaves as it was: the log, the staged order, the stored row."""
    setting = live.store.get_setting(STAGED_KEY.format(race_id=live.race_id))
    return len(live.rows()), live.staged(), live.staged_tail(), setting


def card(live, eid):
    return next(c for c in live.screen().cards if c.entrant_id == eid)


def slot(live, eid):
    return [c.entrant_id for c in live.screen().cards].index(eid)


def check(live):
    """Every invariant of the grid on the screen now; the refusals each done card gives."""
    screen = live.screen()
    if not screen.cards:
        assert screen.review or screen.task.kind in ("final", "none")
        return {}
    assert [c.entrant_id for c in screen.cards] == bib_order(live)
    rows = {r.entrant_id: r for r in screen.rows}
    st = live.standings()
    refusals = {}
    for c in screen.cards:
        if not c.done:
            assert (c.done_text, c.done_status, c.done_tip) == ("", False, "")
            continue
        eid = c.entrant_id
        row = rows.get(eid)
        assert c.badge is None and c.laps == st.by_entrant(eid).net_laps
        if c.done_status:
            standing = st.by_entrant(eid)
            code = standing.status or ("out_of_finish" if standing.out_of_finish else "withdrawn")
            assert (c.done_text, c.done_tip) == DONE_MARKS[code]
            assert not c.tied
        else:
            assert row is not None and (c.done_text, c.tied) == (row.place_text, row.tied)
            assert c.done_tip == ""
        # Two doors to one menu: the card, the rider's menu, and the row agree.
        assert c.actions == tuple(live.rider_actions(eid))
        if row is not None:
            assert c.actions == row.actions
        before = kept(live)
        out = live.click(eid)
        assert not out.ok and out.message
        assert kept(live) == before, "a refused click records nothing"
        refusals[eid] = out.message
    return refusals


def run(live, *steps):
    """Each step in turn, every invariant checked after it; the last refusals."""
    refusals = check(live)
    for op, *args in steps:
        if op == "click":
            ok(live.click(args[0]))
        elif op == "place_last":
            ok(live.place_last(args[0]))
        elif op == "act":
            ok(live.act(*args))
        elif op == "review":
            ok(live.review(*args))
        elif op == "record":
            ok(live.record_sprint())
        elif op == "rest":
            ok(live.place_rest_together())
        elif op == "undo":
            ok(live.undo())
        elif op == "reopen":
            ok(live.reopen_sprint(args[0]))
        elif op == "cancel":
            live.cancel_edit()
        else:
            raise ValueError(op)
        refusals = check(live)
    return refusals


def done_ids(live):
    return [c.entrant_id for c in live.screen().cards if c.done]


# ----- a finish order --------------------------------------------------------


def test_a_chase_keeps_every_card_and_refuses_a_done_one(store, make_race, ids):
    s = LiveRace(store, make_race("chase", [7, 12, 33, 9, 19, 24, 3, 5], R.placings_rules()))
    order = bib_order(s)
    refusals = run(s, ("act", ids[5], "dns"))
    assert refusals[ids[5]] == "#5 Priya Okafor is marked Did Not Start."
    refusals = run(s, ("click", ids[33]))
    assert refusals[ids[33]] == "#33 Jack Moreau is already placed (1st)."
    assert card(s, ids[33]).done_text == "1" and not card(s, ids[33]).done_status
    # Undo turns the card live in the same slot; the click places again.
    at = slot(s, ids[33])
    run(s, ("undo",))
    assert not card(s, ids[33]).done and slot(s, ids[33]) == at
    refusals = run(s, ("click", ids[33]), ("place_last", ids[9]), ("click", ids[7]))
    # Seven left after the DNS, so the back's first mark is 7th.
    assert refusals[ids[9]] == "#9 Ben Szymanski is already placed (7th)."
    # The done card's menu is the staged row's: a tie and a move go to the staged order.
    assert ("tie_above", "Tie with the Rider Above") in card(s, ids[7]).actions
    run(s, ("act", ids[7], "tie_above"))
    assert (card(s, ids[7]).done_text, card(s, ids[7]).tied) == ("1", True)
    assert (card(s, ids[33]).done_text, card(s, ids[33]).tied) == ("1", True)
    run(s, ("undo",), ("act", ids[7], "move_up"))
    assert [card(s, e).done_text for e in (ids[7], ids[33])] == ["1", "2"]
    refusals = run(
        s,
        ("act", ids[12], "dnf"),
        ("act", ids[19], "lap_gained"),
        ("act", ids[24], "withdrawn"),
        ("act", ids[33], "dq"),
    )
    assert refusals[ids[12]] == "#12 Tess Gallagher is marked Did Not Finish."
    assert refusals[ids[24]] == "#24 Kenji Mori is marked Withdrawn."
    assert refusals[ids[33]] == "#33 Jack Moreau is marked Disqualified."
    assert [c.entrant_id for c in s.screen().cards] == order
    assert [e for e in order if e not in done_ids(s)] == [ids[3], ids[19]]
    # The rest placed together completes the result, and the cards leave together.
    run(s, ("rest",))
    assert s.screen().review and s.screen().cards == ()
    run(s, ("undo",))
    assert [c.entrant_id for c in s.screen().cards] == order
    assert not card(s, ids[19]).done


def test_a_win_and_out_keeps_its_lap_winners_as_placed_cards(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33, 9, 19], R.win_and_out_rules(2)))
    refusals = run(s, ("click", ids[7]), ("click", ids[12]))
    assert refusals[ids[7]] == "#7 Maya Petrakis is already placed (1st)."
    assert refusals[ids[12]] == "#12 Tess Gallagher is already placed (2nd)."
    refusals = run(s, ("click", ids[33]))
    assert refusals[ids[33]] == "#33 Jack Moreau is already placed (3rd)."
    run(s, ("act", ids[9], "dq"), ("undo",), ("click", ids[9]), ("click", ids[19]))
    assert s.screen().review and s.screen().cards == ()


# ----- an elimination --------------------------------------------------------


def test_an_elimination_keeps_its_outs_and_their_moves(store, make_race, ids, house):
    bibs = [3, 5, 7, 8, 9, 12]
    s = LiveRace(store, make_race("elimination", bibs, house.elimination()))
    refusals = run(s, ("click", ids[3]), ("click", ids[7]))
    assert refusals[ids[3]] == "#3 Marcus Delgado is already out (6th)."
    assert refusals[ids[7]] == "#7 Maya Petrakis is already out (5th)."
    # The out's done card offers its row's moves, and act moves the row as review does.
    twin = LiveRace(store, make_race("elimination", bibs, house.elimination(), name="Twin"))
    run(twin, ("click", ids[3]), ("click", ids[7]))
    assert "move_down" in [k for k, _ in s.rider_actions(ids[7])]
    run(s, ("act", ids[7], "move_down"))
    run(twin, ("review", ids[7], "move_down"))
    assert s.standings().ranks() == twin.standings().ranks()
    assert s.undo_text() == twin.undo_text()
    # The card renumbers with the row: 7 took 6th.
    assert card(s, ids[7]).done_text == "6"
    assert check(s)[ids[7]] == "#7 Maya Petrakis is already out (6th)."
    refusals = run(s, ("undo",), ("act", ids[8], "dnf"))
    assert refusals[ids[8]] == "#8 Tom Kowalczyk is marked Did Not Finish."
    # A DNF in an elimination keeps its place in the table; the card says the mark.
    assert card(s, ids[8]).done_text == "DNF"
    at = slot(s, ids[8])
    run(s, ("undo",))
    assert not card(s, ids[8]).done and slot(s, ids[8]) == at
    run(s, ("click", ids[8]), ("click", ids[9]))
    assert s.task().kind == "winner"
    run(s, ("click", ids[5]))
    assert s.screen().review and s.screen().cards == ()


def test_an_elimination_final_sprint_places_its_riders(store, make_race, ids):
    rules = R.EliminationRules(survivors=3)
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8], rules))
    run(s, ("click", ids[3]))
    assert s.task().kind == "order"
    refusals = run(s, ("click", ids[8]))
    assert refusals[ids[8]] == "#8 Tom Kowalczyk is already placed (1st)."
    assert refusals[ids[3]] == "#3 Marcus Delgado is already out (4th)."
    run(s, ("click", ids[5]), ("click", ids[7]))
    assert s.screen().review


# ----- the sprint formats ----------------------------------------------------


def test_a_points_race_keeps_its_marked_riders_as_done_cards(store, make_race, ids, house):
    s = LiveRace(store, make_race("points", [7, 12, 33, 9, 19], house.points(3)))
    order = bib_order(s)
    refusals = run(s, ("act", ids[19], "dns"), ("click", ids[7]), ("click", ids[12]))
    assert refusals == {ids[19]: "#19 Omar Rahimi is marked Did Not Start."}
    # A badged card is live: a second click takes the badge off.
    assert card(s, ids[7]).badge == 1 and not card(s, ids[7]).done
    run(s, ("record",), ("act", ids[9], "withdrawn"), ("act", ids[33], "lap_gained"), ("undo",))
    run(s, ("click", ids[33]), ("record",))
    assert s.task().kind == "final_sprint"
    refusals = run(s, ("act", ids[12], "out_of_finish"))
    assert refusals[ids[12]] == "#12 Tess Gallagher is marked Out of the Finish (Mishap)."
    assert refusals[ids[9]] == "#9 Ben Szymanski is marked Withdrawn."
    assert (card(s, ids[12]).done_text, card(s, ids[12]).done_tip) == (
        "Mishap",
        "Out of the Finish (Mishap)",
    )
    assert [c.entrant_id for c in s.screen().cards] == order
    run(s, ("click", ids[7]), ("click", ids[33]))
    assert s.screen().review and s.screen().cards == ()


def test_a_tempo_race_keeps_a_disqualified_rider_in_the_grid(store, make_race, ids):
    s = LiveRace(store, make_race("tempo", [7, 12, 33, 9], R.tempo_rules(sprint_count=3)))
    refusals = run(s, ("click", ids[7]), ("record",), ("act", ids[9], "dq"))
    assert refusals[ids[9]] == "#9 Ben Szymanski is marked Disqualified."
    assert card(s, ids[9]).actions == ()
    run(s, ("click", ids[12]), ("record",), ("click", ids[7]), ("click", ids[12]))
    run(s, ("click", ids[33]))
    assert s.screen().review


def test_a_madison_team_keeps_its_card(store, make_race, ids, house):
    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    s = LiveRace(store, race_id)
    teams = {s.name(t): t for t in s.roster.ids}
    run(s, ("click", teams["Red"]), ("click", teams["Blue"]), ("record",))
    refusals = run(s, ("act", teams["Red"], "withdrawn"))
    assert refusals == {teams["Red"]: "Red is marked Withdrawn."}
    at = slot(s, teams["Red"])
    run(s, ("undo",))
    assert not card(s, teams["Red"]).done and slot(s, teams["Red"]) == at
    run(s, ("act", teams["Red"], "dnf"), ("click", teams["Blue"]), ("click", teams["Orange"]))
    assert s.screen().review


# ----- a reopened sprint -----------------------------------------------------


def test_a_reopened_sprint_shows_the_field_it_had(store, make_race, ids, house):
    """A rider withdrawn at Sprint 3 rode Sprint 2, so its correction may
    place them: a live card. A rider DNS before Sprint 1 never rode it: a
    done card with the mark."""
    s = LiveRace(store, make_race("points", [7, 12, 33, 9, 19], house.points(4)))
    run(s, ("act", ids[19], "dns"), ("click", ids[7]), ("record",))
    run(s, ("click", ids[12]), ("record",), ("act", ids[9], "withdrawn"))
    run(s, ("click", ids[33]), ("record",))
    before = s.screen().cards
    assert done_ids(s) == [ids[9], ids[19]]
    refusals = run(s, ("reopen", 2))
    assert s.task().editing
    assert done_ids(s) == [ids[19]], "the withdrawn rider rode Sprint 2"
    assert (card(s, ids[19]).done_text, card(s, ids[19]).actions) == ("DNS", ())
    assert refusals == {ids[19]: "#19 Omar Rahimi is marked Did Not Start."}
    run(s, ("cancel",))
    assert s.screen().cards == before
    run(s, ("reopen", 2), ("click", ids[9]), ("record",))
    assert s.screen().cards == tuple(
        c if c.entrant_id != ids[9] else card(s, ids[9]) for c in before
    )
    assert done_ids(s) == [ids[9], ids[19]]


def test_a_reopened_sprint_shows_a_rider_who_did_not_finish_after_it_as_live(
    store, make_race, ids, house
):
    s = LiveRace(store, make_race("points", [7, 12, 33, 9], house.points(3)))
    run(s, ("click", ids[7]), ("record",), ("act", ids[9], "dnf"))
    assert card(s, ids[9]).done_text == "DNF"
    run(s, ("reopen", 1))
    assert not card(s, ids[9]).done, "9 rode Sprint 1"
    run(s, ("click", ids[9]), ("record",))
    assert card(s, ids[9]).done


def test_a_refused_click_on_a_done_card_is_the_outcome_alone(store, make_race, ids):
    s = LiveRace(store, make_race("chase", [7, 12, 33], R.placings_rules()))
    run(s, ("click", ids[12]))
    before = kept(s)
    assert s.click(ids[12]) == Outcome(False, "#12 Tess Gallagher is already placed (1st).")
    assert kept(s) == before and s.undo_text() == "Undo: #12 Tess Gallagher placed 1st"
