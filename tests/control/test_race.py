"""LiveRace: the task for the moment, a click, the result, undo, the review.

One scenario per format from docs/design.md section 7, then the
corrections of section 8, all against a real store. Bibs are the
conftest's invented riders; entrant ids are rider ids, or team ids for
a madison.
"""

import pytest
from logbook import event_log

from madtracker.control import board_feed
from madtracker.control import race as rc
from madtracker.control.program import is_scored
from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R
from madtracker.scoring.actions import Eliminated, FinishOrder, SprintResult, Status
from madtracker.store import VOID_KIND

TEAMS = [("Blue", 3, 24), ("Red", 5, 36), ("Orange", 8, 12)]


@pytest.fixture
def ids(event):
    return event[1]


def ok(outcome):
    assert outcome.ok, outcome.message
    return outcome


def chase(store, make_race, bibs=(7, 12, 33, 9)):
    return LiveRace(store, make_race("chase", list(bibs), R.placings_rules(), name="Chase"))


def ranks(live):
    return {live.name(r.entrant_id): r.rank for r in live.standings().rows}


def live_cards(live):
    """The entrants whose card takes a click now; the done cards hold their slots."""
    return [c.entrant_id for c in live.screen().cards if not c.done]


def live_names(live, team=False):
    return [c.entry.team if team else c.entry.names[0] for c in live.screen().cards if not c.done]


# ----- chase ---------------------------------------------------------------


def test_chase_clicks_build_the_finish_order_and_the_last_click_completes(store, make_race, ids):
    s = chase(store, make_race)
    assert s.kind == "placings" and s.state == "setup"
    assert s.state_label() == "Start list"
    assert s.task().text == "Click riders in the order they finish."
    screen = s.screen()
    # Cards sort by bib: 7, 9, 12, 33 (section 7).
    assert [c.entry.names[0] for c in screen.cards] == [
        "Maya Petrakis",
        "Ben Szymanski",
        "Tess Gallagher",
        "Jack Moreau",
    ]
    assert screen.rows == (), "a place nobody has yet is not a row"

    ok(s.click(ids[33]))
    assert s.state == "setup", "a staged place is not an entry"
    assert s.undo_text() == "Undo: #33 Jack Moreau placed 1st"
    screen = s.screen()
    assert screen.rows[0].entry.names == ["Jack Moreau"] and screen.rows[0].staged
    done = next(c for c in screen.cards if c.entry.names[0] == "Jack Moreau")
    assert done.done and done.done_text == "1" and done.badge is None
    # The staged order survives a reload: it is on disk.
    again = LiveRace(store, s.race_id)
    assert again.screen().rows[0].entry.names == ["Jack Moreau"]

    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    # The staged row moves as a result row will, and the first of a
    # place below another can tie with the place above.
    # After the moves, the rider's own actions: the card left with the
    # click, so the row is the place to act on them.
    assert s.screen().rows[2].actions == (
        ("move_up", "Move Up"),
        ("move_to:0", "Move to 1st"),
        ("move_to:1", "Move to 2nd"),
        ("tie_above", "Tie with the Rider Above"),
        ("lap_gained", "Gained a Lap"),
        ("lap_lost", "Lost a Lap"),
        ("dq", "Disqualify"),
    )
    ok(s.tie_above(ids[12]))
    assert [r.place_text for r in s.screen().rows[:3]] == ["1", "2", "2"]
    assert s.rows() == []
    ok(s.click(ids[9]))
    assert s.state == "provisional" and s.state_label() == "Provisional"
    assert ranks(s) == {
        "Jack Moreau": 1,
        "Maya Petrakis": 2,
        "Tess Gallagher": 2,
        "Ben Szymanski": 4,
    }
    screen = s.screen()
    assert screen.review and screen.cards == () and screen.mark_final and not screen.reopen
    assert screen.task.text == rc.REVIEW_TEXT
    assert [r.place_text for r in screen.rows] == ["1", "2", "2", "4"]


def test_chase_second_click_on_a_placed_rider_is_refused_and_undo_takes_a_click_back(
    store, make_race, ids
):
    s = chase(store, make_race)
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    ok(s.undo())
    assert [r.entrant_id for r in s.screen().rows if r.staged] == [ids[7]]
    ok(s.click(ids[12]))
    assert s.click(ids[7]) == rc.Outcome(False, "#7 Maya Petrakis is already placed (1st).")
    assert [r.entrant_id for r in s.screen().rows if r.staged] == [ids[7], ids[12]]


def test_a_dnf_during_a_chase_shrinks_the_field_and_can_complete_it(store, make_race, ids):
    s = chase(store, make_race, (7, 12, 33))
    assert [k for k, _ in s.rider_actions(ids[7])] == [
        "place_last",
        "dns",
        "dnf",
        "withdrawn",
        "lap_gained",
        "lap_lost",
        "dq",
    ]
    ok(s.act(ids[33], "dns"))
    assert s.state == "setup", "a DNS is a pre-race call"
    # The done card offers its row's menu, empty until the result is in.
    assert s.rider_actions(ids[33]) == []
    ok(s.click(ids[7]))
    # 7 is placed, so 7 started, and the done card offers the staged row's
    # menu; 12 has nothing recorded and may still be a no-show.
    assert [k for k, _ in s.rider_actions(ids[7])] == ["lap_gained", "lap_lost", "dq"]
    assert [k for k, _ in s.rider_actions(ids[12])] == [
        "place_last",
        "dns",
        "dnf",
        "withdrawn",
        "lap_gained",
        "lap_lost",
        "dq",
    ]
    ok(s.act(ids[12], "dnf"))
    # Everyone left is placed, so the result completed on the DNF.
    assert s.state == "provisional"
    assert [(r.place_text, r.status) for r in s.screen().rows] == [
        ("1", ""),
        ("DNF", "DNF"),
        ("DNS", "DNS"),
    ]
    refused = s.act(ids[7], "dnf")
    assert not refused.ok and "row's menu" in refused.message


def staged_rows(s: LiveRace) -> list[tuple[str, str]]:
    """(name, shown place) of the staged rows, front and back, as the table lists them."""
    return [(s.name(r.entrant_id), r.place_text) for r in s.screen().rows if r.staged]


def test_place_last_marks_from_the_back_and_numbers_from_the_field_left(store, make_race, ids):
    s = chase(store, make_race)
    assert s.rider_actions(ids[9])[0] == (rc.PLACE_LAST, "Place Last")
    assert not s.screen().rest_together, "nobody placed yet"
    ok(s.act(ids[9], "place_last"))
    assert s.state == "setup" and s.state_label() == "Racing"
    assert staged_rows(s) == [("Ben Szymanski", "4")]
    assert s.undo_text() == "Undo: #9 Ben Szymanski placed 4th"
    screen = s.screen()
    assert "Ben Szymanski" not in live_names(s)
    assert screen.rest_together
    # A second Place Last is not offered; Undo is the way back.
    assert rc.PLACE_LAST not in [k for k, _ in s.rider_actions(ids[9])]
    refused = s.act(ids[9], "place_last")
    assert (
        not refused.ok
        and refused.message == "Ben Szymanski already has a place. Undo takes it back."
    )
    ok(s.act(ids[33], "place_last"))
    assert staged_rows(s) == [("Jack Moreau", "3"), ("Ben Szymanski", "4")]
    assert s.undo_text() == "Undo: #33 Jack Moreau placed 3rd"
    ok(s.click(ids[7]))
    assert staged_rows(s) == [("Maya Petrakis", "1"), ("Jack Moreau", "3"), ("Ben Szymanski", "4")]
    assert s.undo_text() == "Undo: #7 Maya Petrakis placed 1st"
    assert live_names(s) == ["Tess Gallagher"]
    # The tail is on disk with the front.
    again = LiveRace(store, s.race_id)
    assert again.staged() == [[ids[7]]] and again.staged_tail() == [[ids[9]], [ids[33]]]
    assert staged_rows(again) == staged_rows(s)
    # Undo takes one mark back at a time, in order.
    ok(s.undo())
    assert staged_rows(s) == [("Jack Moreau", "3"), ("Ben Szymanski", "4")]
    ok(s.undo())
    assert staged_rows(s) == [("Ben Szymanski", "4")]
    assert s.undo_text() == "Undo: #9 Ben Szymanski placed 4th"
    ok(s.undo())
    assert staged_rows(s) == [] and s.state_label() == "Start list"


def test_a_dnf_after_a_mark_from_the_back_closes_the_places_up(store, make_race, ids):
    s = chase(store, make_race)
    ok(s.act(ids[9], "place_last"))
    ok(s.act(ids[33], "place_last"))
    ok(s.act(ids[12], "dnf"))
    assert s.state == "running"
    assert staged_rows(s) == [("Jack Moreau", "2"), ("Ben Szymanski", "3")]
    # A rider marked from the back who is then disqualified drops out of the tail.
    ok(s.act(ids[33], "dq"))
    assert staged_rows(s) == [("Ben Szymanski", "2")]
    assert LiveRace(store, s.race_id).staged_tail() == [[ids[9]]]


def test_the_front_and_the_back_meeting_records_the_finish(store, make_race, ids):
    s = chase(store, make_race)
    ok(s.act(ids[9], "place_last"))
    ok(s.click(ids[33]))
    ok(s.click(ids[7]))
    assert s.state == "setup"
    out = ok(s.act(ids[12], "place_last"))
    assert s.state == "provisional"
    assert out.message == (
        "Recorded Finish: 1st #33 Jack Moreau, 2nd #7 Maya Petrakis,"
        " 3rd #12 Tess Gallagher, 4th #9 Ben Szymanski"
    )
    assert ranks(s) == {
        "Jack Moreau": 1,
        "Maya Petrakis": 2,
        "Tess Gallagher": 3,
        "Ben Szymanski": 4,
    }
    assert s.undo_text() == "Undo: #12 Tess Gallagher placed 3rd"
    ok(s.undo())
    assert s.state == "setup" and s.rows() == []
    assert staged_rows(s) == [("Jack Moreau", "1"), ("Maya Petrakis", "2"), ("Ben Szymanski", "4")]
    # The front click that meets the back completes it too.
    ok(s.click(ids[12]))
    assert s.state == "provisional" and s.undo_text() == "Undo: #12 Tess Gallagher placed 3rd"
    assert [r.place_text for r in s.screen().rows] == ["1", "2", "3", "4"]


def test_a_dnf_that_makes_the_front_and_back_cover_everyone_completes(store, make_race, ids):
    s = chase(store, make_race)
    ok(s.act(ids[9], "place_last"))
    ok(s.click(ids[33]))
    ok(s.act(ids[7], "dnf"))
    assert s.state == "running"
    ok(s.act(ids[12], "dnf"))
    assert s.state == "provisional"
    assert [(r.entry.names[0], r.place_text) for r in s.screen().rows] == [
        ("Jack Moreau", "1"),
        ("Ben Szymanski", "2"),
        ("Maya Petrakis", "DNF"),
        ("Tess Gallagher", "DNF"),
    ]
    # Marks from the back alone cover the field once the rest leave.
    t = chase(store, make_race, (7, 12, 33))
    ok(t.act(ids[33], "place_last"))
    ok(t.act(ids[12], "place_last"))
    ok(t.act(ids[7], "dnf"))
    assert t.state == "provisional"
    assert ranks(t) == {"Tess Gallagher": 1, "Jack Moreau": 2, "Maya Petrakis": 3}


def test_place_the_rest_together_gives_the_middle_an_equal_placing(store, make_race, ids):
    s = chase(store, make_race, (7, 12, 33, 9, 19, 24, 3))
    assert not s.screen().rest_together
    refused = s.place_rest_together()
    assert not refused.ok and refused.message == "Place at least one rider first."
    ok(s.click(ids[33]))
    ok(s.click(ids[7]))
    ok(s.act(ids[3], "place_last"))
    ok(s.act(ids[24], "place_last"))
    assert s.screen().rest_together
    out = ok(s.place_rest_together())
    assert s.state == "provisional"
    assert out.message == (
        "Recorded Finish: 1st #33 Jack Moreau, 2nd #7 Maya Petrakis,"
        " 3rd #9 Ben Szymanski = #12 Tess Gallagher = #19 Omar Rahimi,"
        " 6th #24 Kenji Mori, 7th #3 Marcus Delgado"
    )
    assert [r.place_text for r in s.screen().rows] == ["1", "2", "3", "3", "3", "6", "7"]
    assert ranks(s) == {
        "Jack Moreau": 1,
        "Maya Petrakis": 2,
        "Ben Szymanski": 3,
        "Tess Gallagher": 3,
        "Omar Rahimi": 3,
        "Kenji Mori": 6,
        "Marcus Delgado": 7,
    }
    # A tied group, as a dead heat is: no note about the judges.
    assert all(not r.notes for r in s.standings().rows)
    assert s.undo_text() == rc.UNDO_REST == "Undo: the rest placed together"
    assert not s.screen().rest_together
    ok(s.undo())
    assert s.state == "setup" and s.rows() == []
    assert s.staged() == [[ids[33]], [ids[7]]]
    assert s.staged_tail() == [[ids[3]], [ids[24]]]
    assert s.undo_text() == "Undo: #24 Kenji Mori placed 6th"
    assert s.screen().rest_together


def test_place_the_rest_together_is_offered_only_while_two_or_more_are_unplaced(
    store, make_race, ids, house
):
    s = chase(store, make_race)
    ok(s.click(ids[7]))
    ok(s.act(ids[9], "place_last"))
    assert s.screen().rest_together
    ok(s.click(ids[12]))
    assert not s.screen().rest_together
    refused = s.place_rest_together()
    assert not refused.ok and refused.message == "Only one rider is left to place."
    e = LiveRace(store, make_race("elimination", [3, 5, 7, 8], house.elimination()))
    ok(e.click(ids[3]))
    assert not e.screen().rest_together
    assert rc.PLACE_LAST not in [k for k, _ in e.rider_actions(ids[5])]
    refused = e.act(ids[5], "place_last")
    assert refused.message == "Place Last applies to a race scored by its finish order."
    assert not e.place_rest_together().ok
    p = points_race(store, make_race, house)
    ok(p.click(ids[12]))
    assert not p.screen().rest_together
    assert rc.PLACE_LAST not in [k for k, _ in p.rider_actions(ids[7])]


def test_a_reopened_finish_is_corrected_from_the_front_alone(store, make_race, ids, house):
    p = points_race(store, make_race, house)
    ok(p.click(ids[12]))
    ok(p.record_sprint())
    for bib in (7, 12, 33):
        ok(p.click(ids[bib]))
    assert p.state == "provisional"
    ok(p.reopen_sprint(2))
    assert p.task().editing
    screen = p.screen()
    assert not screen.rest_together
    assert all(rc.PLACE_LAST not in [k for k, _ in c.actions] for c in screen.cards)
    assert not p.act(ids[33], "place_last").ok
    ok(p.click(ids[7]))  # off
    ok(p.click(ids[7]))  # last
    ok(p.record_sprint())
    assert p.state == "provisional"
    assert ranks(p)["Tess Gallagher"] == 1


def test_place_last_is_refused_outside_its_conditions(store, make_race, ids):
    s = chase(store, make_race)
    ok(s.act(ids[12], "dnf"))
    refused = s.act(ids[12], "place_last")
    assert refused.message == "Tess Gallagher is DNF. Undo takes it back."
    assert s.act(999, "place_last").message == "Not in this race."
    for bib in (7, 33):
        ok(s.click(ids[bib]))
    ok(s.act(ids[9], "place_last"))
    assert s.state == "provisional"
    refused = s.act(ids[9], "place_last")
    assert refused.message == "The result is recorded. Use the row's menu to change it."
    ok(s.mark_final())
    assert s.act(ids[9], "place_last").message == rc.FINAL_TEXT
    assert s.place_rest_together().message == rc.FINAL_TEXT


def test_a_lap_that_drops_the_last_unplaced_rider_completes_the_finish(store, make_race, ids):
    """With "Lapped riders are placed by laps down" off, the engine marks a
    lapped rider DNF; a lap recorded with the rest placed completes the
    finish rather than leaving the race with no cards and no button."""
    rules = R.PlacingsRules(laps_count_for_ranking=True, lapped_riders_placed_by_laps=False)
    s = LiveRace(store, make_race("chase", [7, 12, 33], rules))
    ok(s.click(ids[7]))
    ok(s.act(ids[33], "place_last"))
    ok(s.act(ids[12], "lap_lost"))
    assert s.state == "provisional"
    assert [(r.place_text, r.entry.names[0]) for r in s.screen().rows] == [
        ("1", "Maya Petrakis"),
        ("2", "Jack Moreau"),
        ("DNF", "Tess Gallagher"),
    ]
    assert s.undo_text() == "Undo: #12 Tess Gallagher lost a lap"
    ok(s.undo())
    assert s.state == "setup" and [r.place_text for r in s.screen().rows] == ["1", "3"]


def test_empty_field_and_final_race_refuse_clicks(store, make_race, ids):
    s = chase(store, make_race, ())
    assert s.task().kind == "none" and s.task().text == rc.EMPTY_FIELD
    assert not s.click(ids[7]).ok
    s = chase(store, make_race, (7, 12))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    ok(s.mark_final())
    assert s.state_label() == "Final" and s.task().text == rc.FINAL_TEXT
    assert not s.click(ids[7]).ok and not s.undo().ok and not s.act(ids[7], "dq").ok
    screen = s.screen()
    assert screen.reopen and not screen.mark_final and not screen.undo_enabled
    assert screen.undo_text == rc.REOPEN_FIRST == "Reopen First to Undo"
    ok(s.reopen())
    assert s.state == "provisional"


def test_a_field_with_a_rider_without_a_bib_waits_for_the_roster(store, make_race, ids, event):
    """A bib is required to score, never to register (design section 6)."""
    event_id = event[0]
    store.change_bib(event_id, ids[9], None)
    store.change_bib(event_id, ids[33], None)
    s = chase(store, make_race)
    line = "2 riders have no bib. Edit Event > Roster."
    task = s.task()
    assert (task.kind, task.text, task.stages) == ("blocked", line, False)
    assert s.state_label() == "Start list"
    assert s.click(ids[7]) == rc.Outcome(False, line)
    assert s.rider_actions(ids[7]) == [] and s.act(ids[7], "dns") == rc.Outcome(False, line)
    assert s.staged() == [] and store.live_actions(s.race_id) == []
    screen = s.screen()
    # Every rider still shows, the bibless last, so the scorer sees who lacks one.
    assert [c.entry.bibs for c in screen.cards] == [["7"], ["12"], [], []]
    assert all(c.actions == () and c.badge is None for c in screen.cards)
    assert s.label(ids[33]) == "Jack Moreau", "a rider without a bib is named alone"
    store.change_bib(event_id, ids[9], 9)
    s.reload()
    assert s.task().text == "1 rider has no bib. Edit Event > Roster."
    store.change_bib(event_id, ids[33], 33)
    s.reload()
    assert s.task().kind == "order"
    ok(s.click(ids[7]))


def test_points_race_without_bibs_shows_record_sprint_disabled(store, make_race, ids, event, house):
    store.change_bib(event[0], ids[9], None)
    s = LiveRace(store, make_race("points", [7, 12, 9], house.points(3)))
    screen = s.screen()
    assert screen.record and not screen.record_enabled
    assert s.record_sprint() == rc.Outcome(False, "1 rider has no bib. Edit Event > Roster.")


def test_a_bib_twice_in_one_field_is_refused_and_scoring_waits(store, make_race, ids, event):
    """Riders in different races may share a number; one race's field may not."""
    from madtracker.control.roster import EntryError, bib_clash

    event_id = event[0]
    other = make_race("chase", [5], R.placings_rules(), name="Other")
    s = chase(store, make_race, (7, 12))
    # A number worn in another race is no clash here.
    late = store.add_rider("Cy", "Dorn").rider_id
    assert bib_clash(store, s.race_id, late, 5) == ""
    store.add_entry(event_id, late, 5)
    store.add_race_entry(s.race_id, late)
    di = store.add_rider("Di", "Ash").rider_id
    assert bib_clash(store, s.race_id, di, 7) == "Bib 7 is worn by Maya Petrakis in this race."
    assert bib_clash(store, s.race_id, ids[5], 5) == "Bib 5 is worn by Cy Dorn in this race."
    # A clash that came in by a group fill, or a raw store write, stops scoring.
    store.add_race_entry(s.race_id, ids[5])
    s.reload()
    line = "Bib 5 is worn by two riders in this race. Edit Event > Roster."
    assert s.task().text == line and s.click(ids[7]) == rc.Outcome(False, line)
    # A typed number never finds the wrong rider.
    with pytest.raises(EntryError, match="Bib 5 is worn by two riders in this race"):
        s.roster.resolve("5")
    store.change_bib(event_id, late, 55)
    s.reload()
    assert s.roster.resolve("5") == ids[5] and s.task().text != line
    # Outside the field, a number two riders wear tonight names neither.
    o = LiveRace(store, other)
    store.change_bib(event_id, ids[3], 7)
    o.reload()
    with pytest.raises(EntryError, match=r"^Bib 7 is not in this race$"):
        o.roster.resolve("7")


# ----- elimination ---------------------------------------------------------


