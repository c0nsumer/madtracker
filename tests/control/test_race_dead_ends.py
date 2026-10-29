"""LiveRace at the edges of a night: a field that runs out, a pre-race call, a format change.

Each test is a path a scorer can reach that could leave the race stuck,
the board or Edit event saying the wrong thing, or a label promising
more than the action does. Bibs are the conftest's invented riders.
"""

import pytest

from madtracker.control import board_feed
from madtracker.control import race as rc
from madtracker.control.program import is_scored
from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R
from madtracker.scoring.actions import Status

TEAMS = [("Blue", 3, 24), ("Red", 5, 36), ("Orange", 8, 12)]


@pytest.fixture
def ids(event):
    return event[1]


def ok(outcome):
    assert outcome.ok, outcome.message
    return outcome


def ranks(live):
    return {live.name(r.entrant_id): r.rank for r in live.standings().rows}


# ----- a DNS before the start keeps the start list on the TV ---------------


@pytest.mark.parametrize("fmt", ["chase", "elimination", "points", "win_and_out"])
def test_dns_before_the_start_leaves_the_start_list_on_the_board(store, make_race, ids, house, fmt):
    rules = {
        "chase": R.placings_rules(),
        "elimination": house.elimination(),
        "points": house.points(3),
        "win_and_out": R.win_and_out_rules(2),
    }[fmt]
    s = LiveRace(store, make_race(fmt, [7, 12, 33, 9], rules))
    ok(s.act(ids[7], "dns"))
    assert s.state == "setup" and s.state_label() == "Start list"
    layout, payload = board_feed.board_for(s.view())
    assert layout == "pre_race"
    assert payload.header.status == "Start list"
    assert "Maya Petrakis" not in [n for e in payload.roster for n in e.names]


# ----- every rider leaves ---------------------------------------------------


def test_win_and_out_whose_field_runs_out_completes(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33], R.win_and_out_rules(3)))
    ok(s.click(ids[7]))
    ok(s.act(ids[12], "dnf"))
    ok(s.act(ids[33], "dnf"))
    assert s.state == "provisional"
    # The engine places the DNF group after the decided places.
    assert ranks(s) == {"Maya Petrakis": 1, "Tess Gallagher": 2, "Jack Moreau": 2}
    assert s.task().kind == "review"
    assert s.log_rows()[-1].text == "Finish: nobody left"
    ok(s.mark_final())
    # Undo of the last DNF takes the empty finish with it.
    ok(s.reopen())
    ok(s.undo())
    assert s.state == "running" and s.task().text == "Lap 2: click the winner."


def test_win_and_out_never_asks_for_a_lap_with_no_cards(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12], R.win_and_out_rules(3)))
    ok(s.act(ids[7], "dnf"))
    ok(s.act(ids[12], "dq"))
    screen = s.screen()
    assert screen.task.kind == "review" and screen.mark_final


@pytest.mark.parametrize("fmt", ["chase", "points", "madison"])
def test_a_field_that_all_leaves_reaches_provisional(store, make_race, ids, house, fmt):
    if fmt == "madison":
        s = LiveRace(
            store, make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
        )
    else:
        rules = R.placings_rules() if fmt == "chase" else house.points(3)
        s = LiveRace(store, make_race(fmt, [7, 12, 33], rules))
    entrants = list(s.roster.ids)
    if fmt != "chase":
        ok(s.click(entrants[0]))
        ok(s.record_sprint())
    for i, eid in enumerate(entrants):
        ok(s.act(eid, "dq" if i == 0 else "dnf"))
    assert s.state == "provisional" and s.state_label() == "Provisional"
    screen = s.screen()
    assert screen.task.kind == "review" and screen.mark_final and screen.cards == ()
    assert sorted(r.place_text for r in screen.rows) == ["DNF"] * (len(entrants) - 1) + ["DQ"]
    ok(s.mark_final())
    assert s.state == "final"
    layout, payload = board_feed.board_for(s.view())
    assert payload.header.status == "Final"
    ok(s.reopen())
    ok(s.undo())
    assert s.state == "running" and not s.screen().review


# ----- an undone entry is still in the log --------------------------------


def test_a_race_undone_to_its_start_is_set_up_again_but_never_removed(store, make_race, ids, house):
    """Undo back to the start list leaves no entry standing, so the race's
    format and field open again (design section 6). The store never deletes
    a log row, so Remove race and Delete event are still refused, and the
    screen says so rather than offering them and failing."""
    from madtracker.control.program import ever_scored, race_refusals

    s = LiveRace(store, make_race("elimination", [7, 12, 33, 9], house.elimination()))
    ok(s.click(ids[7]))
    assert is_scored(store, s.race) and ever_scored(store, s.race)
    name = s.race.name
    refusal = race_refusals(store, s.race.event_id, s.race_id)["remove"]
    assert refusal == f"{name} has been scored and cannot be removed."
    ok(s.undo())
    assert s.state == "setup" and s.rows() == []
    assert not is_scored(store, s.race)
    assert ever_scored(store, s.race)
    refusal = race_refusals(store, s.race.event_id, s.race_id)["remove"]
    assert refusal == f"{name} has had entries and cannot be removed."
    assert store.event_raced(s.race.event_id) == s.race.name


