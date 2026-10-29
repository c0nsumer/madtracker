"""LiveRace: Undo names corrections, laps only where they count.

Bibs are the conftest's invented riders; entrant ids are rider ids.
"""

import pytest

from madtracker.control import race as rc
from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R


@pytest.fixture
def ids(event):
    return event[1]


def ok(outcome):
    assert outcome.ok, outcome.message
    return outcome


def finished_chase(store, make_race, ids, fmt="chase", bibs=(7, 12, 33)):
    s = LiveRace(store, make_race(fmt, list(bibs), R.placings_rules()))
    for bib in bibs:
        ok(s.click(ids[bib]))
    assert s.state == "provisional"
    return s


def test_undo_names_a_moved_row_or_a_tie_as_a_correction(store, make_race, ids):
    s = finished_chase(store, make_race, ids)
    # The completing click undoes as a click: the staged order comes back.
    assert s.undo_text() == "Undo: #33 Jack Moreau placed 3rd"
    ok(s.review(ids[33], "move_up"))
    assert (
        s.undo_text() == rc.undo_moved(s.label(ids[33]), "up") == "Undo: #33 Jack Moreau moved up"
    )
    ok(s.review(ids[7], "move_down"))
    assert s.undo_text() == "Undo: #7 Maya Petrakis moved down"
    ok(s.review(ids[7], "tie_above"))
    assert (
        s.undo_text()
        == rc.undo_tied(s.label(ids[7]), s.label(ids[33]))
        == "Undo: #7 Maya Petrakis tied with #33 Jack Moreau"
    )
    ok(s.undo())
    assert s.undo_text() == "Undo: #7 Maya Petrakis moved down"


def test_undo_names_a_win_and_out_lap_swap(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33], R.win_and_out_rules(2)))
    for bib in (7, 12, 33):
        ok(s.click(ids[bib]))
    ok(s.review(ids[12], "move_up"))
    assert s.undo_text() == "Undo: #12 Tess Gallagher and #7 Maya Petrakis swapped"


@pytest.mark.parametrize("fmt", ["chariot", "keirin", "match_sprint"])
def test_formats_decided_on_the_line_offer_no_laps(store, make_race, ids, fmt):
    s = LiveRace(store, make_race(fmt, [7, 12, 33], R.placings_rules()))
    assert [k for k, _ in s.rider_actions(ids[7])] == [
        "place_last",
        "dns",
        "dnf",
        "withdrawn",
        "dq",
    ]
    assert not s.act(ids[7], "lap_gained").ok


def test_a_chase_still_offers_laps(store, make_race, ids):
    s = LiveRace(store, make_race("chase", [7, 12], R.placings_rules()))
    assert "lap_gained" in [k for k, _ in s.rider_actions(ids[7])]


@pytest.mark.parametrize(
    "key,words",
    [
        ("dns", "marked Did Not Start"),
        ("dnf", "marked Did Not Finish"),
        ("dq", "marked Disqualified"),
        ("lap_gained", "gained a lap"),
        ("lap_lost", "lost a lap"),
    ],
)
def test_undo_for_a_rider_action_names_the_rider_then_the_action(store, make_race, ids, key, words):
    """Who first, then what was done, as every other Undo label reads."""
    s = LiveRace(store, make_race("chase", [7, 12, 33], R.placings_rules()))
    ok(s.act(ids[7], key))
    assert s.undo_text() == f"Undo: #7 Maya Petrakis {words}"
    assert words == rc.UNDO_WORDS[key]


def test_undo_past_every_click_of_a_reopened_sprint_cancels_the_correction(
    store, make_race, ids, house
):
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(2)))
    ok(s.click(ids[12]))
    ok(s.click(ids[7]))
    ok(s.record_sprint())
    for bib in (7, 12, 33):
        ok(s.click(ids[bib]))
    assert s.state == "provisional"
    rows = [(r.kind, r.payload) for r in s.rows()]
    ok(s.reopen_sprint(1))
    ok(s.undo())
    ok(s.undo())
    assert s.staged() == [] and s.editing_sprint == 1
    assert s.undo_text() == rc.CANCEL_CORRECTION == "Cancel Correction"
    assert s.can_undo()
    ok(s.undo())
    assert s.editing_sprint is None and s.screen().review
    assert [(r.kind, r.payload) for r in s.rows()] == rows, "no entry was taken back"
    assert s.undo_text() == "Undo: #33 Jack Moreau placed 3rd"