def test_elimination_clicks_put_riders_out_and_the_winner_click_completes(
    store, make_race, ids, house
):
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8], house.elimination()))
    assert s.task().text == "Click the rider who is out."
    ok(s.click(ids[3]))
    assert s.state == "running" and s.state_label() == "Racing"
    assert s.undo_text() == "Undo: #3 Marcus Delgado marked Eliminated"
    screen = s.screen()
    assert [(r.place_text, r.entry.names[0]) for r in screen.rows] == [("4", "Marcus Delgado")]
    assert len(screen.cards) == 4 and live_cards(s) == [ids[5], ids[7], ids[8]]
    ok(s.click(ids[5]))
    assert s.task().text == "Click the winner." and s.state_label() == "Final sprint"
    assert s.click(ids[3]) == rc.Outcome(False, "#3 Marcus Delgado is already out (4th).")
    ok(s.click(ids[8]))
    assert s.state == "provisional"
    assert ranks(s) == {
        "Tom Kowalczyk": 1,
        "Maya Petrakis": 2,
        "Priya Okafor": 3,
        "Marcus Delgado": 4,
    }
    assert s.log_rows()[-1].text == "Final sprint: 1st #8 Tom Kowalczyk, 2nd #7 Maya Petrakis"
    # Review: the bell's places move too, and the final sprint's rows.
    assert [k for k, _ in s.review_actions(ids[3])] == ["move_up", "tie_above", "dq"]
    assert [k for k, _ in s.review_actions(ids[7])] == ["move_up", "tie_above", "dq"]
    assert [k for k, _ in s.review_actions(ids[8])] == ["move_down", "tie_below", "dq"]
    ok(s.review(ids[7], "move_up"))
    assert ranks(s)["Maya Petrakis"] == 1 and ranks(s)["Tom Kowalczyk"] == 2
    assert s.undo_text() == rc.undo_moved(s.label(ids[7]), "up")
    ok(s.undo())
    assert ranks(s)["Tom Kowalczyk"] == 1, "undo of a correction puts the original back"
    assert s.state == "provisional"


def placed(s: LiveRace) -> dict[str, int]:
    """Name to rank for the rows that hold a place."""
    return {name: rank for name, rank in ranks(s).items() if rank is not None}


def test_a_missed_out_is_clicked_late_and_moved_to_where_it_belongs(store, make_race, ids, house):
    """A missed out is fixed where it is, not by undoing back to it: the
    bell's places move while the race runs, as one correction that
    renumbers the sprints."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    for bib in (3, 7, 8):
        ok(s.click(ids[bib]))
    # Priya (5) went out between Marcus (3) and Maya (7) and nobody clicked.
    ok(s.click(ids[5]))
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    assert rows["Priya Okafor"].place_text == "3" and s.state == "running"
    assert [label for _, label in rows["Priya Okafor"].actions] == [
        "Move Down", "Move to 4th", "Move to 5th", "Move to 6th", "Tie with the Rider Below", "Disqualify"
    ]  # fmt: skip
    assert [label for _, label in rows["Marcus Delgado"].actions] == [
        "Move Up", "Move to 3rd", "Move to 4th", "Move to 5th", "Tie with the Rider Above", "Disqualify"
    ]  # fmt: skip
    ok(s.review(ids[5], "move_to:2"))
    assert placed(s) == {
        "Tom Kowalczyk": 3,
        "Maya Petrakis": 4,
        "Priya Okafor": 5,
        "Marcus Delgado": 6,
    }
    assert s.undo_text() == rc.undo_moved(s.label(ids[5]), "to 5th")
    # The log replays the corrected order with the sprints renumbered.
    outs = [(a.sprint_no, a.entrant_ids) for a in s.actions() if isinstance(a, Eliminated)]
    assert outs == [(1, (ids[3],)), (2, (ids[5],)), (3, (ids[7],)), (4, (ids[8],))]
    # Two are left, so the next click names the winner.
    assert s.task().text == "Click the winner."
    assert set(s.standings().remaining_entrants) == {ids[9], ids[12]}
    # One step at a time works too, and Undo walks it all back.
    ok(s.review(ids[5], "move_up"))
    assert ranks(s)["Priya Okafor"] == 4 and ranks(s)["Maya Petrakis"] == 5
    ok(s.review(ids[5], "move_down"))
    assert ranks(s)["Priya Okafor"] == 5
    for _ in range(3):
        ok(s.undo())
    assert placed(s)["Priya Okafor"] == 3 and placed(s)["Tom Kowalczyk"] == 4
    assert s.state == "running"
    # The survivors' places do not move until the result is complete: a
    # survivor's row would offer the card's own actions and no move.
    assert [k for k, _ in s.review_actions(ids[9])] == ["dns", "dnf", "dq"]
    assert not s.review(ids[9], "move_up").ok


def test_the_logbook_names_an_out_that_moved(store, make_race, ids, house):
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    for bib in (3, 7, 8, 5):
        ok(s.click(ids[bib]))
    ok(s.review(ids[5], "move_to:2"))
    lines = [r.text for r in s.log_rows() if not r.voided]
    assert any(t.startswith("Moved #5 Priya Okafor to 5th\nEliminated: ") for t in lines), lines
    assert "Replaced: Eliminated: #7 Maya Petrakis" in lines


def test_two_outs_share_a_bell_and_split_again(store, make_race, ids, house):
    """Two riders out at one sprint (USAC 2E3(d)(i)) share the place; the
    second of the pair can take a place of its own again (Break Tie)."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], house.elimination()))
    for bib in (3, 7, 8):
        ok(s.click(ids[bib]))
    ok(s.review(ids[7], "tie_above"))
    assert ranks(s)["Tom Kowalczyk"] == 3 and ranks(s)["Maya Petrakis"] == 3
    assert ranks(s)["Marcus Delgado"] == 5
    assert s.undo_text() == rc.undo_tied(s.label(ids[7]), s.label(ids[8]))
    outs = [(a.sprint_no, set(a.entrant_ids)) for a in s.actions() if isinstance(a, Eliminated)]
    assert outs == [(1, {ids[3]}), (2, {ids[7], ids[8]})]
    rows = [r for r in s.screen().rows if r.place_text == "3"]
    assert [r.tied for r in rows] == [True, True]
    first, second = (r.entrant_id for r in rows)
    assert [k for k, _ in s.review_actions(second)] == ["move_up", "move_down", "tie_below", "dq"]
    ok(s.review(second, "move_up"))
    assert ranks(s)[s.name(second)] == 3 and ranks(s)[s.name(first)] == 4
    ok(s.undo())
    ok(s.undo())
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}


def test_two_outs_at_one_bell_tie_from_the_lower_row(store, make_race, ids, house):
    """The outs list last out first, so the second rider clicked out takes
    the better place and sits above the first; the tie is on the lower
    row, the first rider's."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], house.elimination()))
    for bib in (3, 7, 8):
        ok(s.click(ids[bib]))
    rows = [(r.place_text, r.entrant_id) for r in s.screen().rows]
    assert rows == [("3", ids[8]), ("4", ids[7]), ("5", ids[3])]
    assert "tie_above" not in [k for k, _ in s.review_actions(ids[8])]
    assert "tie_above" in [k for k, _ in s.review_actions(ids[7])]
    ok(s.review(ids[7], "tie_above"))
    assert ranks(s)["Tom Kowalczyk"] == 3 and ranks(s)["Maya Petrakis"] == 3
    assert s.undo_text() == rc.undo_tied(s.label(ids[7]), s.label(ids[8]))


def test_a_status_marked_while_a_sprint_is_open_keeps_its_undo_after_cancel(
    store, make_race, ids, house
):
    """The DNF is in the log whether the correction is kept or not, so Undo still reaches it."""
    p = LiveRace(store, make_race("points", [3, 5, 7, 8], house.points(2)))
    for bib in (3, 5, 7):
        ok(p.click(ids[bib]))
    ok(p.record_sprint())
    ok(p.reopen_sprint(1))
    ok(p.act(ids[8], "dnf"))
    p.cancel_edit()
    assert p.standings().by_entrant(ids[8]).status == "DNF"
    assert p.undo_text() == f"{rc.UNDO}#8 {p.name(ids[8])} {rc.UNDO_WORDS['dnf']}"
    ok(p.undo())
    assert p.standings().by_entrant(ids[8]).status is None
    assert not p._staged.editing, "undoing the DNF does not reopen the cancelled correction"
    assert p.standings().by_entrant(ids[3]).total_points == 10, "Sprint 1 stands"


def test_a_sheet_reads_the_settled_state_and_writes_nothing(store, make_race, ids, house):
    """An export or a standings must never move a race's state or stamp a change at export time."""
    p = LiveRace(store, make_race("points", [3, 5, 7], house.points(2)))
    for bib in (3, 5, 7):
        ok(p.click(ids[bib]))
    ok(p.record_sprint())
    # The final sprint completes on its last click.
    for bib in (3, 5, 7):
        ok(p.click(ids[bib]))
    assert p.state == "provisional"
    # A file another tool wrote, or an earlier build that judged it differently.
    store.set_state(p.race_id, "running")
    changes = len(store.state_changes(p.race_id))
    read = LiveRace(store, p.race_id, settle=False)
    assert read.state == "provisional" and read.standings().is_complete
    assert store.race(p.race_id).state == "running"
    assert len(store.state_changes(p.race_id)) == changes
    assert LiveRace(store, p.race_id).state == "provisional", "the scoring window settles it"
    assert store.race(p.race_id).state == "provisional"


def test_a_rider_marked_dnf_can_still_be_disqualified_from_the_row(store, make_race, ids, house):
    """USAC 1P1: a protest can disqualify a rider who had already left the
    race. The DNF row offers Disqualify alone; the DQ replaces the mark
    without undoing the DNF, and Undo puts the DNF back."""
    p = LiveRace(store, make_race("points", [3, 5, 7, 8], house.points(2)))
    for bib in (3, 5, 7):
        ok(p.click(ids[bib]))
    ok(p.record_sprint())
    ok(p.act(ids[5], "dnf"))
    assert p.review_actions(ids[5]) == [("dq", "Disqualify")]
    ok(p.reopen_sprint(1))
    assert p.review_actions(ids[5]) == []
    assert p.review(ids[5], "dq") == rc.Outcome(False, rc.CORRECTION_OPEN)
    p.cancel_edit()
    ok(p.review(ids[5], "dq"))
    assert p.standings().by_entrant(ids[5]).status == "DQ"
    assert p.review_actions(ids[5]) == []
    assert p.review(ids[5], "dq") == rc.Outcome(
        False, "Priya Okafor is already DQ. Undo takes it back."
    )
    ok(p.undo())
    assert p.standings().by_entrant(ids[5]).status == "DNF"


def test_a_rider_out_by_dnf_keeps_its_moment_and_outs_move_past_it(store, make_race, ids, house):
    """A DNF is out at that moment (USAC 2E4): its row has no menu, an out
    cannot share its place, and an out may be moved past it."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], house.elimination()))
    ok(s.click(ids[3]))
    ok(s.act(ids[7], "dnf"))
    ok(s.click(ids[8]))
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    # Out of the race, the row offers one thing: a DQ after a protest.
    assert rows["Maya Petrakis"].actions == (("dq", "Disqualify"),)
    assert [k for k, _ in rows["Tom Kowalczyk"].actions] == ["move_down", "move_to:1", "move_to:2", "dq"]  # fmt: skip
    assert "tie_above" not in [k for k, _ in rows["Marcus Delgado"].actions]
    assert not s.review(ids[8], "tie_above").ok
    ok(s.review(ids[8], "move_to:2"))
    assert placed(s) == {"Maya Petrakis": 3, "Marcus Delgado": 4, "Tom Kowalczyk": 5}
    assert s.standings().by_entrant(ids[7]).status == "DNF"
    ok(s.undo())
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}


def test_a_move_rewrites_only_the_outs_from_the_first_change(store, make_race, ids, house):
    """A move voids only from the first change: the rows before it keep
    their ids, and the numbers count on from them."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    for bib in (3, 7, 8, 5):
        ok(s.click(ids[bib]))
    before = {r.action_id: r for r in s.rows() if r.kind == Eliminated.kind}
    ok(s.review(ids[5], "move_down"))
    after = {r.action_id: r for r in s.rows() if r.kind == Eliminated.kind}
    kept = set(before) & set(after)
    assert len(kept) == 2, "the first two outs stand as they were"
    assert sorted(a.sprint_no for a in s.actions() if isinstance(a, Eliminated)) == [1, 2, 3, 4]
    replaced = [r.text for r in s.log_rows() if r.text.startswith("Replaced")]
    assert len(replaced) == 2, replaced


def test_a_dnf_on_a_rider_already_out_is_only_the_mark_whatever_the_log_order(
    store, make_race, ids, house
):
    """A DNF marked on an out rider stays the mark after a move re-appends
    the bell's rows: the bell's row places the rider, never the DNF."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], house.elimination()))
    for bib in (3, 7, 8):
        ok(s.click(ids[bib]))
    # The out row offers no DNF, so the mark goes in as an entry.
    ok(s._record([Status(entrant_id=ids[7], status="DNF")]))
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}
    ok(s.review(ids[8], "move_down"))
    assert placed(s) == {"Maya Petrakis": 3, "Tom Kowalczyk": 4, "Marcus Delgado": 5}
    assert s.standings().by_entrant(ids[7]).status == "DNF"
    ok(s.undo())
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}
    ok(s.review(ids[8], "move_to:2"))
    assert placed(s) == {"Maya Petrakis": 3, "Marcus Delgado": 4, "Tom Kowalczyk": 5}


def test_a_disqualified_riders_own_bell_survives_a_move(store, make_race, ids, house):
    """The row of an out whose every rider is DQ'd keeps its place in the
    log when its neighbor moves."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    for bib in (3, 9, 7, 8):
        ok(s.click(ids[bib]))
    ok(s.act(ids[9], "dq"))
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}
    ok(s.review(ids[3], "move_to:0"))
    assert placed(s) == {"Marcus Delgado": 3, "Tom Kowalczyk": 4, "Maya Petrakis": 5}
    outs = [a.entrant_ids for a in s.actions() if isinstance(a, Eliminated)]
    assert (ids[9],) in outs, "the DQ'd rider's out is still on record"
    assert [o for o in outs if o != (ids[9],)] == [(ids[7],), (ids[8],), (ids[3],)]
    ok(s.review(ids[7], "tie_above"))
    assert (ids[9],) in [a.entrant_ids for a in s.actions() if isinstance(a, Eliminated)]
    ok(s.undo())
    ok(s.undo())
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}


def test_a_dq_after_a_dnf_out_survives_a_move_and_its_undo(store, make_race, ids, house):
    """A DQ that replaced a DNF out leaves the rider no place: a move of
    another out neither counts the DNF as an out nor writes it again
    after the DQ, and Undo of the move leaves the DQ standing."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    ok(s.click(ids[3]))
    ok(s.act(ids[5], "dnf"))
    ok(s.click(ids[7]))
    ok(s.act(ids[5], "dq"))
    assert placed(s) == {"Maya Petrakis": 4, "Marcus Delgado": 5}
    row = next(r for r in s.screen().rows if r.entrant_id == ids[7])
    assert [k for k, _ in row.actions if k.startswith("move")] == ["move_down"]
    ok(s.review(ids[7], "move_down"))
    assert placed(s) == {"Marcus Delgado": 4, "Maya Petrakis": 5}
    assert s.standings().by_entrant(ids[5]).status == "DQ"
    ok(s.undo())
    assert placed(s) == {"Maya Petrakis": 4, "Marcus Delgado": 5}
    assert s.standings().by_entrant(ids[5]).status == "DQ"


def test_a_moved_out_moves_back_after_the_survivors_are_disqualified(store, make_race, ids, house):
    """A move of the outs changes their order, never who is out, so the
    riders left after the last out are the same before and after it. With
    every survivor DQ'd after the finish, an out moved down moves back up,
    and the places are as they were."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    ok(s.act(ids[9], "dnf"))
    ok(s.act(ids[3], "dnf"))
    ok(s.act(ids[12], "dq"))
    ok(s.click(ids[7]))
    ok(s.click(ids[5]))
    assert s.standings().is_complete
    ok(s.review(ids[8], "dq"))
    ok(s.review(ids[5], "dq"))
    before = placed(s)
    ok(s.review(ids[7], "move_down"))
    assert placed(s) != before
    ok(s.review(ids[7], "move_up"))
    assert placed(s) == before


def test_a_tie_splits_after_the_survivors_are_disqualified(store, make_race, ids, house):
    """A split keeps who is out: two tied outs split once both riders left
    at the finish are DQ'd."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    for bib in (3, 7, 8, 5):
        ok(s.click(ids[bib]))
    ok(s.review(ids[8], "tie_above"))
    ok(s.click(ids[9]))
    assert s.standings().is_complete
    for bib in (9, 12):
        ok(s.review(ids[bib], "dq"))
    tied = [r.entrant_id for r in s.screen().rows if r.tied]
    assert len(tied) == 2
    ok(s.review(tied[1], "move_up"))
    assert not [r for r in s.screen().rows if r.tied]


def test_undo_puts_a_corrections_rows_back_at_their_place_in_the_log(store, make_race, ids, house):
    """A DNF out is the moment its row sits in the log. A DQ replaces it, a
    move of another out rewrites the outs, and two Undos later the DNF is
    the third out again, not the first: Undo writes the rows it restores
    back in their order, with every row after them, so the bells stand
    before the DNF as they did."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    ok(s.click(ids[3]))
    ok(s.click(ids[7]))
    ok(s.act(ids[5], "dnf"))
    before = placed(s)
    assert s.standings().by_entrant(ids[5]).rank == 4
    ok(s.act(ids[5], "dq"))
    ok(s.review(ids[7], "move_down"))
    ok(s.undo())
    assert s.standings().by_entrant(ids[5]).status == "DQ"
    ok(s.undo())
    assert s.standings().by_entrant(ids[5]).status == "DNF"
    assert placed(s) == before


def replay_key(rows):
    """The live log as a replay reads it: each row's place in the order and its entry."""
    return [(rc.origin(r), r.kind, r.payload) for r in rows]


def live_before(rows, first_id):
    """The live log as it stood just before row ``first_id`` was written."""
    voided = {r.voids_action_id for r in rows if r.kind == VOID_KIND and r.action_id < first_id}
    return [
        r
        for r in rows
        if r.action_id < first_id and r.kind != VOID_KIND and r.action_id not in voided
    ]


def undo_exactly(s):
    """Undo, and check the live log is the one from before the action it took back."""
    rows = s.store.actions(s.race_id)
    newest = max((r.action_id for r in rows), default=0)
    unchanged = replay_key(s.rows())
    outcome = s.undo()
    if not outcome.ok:
        return outcome
    written = [r for r in s.store.actions(s.race_id) if r.action_id > newest]
    if not written:
        # A staged click or an open correction: the log is untouched.
        assert replay_key(s.rows()) == unchanged
        return outcome
    n = rc.note_parts(written[0].operator_note)[2]
    first = min(r.action_id for r in rows if rc.note_parts(r.operator_note)[1] == n)
    assert replay_key(s.rows()) == replay_key(live_before(rows, first)), outcome.message
    return outcome


def undo_action(s):
    """Undo the newest action, and a correction's own clicks with it."""
    ok(undo_exactly(s))
    while s.editing:
        ok(undo_exactly(s))
    return rc.Outcome(True, "")


def run_exactly(s, script):
    """Run ``script`` (an action, or "undo"), checking every Undo, then undo all of it."""
    for step in script:
        ok(undo_action(s) if step == "undo" else step(s))
    while undo_exactly(s).ok:
        pass
    assert s.rows() == []


def test_undo_returns_the_live_log_to_exactly_its_order_before_the_action(
    store, make_race, ids, house
):
    """After any action and its Undo the live log has the same rows in the
    same order as before it, so every replay (the result, the sheet, the
    board) is the one from before. Scripted over the corrections and
    Undos of an Elimination with DNF outs and of a Points Race, then
    undone to the empty log."""
    e = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12, 19], house.elimination()))
    run_exactly(
        e,
        [
            lambda s: s.click(ids[3]),
            lambda s: s.click(ids[7]),
            lambda s: s.act(ids[5], "dnf"),
            lambda s: s.act(ids[5], "dq"),
            lambda s: s.review(ids[7], "move_down"),
            "undo",
            "undo",
            lambda s: s.review(ids[7], "move_down"),
            lambda s: s.click(ids[8]),
            lambda s: s.review(ids[7], "tie_above"),
            lambda s: s.act(ids[9], "dnf"),
            lambda s: s.review(ids[3], "move_to:0"),
            "undo",
            lambda s: s.review(ids[8], "move_up"),
            "undo",
            "undo",
            lambda s: s.click(ids[12]),
            lambda s: s.review(ids[3], "move_up"),
            lambda s: s.click(ids[19]),
            lambda s: s.review(ids[12], "dq"),
            lambda s: s.review(ids[3], "move_down"),
            "undo",
            "undo",
        ],
    )
    p = points_race(store, make_race, house, bibs=(3, 5, 7, 8), sprints=4)
    run_exactly(
        p,
        [
            lambda s: s.click(ids[3]),
            lambda s: s.click(ids[5]),
            lambda s: s.click(ids[7]),
            lambda s: s.record_sprint(),
            lambda s: s.act(ids[5], "dnf"),
            lambda s: s.click(ids[7]),
            lambda s: s.click(ids[3]),
            lambda s: s.record_sprint(),
            lambda s: reenter(s, 1, ids, 7, 3, 5),
            lambda s: reenter(s, 2, ids, 3, 7),
            "undo",
            "undo",
            lambda s: s.act(ids[8], "lap_gained"),
            lambda s: reenter(s, 2, ids, 8, 3),
            lambda s: reenter(s, 1, ids, 5, 3),
            "undo",
            lambda s: s.click(ids[8]),
            lambda s: s.record_sprint(),
            lambda s: reenter(s, 3, ids, 3, 8),
            "undo",
            "undo",
            "undo",
        ],
    )