def test_a_live_entry_before_the_start_keeps_the_race_locked(store, make_race, ids, house):
    """A DNS is a pre-race call: the race is in setup, and its one standing
    entry names the field, so the field stays fixed until that is undone."""
    s = LiveRace(store, make_race("elimination", [7, 12, 33, 9], house.elimination()))
    ok(s.act(ids[7], "dns"))
    assert s.state == "setup"
    assert is_scored(store, s.race)
    ok(s.undo())
    assert not is_scored(store, s.race)


def test_a_partial_undo_keeps_the_race_locked_until_the_last_entry_goes(
    store, make_race, ids, house
):
    s = LiveRace(store, make_race("elimination", [7, 12, 33, 9], house.elimination()))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    ok(s.undo())
    assert s.state == "running" and is_scored(store, s.race)
    ok(s.undo())
    assert s.state == "setup" and not is_scored(store, s.race)


def test_a_complete_or_reopened_result_keeps_the_race_locked(store, make_race, ids, house):
    s = LiveRace(store, make_race("chase", [7, 12], R.placings_rules()))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    assert s.state == "provisional" and is_scored(store, s.race)
    ok(s.mark_final())
    assert is_scored(store, s.race)
    ok(s.reopen())
    assert s.state == "provisional" and is_scored(store, s.race)
    ok(s.undo())
    ok(s.undo())
    assert s.state == "setup" and not is_scored(store, s.race)


# ----- staged clicks and a format change -----------------------------------


def test_staged_clicks_do_not_survive_a_format_change(store, make_race, ids, house):
    s = LiveRace(store, make_race("chase", [7, 12, 33], R.placings_rules()))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    assert not is_scored(store, s.race)
    store.update_race(s.race_id, format="points", rules=house.points(3).to_dict())
    s.reload()
    screen = s.screen()
    assert all(c.badge is None for c in screen.cards)
    assert s.staged() == [] and s.undo_text() == rc.NOTHING_TO_UNDO_LABEL
    # The new format's clicks stage and undo as usual.
    ok(s.click(ids[33]))
    assert s.undo_text() == "Undo: #33 Jack Moreau placed 1st"
    again = LiveRace(store, s.race_id)
    assert again.staged() == [[ids[33]]]


# ----- Undo after the completing click names that click --------------------


def test_undo_after_the_completing_click_names_the_click(store, make_race, ids):
    s = LiveRace(store, make_race("chase", [7, 12, 33], R.placings_rules()))
    for bib in (7, 12, 33):
        ok(s.click(ids[bib]))
    assert s.state == "provisional"
    assert s.undo_text() == "Undo: #33 Jack Moreau placed 3rd"
    ok(s.undo())
    assert s.staged() == [[ids[7]], [ids[12]]]
    assert s.undo_text() == "Undo: #12 Tess Gallagher placed 2nd"


def test_undo_after_the_last_click_of_a_win_and_out_fill_names_its_place(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33, 9], R.win_and_out_rules(2)))
    for bib in (7, 12, 33, 9):
        ok(s.click(ids[bib]))
    assert s.undo_text() == "Undo: #9 Ben Szymanski placed 4th"


def test_the_last_lap_click_undoes_as_that_lap(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12], R.win_and_out_rules(3)))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    assert s.state == "provisional" and s.undo_text() == "Undo: #12 Tess Gallagher won Lap 2"


def test_the_elimination_winner_click_undoes_the_final_sprint(store, make_race, ids, house):
    s = LiveRace(store, make_race("elimination", [7, 12, 33], house.elimination()))
    ok(s.click(ids[33]))
    ok(s.click(ids[7]))
    assert s.state == "provisional" and s.undo_text() == "Undo: Final sprint recorded"
    ok(s.undo())
    assert s.task().kind == "winner"


# ----- the win-and-out log numbers the fill from the first open place ------


def test_win_and_out_fill_logs_the_places_it_took(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33, 9, 19], R.win_and_out_rules(3)))
    for bib in (7, 12, 33, 9, 19):
        ok(s.click(ids[bib]))
    expected = "Finish: 4th #9 Ben Szymanski, 5th #19 Omar Rahimi"
    assert s.log_rows()[-1].text == expected
    ok(s.undo())
    assert s.log_rows()[-1].text == "Undone: " + expected