def test_undo_puts_the_log_back_in_its_order_after_two_corrections(store, make_race, ids, house):
    """Two corrections undone in turn leave the log as it was: each Undo
    places its rows by the row they copy, not by their own ids, which a
    first Undo has already renumbered."""
    s = points_race(store, make_race, house, bibs=(7, 12, 33), sprints=4)
    for bib in (7, 12, 33):
        clicks(s, ids, bib)
        ok(s.record_sprint())
    before = s.actions()
    ok(reenter(s, 2, ids, 7))
    ok(reenter(s, 1, ids, 33))
    for _ in range(2):
        ok(s.undo())
        while s.editing:
            ok(s.undo())
    assert s.actions() == before
    assert [rc.origin(r) for r in s.rows()] == sorted(rc.origin(r) for r in s.rows())


def test_a_dnf_before_a_sprint_stays_out_of_its_correction_after_an_undo(
    store, make_race, ids, house
):
    """A rider who left before a sprint was ridden cannot be placed in its
    correction. An Undo writes the DNF again later in the log; its moment
    is still the row it copies, so the rider stays out of the sprint."""
    s = points_race(store, make_race, house, bibs=(3, 5, 7, 8), sprints=4)
    clicks(s, ids, 3, 5, 7)
    ok(s.record_sprint())
    ok(s.act(ids[5], "dnf"))
    clicks(s, ids, 3, 7)
    ok(s.record_sprint())
    ok(s.reopen_sprint(1))
    ok(s.move_staged(ids[7], "move_up"))
    ok(s.record_sprint())
    ok(s.undo())
    dnf = next(r for r in s.rows() if r.kind == "status")
    assert "[from " in dnf.operator_note, "the Undo wrote the DNF again"
    ok(s.reopen_sprint(2))
    assert s.click(ids[5]) == rc.Outcome(False, "#5 Priya Okafor is marked Did Not Finish.")


def test_a_sprint_ridden_again_after_an_undo_to_the_start_has_its_own_moment(
    store, make_race, ids, house
):
    """The race was scored, undone to its start list, and ridden again with
    a DNF before its first sprint. The first run's rows are dead; they say
    nothing about when this run's sprint was ridden, so the rider who left
    before it cannot be placed in its correction."""
    s = points_race(store, make_race, house, bibs=(3, 5, 7, 8), sprints=4)
    clicks(s, ids, 3, 5, 7)
    ok(s.record_sprint())
    for _ in range(4):
        ok(s.undo())
    assert s.rows() == [] and s.state == "setup" and s.staged() == []
    ok(s.act(ids[5], "dnf"))
    clicks(s, ids, 3)
    ok(s.record_sprint())
    ok(s.reopen_sprint(1))
    assert s.click(ids[5]) == rc.Outcome(False, "#5 Priya Okafor is marked Did Not Finish.")
    # A DNF after this run's sprint still places in its correction.
    s.cancel_edit()
    ok(s.act(ids[7], "dnf"))
    ok(s.reopen_sprint(1))
    ok(s.click(ids[7]))
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[7]).sprint_points[0] > 0
    assert s.standings().by_entrant(ids[5]).sprint_points[0] == 0


def test_a_dnf_replaced_by_a_dq_is_no_out_for_a_move(store, make_race, ids, house):
    """A DQ on a rider out by DNF replaces the mark: the DNF's row is no
    longer an out, so a move neither counts it as a place nor writes it
    again after the DQ, where it would read as the later status."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    ok(s.click(ids[3]))
    ok(s.act(ids[7], "dnf"))
    ok(s.click(ids[8]))
    ok(s.act(ids[7], "dq"))
    assert placed(s) == {"Tom Kowalczyk": 4, "Marcus Delgado": 5}
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    assert [k for k, _ in rows["Tom Kowalczyk"].actions] == ["move_down", "tie_below", "dq"]
    ok(s.review(ids[8], "move_down"))
    assert placed(s) == {"Marcus Delgado": 4, "Tom Kowalczyk": 5}
    assert s.standings().by_entrant(ids[7]).status == "DQ"
    ok(s.undo())
    assert placed(s) == {"Tom Kowalczyk": 4, "Marcus Delgado": 5}
    assert s.standings().by_entrant(ids[7]).status == "DQ"


def test_a_dnf_before_the_first_out_does_not_break_a_later_move(store, make_race, ids, house):
    """A move works with a DNF unit at the head of the log."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], house.elimination()))
    ok(s.act(ids[7], "dnf"))
    ok(s.click(ids[3]))
    ok(s.click(ids[8]))
    assert placed(s) == {"Tom Kowalczyk": 3, "Marcus Delgado": 4, "Maya Petrakis": 5}
    ok(s.review(ids[8], "move_down"))
    assert placed(s) == {"Marcus Delgado": 3, "Tom Kowalczyk": 4, "Maya Petrakis": 5}
    ok(s.undo())
    assert placed(s) == {"Tom Kowalczyk": 3, "Marcus Delgado": 4, "Maya Petrakis": 5}


def test_a_tied_bell_splits_again_after_the_finish_is_recorded(store, make_race, ids, house):
    """A bell split off after the finish is in passes the finish's
    survivors check."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    for bib in (3, 7, 8):
        ok(s.click(ids[bib]))
    ok(s.review(ids[7], "tie_above"))
    ok(s.click(ids[5]))
    ok(s.click(ids[9]))
    assert s.state == "provisional"
    tied = [r.entrant_id for r in s.screen().rows if r.tied]
    assert len(tied) == 2
    ok(s.review(tied[1], "move_up"))
    assert not [r for r in s.screen().rows if r.tied]
    assert s.state == "provisional" and s.standings().is_complete
    ok(s.undo())
    # Out of the tie into the last bell's place: 5th, with the first out 6th.
    ok(s.review(tied[1], "move_to:2"))
    assert placed(s)[s.name(tied[1])] == 5 and placed(s)["Marcus Delgado"] == 6
    ok(s.undo())
    assert [r.entrant_id for r in s.screen().rows if r.tied] == tied


def test_a_dq_between_the_bells_does_not_block_a_move(store, make_race, ids, house):
    """The DQ'd rider's hidden bell, re-recorded after the DQ mark, is not
    refused as "cannot be placed"."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    ok(s.click(ids[3]))
    ok(s.click(ids[9]))
    ok(s.act(ids[9], "dq"))
    ok(s.click(ids[7]))
    ok(s.click(ids[8]))
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}
    ok(s.review(ids[8], "move_to:2"))
    assert placed(s) == {"Maya Petrakis": 3, "Marcus Delgado": 4, "Tom Kowalczyk": 5}
    assert s.standings().by_entrant(ids[9]).status == "DQ"
    ok(s.undo())
    assert placed(s) == {"Tom Kowalczyk": 3, "Maya Petrakis": 4, "Marcus Delgado": 5}


def test_a_move_keeps_a_half_staged_final_sprint(store, make_race, ids):
    """A move while the final sprint is half clicked keeps the staged clicks."""
    rules = R.elimination_rules(survivors=3)
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], rules))
    ok(s.click(ids[3]))
    ok(s.click(ids[7]))
    assert s.task().text == "Final sprint: click riders in the order they finish."
    ok(s.click(ids[9]))
    assert s.staged() == [[ids[9]]]
    ok(s.review(ids[7], "move_down"))
    assert placed(s) == {"Marcus Delgado": 4, "Maya Petrakis": 5}
    assert s.staged() == [[ids[9]]], "the final sprint's clicks stay"
    ok(s.click(ids[5]))
    ok(s.click(ids[8]))
    assert s.state == "provisional" and placed(s)["Ben Szymanski"] == 1


def test_outs_move_again_after_a_correction_put_bells_after_the_finish(
    store, make_race, ids, house
):
    """Once a move or an Undo re-appends bells after the finish order, a
    move of a bell still before it is not refused as riders "still in":
    the finish counts every bell wherever it stands."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], house.elimination()))
    for bib in (3, 7, 8):
        ok(s.click(ids[bib]))
    ok(s.click(ids[5]))
    assert s.state == "provisional"
    ok(s.review(ids[8], "move_down"))
    ok(s.review(ids[3], "move_to:0"))
    assert placed(s) == {"Priya Okafor": 1, "Ben Szymanski": 2, "Marcus Delgado": 3, "Maya Petrakis": 4, "Tom Kowalczyk": 5}  # fmt: skip
    ok(s.undo())
    ok(s.undo())
    ok(s.review(ids[8], "move_down"))
    ok(s.undo())
    ok(s.review(ids[3], "move_up"))
    assert placed(s)["Marcus Delgado"] == 4 and placed(s)["Maya Petrakis"] == 5
    ok(s.undo())
    t = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9, 12], house.elimination()))
    for bib in (3, 7, 8, 5):
        ok(t.click(ids[bib]))
    ok(t.click(ids[9]))
    ok(t.review(ids[8], "tie_above"))
    ok(t.review(ids[3], "move_up"))
    assert placed(t)["Marcus Delgado"] == 5 and placed(t)["Maya Petrakis"] == 6


def test_a_tied_bell_before_a_dnf_splits_after_the_finish(store, make_race, ids, house):
    """With the finish recorded, a tie that stood before a DNF splits; the
    DNF, re-appended with the bells, is still an out the finish counts and
    not a DNF after the finish."""
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], house.elimination()))
    ok(s.click(ids[8]))
    ok(s.click(ids[7]))
    ok(s.review(ids[8], "tie_above"))
    ok(s.act(ids[3], "dnf"))
    ok(s.click(ids[5]))
    assert s.state == "provisional"
    assert placed(s) == {"Priya Okafor": 1, "Ben Szymanski": 2, "Marcus Delgado": 3, "Maya Petrakis": 4, "Tom Kowalczyk": 4}  # fmt: skip
    ok(s.review(ids[7], "move_up"))
    assert placed(s) == {"Priya Okafor": 1, "Ben Szymanski": 2, "Marcus Delgado": 3, "Maya Petrakis": 4, "Tom Kowalczyk": 5}  # fmt: skip
    assert s.standings().by_entrant(ids[3]).status == "DNF"
    ok(s.undo())
    assert placed(s)["Tom Kowalczyk"] == 4 and placed(s)["Maya Petrakis"] == 4


def test_elimination_with_more_survivors_stages_a_final_sprint(store, make_race, ids):
    rules = R.elimination_rules(survivors=3)
    s = LiveRace(store, make_race("elimination", [3, 5, 7, 8, 9], rules))
    ok(s.click(ids[3]))
    ok(s.click(ids[5]))
    assert s.task().text == "Final sprint: click riders in the order they finish."
    assert s.state_label() == "Final sprint"
    ok(s.click(ids[9]))
    assert s.screen().rows[0].entry.names == ["Ben Szymanski"] and s.screen().rows[0].staged
    ok(s.click(ids[8]))
    ok(s.click(ids[7]))
    assert s.state == "provisional"
    assert [r.place_text for r in s.screen().rows] == ["1", "2", "3", "4", "5"]


def test_undo_of_an_elimination_reopens_the_race_back_to_the_start_list(
    store, make_race, ids, house
):
    s = LiveRace(store, make_race("elimination", [3, 5, 7], house.elimination()))
    ok(s.click(ids[3]))
    ok(s.click(ids[7]))
    assert s.state == "provisional"
    ok(s.undo())
    assert s.state == "running" and s.task().text == "Click the winner."
    ok(s.undo())
    assert s.state == "setup" and s.undo_text() == rc.NOTHING_TO_UNDO_LABEL
    assert not s.undo().ok


# ----- points race and madison ---------------------------------------------


def test_points_race_badges_record_sprint_and_the_final_completes(store, make_race, ids, house):
    s = LiveRace(store, make_race("points", [7, 12, 33, 9], house.points(2)))
    task = s.task()
    assert task.text == "Sprint 1: click the first 6 riders in order, then Record Sprint."
    assert task.record and not task.record_enabled
    assert not s.record_sprint().ok
    ok(s.click(ids[12]))
    ok(s.click(ids[7]))
    screen = s.screen()
    badges = {c.entry.names[0]: c.badge for c in screen.cards}
    assert badges == {
        "Tess Gallagher": 1,
        "Maya Petrakis": 2,
        "Jack Moreau": None,
        "Ben Szymanski": None,
    }
    assert screen.record_enabled and screen.undo_text == "Undo: #7 Maya Petrakis placed 2nd"
    assert screen.sprint_columns == (1, 2)
    assert all(r.sprints == (None, None) for r in screen.rows)
    ok(s.click(ids[7]))  # a second click takes the badge off
    assert {c.entry.names[0]: c.badge for c in s.screen().cards}["Maya Petrakis"] is None
    ok(s.click(ids[7]))
    ok(s.record_sprint())
    assert s.state == "running" and s.undo_text() == "Undo: Sprint 1 recorded"
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    assert rows["Tess Gallagher"].sprints == (10, None) and rows["Tess Gallagher"].total == 10
    assert rows["Maya Petrakis"].sprints == (7, None)
    assert s.screen().current_sprint == 1
    ok(s.act(ids[9], "lap_gained"))
    assert rows["Ben Szymanski"].laps == 0
    assert {r.entry.names[0]: r.laps for r in s.screen().rows}["Ben Szymanski"] == 1
    assert s.task().text == "Final sprint: click every rider in order."
    assert s.state_label() == "Final sprint"
    for bib in (9, 33, 12):
        ok(s.click(ids[bib]))
    assert s.state == "running"
    ok(s.click(ids[7]))
    assert s.state == "provisional"
    assert s.standings().by_entrant(ids[9]).total_points == 10 + 20
    assert ranks(s) == {
        "Ben Szymanski": 1,
        "Tess Gallagher": 2,
        "Jack Moreau": 3,
        "Maya Petrakis": 4,
    }
    assert [k for k, _ in s.review_actions(ids[9])] == ["points_penalty", "lap_not_counted", "dq"]
    assert [k for k, _ in s.review_actions(ids[7])] == ["points_penalty", "dq"]
    assert s.screen().sprint_headers_open


def test_points_review_reopens_a_sprint_exactly_as_scored(store, make_race, ids, house):
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(2)))
    ok(s.click(ids[12]))
    ok(s.click(ids[7]))
    ok(s.record_sprint())
    for bib in (7, 12, 33):
        ok(s.click(ids[bib]))
    assert s.state == "provisional"
    ok(s.reopen_sprint(1))
    screen = s.screen()
    assert screen.task.editing and screen.task.text.startswith("Sprint 1:")
    assert not screen.review and screen.record and screen.record_enabled
    assert {c.entry.names[0]: c.badge for c in screen.cards} == {
        "Tess Gallagher": 1,
        "Maya Petrakis": 2,
        "Jack Moreau": None,
    }
    ok(s.click(ids[12]))  # off
    ok(s.click(ids[33]))
    ok(s.click(ids[12]))
    ok(s.record_sprint())
    assert s.state == "provisional" and s.task().text == rc.REVIEW_TEXT
    rows = {r.entry.names[0]: r.sprints for r in s.screen().rows}
    assert rows["Maya Petrakis"] == (10, 20) and rows["Jack Moreau"] == (7, 10)
    assert rows["Tess Gallagher"] == (5, 14)
    assert [r.text for r in s.log_rows() if r.voided] == [
        "Sprint 1: 1st #12 Tess Gallagher, 2nd #7 Maya Petrakis"
    ]
    ok(s.undo())
    assert {r.entry.names[0]: r.sprints for r in s.screen().rows}["Tess Gallagher"] == (10, 14)
    # The final sprint reopens too and needs everyone.
    ok(s.reopen_sprint(2))
    ok(s.click(ids[7]))
    refused = s.record_sprint()
    assert not refused.ok and "every rider" in refused.message
    s.cancel_edit()
    assert s.screen().review


def test_a_dead_heat_in_a_sprint_is_tied_from_the_card(store, make_race, ids, house):
    """Section 7: a points sprint is built on the cards, so the tie is there.

    The card of the rider placed just below another offers it; both
    badges then show the shared place, Undo names the tie, and the
    recorded sprint awards the shared place to both.
    """
    s = LiveRace(store, make_race("points", [7, 12, 33, 9], house.points(2)))
    ok(s.click(ids[12]))
    ok(s.click(ids[7]))
    cards = {c.entry.names[0]: c for c in s.screen().cards}
    tie = ("tie_above", "Tie with the Rider Above")
    assert cards["Maya Petrakis"].actions[:2] == (("move_up", "Move Up"), tie)
    assert tie not in cards["Tess Gallagher"].actions, "1st has nobody above"
    assert tie not in cards["Jack Moreau"].actions, "not placed"
    ok(s.act(ids[7], "tie_above"))
    cards = {c.entry.names[0]: c for c in s.screen().cards}
    assert (cards["Tess Gallagher"].badge, cards["Tess Gallagher"].tied) == (1, True)
    assert (cards["Maya Petrakis"].badge, cards["Maya Petrakis"].tied) == (1, True)
    assert tie not in cards["Maya Petrakis"].actions, "tied already"
    assert s.undo_text() == rc.undo_tied(s.label(ids[7]), s.label(ids[12]))
    ok(s.click(ids[33]))
    assert {c.entry.names[0]: c.badge for c in s.screen().cards}["Jack Moreau"] == 3
    ok(s.undo())
    ok(s.undo())
    assert {c.entry.names[0]: c.badge for c in s.screen().cards}["Maya Petrakis"] == 2
    ok(s.act(ids[7], "tie_above"))
    ok(s.record_sprint())
    rows = {r.entry.names[0]: r.sprints for r in s.screen().rows}
    assert rows["Tess Gallagher"][0] == rows["Maya Petrakis"][0] == 10
    assert s.log_rows()[-1].text == "Sprint 1: 1st #12 Tess Gallagher = #7 Maya Petrakis"
    assert not s.act(ids[33], "tie_above").ok


def test_a_team_taken_out_in_edit_race_takes_the_staged_clicks_with_it(
    store, make_race, ids, house
):
    """SQLite gives a removed team's id to the next team added, so a click kept by id
    would name another team; a save that leaves the teams alone keeps the clicks."""
    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    s = LiveRace(store, race_id)
    teams = {s.name(t): t for t in s.roster.ids}
    ok(s.click(teams["Blue"]))
    ok(s.click(teams["Red"]))
    event_id = store.race(race_id).event_id
    field = [ids[b] for b in (3, 24, 5, 36, 8, 12)]
    shapes = [(t.name, t.color, t.color_hex, t.members) for t in store.teams(race_id)]
    store.save_race(event_id, race_id, {"name": "Madison"}, field, shapes)
    s.reload()
    assert [[s.name(e) for e in g] for g in s.staged()] == [["Blue"], ["Red"]]
    # Remove Team on Blue: Red and Orange move up a place and are written again.
    store.save_race(event_id, race_id, {}, field[2:], shapes[1:])
    s.reload()
    assert s.staged() == []
    assert s.undo_text() == "Nothing to Undo"
    assert [c.badge for c in s.screen().cards] == [None, None]


def test_a_team_renamed_or_recolored_in_edit_race_keeps_the_staged_clicks(
    store, make_race, ids, house
):
    """A team is its riders, so a new name, a new color, or a new place in the list
    keeps its id, its clicks, and Undo; two teams may trade names."""
    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    s = LiveRace(store, race_id)
    teams = {s.name(t): t for t in s.roster.ids}
    ok(s.click(teams["Blue"]))
    ok(s.click(teams["Red"]))
    event_id = store.race(race_id).event_id
    field = [ids[b] for b in (3, 24, 5, 36, 8, 12)]
    blue, red, orange = ((t.name, t.color, t.color_hex, t.members) for t in store.teams(race_id))
    shapes = [("Red", *blue[1:]), ("Blue", *red[1:]), ("Comets", "Purple", None, orange[3])]
    store.save_race(event_id, race_id, {}, field, [shapes[2], shapes[0], shapes[1]])
    s.reload()
    assert [t.team_id for t in store.teams(race_id)] == [
        teams["Orange"],
        teams["Blue"],
        teams["Red"],
    ]
    assert [[s.name(e) for e in g] for g in s.staged()] == [["Red"], ["Blue"]]
    assert s.undo_text() != "Nothing to Undo"
    assert [(t.name, t.color) for t in store.teams(race_id)] == [
        ("Comets", "Purple"),
        ("Red", "Blue"),
        ("Blue", "Red"),
    ]


def test_a_rider_deleted_from_all_riders_takes_the_staged_clicks_with_it(
    store, make_race, ids, event
):
    """SQLite gives a deleted rider's id to the next rider added, who may enter the same
    race: a click kept by id would put a rider nobody clicked in the staged order."""
    s = chase(store, make_race, bibs=(7, 12, 44))
    ok(s.click(ids[44]))
    ok(s.click(ids[7]))
    store.delete_rider(ids[44])
    s.reload()
    assert s.staged() == []
    assert s.undo_text() == "Nothing to Undo"
    newcomer = store.add_rider("Ada", "Lindqvist").rider_id
    assert newcomer == ids[44]
    store.add_entry(event[0], newcomer, 45)
    store.add_race_entry(s.race_id, newcomer)
    s.reload()
    assert s.staged() == []
    assert [c.badge for c in s.screen().cards] == [None, None, None]


def test_a_rider_merged_away_takes_the_staged_clicks_with_it(store, make_race, ids):
    """The spare's id names nobody once merged, and its field place is the kept rider's,
    who was never clicked: the race starts its clicks over."""
    s = chase(store, make_race, bibs=(7, 12, 44))
    ok(s.click(ids[44]))
    ok(s.click(ids[7]))
    keep = store.add_rider("Eli", "Brandt").rider_id
    store.merge_riders(keep, ids[44])
    s.reload()
    assert keep in s.roster.ids
    assert s.staged() == []
    assert s.undo_text() == "Nothing to Undo"


def test_a_madison_card_ties_with_the_team_above(store, make_race, ids, house):
    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    s = LiveRace(store, race_id)
    teams = {s.name(t): t for t in s.roster.ids}
    ok(s.click(teams["Orange"]))
    ok(s.click(teams["Blue"]))
    card = next(c for c in s.screen().cards if c.entry.team == "Blue")
    assert card.actions[:2] == (("move_up", "Move Up"), ("tie_above", "Tie with the Team Above"))


def test_madison_teams_are_the_cards_and_the_entrants(store, make_race, ids, house):
    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    s = LiveRace(store, race_id)
    assert s.kind == "madison" and s.noun == "team"
    assert s.screen().field == f"{len(s.roster.entrants)} teams"
    assert s.task().text == "Sprint 1: click the first 4 teams in order, then Record Sprint."
    teams = {s.name(t): t for t in s.roster.ids}
    screen = s.screen()
    assert [c.entry.team for c in screen.cards] == ["Blue", "Red", "Orange"], "by lowest bib"
    assert screen.cards[0].entry.names == ["Marcus Delgado", "Kenji Mori"]
    assert [k for k, _ in screen.cards[0].actions] == [
        "dns", "dnf", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "dq"
    ]  # fmt: skip
    ok(s.click(teams["Orange"]))
    ok(s.click(teams["Blue"]))
    ok(s.record_sprint())
    assert s.log_rows()[-1].text == "Sprint 1: 1st Orange, 2nd Blue"
    assert s.task().text == "Final sprint: click every team in order."
    ok(s.act(teams["Red"], "dnf"))
    ok(s.click(teams["Blue"]))
    ok(s.click(teams["Orange"]))
    assert s.state == "provisional"
    assert ranks(s) == {"Blue": 1, "Orange": 2, "Red": 3}
    assert s.screen().rows[-1].status == "DNF"


# ----- win-and-out ---------------------------------------------------------


def test_win_and_out_staged_places_after_a_vacated_place_are_the_result(store, make_race, ids):
    """R-WIN-1: a lap winner who leaves vacates the place and the rest
    close up, in the result so far as in the result, so the finish moves
    no row the scorer has already seen."""
    s = LiveRace(store, make_race("win_and_out", [33, 7, 9, 12, 19], R.win_and_out_rules(3)))
    ok(s.click(ids[33]))
    ok(s.click(ids[7]))
    # The lap winner's row offers no DNF, so the mark goes in as an entry.
    ok(s._record([Status(entrant_id=ids[7], status="DNF")]))
    ok(s.click(ids[9]))
    ok(s.click(ids[12]))
    shown = [(r.entry.bibs[0], r.place_text, r.staged) for r in s.screen().rows]
    assert shown == [("33", "1", False), ("9", "2", False), ("12", "3", True), ("7", "DNF", False)]
    assert s.undo_text() == f"Undo: {s.label(ids[12])} placed 3rd"
    ok(s.click(ids[19]))
    assert [(r.entry.bibs[0], r.place_text) for r in s.screen().rows] == [
        ("33", "1"),
        ("9", "2"),
        ("12", "3"),
        ("19", "4"),
        ("7", "DNF"),
    ]


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("forward", {7: 1, 12: 2, 33: 3, 9: 4, 19: 5}),
        ("reverse", {7: 3, 12: 2, 33: 1, 9: 4, 19: 5}),
    ],
)
def test_win_and_out_laps_then_the_rest(store, make_race, ids, direction, expected):
    rules = R.win_and_out_rules(3, direction)
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33, 9, 19], rules))
    assert s.task().text == "Lap 1: click the winner."
    ok(s.click(ids[7]))
    assert s.state_label() == "Racing"
    want = "1st" if direction == "forward" else "3rd"
    assert s.log_rows()[-1].text == f"Lap 1: #7 Maya Petrakis takes {want}"
    assert s.undo_text() == "Undo: #7 Maya Petrakis won Lap 1"
    assert s.click(ids[7]) == rc.Outcome(False, f"#7 Maya Petrakis is already placed ({want}).")
    assert s.task().text == "Lap 2: click the winner."
    ok(s.click(ids[12]))
    ok(s.click(ids[33]))
    assert s.task().text == "Click the rest in the order they finish."
    assert s.state_label() == "Final sprint"
    screen = s.screen()
    assert len(screen.cards) == 5 and live_cards(s) == [ids[9], ids[19]]
    assert len(screen.rows) == 3 and all(r.entrant_id for r in screen.rows)
    ok(s.click(ids[9]))
    assert s.screen().rows[3].staged and s.screen().rows[3].place_text == "4"
    ok(s.click(ids[19]))
    assert s.state == "provisional"
    assert {int(s.roster.short(r.entrant_id)): r.rank for r in s.standings().rows} == expected


def test_win_and_out_dead_heat_on_a_lap_keeps_every_rider_in_the_table(store, make_race, ids):
    """Two riders who dead-heat a place lap share it (1, 1) and use both
    of a two-place race's places, so no second bell is due: the rest fill
    from 3rd (USAC 1M6(a)). The table has a row for every rider and drops
    nobody."""
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33, 9, 19], R.win_and_out_rules(2)))
    # Nothing on the surface ties a lap yet; the engine takes the entry,
    # so it goes in through the one record path.
    ok(s._record([SprintResult(sprint_no=1, places=[[ids[7], ids[12]]])]))
    assert s.task().kind == "order"
    ok(s.click(ids[33]))

    def shown():
        return [(r.entry.bibs[0], r.place_text, r.staged) for r in s.screen().rows]

    assert shown() == [("7", "1", False), ("12", "1", False), ("33", "3", True)]
    assert s.undo_text() == f"Undo: {s.label(ids[33])} placed 3rd"
    ok(s.click(ids[9]))
    assert shown()[3] == ("9", "4", True), "the fill counts on from the places the bell used"
    # The board and the operator's copy list every rider too.
    _, payload = board_feed.board_for(s.view())
    assert [(p.place, p.entry.bibs[0]) for p in payload.placings] == [(1, "7"), (1, "12")]
    ok(s.click(ids[19]))
    assert s.state == "provisional"
    assert shown() == [
        ("7", "1", False),
        ("12", "1", False),
        ("33", "3", False),
        ("9", "4", False),
        ("19", "5", False),
    ]
    _, payload = board_feed.board_for(s.view())
    assert [(p.place, p.entry.bibs[0]) for p in payload.placings] == [
        (1, "7"),
        (1, "12"),
        (3, "33"),
        (4, "9"),
        (5, "19"),
    ]


def test_win_and_out_review_swaps_laps_as_one_undo(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33], R.win_and_out_rules(2)))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    ok(s.click(ids[33]))
    assert s.state == "provisional"
    assert [k for k, _ in s.review_actions(ids[7])] == ["move_down", "dq"]
    assert [k for k, _ in s.review_actions(ids[12])] == ["move_up", "dq"]
    assert [k for k, _ in s.review_actions(ids[33])] == ["dq"]
    ok(s.review(ids[12], "move_up"))
    assert ranks(s) == {"Tess Gallagher": 1, "Maya Petrakis": 2, "Jack Moreau": 3}
    assert len([e for e in s.actions() if isinstance(e, SprintResult)]) == 2
    ok(s.undo())
    assert ranks(s) == {"Maya Petrakis": 1, "Tess Gallagher": 2, "Jack Moreau": 3}


def test_last_rider_taking_the_last_lap_completes_the_race(store, make_race, ids):
    s = LiveRace(store, make_race("win_and_out", [7, 12], R.win_and_out_rules(3)))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    assert s.state == "provisional"
    assert ranks(s) == {"Maya Petrakis": 1, "Tess Gallagher": 2}


# ----- the review ----------------------------------------------------------


def test_review_moves_ties_and_disqualifies(store, make_race, ids):
    s = chase(store, make_race, (7, 12, 33, 9))
    for bib in (7, 12, 33, 9):
        ok(s.click(ids[bib]))
    assert s.review_actions(ids[7]) == [
        ("move_down", "Move Down"),
        ("move_to:1", "Move to 2nd"),
        ("move_to:2", "Move to 3rd"),
        ("move_to:3", "Move to 4th"),
        ("tie_below", "Tie with the Rider Below"),
        ("dq", "Disqualify"),
    ]
    assert [k for k, _ in s.review_actions(ids[9])] == [
        "move_up", "move_to:0", "move_to:1", "move_to:2", "tie_above", "dq"
    ]  # fmt: skip
    # A long move in one step: last to first, the rest close up.
    ok(s.review(ids[9], "move_to:0"))
    assert ranks(s) == {
        "Ben Szymanski": 1,
        "Maya Petrakis": 2,
        "Tess Gallagher": 3,
        "Jack Moreau": 4,
    }
    ok(s.review(ids[9], "move_to:3"))
    assert ranks(s)["Ben Szymanski"] == 4 and ranks(s)["Maya Petrakis"] == 1
    ok(s.review(ids[9], "move_up"))
    assert ranks(s) == {
        "Maya Petrakis": 1,
        "Tess Gallagher": 2,
        "Ben Szymanski": 3,
        "Jack Moreau": 4,
    }
    ok(s.review(ids[9], "tie_above"))
    assert ranks(s)["Ben Szymanski"] == 2 and ranks(s)["Tess Gallagher"] == 2
    # Only the first row of the tied pair can join 1st; the other is tied
    # with the row above already. Which is first follows the table's order.
    first, second = [r.entrant_id for r in s.screen().rows if r.place_text == "2"]
    assert [k for k, _ in s.review_actions(first)] == [
        "move_up", "move_down", "move_to:0", "move_to:2", "tie_above", "dq"
    ]  # fmt: skip
    assert [k for k, _ in s.review_actions(second)] == [
        "move_up", "move_down", "move_to:0", "move_to:2", "tie_below", "dq"
    ]  # fmt: skip
    ok(s.review(ids[9], "move_down"))
    assert ranks(s) == {
        "Maya Petrakis": 1,
        "Tess Gallagher": 2,
        "Ben Szymanski": 3,
        "Jack Moreau": 4,
    }
    ok(s.review(ids[7], "dq"))
    assert s.standings().by_entrant(ids[7]).status == "DQ"
    assert s.review_actions(ids[7]) == []
    assert s.screen().rows[-1].place_text == "DQ"
    assert ranks(s)["Tess Gallagher"] == 1
    # The undos walk the corrections back to the order as clicked.
    for _ in range(6):
        ok(s.undo())
    assert ranks(s) == {
        "Maya Petrakis": 1,
        "Tess Gallagher": 2,
        "Jack Moreau": 3,
        "Ben Szymanski": 4,
    }
    assert s.state == "provisional"
    assert [e for e in s.actions() if isinstance(e, FinishOrder)][-1].places == (
        (ids[7],),
        (ids[12],),
        (ids[33],),
        (ids[9],),
    )


CLICKED = "Finish: 1st #7 Maya Petrakis, 2nd #12 Tess Gallagher, 3rd #33 Jack Moreau, 4th #9 Ben Szymanski"
MOVED = "Finish: 1st #7 Maya Petrakis, 2nd #12 Tess Gallagher, 3rd #9 Ben Szymanski, 4th #33 Jack Moreau"


def test_logbook_reads_a_correction_in_the_order_the_scorer_made_it(store, make_race, ids):
    s = chase(store, make_race, (7, 12, 33, 9))
    for bib in (7, 12, 33, 9):
        ok(s.click(ids[bib]))
    ok(s.review(ids[9], "move_up"))
    # The old finish is taken away before the new one goes in, and the
    # void says it was a correction, not an Undo. The struck line carries
    # the old order, so the void names it rather than repeating it, and
    # the new entry says who moved and where.
    assert [(r.text, r.voided) for r in s.log_rows()] == [
        (CLICKED, True),
        ("Replaced: the finish order", False),
        ("Moved #9 Ben Szymanski to 3rd\n" + MOVED, False),
    ]
    ok(s.review(ids[33], "tie_above"))
    assert s.log_rows()[-1].text.startswith("Tied #33 Jack Moreau for 3rd\nFinish: ")
    assert s.log_rows()[-2].text == "Replaced: the finish order"


def test_a_name_with_a_tag_in_brackets_is_read_as_a_name(store, make_race, ids):
    """The log's tags are read only where the app writes them, never from a rider's name."""
    store.update_rider(ids[9], first_name="Pat [undo of 2]", last_name="Lee")
    s = chase(store, make_race, (7, 12, 33, 9))
    for bib in (7, 12, 33, 9):
        ok(s.click(ids[bib]))
    ok(s.review(ids[9], "move_up"))
    assert s.undo_text() == "Undo: #9 Pat [undo of 2] Lee moved up"
    pat = "#9 Pat [undo of 2] Lee"
    clicked = (
        f"Finish: 1st #7 Maya Petrakis, 2nd #12 Tess Gallagher, 3rd #33 Jack Moreau, 4th {pat}"
    )
    moved = f"Finish: 1st #7 Maya Petrakis, 2nd #12 Tess Gallagher, 3rd {pat}, 4th #33 Jack Moreau"
    assert [(r.text, r.voided) for r in s.log_rows()][-1] == (f"Moved {pat} to 3rd\n{moved}", False)
    ok(s.undo())
    assert s.undo_text() == f"Undo: {pat} placed 4th"
    assert [(r.text, r.voided) for r in s.log_rows()] == [
        (clicked, True),
        ("Replaced: the finish order", False),
        (f"Moved {pat} to 3rd\n{moved}", True),
        (f"Undone: {moved}", False),
        (f"{clicked} (restored by undo)", False),
    ]


def test_logbook_reads_an_undo_then_a_new_entry_in_order(store, make_race, ids):
    s = chase(store, make_race, (7, 12, 33, 9))
    for bib in (7, 12, 33, 9):
        ok(s.click(ids[bib]))
    # Undo takes the finish back to the order as staged before the last
    # click; a second Undo unplaces 33, and the last two go the other way round.
    ok(s.undo())
    ok(s.undo())
    for bib in (9, 33):
        ok(s.click(ids[bib]))
    assert [(r.text, r.voided) for r in s.log_rows()] == [
        (CLICKED, True),
        ("Undone: " + CLICKED, False),
        (MOVED, False),
    ]


def test_mark_final_and_reopen_gates(store, make_race, ids):
    s = chase(store, make_race, (7, 12))
    assert not s.mark_final().ok and not s.reopen().ok
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    ok(s.mark_final())
    assert s.state == "final" and not s.mark_final().ok
    assert s.review_actions(ids[7]) == [] and s.rider_actions(ids[7]) == []
    assert not s.reopen_sprint(1).ok
    ok(s.reopen())
    assert s.state == "provisional"


def test_the_logbook_keeps_each_move_into_and_out_of_a_result(store, make_race, ids, event):
    """race.state says only where a race is now; a
    disputed result needs when it became provisional and final, and back."""
    event_id, _ = event
    s = chase(store, make_race, (7, 12))
    ok(s.click(ids[7]))
    ok(s.click(ids[12]))
    assert s.state == "provisional"
    ok(s.undo())
    assert s.state != "provisional"
    ok(s.click(ids[12]))
    ok(s.mark_final())
    ok(s.reopen())
    ok(s.mark_final())
    texts = [
        line.text
        for line in event_log(store, event_id)
        if not line.text.startswith(("Finish", "Undone"))
    ]
    assert texts == [
        "Provisional",
        "No longer provisional",
        "Provisional",
        "Marked final",
        "Reopened",
        "Marked final",
    ]
    changes = store.state_changes(s.race_id)
    assert [(c.from_state, c.to_state) for c in changes][-3:] == [
        ("provisional", "final"),
        ("final", "provisional"),
        ("provisional", "final"),
    ]
    # The history is the file's, as the log is: nothing edits it.
    import sqlite3

    for sql in ("UPDATE race_state_change SET to_state = 'x'", "DELETE FROM race_state_change"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            store._conn.execute(sql)


def test_event_log_and_live_race_across_the_event(store, make_race, ids, event):
    event_id, _ = event
    first = chase(store, make_race, (7, 12))
    second = chase(store, make_race, (33, 9))
    assert rc.live_race_id(store, event_id) == first.race_id
    ok(second.click(ids[33]))
    ok(second.click(ids[9]))
    assert rc.live_race_id(store, event_id) == second.race_id
    ok(first.click(ids[7]))
    ok(first.click(ids[12]))
    log = event_log(store, event_id)
    assert [(line.race_id, line.text[:7]) for line in log] == [
        (second.race_id, "Finish:"),
        (second.race_id, "Provisi"),
        (first.race_id, "Finish:"),
        (first.race_id, "Provisi"),
    ]
    assert log[0].race_id == second.race_id
    assert is_scored(store, store.race(first.race_id))
    assert not is_scored(store, store.race(make_race("chase", [3], R.placings_rules())))


# ----- a correction after a correction -------------------------------------
#
# A corrected sprint is appended at the end of the live log, and so is a
# row that Undo restores, so the log's order does not say which sprints
# exist. Each case corrects an entry that was logged before an earlier
# correction or undo and checks two things: the correction is accepted,
# and the standings equal those of a fresh race where the corrected values
# were entered directly.


def table(live):
    """One race's standings by name, everything a sheet prints from a row."""
    return {
        live.name(r.entrant_id): (
            r.rank,
            r.tied,
            r.status,
            r.total_points,
            r.sprint_points,
            r.final_sprint_place,
            r.laps_gained,
            r.laps_lost,
        )
        for r in live.standings().rows
    }


def clicks(s, ids, *bibs):
    for bib in bibs:
        ok(s.click(ids[bib]))


def reenter(s, number, ids, *bibs):
    """Reopen sprint ``number``, click its staged riders off, click ``bibs`` in order."""
    ok(s.reopen_sprint(number))
    for eid in [e for group in s.staged() for e in group]:
        ok(s.click(eid))
    clicks(s, ids, *bibs)
    return s.record_sprint()


def log_order(s):
    return [(r.kind, r.payload.get("sprint_no")) for r in s.rows()]


def wao(store, make_race, places, bibs):
    rules = R.win_and_out_rules(places, "forward")
    return LiveRace(store, make_race("win_and_out", list(bibs), rules))


def test_a_sprint_is_corrected_after_a_later_sprint_was_corrected(store, make_race, ids, house):
    """R1: s1, s2 recorded; correct s1; then correct s2; then the finish, corrected too."""
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(3)))
    clicks(s, ids, 12)
    ok(s.record_sprint())
    clicks(s, ids, 7)
    ok(s.record_sprint())
    ok(reenter(s, 1, ids, 33, 7))
    assert log_order(s) == [("sprint_result", 2), ("sprint_result", 1)]
    ok(reenter(s, 2, ids, 12, 33))
    clicks(s, ids, 7, 12, 33)
    assert s.standings().is_complete
    ok(reenter(s, 3, ids, 33, 7, 12))

    direct = LiveRace(store, make_race("points", [7, 12, 33], house.points(3)))
    clicks(direct, ids, 33, 7)
    ok(direct.record_sprint())
    clicks(direct, ids, 12, 33)
    ok(direct.record_sprint())
    clicks(direct, ids, 33, 7, 12)
    assert table(s) == table(direct)
    # 33: 10 + 7 + 20; 7: 7 + 14; 12: 10 + 10.
    assert ranks(s) == {"Jack Moreau": 1, "Maya Petrakis": 2, "Tess Gallagher": 3}


def test_the_finish_is_corrected_after_an_earlier_sprint_was_corrected(
    store, make_race, ids, house
):
    """R2: s1, the finish; correct s1; then correct the finish; a DQ still works."""
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(2)))
    clicks(s, ids, 12)
    ok(s.record_sprint())
    clicks(s, ids, 12, 7, 33)
    ok(reenter(s, 1, ids, 7, 12))
    assert log_order(s) == [("finish_order", None), ("sprint_result", 1)]
    ok(reenter(s, 2, ids, 33, 7, 12))

    direct = LiveRace(store, make_race("points", [7, 12, 33], house.points(2)))
    clicks(direct, ids, 7, 12)
    ok(direct.record_sprint())
    clicks(direct, ids, 33, 7, 12)
    assert table(s) == table(direct)
    ok(s.review(ids[33], "dq"))
    ok(direct.review(ids[33], "dq"))
    assert table(s) == table(direct)


def test_the_finish_is_corrected_after_a_correction_was_undone(store, make_race, ids, house):
    """R3: Undo puts the restored sprint back before the finish; the finish still corrects."""
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(2)))
    clicks(s, ids, 12)
    ok(s.record_sprint())
    clicks(s, ids, 12, 7, 33)
    ok(reenter(s, 1, ids, 7, 12))
    ok(s.undo())
    assert log_order(s) == [("sprint_result", 1), ("finish_order", None)]
    ok(reenter(s, 2, ids, 33, 7, 12))

    direct = LiveRace(store, make_race("points", [7, 12, 33], house.points(2)))
    clicks(direct, ids, 12)
    ok(direct.record_sprint())
    clicks(direct, ids, 33, 7, 12)
    assert table(s) == table(direct)