def test_win_and_out_fill_after_a_vacated_place_logs_the_closed_up_places(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33, 9, 19], R.win_and_out_rules(3)))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    # The lap winner's row offers no DNF, so the mark goes in as an entry.
    ok(s._record([Status(entrant_id=ids[12], status="DNF")]))
    ok(s.click(ids[33]))
    ok(s.click(ids[9]))
    out = ok(s.click(ids[19]))
    rank = ranks(s)
    assert (rank["Ben Szymanski"], rank["Omar Rahimi"]) == (3, 4)
    expected = "Finish: 3rd #9 Ben Szymanski, 4th #19 Omar Rahimi"
    assert s.log_rows()[-1].text == expected
    assert out.message == "Recorded " + expected


# ----- the points table has no place before the first sprint ---------------


def test_points_table_shows_no_place_before_the_first_sprint(store, make_race, ids, house):
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(3)))
    assert [r.place_text for r in s.screen().rows] == ["", "", ""]
    ok(s.click(ids[12]))
    ok(s.record_sprint())
    assert s.screen().rows[0].place_text == "1"


# ----- a sprint reopens for correction mid-race ----------------------------


def test_a_sprint_reopens_mid_race_and_the_sprint_in_progress_keeps_its_clicks(
    store, make_race, ids, house
):
    """A wrong sprint 1 noticed during sprint 3 is fixed
    where it is, not by undoing sprints 3 and 2."""
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(3)))
    ok(s.click(ids[7]))
    ok(s.record_sprint())
    assert s.screen().open_sprints == (1,)
    ok(s.click(ids[12]))
    ok(s.reopen_sprint(1))
    assert s.editing_sprint == 1 and s.staged() == [[ids[7]]]
    assert s.screen().open_sprints == (), "no second correction inside the first"
    ok(s.undo())
    ok(s.click(ids[33]))
    ok(s.record_sprint())
    assert s.editing_sprint is None and s.staged() == [[ids[12]]]
    assert s.recorded_sprints()[1].payload["places"] == [[ids[33]]]
    # Cancel puts the sprint in progress back too.
    ok(s.reopen_sprint(1))
    s.cancel_edit()
    assert s.staged() == [[ids[12]]] and s.editing_sprint is None


def test_a_one_rider_elimination_is_a_start_list_until_something_is_entered(store, event):
    """The engine calls a field of one decided; the surface calls it a start list."""
    from madtracker.control.race import LiveRace

    event_id, _ids = event
    rider = store.add_rider("Solo", "Rider")
    store.add_entry(event_id, rider.rider_id, 77)
    race = store.add_race(event_id, "Solo elimination", "elimination")
    store.add_race_entry(race.race_id, rider.rider_id)
    live = LiveRace(store, race.race_id)
    assert live.state_label() == "Start list"
    assert live.state == "setup"


def test_a_sprint_corrected_after_a_dq_does_not_block_a_later_correction(
    store, make_race, ids, house
):
    """A corrected sprint stands at the end of the log, after a DQ entered
    since it was ridden; re-read there it places a rider now out. It was
    accepted when written, so a later correction must not refuse over it."""
    s = LiveRace(store, make_race("points", [7, 12, 33, 5], house.points(4)))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    ok(s.record_sprint())  # sprint 1: 7, 12
    ok(s.click(ids[33]))
    ok(s.click(ids[7]))
    ok(s.record_sprint())  # sprint 2: 33, 7
    ok(s.act(ids[7], "dq"))
    # Sprint 1 was really 12, 7: corrected after the DQ, which the rules allow.
    ok(s.reopen_sprint(1))
    ok(s.move_staged(ids[12], "move_up"))
    ok(s.record_sprint())
    # Sprint 2 was really 7, 33: the earlier correction must not stand in the way.
    ok(s.reopen_sprint(2))
    ok(s.move_staged(ids[7], "move_up"))
    out = s.record_sprint()
    assert out.ok, out.message
    assert s.recorded_sprints()[1].payload["places"] == [[ids[12]], [ids[7]]]
    assert s.recorded_sprints()[2].payload["places"] == [[ids[7]], [ids[33]]]
    # The same correction undone and redone still stands.
    ok(s.undo())
    ok(s.reopen_sprint(2))
    ok(s.move_staged(ids[7], "move_up"))
    ok(s.record_sprint())
    # A DQ rider the sprint never placed still cannot be added to it.
    ok(s.act(ids[5], "dq"))
    ok(s.reopen_sprint(1))
    assert s.click(ids[5]) == rc.Outcome(False, "#5 Priya Okafor is marked Disqualified.")