def test_win_and_out_laps_swap_twice(store, make_race, ids):
    """R4: the review swaps two laps, then swaps them back; each is the direct result."""
    s = wao(store, make_race, 2, (7, 12, 33))
    clicks(s, ids, 7, 12, 33)
    ok(s.review(ids[12], "move_up"))
    swapped = wao(store, make_race, 2, (7, 12, 33))
    clicks(swapped, ids, 12, 7, 33)
    assert table(s) == table(swapped)

    ok(s.review(ids[7], "move_up"))
    direct = wao(store, make_race, 2, (7, 12, 33))
    clicks(direct, ids, 7, 12, 33)
    assert table(s) == table(direct)
    assert ranks(s) == {"Maya Petrakis": 1, "Tess Gallagher": 2, "Jack Moreau": 3}


def test_win_and_out_swap_undone_then_another_swap(store, make_race, ids):
    """A lap swap, undone, puts both laps back in their order; another pair still swaps."""
    s = wao(store, make_race, 4, (7, 12, 33, 9, 3))
    clicks(s, ids, 7, 12, 33, 9, 3)
    ok(s.review(ids[12], "move_up"))
    ok(s.undo())
    laps = [n for kind, n in log_order(s) if kind == "sprint_result"]
    assert laps == [1, 2, 3, 4], "the restored laps stand where they were ridden"
    ok(s.review(ids[9], "move_up"))

    direct = wao(store, make_race, 4, (7, 12, 33, 9, 3))
    clicks(direct, ids, 7, 12, 9, 33, 3)
    assert table(s) == table(direct)
    ok(s.review(ids[12], "move_up"))
    both = wao(store, make_race, 4, (7, 12, 33, 9, 3))
    clicks(both, ids, 12, 7, 9, 33, 3)
    assert table(s) == table(both)


def test_a_sprint_corrected_mid_race_leaves_every_other_sprint_correctable(
    store, make_race, ids, house
):
    """R5: s1 corrected during sprint 3; the race runs on; s3 and then s2 correct afterwards."""
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(4)))
    clicks(s, ids, 12)
    ok(s.record_sprint())
    clicks(s, ids, 7)
    ok(s.record_sprint())
    clicks(s, ids, 33)  # sprint 3 in progress
    ok(reenter(s, 1, ids, 7, 12))
    assert s.staged() == [[ids[33]]], "the clicks for the sprint in progress come back"
    ok(s.record_sprint())
    clicks(s, ids, 12, 7, 33)
    assert s.standings().is_complete
    ok(reenter(s, 3, ids, 12, 33))
    ok(reenter(s, 2, ids, 33, 7))

    direct = LiveRace(store, make_race("points", [7, 12, 33], house.points(4)))
    for order in ((7, 12), (33, 7), (12, 33)):
        clicks(direct, ids, *order)
        ok(direct.record_sprint())
    clicks(direct, ids, 12, 7, 33)
    assert table(s) == table(direct)


def test_real_slips_are_still_refused_after_a_correction(store, make_race, ids, house):
    """The sequence checks go by sprint number and still catch every real slip."""
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(4)))
    clicks(s, ids, 12)
    ok(s.record_sprint())
    clicks(s, ids, 7)
    ok(s.record_sprint())
    ok(reenter(s, 1, ids, 33))
    assert log_order(s) == [("sprint_result", 2), ("sprint_result", 1)]
    twice = s._record([SprintResult(sprint_no=2, places=[[ids[12]]])])
    assert not twice.ok and twice.message == "Sprint 2 is already recorded; void it to re-enter"
    skipped = s._record([SprintResult(sprint_no=4, places=[[ids[12]]])])
    assert not skipped.ok and skipped.message == "Expected sprint 3, got 4"
    early = s._record([FinishOrder(places=[[ids[12]], [ids[7]], [ids[33]]])])
    assert not early.ok and early.message == "Sprint 3 of 4 has not been recorded"
    clicks(s, ids, 33)
    ok(s.record_sprint())
    clicks(s, ids, 12, 7, 33)
    assert s.standings().is_complete
    late = s._record([SprintResult(sprint_no=3, places=[[ids[12]]])])
    assert not late.ok and late.message == rc._AFTER_FINISH
    problems = s.validate(SprintResult(sprint_no=3, places=[[ids[12]]]), s.actions())
    assert "Sprint 3 is already recorded; void it to re-enter" in problems


def test_win_and_out_slips_are_still_refused_after_a_swap(store, make_race, ids):
    """Mid-race, so laps 3 and 4 are still open; the swap is recorded as the review records it."""
    s = wao(store, make_race, 4, (7, 12, 33, 9))
    clicks(s, ids, 7, 12)
    laps = s.recorded_sprints()
    swap = [
        SprintResult(sprint_no=1, places=[[ids[12]]]),
        SprintResult(sprint_no=2, places=[[ids[7]]]),
    ]
    ok(s._record(swap, replaces=[laps[1], laps[2]]))
    assert log_order(s) == [("sprint_result", 1), ("sprint_result", 2)]
    assert ranks(s)["Tess Gallagher"] == 1 and ranks(s)["Maya Petrakis"] == 2
    skipped = s._record([SprintResult(sprint_no=4, places=[[ids[33]]])])
    assert not skipped.ok and skipped.message == "Expected lap 3, got 4"
    twice = s._record([SprintResult(sprint_no=1, places=[[ids[33]]])])
    assert not twice.ok and twice.message == "Lap 1 is already recorded; void it to re-enter"
    again = s._record([SprintResult(sprint_no=3, places=[[ids[7]]])])
    assert not again.ok and "already took a place" in again.message
    ok(s._record([SprintResult(sprint_no=3, places=[[ids[33]]])]))


# ----- out of the finish (mishap), USAC 2M7(b) and 2M8(a) ----------------------


def points_race(store, make_race, house, bibs=(7, 12, 33), sprints=2):
    return LiveRace(store, make_race("points", list(bibs), house.points(sprints)))


def test_a_correction_placing_a_rider_dnf_since_records_again_after_its_undo(
    store, make_race, ids, house
):
    """A rider whose DNF came after a sprint may be placed in its
    correction. Undo of that correction puts the sprint's row back after
    the DNF in the log; the same correction entered again records, as the
    click that placed the rider says it may."""
    s = points_race(store, make_race, house, bibs=(7, 12, 33, 9), sprints=3)
    ok(s.click(ids[7]))
    ok(s.record_sprint())
    ok(s.act(ids[9], "dnf"))
    ok(s.reopen_sprint(1))
    ok(s.click(ids[9]))
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[9]).sprint_points[0] > 0
    ok(s.undo())
    assert s.editing and s.staged() == [[ids[7]], [ids[9]]]
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[9]).sprint_points[0] > 0
    ok(s.undo())
    s.cancel_edit()
    ok(s.reopen_sprint(1))
    ok(s.click(ids[9]))
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[9]).status == "DNF"


def test_points_race_mishap_in_the_final_sprint_is_placed_on_points(store, make_race, ids, house):
    """A 2-sprint Points Race, 3 riders, 2 of 3 cross the line.
    The third's free laps ran into the last kilometer. The card's ⋯ offers
    Out of the finish (mishap) during the final sprint, so the finish
    completes with the others, with no wrong DNF or final-sprint place, and
    the rider ranks on the points held (R-POINTS-5)."""
    s = points_race(store, make_race, house)
    clicks(s, ids, 7, 33, 12)
    # Not offered before the final sprint.
    assert "out_of_finish" not in [k for k, _ in s.rider_actions(ids[7])]
    ok(s.record_sprint())
    assert s.task().kind == "final_sprint"
    assert [k for k, _ in s.rider_actions(ids[7])] == [
        "dnf", "out_of_finish", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "dq"
    ]  # fmt: skip
    clicks(s, ids, 12, 33)
    assert s.state == "running" and not s.record_sprint().ok
    # A rider already placed in the final sprint is not offered the action.
    assert "out_of_finish" not in [k for k, _ in s.rider_actions(ids[12])]
    refused = s.act(ids[12], "out_of_finish")
    assert refused == rc.Outcome(
        False,
        "Tess Gallagher is placed in the final sprint. Click the card to take the place off first.",
    )
    out = ok(s.act(ids[7], "out_of_finish"))
    assert out.message == (
        "Recorded Out of the finish (mishap): #7 Maya Petrakis;"
        " Final sprint: 1st #12 Tess Gallagher, 2nd #33 Jack Moreau"
    )
    assert s.state == "provisional"
    # (rank, tied, status, total, per sprint, final place, gained, lost):
    # 7 holds the 10 of sprint 1 and no final-sprint place, and ranks on it.
    assert table(s) == {
        "Tess Gallagher": (1, False, None, 25, (5, 20), 1, 0, 0),
        "Jack Moreau": (2, False, None, 21, (7, 14), 2, 0, 0),
        "Maya Petrakis": (3, False, None, 10, (10, 0), None, 0, 0),
    }
    row = s.standings().by_entrant(ids[7])
    assert row.out_of_finish and row.placed and row.status is None and row.total_points == 10
    screen = s.screen()
    assert screen.review and screen.cards == ()
    maya = next(r for r in screen.rows if r.entry.names == ["Maya Petrakis"])
    assert (maya.place_text, maya.status, maya.note) == ("3", "", "Out of the finish (mishap)")
    assert [k for k, _ in s.review_actions(ids[7])] == ["points_penalty", "dq"]
    assert s.log_rows()[-2].text == "Out of the finish (mishap): #7 Maya Petrakis"
    assert s.undo_text() == "Undo: #7 Maya Petrakis marked Out of the Finish (Mishap)"
    # Undo takes back the mark and the finish it completed: the final sprint is open again.
    ok(s.undo())
    assert s.state == "running" and s.task().kind == "final_sprint"
    assert [c.badge for c in s.screen().cards if c.entry.names == ["Maya Petrakis"]] == [None]
    assert [r.staged for r in s.screen().rows] == [False, False, False]
    assert not s.standings().by_entrant(ids[7]).out_of_finish
    assert s.staged() == [[ids[12]], [ids[33]]], "the clicks before it come back"


def test_a_points_race_ended_after_eighty_percent_stands_on_the_sprints_ridden(
    store, make_race, ids, house
):
    """USAC 2M6: stopped after 80 percent, the results stand. The task line's
    ⋯ offers End Race Now, Result As-Is from the first recorded sprint, the
    final sprint included; the race completes on the sprints ridden with
    no doubled final, the staged clicks of the sprint being built are
    dropped, and Undo reopens the race where it was."""
    s = points_race(store, make_race, house, sprints=3)
    assert s.race_actions() == [], "nothing stands before a sprint is recorded"
    assert s.end_race() == rc.Outcome(False, "Record a sprint first; nothing stands yet.")
    clicks(s, ids, 7, 33, 12)
    ok(s.record_sprint())
    assert s.race_actions() == [
        ("end_race", "End Race Now, Result As-Is..."),
        ("shorten_race", "Shorten Race..."),
    ]
    assert s.screen().race_actions == tuple(s.race_actions())
    clicks(s, ids, 12)
    assert s.staged() == [[ids[12]]]
    out = ok(s.end_race())
    assert out.message == "Recorded Race ended after 1 sprint"
    assert s.state == "provisional" and s.standings().is_complete and s.standings().ended
    assert s.staged() == [], "the clicks of the sprint being built are dropped"
    assert s.sprint_columns() == [1], "the sprints ridden, no empty final column"
    # (rank, tied, status, total, per sprint, final place, gained, lost)
    assert table(s) == {
        "Maya Petrakis": (1, False, None, 10, (10,), None, 0, 0),
        "Jack Moreau": (2, False, None, 7, (7,), None, 0, 0),
        "Tess Gallagher": (3, False, None, 5, (5,), None, 0, 0),
    }
    screen = s.screen()
    assert screen.review and screen.cards == () and screen.race_actions == ()
    assert screen.mark_final and screen.sprint_columns == (1,)
    assert s.race_actions() == []
    assert s.end_race() == rc.Outcome(False, "The race is already complete.")
    assert s.act(ids[7], "dnf").ok is False, "no scoring entry after the end"
    assert s.undo_text() == "Undo: race ended after 1 sprint"
    assert s.log_rows()[-1].text == "Race ended after 1 sprint"
    ok(s.mark_final())
    assert s.state == "final"
    ok(s.reopen())
    ok(s.undo())
    assert s.state == "running" and not s.standings().is_complete
    assert s.task().kind == "sprint" and s.task().sprint_no == 2
    assert s.race_actions() == [
        ("end_race", "End Race Now, Result As-Is..."),
        ("shorten_race", "Shorten Race..."),
    ]


def test_results_stand_is_offered_in_the_final_sprint_and_not_during_a_correction(
    store, make_race, ids, house
):
    """A stoppage after 80 percent can land in the final sprint, where
    Record Sprint is not shown, so the race's ⋯ is still there; a reopened
    sprint hides it until the correction is recorded or cancelled."""
    s = points_race(store, make_race, house, sprints=2)
    clicks(s, ids, 7, 33, 12)
    ok(s.record_sprint())
    assert s.task().kind == "final_sprint"
    assert s.race_actions() == [("end_race", "End Race Now, Result As-Is...")]
    ok(s.reopen_sprint(1))
    assert s.race_actions() == []
    assert s.end_race() == rc.Outcome(False, rc.CORRECTION_OPEN)
    s.cancel_edit()
    clicks(s, ids, 12, 7)
    ok(s.end_race())
    assert s.standings().is_complete and s.sprint_columns() == [1]
    assert table(s)["Maya Petrakis"][3] == 10, "the final sprint's clicks did not score"


def test_results_stand_is_not_offered_in_a_tempo_race_or_a_placings_race(
    store, make_race, ids, house
):
    """USAC 2P5 restarts or reruns a stopped Tempo Race; the other formats'
    tables say rerun or restart. The item is not on the menu and the entry
    is refused; a Tempo Race's menu has Shorten Race alone."""
    tempo = LiveRace(store, make_race("tempo", [7, 12, 33], R.tempo_rules(sprint_count=3)))
    clicks(tempo, ids, 7)
    ok(tempo.record_sprint())
    assert tempo.race_actions() == [("shorten_race", "Shorten Race...")]
    assert tempo.screen().race_actions == (("shorten_race", "Shorten Race..."),)
    assert tempo.end_race() == rc.Outcome(
        False, "Only a Points Race or Madison can end early with its result as-is."
    )
    chase = LiveRace(store, make_race("chase", [7, 12, 33], R.placings_rules()))
    assert chase.race_actions() == [] and chase.end_race().ok is False


def test_a_shortened_points_race_rides_to_its_new_final_sprint(store, make_race, ids, house):
    """USAC 1G4(b), 2M2(f): set for 4 sprints, shortened to 3 after Sprint 2.
    The task line turns to the final sprint at once, Record Sprint goes,
    the click already staged in Sprint 3 is the first place of the finish,
    and Sprint 3 scores doubled. Undo takes the shortening back."""
    s = points_race(store, make_race, house, sprints=4)
    assert s.shorten_refusal() == "Record a sprint first."
    assert s.shorten_race(3) == rc.Outcome(False, "Record a sprint first.")
    clicks(s, ids, 7, 33, 12)
    ok(s.record_sprint())
    assert s.shorten_bounds() == (2, 3)
    assert s.shorten_race(1) == rc.Outcome(
        False, "Shorten to at least Sprint 2; Sprint 1 is recorded."
    )
    clicks(s, ids, 33, 7, 12)
    ok(s.record_sprint())
    assert s.shorten_bounds() == (3, 3)
    assert s.shorten_race(2) == rc.Outcome(
        False, "Shorten to at least Sprint 3; Sprints 1 and 2 are recorded."
    )
    assert s.shorten_race(4) == rc.Outcome(False, "The race has 4 sprints; shorten to fewer.")
    clicks(s, ids, 12)
    assert s.task().kind == "sprint" and s.task().record
    out = ok(s.shorten_race(3))
    assert out.message == "Recorded Race shortened to 3 sprints"
    assert s.sprint_count == 3 and s.rules.sprint_count == 4, "the race's own count stays"
    task = s.task()
    assert task.kind == "final_sprint" and not task.record
    assert task.text == "Final sprint: click every rider in order."
    assert s.staged() == [[ids[12]]], "the staged click is the finish's first place"
    assert s.race_actions() == [("end_race", "End Race Now, Result As-Is...")]
    assert s.sprint_columns() == [1, 2, 3]
    assert s.undo_text() == "Undo: race shortened to 3 sprints"
    assert s.log_rows()[-1].text == "Race shortened to 3 sprints"
    clicks(s, ids, 7, 33)
    assert s.state == "provisional" and s.standings().is_complete
    # (rank, tied, status, total, per sprint, final place, gained, lost)
    assert table(s) == {
        "Maya Petrakis": (1, False, None, 31, (10, 7, 14), 2, 0, 0),
        "Tess Gallagher": (2, False, None, 30, (5, 5, 20), 1, 0, 0),
        "Jack Moreau": (3, False, None, 27, (7, 10, 10), 3, 0, 0),
    }
    assert s.shorten_race(3) == rc.Outcome(False, "The race is already complete.")
    # Undo the finish's last click, then the shortening: Sprint 3 of 4 again,
    # with its click still staged.
    ok(s.undo())
    ok(s.undo())
    ok(s.undo())
    assert s.sprint_count == 4
    assert s.task().kind == "sprint" and s.task().sprint_no == 3 and s.task().record
    assert s.staged() == [[ids[12]]]


def test_a_second_shortening_lowers_the_count_again_and_undo_takes_the_latest_back(
    store, make_race, ids, house
):
    s = points_race(store, make_race, house, sprints=5)
    clicks(s, ids, 7, 33, 12)
    ok(s.record_sprint())
    ok(s.shorten_race(4))
    assert s.shorten_bounds() == (2, 3)
    assert s.shorten_race(4) == rc.Outcome(False, "The race has 4 sprints; shorten to fewer.")
    ok(s.shorten_race(3))
    assert s.sprint_count == 3 and s.sprint_columns() == [1, 2, 3]
    assert [r.text for r in s.log_rows()[-2:]] == [
        "Race shortened to 4 sprints",
        "Race shortened to 3 sprints",
    ]
    ok(s.undo())
    assert s.sprint_count == 4 and s.sprint_columns() == [1, 2, 3, 4]
    assert s.undo_text() == "Undo: race shortened to 4 sprints"


def test_shorten_race_is_refused_during_a_correction_and_in_the_final_sprint(
    store, make_race, ids, house
):
    """A reopened sprint hides the race's menu; once the final sprint has
    begun there is no later sprint to make final, and a stoppage there is
    End Race, which the refusal names."""
    s = points_race(store, make_race, house, sprints=3)
    clicks(s, ids, 7, 33, 12)
    ok(s.record_sprint())
    ok(s.reopen_sprint(1))
    assert s.race_actions() == []
    assert s.shorten_race(2) == rc.Outcome(False, rc.CORRECTION_OPEN)
    s.cancel_edit()
    clicks(s, ids, 33, 7, 12)
    ok(s.record_sprint())
    assert s.task().kind == "final_sprint"
    assert s.race_actions() == [("end_race", "End Race Now, Result As-Is...")]
    assert s.shorten_race(2) == rc.Outcome(
        False,
        "The final sprint has begun; use End Race Now, Result As-Is... to stop the race.",
    )
    ok(s.end_race())
    assert s.shorten_race(2) == rc.Outcome(False, "The race is already complete.")


def test_a_tempo_race_can_be_shortened_and_a_scratch_race_cannot(store, make_race, ids):
    """USAC 1G4(b): a shortened Tempo Race finishes sooner; a format with
    no sprint count is entered as it is ridden."""
    tempo = LiveRace(store, make_race("tempo", [7, 12, 33], R.tempo_rules(sprint_count=4)))
    clicks(tempo, ids, 7)
    ok(tempo.record_sprint())
    ok(tempo.shorten_race(2))
    assert tempo.task().kind == "final_sprint"
    assert tempo.race_actions() == []
    assert tempo.shorten_race(2) == rc.Outcome(False, "The final sprint has begun.")
    clicks(tempo, ids, 12, 7, 33)
    assert tempo.standings().is_complete and tempo.sprint_columns() == [1, 2]
    chase = LiveRace(store, make_race("chase", [7, 12, 33], R.placings_rules()))
    assert chase.race_actions() == []
    assert chase.shorten_race(2) == rc.Outcome(
        False, "Shorten Race is scored in a Points Race, Madison, or Tempo Race only."
    )


def test_points_race_mishap_result_equals_the_engine_without_the_mark(store, make_race, ids, house):
    """The ranking is exactly R-POINTS-5's: the log minus the OutOfFinish
    action, replayed, gives the same ranks and totals."""
    from madtracker.scoring import compute_for_format
    from madtracker.scoring.actions import OutOfFinish

    s = points_race(store, make_race, house, bibs=(7, 12, 33, 9), sprints=3)
    clicks(s, ids, 7, 33)
    ok(s.record_sprint())
    ok(s.act(ids[9], "lap_gained"))
    clicks(s, ids, 9, 7)
    ok(s.record_sprint())
    ok(s.act(ids[7], "out_of_finish"))
    clicks(s, ids, 12, 33, 9)
    assert s.state == "provisional"
    actions = s.actions()
    without = [a for a in actions if not isinstance(a, OutOfFinish)]
    plain = compute_for_format("points", s.rules, s.roster.ids, without)
    got = s.standings()
    assert got.ranks() == plain.ranks()
    assert [r.total_points for r in got.rows] == [r.total_points for r in plain.rows]
    assert got.by_entrant(ids[7]).out_of_finish and not plain.by_entrant(ids[7]).out_of_finish


def test_a_mishap_refused_outside_the_final_sprint_and_in_other_formats(
    store, make_race, ids, house
):
    s = points_race(store, make_race, house, sprints=3)
    assert "out_of_finish" not in [k for k, _ in s.rider_actions(ids[7])]
    assert s.act(ids[7], "out_of_finish") == rc.Outcome(
        False, "Out of the Finish (Mishap) applies during the final sprint."
    )
    clicks(s, ids, 7)
    ok(s.record_sprint())
    assert s.act(ids[12], "out_of_finish").ok is False
    clicks(s, ids, 12)
    ok(s.record_sprint())
    assert s.task().kind == "final_sprint"
    ok(s.act(ids[12], "out_of_finish"))
    # Once out of the finish: a done card, no second mark, no DNF, a click refused.
    assert ids[12] not in live_cards(s)
    assert s.rider_actions(ids[12]) == []
    line = "Tess Gallagher is out of the finish (mishap). Undo takes it back."
    assert s.act(ids[12], "dnf") == rc.Outcome(False, line)
    assert s.act(ids[12], "out_of_finish") == rc.Outcome(False, line)
    assert s.click(ids[12]) == rc.Outcome(
        False, "#12 Tess Gallagher is marked Out of the Finish (Mishap)."
    )
    for fmt, rules in (
        ("chase", R.placings_rules()),
        ("elimination", house.elimination()),
        ("win_and_out", R.win_and_out_rules(2)),
    ):
        other = LiveRace(store, make_race(fmt, [7, 12, 33], rules))
        assert "out_of_finish" not in [k for k, _ in other.rider_actions(ids[7])]
        assert other.act(ids[7], "out_of_finish") == rc.Outcome(
            False, "Out of the Finish (Mishap) applies to a Points Race, Madison, or Tempo Race."
        )


def test_a_mishap_rider_rides_an_earlier_sprints_correction_but_not_the_finish(
    store, make_race, ids, house
):
    """USAC 2M7(b): the points before the mishap stand, so a correction of
    sprint 1 may still place the rider; the finish may not."""
    s = points_race(store, make_race, house)
    clicks(s, ids, 7, 33)
    ok(s.record_sprint())
    ok(s.act(ids[12], "out_of_finish"))
    clicks(s, ids, 7, 33)
    assert s.state == "provisional"
    ok(s.reopen_sprint(1))
    assert ids[12] in live_cards(s)
    for eid in [e for g in s.staged() for e in g]:
        ok(s.click(eid))
    clicks(s, ids, 12, 7, 33)
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[12]).sprint_points == (10, 0)
    assert ranks(s) == {"Maya Petrakis": 1, "Jack Moreau": 2, "Tess Gallagher": 3}
    ok(s.reopen_sprint(2))
    assert ids[12] not in live_cards(s)
    assert s.click(ids[12]) == rc.Outcome(
        False, "#12 Tess Gallagher is marked Out of the Finish (Mishap)."
    )
    s.cancel_edit()


def test_madison_team_out_of_finish_completes_with_the_other_teams(store, make_race, ids, house):
    """USAC 2N6(c), 2N7(a): the team is placed on the laps and points held."""
    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    s = LiveRace(store, race_id)
    teams = {s.name(t): t for t in s.roster.ids}
    ok(s.click(teams["Red"]))
    ok(s.click(teams["Blue"]))
    ok(s.record_sprint())
    assert [k for k, _ in s.rider_actions(teams["Red"])] == [
        "dnf", "out_of_finish", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "dq"
    ]  # fmt: skip
    ok(s.act(teams["Red"], "lap_gained"))
    out = ok(s.act(teams["Red"], "out_of_finish"))
    assert out.message == "Recorded Out of the finish (mishap): Red"
    assert s.undo_text() == "Undo: Red marked Out of the Finish (Mishap)"
    assert live_names(s, team=True) == ["Blue", "Orange"]
    assert s.task().text == "Final sprint: click every team in order."
    ok(s.click(teams["Orange"]))
    ok(s.click(teams["Blue"]))
    assert s.state == "provisional"
    assert ranks(s) == {"Red": 1, "Orange": 2, "Blue": 3}
    red = s.standings().by_entrant(teams["Red"])
    assert red.out_of_finish and red.total_points == 5 + house.LAP
    assert s.log_rows()[-2].text == "Out of the finish (mishap): Red"
    # Undo: the final sprint's last click, then Orange's click, then the mark.
    ok(s.undo())
    assert s.state == "running"
    ok(s.undo())
    assert s.undo_text() == "Undo: Red marked Out of the Finish (Mishap)"
    ok(s.undo())
    assert not s.standings().by_entrant(teams["Red"]).out_of_finish
    assert [c.entry.team for c in s.screen().cards] == ["Blue", "Red", "Orange"]


def test_tempo_rider_out_of_finish_keeps_the_sprints_won(store, make_race, ids):
    """USAC 2P2(a): the Points Race rules apply to the Tempo Race."""
    s = LiveRace(store, make_race("tempo", [7, 12, 33], R.tempo_rules(sprint_count=3)))
    assert s.kind == "points"
    clicks(s, ids, 7)
    ok(s.record_sprint())
    clicks(s, ids, 7)
    ok(s.record_sprint())
    assert s.task().kind == "final_sprint"
    ok(s.act(ids[7], "out_of_finish"))
    clicks(s, ids, 33, 12)
    assert s.state == "provisional"
    assert ranks(s) == {"Maya Petrakis": 1, "Jack Moreau": 2, "Tess Gallagher": 3}
    assert s.standings().by_entrant(ids[7]).total_points == 2
    assert s.standings().by_entrant(ids[7]).out_of_finish


def test_every_rider_out_of_the_finish_completes_the_race_on_points(store, make_race, ids, house):
    """A pile-up in the last kilometer: nobody is left to click, so the
    result is the standings as they stand."""
    s = points_race(store, make_race, house)
    clicks(s, ids, 7, 33)
    ok(s.record_sprint())
    ok(s.act(ids[12], "out_of_finish"))
    ok(s.act(ids[7], "out_of_finish"))
    assert s.state == "running"
    ok(s.act(ids[33], "out_of_finish"))
    assert s.state == "provisional" and s.task().kind == "review"
    assert ranks(s) == {"Maya Petrakis": 1, "Jack Moreau": 2, "Tess Gallagher": 3}
    assert all(r.out_of_finish for r in s.standings().rows)


# ----- withdrawn, USAC 2O3(e) and 1M6(d) -------------------------------------


def test_withdrawn_is_offered_where_did_not_finish_is(store, make_race, ids, house):
    """Races placed at the line, the Points Race, the Madison, and the Tempo
    Race place a withdrawn rider by the moment; the menu offers the entry
    beside Did Not Finish, after Out of the Finish (Mishap)."""
    s = chase(store, make_race)
    assert keys_of(s, ids[7]) == [
        "place_last", "dns", "dnf", "withdrawn", "lap_gained", "lap_lost", "dq"
    ]  # fmt: skip
    s = points_race(store, make_race, house)
    assert keys_of(s, ids[7]) == [
        "dns", "dnf", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "dq"
    ]  # fmt: skip
    clicks(s, ids, 7)
    ok(s.record_sprint())
    assert keys_of(s, ids[12]) == [
        "dns", "dnf", "out_of_finish", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "dq"
    ]  # fmt: skip
    tempo = LiveRace(store, make_race("tempo", [7, 12, 33], R.tempo_rules(sprint_count=3)))
    assert "withdrawn" in keys_of(tempo, ids[7])
    madison = LiveRace(store, make_race("madison", [3, 24, 5, 36], house.madison(2), teams=TEAMS[:2]))  # fmt: skip
    assert "withdrawn" in keys_of(madison, madison.roster.ids[0])
    for fmt, rules in (
        ("elimination", house.elimination()),
        ("win_and_out", R.win_and_out_rules(2)),
    ):
        other = LiveRace(store, make_race(fmt, [7, 12, 33], rules))
        assert "withdrawn" not in keys_of(other, ids[7])
        assert other.act(ids[7], "withdrawn") == rc.Outcome(
            False,
            "Withdrawn applies to a race placed at the line, a Points Race, a Madison,"
            " or a Tempo Race.",
        )


def test_a_withdrawn_rider_leaves_the_field_and_ranks_after_the_finishers(store, make_race, ids):
    """USAC 2O3(e): the later withdrawn ranks higher, each with its own
    place; the finish completes without them, and the row prints the
    place with "Withdrawn" beside the name."""
    s = chase(store, make_race)
    out = ok(s.act(ids[9], "withdrawn"))
    assert out.message == "Recorded Withdrawn: #9 Ben Szymanski"
    assert s.undo_text() == "Undo: #9 Ben Szymanski marked Withdrawn"
    assert s.log_rows()[-1].text == "Withdrawn: #9 Ben Szymanski"
    assert ids[9] not in live_cards(s)
    assert s.rider_actions(ids[9]) == [] and s.review_actions(ids[9]) == []
    clicks(s, ids, 33, 7)
    # A rider with a place in the finish crossed the line: the badge first.
    assert "withdrawn" not in keys_of(s, ids[7])
    assert s.act(ids[7], "withdrawn") == rc.Outcome(
        False, "Maya Petrakis is placed in this finish. Click the card to take the place off first."
    )
    ok(s.act(ids[12], "withdrawn"))
    assert s.state == "provisional", "the last rider left completes the finish"
    assert ranks(s) == {
        "Jack Moreau": 1, "Maya Petrakis": 2, "Tess Gallagher": 3, "Ben Szymanski": 4
    }  # fmt: skip
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    assert (rows["Ben Szymanski"].place_text, rows["Ben Szymanski"].note) == ("4", "Withdrawn")
    assert rows["Ben Szymanski"].status == ""
    # No move reaches a withdrawn row, from it or from the finisher above.
    assert "move_down" not in [k for k, _ in s.review_actions(ids[7])]
    assert [k for k, _ in s.review_actions(ids[9])] == ["dq"]


def test_a_withdrawn_row_refuses_what_it_cannot_take(store, make_race, ids, house):
    s = points_race(store, make_race, house, bibs=(7, 12, 33, 9), sprints=3)
    clicks(s, ids, 7, 12)
    ok(s.record_sprint())
    ok(s.act(ids[12], "withdrawn"))
    line = "Tess Gallagher is withdrawn. Undo takes it back."
    for key in ("dnf", "withdrawn", "lap_gained"):
        assert s.act(ids[12], key) == rc.Outcome(False, line)
    assert s.click(ids[12]) == rc.Outcome(False, "#12 Tess Gallagher is marked Withdrawn.")
    # The points held stay as figures.
    assert s.standings().by_entrant(ids[12]).sprint_points[0] == 7
    ok(s.reopen_sprint(1))
    assert "withdrawn" not in keys_of(s, ids[33])
    assert s.act(ids[33], "withdrawn") == rc.Outcome(False, rc.CORRECTION_OPEN)
    s.cancel_edit()


def test_a_disqualify_after_a_withdrawal_wins(store, make_race, ids):
    s = chase(store, make_race, (7, 12, 33))
    ok(s.act(ids[12], "withdrawn"))
    clicks(s, ids, 33, 7)
    assert s.state == "provisional"
    assert [k for k, _ in s.review_actions(ids[12])] == ["dq"]
    ok(s.review(ids[12], "dq"))
    row = s.standings().by_entrant(ids[12])
    assert row.status == "DQ" and row.rank is None
    assert ranks(s)["Jack Moreau"] == 1 and ranks(s)["Maya Petrakis"] == 2


def test_tempo_two_withdrawn_rank_by_the_moment_with_the_points_as_figures(store, make_race, ids):
    """USAC 2O3(e): in the omnium's Tempo Race a rider two laps down is
    withdrawn; the later withdrawn ranks higher, whatever the points."""
    s = LiveRace(store, make_race("tempo", [7, 12, 33, 9], R.tempo_rules(sprint_count=3)))
    clicks(s, ids, 9)
    ok(s.record_sprint())
    ok(s.act(ids[9], "withdrawn"))
    clicks(s, ids, 7)
    ok(s.record_sprint())
    ok(s.act(ids[12], "withdrawn"))
    clicks(s, ids, 7, 33)
    assert s.state == "provisional"
    assert ranks(s) == {
        "Maya Petrakis": 1, "Jack Moreau": 2, "Tess Gallagher": 3, "Ben Szymanski": 4
    }  # fmt: skip
    assert s.standings().by_entrant(ids[9]).total_points == 1


def test_a_madison_team_withdrawn_keeps_a_done_card(store, make_race, ids, house):
    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    s = LiveRace(store, race_id)
    teams = {s.name(t): t for t in s.roster.ids}
    out = ok(s.act(teams["Red"], "withdrawn"))
    assert out.message == "Recorded Withdrawn: Red"
    assert s.undo_text() == "Undo: Red marked Withdrawn"
    assert [c.entry.team for c in s.screen().cards] == ["Blue", "Red", "Orange"]
    assert live_names(s, team=True) == ["Blue", "Orange"]
    assert s.click(teams["Red"]) == rc.Outcome(False, "Red is marked Withdrawn.")
    ok(s.undo())
    assert live_names(s, team=True) == ["Blue", "Red", "Orange"]


def test_a_correction_placing_a_rider_withdrawn_since_records_again_after_its_undo(
    store, make_race, ids, house
):
    """A rider withdrawn after a sprint may be placed in its correction.
    Undo of that correction puts the sprint's row back after the
    withdrawal in the log; the same correction entered again records, as
    the click that placed the rider says it may. A sprint ridden after the
    withdrawal may not place the rider."""
    s = points_race(store, make_race, house, bibs=(7, 12, 33, 9), sprints=3)
    ok(s.click(ids[7]))
    ok(s.record_sprint())
    ok(s.act(ids[9], "withdrawn"))
    ok(s.reopen_sprint(1))
    assert ids[9] in live_cards(s)
    ok(s.click(ids[9]))
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[9]).sprint_points[0] > 0
    ok(s.undo())
    assert s.editing and s.staged() == [[ids[7]], [ids[9]]]
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[9]).sprint_points[0] > 0
    ok(s.undo())
    s.cancel_edit()
    ok(s.reopen_sprint(1))
    ok(s.click(ids[9]))
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[9]).withdrawn
    clicks(s, ids, 33)
    ok(s.record_sprint())
    ok(s.reopen_sprint(2))
    assert ids[9] not in live_cards(s)
    assert s.click(ids[9]) == rc.Outcome(False, "#9 Ben Szymanski is marked Withdrawn.")
    s.cancel_edit()


# ----- Did not start while the rider has nothing recorded ------------------------


def test_dns_is_offered_until_the_rider_has_a_result_in_every_format(store, make_race, ids, house):
    """A no-show may be found once the race is under way.
    DNS stays on a rider's menu while nothing is recorded or staged for
    them, whatever the rest of the field has done; a place, a lap, a bell
    or a mishap takes it off, and the refusal says so."""
    keys = lambda s, bib: [k for k, _ in s.rider_actions(ids[bib])]  # noqa: E731

    s = chase(store, make_race, (7, 12, 33))
    clicks(s, ids, 7)
    assert "dns" in keys(s, 12) and "dns" not in keys(s, 7)
    ok(s.act(ids[12], "lap_gained"))
    assert "dns" not in keys(s, 12)
    assert s.act(ids[12], "dns") == rc.Outcome(
        False, "Tess Gallagher has a result in this race; riders who leave did not finish."
    )
    ok(s.act(ids[33], "dns"))
    assert s.state == "running", "a DNS after the first click does not unstart the race"
    assert [(r.place_text, r.status) for r in s.screen().rows] == [("1", ""), ("DNS", "DNS")]

    e = LiveRace(store, make_race("elimination", [3, 5, 7, 8], house.elimination()))
    clicks(e, ids, 3, 5)
    assert "dns" in keys(e, 7) and e.act(ids[3], "dns") == rc.Outcome(
        False, "Marcus Delgado has a result in this race; riders who leave did not finish."
    )
    ok(e.act(ids[7], "dns"))
    # Three started: 8 wins outright, 5 is 2nd, 3 is 3rd, 7 is never placed.
    assert e.state == "provisional"
    assert ranks(e) == {
        "Tom Kowalczyk": 1,
        "Priya Okafor": 2,
        "Marcus Delgado": 3,
        "Maya Petrakis": None,
    }
    assert e.standings().by_entrant(ids[7]).status == "DNS"

    p = points_race(store, make_race, house, bibs=(7, 12, 33, 9))
    clicks(p, ids, 7, 12)
    ok(p.record_sprint())
    assert "dns" in keys(p, 33) and "dns" not in keys(p, 7) and "dns" not in keys(p, 12)
    ok(p.act(ids[33], "dns"))
    assert p.state == "running"
    assert p.task().kind == "final_sprint"
    clicks(p, ids, 9, 12, 7)
    assert p.state == "provisional"
    # 12 has 7 + 14; 9 and 7 are level on 20 and the final sprint splits them.
    assert ranks(p) == {
        "Tess Gallagher": 1,
        "Ben Szymanski": 2,
        "Maya Petrakis": 3,
        "Jack Moreau": None,
    }

    w = wao(store, make_race, 2, (7, 12, 33, 9))
    clicks(w, ids, 7)
    assert "dns" in keys(w, 12) and "dns" not in keys(w, 7)
    ok(w.act(ids[12], "dns"))
    clicks(w, ids, 33, 9)
    assert w.state == "provisional"
    assert ranks(w) == {
        "Maya Petrakis": 1,
        "Jack Moreau": 2,
        "Ben Szymanski": 3,
        "Tess Gallagher": None,
    }

    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    m = LiveRace(store, race_id)
    teams = {m.name(t): t for t in m.roster.ids}
    ok(m.click(teams["Blue"]))
    ok(m.record_sprint())
    assert "dns" in [k for k, _ in m.rider_actions(teams["Red"])]
    assert m.act(teams["Blue"], "dns") == rc.Outcome(
        False, "Blue has a result in this race; teams who leave did not finish."
    )
    ok(m.act(teams["Red"], "dns"))
    assert m.standings().by_entrant(teams["Red"]).status == "DNS"


def test_a_staged_place_counts_as_a_result_for_dns(store, make_race, ids, house):
    s = points_race(store, make_race, house)
    clicks(s, ids, 7)
    assert "dns" not in [k for k, _ in s.rider_actions(ids[7])]
    assert "has a result" in s.act(ids[7], "dns").message
    ok(s.click(ids[7]))  # the badge comes off
    assert "dns" in [k for k, _ in s.rider_actions(ids[7])]


def test_a_sprint_says_how_many_it_awards_and_a_click_past_them_scores_nothing(
    store, make_race, ids
):
    """Where to stop, said up front; a click past it allowed for a dead heat."""
    from madtracker.scoring import rules as R

    s = LiveRace(store, make_race("points", [7, 12, 33, 9, 3], R.points_race_rules(sprint_count=2)))
    assert s.task().text == "Sprint 1: click the first 4 riders in order, then Record Sprint."
    for bib in (7, 12, 33, 9, 3):
        ok(s.click(ids[bib]))
    cards = {c.entrant_id: c for c in s.screen().cards}
    assert [cards[ids[b]].past_awarded for b in (7, 12, 33, 9, 3)] == [False] * 4 + [True]
    # Tied up into 4th, the fifth click scores after all.
    ok(s.tie_above(ids[3]))
    cards = {c.entrant_id: c for c in s.screen().cards}
    assert cards[ids[3]].badge == 4 and not cards[ids[3]].past_awarded
    ok(s.record_sprint())
    # The final sprint takes every rider, so every badge there scores.
    assert s.task().kind == "final_sprint"
    ok(s.click(ids[7]))
    assert not any(c.past_awarded for c in s.screen().cards)


def test_a_tempo_sprint_asks_for_the_winner(store, make_race, ids):
    from madtracker.scoring import rules as R

    s = LiveRace(store, make_race("tempo", [7, 12, 33], R.tempo_rules(sprint_count=3)))
    assert s.task().text == "Sprint 1: click the winner, then Record Sprint."


def test_a_win_and_out_lap_does_not_reopen_as_a_sprint(store, make_race, ids):
    """A lap has one winner: staged as a points sprint it would take a second place."""
    from madtracker.scoring import rules as R

    s = LiveRace(store, make_race("win_and_out", [7, 12, 33, 9], R.win_and_out_rules(2)))
    ok(s.click(ids[7]))
    log = list(store.live_actions(s.race_id))
    assert s.reopen_sprint(1) == rc.Outcome(False, "There is no sprint to record now.")
    assert not s.editing and s.staged() == []
    assert s.task().text == "Lap 2: click the winner."
    assert not any(c.past_awarded for c in s.screen().cards)
    assert list(store.live_actions(s.race_id)) == log


# ----- the officials' rulings: a points penalty, a lap not counted ----------


def test_disqualify_waits_while_a_sprint_is_reopened(store, make_race, ids, house):
    """R-NF-4: a DQ'd rider is not placed and the sprint points stand. The
    correction (the order across the line) and the DQ (a ruling) are two
    calls; the DQ waits for Record, so a rider the correction places keeps
    that sprint's points once disqualified, and nobody behind moves up in
    the sprint."""
    s = points_race(store, make_race, house, bibs=(3, 5, 7, 8), sprints=3)
    clicks(s, ids, 3, 5, 7)
    ok(s.record_sprint())
    ok(s.reopen_sprint(1))
    ok(s.click(ids[8]))
    assert "dq" not in keys_of(s, ids[8])
    assert s.act(ids[8], "dq") == rc.Outcome(False, rc.CORRECTION_OPEN)
    ok(s.record_sprint())
    assert "dq" in keys_of(s, ids[8])
    ok(s.act(ids[8], "dq"))
    row = s.standings().by_entrant(ids[8])
    assert (row.status, row.rank) == ("DQ", None)
    assert row.sprint_points[0] == house.POINTS_TABLE[3], "4th in Sprint 1 stands"
    assert s.standings().by_entrant(ids[3]).sprint_points[0] == house.POINTS_TABLE[0]
    ok(s.undo())
    assert s.standings().by_entrant(ids[8]).status is None


def test_rulings_are_offered_on_the_card_and_the_row_and_never_when_final(
    store, make_race, ids, house
):
    """USAC 8D5(b), 8D5(c), 2N3(e): the officials take points or a lap; the
    scorer records the number. On the card while the race runs, on the
    row once the result is complete, nowhere while a sprint is reopened
    or the race is final."""
    s = points_race(store, make_race, house)
    keys = lambda bib: [k for k, _ in s.rider_actions(ids[bib])]  # noqa: E731
    assert keys(7) == ["dns", "dnf", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "dq"]
    assert s.act(ids[7], "lap_not_counted") == rc.Outcome(
        False, "Maya Petrakis has no lap gained to cancel."
    )
    ok(s.act(ids[7], "lap_gained"))
    assert keys(7) == [
        "dnf", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "lap_not_counted", "dq"
    ]  # fmt: skip
    assert [k for k, _ in s.review_actions(ids[7])] == keys(7), "the row offers what the card does"
    clicks(s, ids, 7, 33)
    ok(s.record_sprint())
    ok(s.reopen_sprint(1))
    assert keys(7) == ["move_down", "tie_below", "dnf", "lap_gained", "lap_lost"]
    assert s.act(ids[7], "points_penalty:5") == rc.Outcome(
        False, "Points Penalty waits until the sprint being corrected is recorded or cancelled."
    )
    assert s.act(ids[7], "dq") == rc.Outcome(False, rc.CORRECTION_OPEN)
    s.cancel_edit()
    clicks(s, ids, 12, 7, 33)
    assert s.state == "provisional"
    assert [k for k, _ in s.review_actions(ids[7])] == ["points_penalty", "lap_not_counted", "dq"]
    assert [k for k, _ in s.review_actions(ids[12])] == ["points_penalty", "dq"]
    assert keys(7) == ["points_penalty", "lap_not_counted", "dq"]
    assert s.screen().rows[0].actions[0] == ("points_penalty", "Points Penalty...")
    ok(s.review(ids[12], "dq"))
    # The row refuses a ruling with the card's sentence.
    assert s.review(ids[12], "points_penalty:5") == rc.Outcome(
        False, "Tess Gallagher is already DQ. Undo takes it back."
    )
    ok(s.mark_final())
    assert s.review_actions(ids[7]) == [] and keys(7) == []
    assert s.review(ids[7], "points_penalty:5") == rc.Outcome(False, rc.FINAL_TEXT)
    assert s.act(ids[7], "lap_not_counted") == rc.Outcome(False, rc.FINAL_TEXT)


def test_a_penalty_after_the_result_keeps_it_provisional_and_ranks_by_the_total(
    store, make_race, ids, house
):
    s = points_race(store, make_race, house)
    clicks(s, ids, 7, 33)
    ok(s.record_sprint())
    clicks(s, ids, 7, 12, 33)
    assert s.state == "provisional"
    # 7: 10 + 20, 33: 7 + 10, 12: 14.
    assert ranks(s) == {"Maya Petrakis": 1, "Jack Moreau": 2, "Tess Gallagher": 3}
    # The menu's bare key, and a number that is not one, record nothing.
    for key in ("points_penalty", "points_penalty:-3", "points_penalty:x"):
        assert s.review(ids[7], key) == rc.Outcome(False, "Enter the penalty in points."), key
    assert s.review(ids[7], "points_penalty:0") == rc.Outcome(
        False, "Maya Petrakis has no penalty."
    )
    assert s.review(ids[7], "nonsense") == rc.Outcome(False, "Unknown action 'nonsense'.")
    out = ok(s.review(ids[7], "points_penalty:20"))
    assert out.message == "Recorded #7 Maya Petrakis: points penalty 20"
    assert s.state == "provisional" and s.screen().mark_final
    row = s.standings().by_entrant(ids[7])
    assert (row.adjust_points, row.total_points, row.sprint_points) == (-20, 10, (10, 20))
    assert ranks(s) == {"Jack Moreau": 1, "Tess Gallagher": 2, "Maya Petrakis": 3}
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    assert (rows["Maya Petrakis"].penalty, rows["Maya Petrakis"].total) == (-20, 10)
    assert rows["Jack Moreau"].penalty == 0
    assert s.undo_text() == "Undo: #7 Maya Petrakis penalty set to 20"
    assert s.log_rows()[-1].text == "#7 Maya Petrakis: points penalty 20"
    # The board's standings carry it too, and only it.
    feed = board_feed.standings(s.view())
    assert [(r.entry.names[0], r.penalty) for r in feed.rows] == [
        ("Jack Moreau", 0),
        ("Tess Gallagher", 0),
        ("Maya Petrakis", -20),
    ]
    # A second ruling sets the number anew; Undo takes back one at a time.
    ok(s.review(ids[7], "points_penalty:21"))
    assert s.standings().by_entrant(ids[7]).adjust_points == -21
    assert s.log_rows()[-1].text == "#7 Maya Petrakis: points penalty 21 (was 20)"
    ok(s.undo())
    assert s.standings().by_entrant(ids[7]).adjust_points == -20
    ok(s.undo())
    assert s.standings().by_entrant(ids[7]).adjust_points == 0 and s.state == "provisional"
    assert ranks(s) == {"Maya Petrakis": 1, "Jack Moreau": 2, "Tess Gallagher": 3}
    assert s.log_rows()[-1].text == "Undone: #7 Maya Petrakis: points penalty 20"
    # A reopened sprint after the ruling still checks out: the ruling
    # stands after the finish in the log, where a scoring entry could not.
    ok(s.review(ids[7], "points_penalty:20"))
    assert reenter(s, 1, ids, 33, 7).ok
    assert s.standings().by_entrant(ids[7]).total_points == 7 + 20 - 20


def test_the_penalty_is_one_number_set_from_the_card_or_the_row(store, make_race, ids, house):
    """The result has one Penalty figure per rider, so the dialog sets
    that number: a second ruling, a reversal, or a wrong rider is one
    entry each, and the log keeps the difference so one Undo puts the
    earlier number back. It reaches past the sprints recorded since,
    where Undo cannot."""
    s = points_race(store, make_race, house)
    keys = lambda bib: [k for k, _ in s.rider_actions(ids[bib])]  # noqa: E731
    assert s.act(ids[7], "points_penalty:0") == rc.Outcome(False, "Maya Petrakis has no penalty.")
    out = ok(s.act(ids[7], "points_penalty:5"))
    assert out.message == "Recorded #7 Maya Petrakis: points penalty 5"
    assert keys(7) == ["dnf", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "dq"]
    clicks(s, ids, 7, 33)
    ok(s.record_sprint())
    assert s.standings().by_entrant(ids[7]).adjust_points == -5
    # The same number records nothing; a new one replaces it.
    assert s.act(ids[7], "points_penalty:5") == rc.Outcome(
        False, "Maya Petrakis's penalty is already 5 points."
    )
    out = ok(s.act(ids[7], "points_penalty:8"))
    assert out.message == "Recorded #7 Maya Petrakis: points penalty 8 (was 5)"
    assert s.standings().by_entrant(ids[7]).adjust_points == -8
    assert s.undo_text() == "Undo: #7 Maya Petrakis penalty set to 8"
    assert s.log_rows()[-1].text == "#7 Maya Petrakis: points penalty 8 (was 5)"
    # Taken off: the column empties, the sprint recorded between stays.
    out = ok(s.act(ids[7], "points_penalty:0"))
    assert out.message == "Recorded #7 Maya Petrakis: penalty removed (was 8)"
    assert s.standings().by_entrant(ids[7]).adjust_points == 0
    assert s.standings().by_entrant(ids[7]).total_points == 10
    assert all(r.penalty == 0 for r in s.screen().rows), "the Penalty column empties"
    assert s.undo_text() == "Undo: #7 Maya Petrakis penalty set to 0"
    ok(s.undo())
    assert s.standings().by_entrant(ids[7]).adjust_points == -8
    assert s.log_rows()[-1].text == "Undone: #7 Maya Petrakis: penalty removed (was 8)"
    ok(s.undo())
    assert s.standings().by_entrant(ids[7]).adjust_points == -5
    assert s.undo_text() == "Undo: Sprint 1 recorded"
    # The row offers the same entry while the race runs, and the dialog
    # is refused while a sprint is reopened, as on the card.
    row = next(r for r in s.screen().rows if r.entrant_id == ids[7])
    assert ("points_penalty", "Points Penalty...") in row.actions
    ok(s.review(ids[7], "points_penalty:3"))
    assert s.standings().by_entrant(ids[7]).adjust_points == -3
    ok(s.reopen_sprint(1))
    assert s.review(ids[7], "points_penalty:0") == rc.Outcome(
        False, "Points Penalty waits until the sprint being corrected is recorded or cancelled."
    )
    s.cancel_edit()
    clicks(s, ids, 7, 12, 33)
    assert s.state == "provisional"
    ok(s.review(ids[7], "points_penalty:0"))
    assert s.standings().by_entrant(ids[7]).adjust_points == 0 and s.state == "provisional"
    ok(s.mark_final())
    assert s.review(ids[7], "points_penalty:3") == rc.Outcome(False, rc.FINAL_TEXT)


def test_record_sprint_with_fewer_than_the_scoring_places_is_a_shortfall(
    store, make_race, ids, house
):
    """A sprint awards its places to that many riders; fewer clicked is nearly
    always an early Record, so the app asks first: more is allowed, less
    should not slip through. The need drops to the
    riders left when fewer remain, and a reopened sprint counts the same."""
    s = points_race(store, make_race, house)
    places = s.scoring_places(1)
    left = len(s.standings().remaining_entrants)
    need = min(places, left)
    assert need >= 2, (places, left)
    assert s.sprint_shortfall() is None, "nothing clicked: Record is off, not short"
    clicks(s, ids, 7)
    assert s.sprint_shortfall() == (1, need, 1)
    # The app's Record asks through the same replay: nothing is written.
    assert s.record_sprint(ask_short=True) == rc.Outcome(False, short=(1, need, 1))
    assert not s.recorded_sprints()
    clicks(s, ids, *[b for b in (33, 12, 9, 4) if b in ids][: need - 1])
    assert s.sprint_shortfall() is None, "the scoring places are filled"
    ok(s.record_sprint())
    # Reopened, the same count applies; a rider who left lowers the need.
    ok(s.reopen_sprint(1))
    assert s.sprint_shortfall() is None
    ok(s.click(ids[7]))
    assert s.sprint_shortfall() == (need - 1, need, 1)
    s.cancel_edit()


def test_undo_stack_entries_are_shared_between_copies_and_never_change(
    store, make_race, ids, house
):
    """A copy of the staged order shares the stack's entries rather than
    copying them, since the stack grows with every click of the race; an
    entry is immutable, so no copy can change another's."""
    s = points_race(store, make_race, house)
    clicks(s, ids, 7, 12)
    work = s._work()
    assert work.stack == s._staged.stack and work.stack is not s._staged.stack
    assert all(a is b for a, b in zip(work.stack, s._staged.stack, strict=True))
    with pytest.raises(AttributeError):
        work.stack[-1].text = "changed"
    work.stack.pop()
    assert len(s._staged.stack) == 2
    # The stored form is one object per entry, and a reread rebuilds it.
    again = LiveRace(store, s.race_id)
    assert again._staged.stack == s._staged.stack
    ok(again.undo())
    assert again.staged() == [[ids[7]]]


def test_a_penalty_while_racing_sits_beside_the_staged_order(store, make_race, ids, house):
    s = points_race(store, make_race, house)
    clicks(s, ids, 7, 33)
    assert s.staged() == [[ids[7]], [ids[33]]]
    ok(s.act(ids[12], "points_penalty:3"))
    assert s.staged() == [[ids[7]], [ids[33]]], "the clicks stay"
    assert s.state == "running"
    assert s.standings().by_entrant(ids[12]).total_points == -3
    assert s.undo_text() == "Undo: #12 Tess Gallagher penalty set to 3"
    ok(s.record_sprint())
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    assert (rows["Tess Gallagher"].penalty, rows["Tess Gallagher"].total) == (-3, -3)
    assert rows["Maya Petrakis"].penalty == 0 and rows["Maya Petrakis"].total == 10
    ok(s.act(ids[33], "dq"))
    assert s.act(ids[33], "points_penalty:2") == rc.Outcome(
        False, "Jack Moreau is already DQ. Undo takes it back."
    )
    # A DNF keeps the points shown, so a ruling on it stands (engine), but
    # the card's menu is gone with the status: Undo is the way back.
    ok(s.act(ids[12], "dnf"))
    assert s.rider_actions(ids[12]) == [("dq", "Disqualify")]


def test_a_lap_not_counted_takes_back_the_lap_and_its_points(store, make_race, ids, house):
    """Unlike Lost a Lap (a second event, net laps 0 with both on the
    sheet), Lap Not Counted makes the gain never have happened."""
    s = points_race(store, make_race, house)
    ok(s.act(ids[7], "lap_gained"))
    assert {c.entry.names[0]: c.laps for c in s.screen().cards}["Maya Petrakis"] == 1
    assert s.standings().by_entrant(ids[7]).total_points == house.LAP
    out = ok(s.act(ids[7], "lap_not_counted"))
    assert out.message == "Recorded #7 Maya Petrakis: lap not counted"
    assert {c.entry.names[0]: c.laps for c in s.screen().cards}["Maya Petrakis"] == 0
    row = s.standings().by_entrant(ids[7])
    assert (row.laps_gained, row.laps_lost, row.lap_points, row.total_points) == (0, 0, 0, 0)
    assert s.undo_text() == "Undo: #7 Maya Petrakis marked Lap Not Counted"
    assert "lap_not_counted" not in [k for k, _ in s.rider_actions(ids[7])]
    assert s.act(ids[7], "lap_not_counted") == rc.Outcome(
        False, "Maya Petrakis has no lap gained to cancel."
    )
    assert s.log_rows()[-1].text == "#7 Maya Petrakis: lap not counted"
    ok(s.undo())
    assert s.standings().by_entrant(ids[7]).laps_gained == 1
    ok(s.act(ids[7], "lap_lost"))
    assert s.standings().by_entrant(ids[7]).net_laps == 0
    assert "lap_not_counted" in [k for k, _ in s.rider_actions(ids[7])], "the gain still stands"
    ok(s.undo())
    # From the row, after the finish: net laps 0 and the lap points gone.
    clicks(s, ids, 7, 33)
    ok(s.record_sprint())
    clicks(s, ids, 7, 12, 33)
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    assert (rows["Maya Petrakis"].laps, rows["Maya Petrakis"].lap_points) == (1, house.LAP)
    ok(s.review(ids[7], "lap_not_counted"))
    assert s.state == "provisional"
    rows = {r.entry.names[0]: r for r in s.screen().rows}
    assert (rows["Maya Petrakis"].laps, rows["Maya Petrakis"].lap_points) == (0, 0)
    assert rows["Maya Petrakis"].total == 10 + 20
    assert [k for k, _ in s.review_actions(ids[7])] == ["points_penalty", "dq"]


def test_a_lap_not_counted_is_noted_beside_the_name(store, make_race, ids, house):
    """The struck lap leaves no figure on the row, so the
    row says so beside the name (the sheet prints it, the table tips it),
    as a mishap out of the finish does."""
    s = LiveRace(store, make_race("points", [3, 5, 7], house.points(2)))
    ok(s.act(ids[7], "lap_gained"))
    ok(s.act(ids[7], "lap_not_counted"))
    notes = {r.entry.names[0]: r.note for r in s.screen().rows}
    assert notes == {"Maya Petrakis": "Lap not counted", "Marcus Delgado": "", "Priya Okafor": ""}
    ok(s.act(ids[7], "lap_gained"))
    ok(s.act(ids[7], "lap_not_counted"))
    assert {r.note for r in s.screen().rows if r.entrant_id == ids[7]} == {"2 laps not counted"}
    ok(s.undo())
    assert {r.note for r in s.screen().rows if r.entrant_id == ids[7]} == {"Lap not counted"}
    # A chase row carries the same note once the finish is in.
    c = chase(store, make_race)
    ok(c.act(ids[7], "lap_gained"))
    ok(c.act(ids[7], "lap_not_counted"))
    for bib in (7, 9, 12, 33):
        ok(c.click(ids[bib]))
    assert [r.note for r in c.screen().rows] == ["Lap not counted", "", "", ""]


def test_finish_order_moves_stay_within_the_riders_lap(store, make_race, ids):
    """The engine ranks by laps before the line (USAC 2C4), so with a rider
    a lap up the moves name and give places on another rider's own lap
    only: no "Move to 1st" that gives 2nd, no Move Up that does nothing."""
    s = chase(store, make_race)
    ok(s.act(ids[7], "lap_gained"))
    for bib in (12, 33, 9, 7):
        ok(s.click(ids[bib]))
    assert ranks(s) == {
        "Maya Petrakis": 1,
        "Tess Gallagher": 2,
        "Jack Moreau": 3,
        "Ben Szymanski": 4,
    }
    # The lap-up rider is alone on their lap: nothing to move among.
    assert [k for k, _ in s.review_actions(ids[7])] == ["lap_not_counted", "dq"]
    # The others move among themselves, and the labels name their lap's places.
    assert s.review_actions(ids[9]) == [
        ("move_up", "Move Up"),
        ("move_to:0", "Move to 2nd"),
        ("move_to:1", "Move to 3rd"),
        ("tie_above", "Tie with the Rider Above"),
        ("dq", "Disqualify"),
    ]
    ok(s.review(ids[9], "move_to:0"))
    assert ranks(s) == {
        "Maya Petrakis": 1,
        "Ben Szymanski": 2,
        "Tess Gallagher": 3,
        "Jack Moreau": 4,
    }
    ok(s.review(ids[33], "move_up"))
    assert ranks(s)["Jack Moreau"] == 3 and ranks(s)["Tess Gallagher"] == 4
    ok(s.undo())
    ok(s.undo())
    assert ranks(s) == {
        "Maya Petrakis": 1,
        "Tess Gallagher": 2,
        "Jack Moreau": 3,
        "Ben Szymanski": 4,
    }
    # A lap not counted puts the rider back on the bunch's lap, movable again.
    ok(s.review(ids[7], "lap_not_counted"))
    assert ranks(s)["Maya Petrakis"] == 4
    keys = [k for k, _ in s.review_actions(ids[7])]
    assert keys[0] == "move_up" and "tie_above" in keys


def finish_order(s: LiveRace) -> list[list[int]]:
    return [list(g) for a in s.actions() if isinstance(a, FinishOrder) for g in a.places]


def test_a_move_keeps_the_line_so_a_lap_not_counted_still_drops_the_rider(store, make_race, ids):
    """A move reorders only the riders on its lap, in their own places in
    the line, and a lap not counted takes the lap back as if it was never
    recorded (the Scoring help page), so a later Lap Not Counted never
    leaves the lap-up rider 1st with no lap."""
    line = (7, 12, 33, 9, 19, 24, 36, 44, 3, 5)
    s = chase(store, make_race, bibs=line)
    ok(s.act(ids[5], "lap_gained"))
    for bib in line:
        ok(s.click(ids[bib]))
    assert ranks(s)["Priya Okafor"] == 1, "the lap ranks first, from last across the line"
    ok(s.review(ids[5], "lap_not_counted"))
    assert ranks(s)["Priya Okafor"] == 10
    ok(s.undo())
    ok(s.review(ids[12], "move_up"))
    moved = (12, 7, 33, 9, 19, 24, 36, 44, 3, 5)
    assert finish_order(s) == [[ids[b]] for b in moved], "the lap-up rider keeps his slot"
    assert ranks(s)["Priya Okafor"] == 1 and ranks(s)["Tess Gallagher"] == 2
    ok(s.review(ids[5], "lap_not_counted"))
    expected = {s.name(ids[b]): place for place, b in enumerate(moved, start=1)}
    assert ranks(s) == expected


def test_a_tie_across_a_lap_up_rider_in_the_line_is_one_place(store, make_race, ids):
    """The riders of a lap may sit on both sides of a lap-up rider in the
    line. A tie between them is one group in the line, written at the
    upper rider's slot; the lap-up rider keeps the slot the line gave him."""
    s = chase(store, make_race, bibs=(7, 12, 33, 9))
    ok(s.act(ids[12], "lap_gained"))
    for bib in (7, 12, 33, 9):
        ok(s.click(ids[bib]))
    ok(s.review(ids[33], "tie_above"))
    assert finish_order(s) == [[ids[7], ids[33]], [ids[12]], [ids[9]]]
    assert ranks(s) == {
        "Tess Gallagher": 1,
        "Maya Petrakis": 2,
        "Jack Moreau": 2,
        "Ben Szymanski": 4,
    }
    ok(s.review(ids[12], "lap_not_counted"))
    assert ranks(s) == {
        "Maya Petrakis": 1,
        "Jack Moreau": 1,
        "Tess Gallagher": 3,
        "Ben Szymanski": 4,
    }


def test_lap_not_counted_follows_where_laps_count(store, make_race, ids, house):
    c = chase(store, make_race)
    assert "points_penalty" not in [k for k, _ in c.rider_actions(ids[7])]
    assert c.act(ids[7], "points_penalty:5") == rc.Outcome(
        False, "Points Penalty applies to a Points Race, Madison, or Tempo Race."
    )
    ok(c.act(ids[7], "lap_gained"))
    assert [k for k, _ in c.rider_actions(ids[7])] == [
        "place_last", "dnf", "withdrawn", "lap_gained", "lap_lost", "lap_not_counted", "dq"
    ]  # fmt: skip
    clicks(c, ids, 12, 33, 9, 7)
    assert ranks(c)["Maya Petrakis"] == 1, "a lap up wins from last across the line"
    assert [k for k, _ in c.review_actions(ids[7])][-2:] == ["lap_not_counted", "dq"]
    ok(c.review(ids[7], "lap_not_counted"))
    assert ranks(c)["Maya Petrakis"] == 4 and c.state == "provisional"
    e = LiveRace(store, make_race("elimination", [7, 12, 33], house.elimination()))
    keys = [k for k, _ in e.rider_actions(ids[7])]
    assert "lap_not_counted" not in keys and "points_penalty" not in keys
    assert e.act(ids[7], "lap_not_counted") == rc.Outcome(False, "Laps do not count in this race.")


# ----- moves on the staged order -------------------------------------------


def badges(s: LiveRace) -> list[tuple[str, int | None]]:
    """(name, badge) of the badged cards, in badge order."""
    cards = [(c.entry.names[0], c.badge) for c in s.screen().cards if c.badge is not None]
    return sorted(cards, key=lambda item: item[1])


def keys_of(s: LiveRace, eid: int) -> list[str]:
    return [k for k, _ in s.rider_actions(eid)]


def test_a_staged_badge_moves_up_down_and_to_a_place(store, make_race, ids, house):
    """Section 7: a wrong click order is fixed on the card, one move per Undo."""
    s = points_race(store, make_race, house, bibs=(7, 12, 33, 9))
    clicks(s, ids, 12, 7, 33, 9)
    assert badges(s) == [
        ("Tess Gallagher", 1),
        ("Maya Petrakis", 2),
        ("Jack Moreau", 3),
        ("Ben Szymanski", 4),
    ]
    assert s.rider_actions(ids[33])[:6] == [
        ("move_up", "Move Up"),
        ("move_down", "Move Down"),
        ("move_to:0", "Move to 1st"),
        ("move_to:1", "Move to 2nd"),
        ("move_to:3", "Move to 4th"),
        ("tie_above", "Tie with the Rider Above"),
    ]
    # 1st has nowhere up, 4th nowhere down.
    assert "move_up" not in keys_of(s, ids[12]) and "move_down" in keys_of(s, ids[12])
    assert "move_down" not in keys_of(s, ids[9]) and "move_up" in keys_of(s, ids[9])
    ok(s.act(ids[33], "move_up"))
    assert badges(s) == [
        ("Tess Gallagher", 1),
        ("Jack Moreau", 2),
        ("Maya Petrakis", 3),
        ("Ben Szymanski", 4),
    ]
    assert s.undo_text() == rc.undo_moved(s.label(ids[33]), "up")
    ok(s.act(ids[9], "move_to:0"))
    assert badges(s) == [
        ("Ben Szymanski", 1),
        ("Tess Gallagher", 2),
        ("Jack Moreau", 3),
        ("Maya Petrakis", 4),
    ]
    ok(s.act(ids[9], "move_down"))
    assert [name for name, _ in badges(s)][:2] == ["Tess Gallagher", "Ben Szymanski"]
    # The staged order is on disk, moves included.
    assert badges(LiveRace(store, s.race_id)) == badges(s)
    # Undo takes one move back at a time, then the clicks as before.
    ok(s.undo())
    assert [name for name, _ in badges(s)][0] == "Ben Szymanski"
    ok(s.undo())
    assert [name for name, _ in badges(s)] == [
        "Tess Gallagher",
        "Jack Moreau",
        "Maya Petrakis",
        "Ben Szymanski",
    ]
    ok(s.undo())
    assert [name for name, _ in badges(s)] == [
        "Tess Gallagher",
        "Maya Petrakis",
        "Jack Moreau",
        "Ben Szymanski",
    ]
    assert s.undo_text() == "Undo: #9 Ben Szymanski placed 4th"
    # The second click still takes the badge off.
    ok(s.click(ids[9]))
    assert len(badges(s)) == 3
    # Recorded as moved.
    ok(s.act(ids[33], "move_to:0"))
    ok(s.record_sprint())
    assert s.log_rows()[-1].text.startswith("Sprint 1: 1st #33 Jack Moreau, 2nd #12 Tess Gallagher")


def test_a_staged_badges_moves_are_refused_where_they_do_not_apply(store, make_race, ids, house):
    s = points_race(store, make_race, house, bibs=(7, 12, 33, 9))
    assert s.act(ids[7], "move_up") == rc.Outcome(False, "Maya Petrakis is not placed yet.")
    clicks(s, ids, 12, 7)
    assert s.act(ids[12], "move_up") == rc.Outcome(False, rc.NO_MOVE)
    assert s.act(ids[7], "move_down") == rc.Outcome(False, rc.NO_MOVE)
    assert s.act(ids[7], "move_to:0") == rc.Outcome(False, rc.NO_MOVE), "two groups: up and down"
    assert s.act(ids[7], "move_to:x") == rc.Outcome(False, rc.NO_MOVE)
    assert not s.move_staged(ids[7], "sideways").ok
    assert s.move_staged(999_999, "move_up") == rc.Outcome(False, "Not in this race.")
    # A chase's cards never move: the placed ones leave the grid.
    c = chase(store, make_race)
    ok(c.click(ids[7]))
    assert "move_up" not in keys_of(c, ids[12])
    assert c.act(ids[12], "move_up") == rc.Outcome(False, rc.NO_MOVE)
    assert c.move_staged(ids[12], "move_up") == rc.Outcome(
        False, "Tess Gallagher is not placed yet."
    )
    # Complete and final results refuse too.
    clicks(c, ids, 12, 33, 9)
    assert c.move_staged(ids[12], "move_up") == rc.Outcome(
        False, "The result is recorded. Use the row's menu to change it."
    )
    ok(c.mark_final())
    assert c.move_staged(ids[12], "move_up") == rc.Outcome(False, rc.FINAL_TEXT)


def test_break_tie_takes_the_second_of_a_dead_heat_out_of_it(store, make_race, ids, house):
    s = points_race(store, make_race, house, bibs=(7, 12, 33, 9))
    clicks(s, ids, 12, 7)
    ok(s.act(ids[7], "tie_above"))
    cards = {c.entry.names[0]: c for c in s.screen().cards}
    assert (cards["Maya Petrakis"].badge, cards["Maya Petrakis"].tied) == (1, True)
    # Both tied cards can leave the tie either way; the menu says Break
    # Tie for Move Up there (cards.menu_items), the key is the same.
    assert keys_of(s, ids[7])[:2] == ["move_up", "move_down"]
    assert keys_of(s, ids[12])[:2] == ["move_up", "move_down"]
    assert "tie_above" not in keys_of(s, ids[7])
    ok(s.act(ids[7], "move_up"))
    assert badges(s) == [("Maya Petrakis", 1), ("Tess Gallagher", 2)]
    assert not any(c.tied for c in s.screen().cards)
    assert s.undo_text() == rc.undo_moved(s.label(ids[7]), "up")
    ok(s.undo())
    assert sorted(badges(s)) == [("Maya Petrakis", 1), ("Tess Gallagher", 1)]
    ok(s.act(ids[12], "move_down"))
    assert badges(s) == [("Maya Petrakis", 1), ("Tess Gallagher", 2)]


def test_the_past_places_badge_follows_a_move(store, make_race, ids):
    s = LiveRace(store, make_race("points", [7, 12, 33, 9, 3], R.points_race_rules(sprint_count=2)))
    clicks(s, ids, 7, 12, 33, 9, 3)
    cards = {c.entrant_id: c for c in s.screen().cards}
    assert [cards[ids[b]].past_awarded for b in (9, 3)] == [False, True]
    ok(s.act(ids[3], "move_up"))
    cards = {c.entrant_id: c for c in s.screen().cards}
    assert (cards[ids[3]].badge, cards[ids[3]].past_awarded) == (4, False)
    assert (cards[ids[9]].badge, cards[ids[9]].past_awarded) == (5, True)
    ok(s.act(ids[9], "move_to:0"))
    cards = {c.entrant_id: c for c in s.screen().cards}
    assert (cards[ids[9]].badge, cards[ids[9]].past_awarded) == (1, False)
    assert (cards[ids[7]].badge, cards[ids[7]].past_awarded) == (2, False)
    assert (cards[ids[33]].badge, cards[ids[33]].past_awarded) == (4, False)
    assert (cards[ids[3]].badge, cards[ids[3]].past_awarded) == (5, True)


def test_a_reopened_sprint_moves_its_badges_and_record_sprint_confirms(
    store, make_race, ids, house
):
    """Section 8: the badges of a reopened sprint move as live ones do.

    Record Sprint writes the moved order and Undo of that correction
    puts the sprint back; Cancel discards the moves.
    """
    s = points_race(store, make_race, house)
    clicks(s, ids, 12, 7, 33)
    ok(s.record_sprint())
    sprint = lambda: {r.entry.names[0]: r.sprints[0] for r in s.screen().rows}  # noqa: E731
    assert sprint() == {"Tess Gallagher": 10, "Maya Petrakis": 7, "Jack Moreau": 5}
    ok(s.reopen_sprint(1))
    assert keys_of(s, ids[33])[:4] == ["move_up", "move_to:0", "move_to:1", "tie_above"]
    ok(s.act(ids[33], "move_to:0"))
    assert badges(s) == [("Jack Moreau", 1), ("Tess Gallagher", 2), ("Maya Petrakis", 3)]
    assert s.undo_text() == rc.undo_moved(s.label(ids[33]), "to 1st")
    ok(s.act(ids[7], "move_up"))
    assert badges(s) == [("Jack Moreau", 1), ("Maya Petrakis", 2), ("Tess Gallagher", 3)]
    ok(s.record_sprint())
    assert s.editing_sprint is None
    assert sprint() == {"Jack Moreau": 10, "Maya Petrakis": 7, "Tess Gallagher": 5}
    assert s.log_rows()[-1].text == (
        "Sprint 1: 1st #33 Jack Moreau, 2nd #7 Maya Petrakis, 3rd #12 Tess Gallagher"
    )
    assert s.undo_text() != rc.undo_moved(s.label(ids[33]), "to 1st"), (
        "the correction is one log action"
    )
    ok(s.undo())
    assert sprint() == {"Tess Gallagher": 10, "Maya Petrakis": 7, "Jack Moreau": 5}
    # Cancel discards the moves.
    ok(s.reopen_sprint(1))
    ok(s.act(ids[33], "move_up"))
    ok(s.act(ids[33], "move_up"))
    assert badges(s)[0] == ("Jack Moreau", 1)
    s.cancel_edit()
    assert s.editing_sprint is None and s.staged() == []
    assert sprint() == {"Tess Gallagher": 10, "Maya Petrakis": 7, "Jack Moreau": 5}
    # Undo inside the correction takes the moves back one at a time, then the places.
    ok(s.reopen_sprint(1))
    ok(s.act(ids[33], "move_up"))
    ok(s.undo())
    assert badges(s) == [("Tess Gallagher", 1), ("Maya Petrakis", 2), ("Jack Moreau", 3)]
    assert s.undo_text() == "Undo: #33 Jack Moreau placed 3rd"
    s.cancel_edit()


def test_a_stray_move_names_why_it_is_refused(store, make_race, ids, house):
    """A tie asked of a tail rider, and a move asked of a DNF rider in a
    reopened sprint, each say the real reason, not "not placed yet" or
    that there is no place."""
    s = chase(store, make_race)
    ok(s.click(ids[7]))
    ok(s.act(ids[9], "place_last"))
    assert s.move_staged(ids[9], "tie_above") == rc.Outcome(False, rc.NO_MOVE)
    p = LiveRace(store, make_race("points", [3, 5, 7, 8], house.points(2)))
    for bib in (3, 5, 7):
        ok(p.click(ids[bib]))
    ok(p.record_sprint())
    ok(p.act(ids[5], "dnf"))
    ok(p.reopen_sprint(1))
    assert p.act(ids[5], "move_up") == rc.Outcome(
        False, "Priya Okafor is already DNF. Undo takes it back."
    )


def test_a_chases_staged_rows_move_from_the_front_and_from_the_back(store, make_race, ids):
    """Section 7: the finish order being built is corrected in the result list.

    The front rows move among the places clicked from the front, the
    rows Place Last marked move among the back, numbered from the field
    left, and neither crosses the open places between them.
    """
    s = chase(store, make_race, bibs=(7, 12, 33, 9, 3))
    clicks(s, ids, 7, 12, 33)
    rows = {r.entry.names[0]: [k for k, _ in r.actions] for r in s.screen().rows}
    own = ["lap_gained", "lap_lost", "dq"]
    assert rows["Maya Petrakis"] == ["move_down", "move_to:1", "move_to:2", "tie_below", *own]
    assert rows["Tess Gallagher"] == [
        "move_up", "move_down", "move_to:0", "move_to:2", "tie_above", "tie_below", *own
    ]  # fmt: skip
    assert rows["Jack Moreau"] == ["move_up", "move_to:0", "move_to:1", "tie_above", *own]
    labels = {label for r in s.screen().rows for _, label in r.actions}
    assert {"Move to 1st", "Move to 2nd", "Move to 3rd"} <= labels
    ok(s.move_staged(ids[33], "move_up"))
    assert staged_rows(s) == [("Maya Petrakis", "1"), ("Jack Moreau", "2"), ("Tess Gallagher", "3")]
    assert s.undo_text() == rc.undo_moved(s.label(ids[33]), "up")
    ok(s.move_staged(ids[7], "move_to:2"))
    assert staged_rows(s) == [("Jack Moreau", "1"), ("Tess Gallagher", "2"), ("Maya Petrakis", "3")]
    ok(s.undo())
    ok(s.undo())
    assert staged_rows(s) == [("Maya Petrakis", "1"), ("Tess Gallagher", "2"), ("Jack Moreau", "3")]
    assert s.undo_text() == "Undo: #33 Jack Moreau placed 3rd"
    assert s.move_staged(ids[7], "move_up") == rc.Outcome(False, rc.NO_MOVE)
    assert s.move_staged(ids[33], "move_down") == rc.Outcome(False, rc.NO_MOVE)
    ok(s.undo())
    # From the back: tail[0] is the last place, so up is toward the front.
    ok(s.place_last(ids[9]))
    ok(s.place_last(ids[3]))
    assert staged_rows(s) == [
        ("Maya Petrakis", "1"),
        ("Tess Gallagher", "2"),
        ("Marcus Delgado", "4"),
        ("Ben Szymanski", "5"),
    ]
    rows = {r.entry.names[0]: [k for k, _ in r.actions] for r in s.screen().rows}
    assert rows["Ben Szymanski"] == ["move_up", *own]
    assert rows["Marcus Delgado"] == ["move_down", *own]
    assert s.move_staged(ids[9], "move_down") == rc.Outcome(False, rc.NO_MOVE)
    assert s.move_staged(ids[9], "move_to:0") == rc.Outcome(False, rc.NO_MOVE), (
        "no long moves at the back"
    )
    ok(s.move_staged(ids[9], "move_up"))
    assert staged_rows(s)[2:] == [("Ben Szymanski", "4"), ("Marcus Delgado", "5")]
    assert s.staged_tail() == [[ids[3]], [ids[9]]]
    assert s.undo_text() == rc.undo_moved(s.label(ids[9]), "up")
    ok(s.move_staged(ids[9], "move_down"))
    assert staged_rows(s)[2:] == [("Marcus Delgado", "4"), ("Ben Szymanski", "5")]
    ok(s.undo())
    ok(s.undo())
    assert staged_rows(s)[2:] == [("Marcus Delgado", "4"), ("Ben Szymanski", "5")]
    assert s.undo_text() == "Undo: #3 Marcus Delgado placed 4th"
    # The front stays where it was through the back's moves, and the
    # last click still completes the finish.
    ok(s.move_staged(ids[3], "move_down"))
    ok(s.click(ids[33]))
    assert s.state == "provisional"
    assert ranks(s) == {
        "Maya Petrakis": 1,
        "Tess Gallagher": 2,
        "Jack Moreau": 3,
        "Ben Szymanski": 4,
        "Marcus Delgado": 5,
    }


def test_tie_with_the_rider_below_is_the_same_tie_from_the_upper_row(store, make_race, ids, house):
    """The scorer's eye is on the row the officials named; either row records
    the one tie."""
    s = chase(store, make_race, bibs=(7, 12, 33, 9))
    for bib in (7, 12, 33, 9):
        ok(s.click(ids[bib]))
    # The first row has nobody above, so it offers the tie below only;
    # the last has nobody below.
    keys = [k for k, _ in s.review_actions(ids[7])]
    assert keys[0] == "move_down" and "tie_below" in keys and "tie_above" not in keys
    assert "tie_below" not in [k for k, _ in s.review_actions(ids[9])]
    ok(s.review(ids[7], "tie_below"))
    assert ranks(s)["Maya Petrakis"] == 1 and ranks(s)["Tess Gallagher"] == 1
    assert s.undo_text() == "Undo: #12 Tess Gallagher tied with #7 Maya Petrakis", (
        "the rider below joins: the label names them"
    )
    # Within a tie the last row carries the tie below, the first the tie above.
    assert "tie_below" in [k for k, _ in s.review_actions(ids[12])]
    assert "tie_below" not in [k for k, _ in s.review_actions(ids[7])]
    ok(s.undo())
    assert ranks(s)["Maya Petrakis"] == 1 and ranks(s)["Tess Gallagher"] == 2

    # An elimination: the second rider clicked out sits above the first,
    # and ties them from there.
    e = LiveRace(store, make_race("elimination", [3, 5, 7, 8], house.elimination()))
    ok(e.click(ids[3]))
    ok(e.click(ids[5]))
    assert "tie_below" in [k for k, _ in e.review_actions(ids[5])]
    assert "tie_above" in [k for k, _ in e.review_actions(ids[3])]
    ok(e.review(ids[5], "tie_below"))
    out = {r.entrant_id: r.rank for r in e.standings().ranked() if r.eliminated_at is not None}
    assert out[ids[3]] == out[ids[5]]
    assert e.undo_text() == "Undo: #3 Marcus Delgado tied with #5 Priya Okafor", (
        "the rider below joins: the label names them"
    )

    # A staged sprint: the leading badge ties the badge below to it.
    p = LiveRace(store, make_race("points", [7, 12, 33, 9], house.points(2)))
    ok(p.click(ids[7]))
    ok(p.click(ids[12]))
    assert ("tie_below", "Tie with the Rider Below") in p.rider_actions(ids[7])
    assert ("tie_above", "Tie with the Rider Above") in p.rider_actions(ids[12])
    ok(p.act(ids[7], "tie_below"))
    assert p.staged() == [[ids[7], ids[12]]]
    assert p.undo_text() == "Undo: #12 Tess Gallagher tied with #7 Maya Petrakis", (
        "the rider below joins: the label names them"
    )
    assert not p.act(ids[12], "tie_below").ok


def test_the_live_standings_replay_once_per_log_and_again_whenever_it_changes(
    store, make_race, ids, monkeypatch
):
    s = chase(store, make_race)
    replays: list[int] = []
    replay = LiveRace._replay
    monkeypatch.setattr(
        LiveRace,
        "_replay",
        lambda self, actions: replays.append(len(actions)) or replay(self, actions),
    )

    def fresh():
        return LiveRace(store, s.race_id).standings()

    first = s.standings()
    s.screen()
    assert s.standings() is first
    assert len(replays) == 1, "the same log is replayed once"
    ok(s.act(ids[33], "dnf"))
    after_dnf = s.standings()
    assert after_dnf is not first and after_dnf.by_entrant(ids[33]).status == "DNF"
    ok(s.undo())
    assert s.standings().by_entrant(ids[33]).status is None
    ok(s.act(ids[33], "dnf"))
    # Another window's entry, and its undo, change the log this session reads.
    other = LiveRace(store, s.race_id)
    ok(other.act(ids[12], "dnf"))
    assert s.standings().by_entrant(ids[12]).status == "DNF"
    assert s.standings() == fresh()
    ok(other.undo())
    assert s.standings().by_entrant(ids[12]).status is None
    assert s.standings() == fresh()


def test_a_rider_on_two_teams_is_refused_and_the_teams_stay(store, make_race, ids, house):
    """Edit Race's teams are matched by their riders, so two teams with the same
    riders would merge into one; the store refuses the save instead."""
    from madtracker.store import DuplicateEntryError

    race_id = make_race("madison", [3, 24, 5, 36, 8, 12], house.madison(2), teams=TEAMS)
    event_id = store.race(race_id).event_id
    field = [ids[b] for b in (3, 24, 5, 36, 8, 12)]
    before = [(t.team_id, t.name, t.members) for t in store.teams(race_id)]
    blue = store.teams(race_id)[0]
    for clash in (blue.members, (blue.members[0], ids[8])):
        teams = [(t.name, t.color, t.color_hex, t.members) for t in store.teams(race_id)]
        teams.append(("Wolves", "Green", None, clash))
        with pytest.raises(DuplicateEntryError):
            store.save_race(event_id, race_id, {}, field, teams)
        assert [(t.team_id, t.name, t.members) for t in store.teams(race_id)] == before
