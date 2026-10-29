"""LiveRace under a crash, a second window and a long Undo.

A crash is simulated this way: the Store's transaction
context is wrapped so that the write after the first ``commits`` raises
before BEGIN, as a power cut would stop the process there. A fresh
LiveRace then opens the file, and what it shows must be the state before
the action or the state after it, never something in between.

Bibs are the conftest's invented riders; entrant ids are rider ids.
"""

import sqlite3
from contextlib import contextmanager

import pytest

from madtracker.control import race as rc
from madtracker.control.race import LiveRace
from madtracker.scoring import rules as R
from madtracker.scoring.actions import FinishOrder, SprintResult
from madtracker.store import StoreError


@pytest.fixture
def ids(event):
    return event[1]


def ok(outcome):
    assert outcome.ok, outcome.message
    return outcome


class Crash(Exception):
    """The process stopped here."""


@contextmanager
def crash_after(store, commits: int):
    """Let ``commits`` transactions through, then fail the next one at BEGIN."""
    real = store._write
    done = [0]

    @contextmanager
    def write():
        if done[0] >= commits:
            raise Crash
        with real() as conn:
            yield conn
        done[0] += 1

    store._write = write
    try:
        yield done
    finally:
        del store._write


def snap(live: LiveRace) -> tuple:
    """What a scorer sees after a reopen, in terms that compare across races."""
    st = live.standings()
    return (
        live.state,
        tuple((r.kind, tuple(sorted(r.payload.items()))) for r in live.rows()),
        tuple(tuple(g) for g in live.staged(st)),
        live.editing_sprint,
        tuple((r.entrant_id, r.rank, r.status, r.total_points) for r in st.rows),
        st.is_complete,
        live.undo_text(st),
    )


def ranks(live):
    return {live.name(r.entrant_id): r.rank for r in live.standings().rows}


def chase(make_race, bibs=(7, 12, 33, 9)):
    return make_race("chase", list(bibs), R.placings_rules(), name="Chase")


# Each scenario builds a race, brings it to the moment before the action,
# and returns the live race; the action is the one thing that must be atomic.
def _chase_last_click(store, make_race, ids, house=None):
    s = LiveRace(store, chase(make_race))
    for bib in (7, 12, 33):
        ok(s.click(ids[bib]))
    return s, lambda s: s.click(ids[9])


def _chase_dnf_completes(store, make_race, ids, house=None):
    s = LiveRace(store, chase(make_race))
    for bib in (7, 12, 33):
        ok(s.click(ids[bib]))
    return s, lambda s: s.act(ids[9], "dnf")


def _chase_move_up(store, make_race, ids, house=None):
    s, last = _chase_last_click(store, make_race, ids)
    ok(last(s))
    return s, lambda s: s.review(ids[9], "move_up")


def _chase_undo_of_move_up(store, make_race, ids, house=None):
    s, move = _chase_move_up(store, make_race, ids)
    ok(move(s))
    return s, lambda s: s.undo()


def _points_record_sprint(store, make_race, ids, house):
    s = LiveRace(store, make_race("points", [7, 12, 33, 9], house.points(3)))
    ok(s.click(ids[12]))
    ok(s.click(ids[7]))
    return s, lambda s: s.record_sprint()


def _finish_points(s, ids, sprint2=(33,), final=(7, 12, 33, 9)):
    """Record sprint 2 and click the final sprint: a sprint reopens only in the review."""
    for bib in sprint2:
        ok(s.click(ids[bib]))
    ok(s.record_sprint())
    for bib in final:
        ok(s.click(ids[bib]))
    assert s.state == "provisional"


def _points_correction(store, make_race, ids, house):
    s, record = _points_record_sprint(store, make_race, ids, house)
    ok(record(s))
    _finish_points(s, ids)
    ok(s.reopen_sprint(1))
    ok(s.click(ids[12]))
    ok(s.click(ids[33]))
    return s, lambda s: s.record_sprint()


def _win_and_out_swap(store, make_race, ids, house=None):
    s = LiveRace(store, make_race("win_and_out", [7, 12, 33], R.win_and_out_rules(2)))
    for bib in (7, 12, 33):
        ok(s.click(ids[bib]))
    return s, lambda s: s.review(ids[12], "move_up")


def _elimination_undo_winner(store, make_race, ids, house):
    s = LiveRace(store, make_race("elimination", [3, 5, 7], house.elimination()))
    ok(s.click(ids[3]))
    ok(s.click(ids[7]))
    return s, lambda s: s.undo()


SCENARIOS = {
    "chase last click": _chase_last_click,
    "chase dnf completes": _chase_dnf_completes,
    "chase move up": _chase_move_up,
    "chase undo of a move": _chase_undo_of_move_up,
    "points record sprint": _points_record_sprint,
    "points correction": _points_correction,
    "win-and-out swap": _win_and_out_swap,
    "elimination undo of the winner": _elimination_undo_winner,
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_every_action_is_one_transaction(store, make_race, ids, house, name):
    """A crash anywhere leaves the before or the after, nothing else."""
    build = SCENARIOS[name]

    def scenario():
        return build(store, make_race, ids, house)

    s, action = scenario()
    ok(action(s))
    after = snap(LiveRace(store, s.race_id))

    for commits in range(6):
        s, action = scenario()
        before = snap(LiveRace(store, s.race_id))
        with crash_after(store, commits):
            try:
                action(s)
            except Crash:
                pass
        reopened = snap(LiveRace(store, s.race_id))
        assert reopened in (before, after), f"crash after {commits} commits: {reopened}"


# ----- Undo, Undo after a correction -----------------------------------------


def test_undo_twice_after_a_win_and_out_swap_takes_back_the_swap_then_the_last_click(
    store, make_race, ids
):
    s, swap = _win_and_out_swap(store, make_race, ids)
    ok(swap(s))
    ok(s.undo())
    assert ranks(s) == {"Maya Petrakis": 1, "Tess Gallagher": 2, "Jack Moreau": 3}
    ok(s.undo())
    # The second Undo takes back the click that placed 33, nothing else.
    laps = sorted((e.sprint_no, e.places[0]) for e in s.actions() if isinstance(e, SprintResult))
    assert laps == [(1, (ids[7],)), (2, (ids[12],))]
    assert not s.standings().is_complete and s.state == "running"
    assert s.task().kind == "order"
    assert not s.mark_final().ok


def test_undo_twice_after_a_points_correction_keeps_sprint_one(store, make_race, ids, house):
    s, record = _points_record_sprint(store, make_race, ids, house)
    ok(record(s))
    _finish_points(s, ids, sprint2=(9,))
    ok(s.reopen_sprint(1))
    ok(s.click(ids[12]))  # off
    ok(s.click(ids[33]))
    ok(s.record_sprint())
    ok(s.undo())
    s.cancel_edit()
    ok(s.undo())
    # Sprint 1 is as first recorded; the final sprint is taken back to its
    # badges less the last click.
    recorded = s.recorded_sprints()
    assert sorted(recorded) == [1, 2]
    assert SprintResult.from_payload(recorded[1].payload).places == ((ids[12],), (ids[7],))
    assert s.staged() == [[ids[7]], [ids[12]], [ids[33]]]
    assert s.task().kind == "final_sprint"


def test_undo_twice_after_a_dq_and_a_move_puts_the_clicked_order_back(store, make_race, ids):
    s, last = _chase_last_click(store, make_race, ids)
    ok(last(s))
    clicked = ranks(s)
    ok(s.act(ids[7], "dq"))
    ok(s.review(ids[9], "move_up"))
    ok(s.undo())
    ok(s.undo())
    assert ranks(s) == clicked and s.state == "provisional"
    assert len([e for e in s.actions() if isinstance(e, FinishOrder)]) == 1


# ----- a reopened sprint is exactly what was scored --------------------------


def test_reopened_sprint_keeps_a_rider_who_since_has_a_status(store, make_race, ids, house):
    s, record = _points_record_sprint(store, make_race, ids, house)
    ok(record(s))
    ok(s.act(ids[7], "dnf"))
    _finish_points(s, ids, final=(12, 33, 9))
    points = {r.entrant_id: r.total_points for r in s.standings().rows}
    ok(s.reopen_sprint(1))
    assert s.staged() == [[ids[12]], [ids[7]]]
    assert {c.entrant_id: c.badge for c in s.screen().cards}[ids[7]] == 2
    ok(s.record_sprint())
    assert {r.entrant_id: r.total_points for r in s.standings().rows} == points


def test_a_reopened_sprint_places_a_rider_whose_dnf_came_after_it(store, make_race, ids, house):
    """A rider can score a sprint and leave later; a correction of a sprint ridden
    before their DNF places them, and the DNF stands."""
    s, record = _points_record_sprint(store, make_race, ids, house)
    ok(record(s))
    ok(s.act(ids[9], "dnf"))
    _finish_points(s, ids, final=(12, 33, 7))
    ok(s.reopen_sprint(1))
    ok(s.click(ids[9]))
    assert s.staged() == [[ids[12]], [ids[7]], [ids[9]]]
    ok(s.record_sprint())
    row = s.standings().by_entrant(ids[9])
    assert row.status == "DNF" and row.sprint_points[0] > 0


def test_a_reopened_sprint_refuses_a_rider_out_before_it_was_ridden(store, make_race, ids, house):
    """A DNF before the sprint, or a DNS, never raced it."""
    s = LiveRace(store, make_race("points", [7, 12, 33, 9], house.points(3)))
    ok(s.act(ids[9], "dnf"))
    ok(s.act(ids[33], "dns"))
    ok(s.click(ids[12]))
    ok(s.click(ids[7]))
    ok(s.record_sprint())
    _finish_points(s, ids, sprint2=(12,), final=(12, 7))
    ok(s.reopen_sprint(1))
    assert s.click(ids[9]).message == "#9 Ben Szymanski is marked Did Not Finish."
    assert not s.click(ids[33]).ok


# ----- the stored state follows the replay -----------------------------------


def test_mark_final_needs_a_complete_result_not_a_stored_state(store, make_race, ids):
    race_id = chase(make_race, (7, 12))
    store.set_state(race_id, "provisional")  # a drift, as a crash could leave
    s = LiveRace(store, race_id)
    assert s.state == "setup", "the stored state is reconciled from the replay on load"
    assert not s.mark_final().ok
    assert store.race(race_id).state == "setup"


# ----- Undo takes back the last action exactly -------------------------------


def test_undo_takes_a_newer_rider_action_before_an_older_staged_click(store, make_race, ids, house):
    s = LiveRace(store, make_race("points", [7, 12, 33, 9], house.points(3)))
    ok(s.click(ids[12]))
    ok(s.act(ids[9], "lap_gained"))
    assert s.undo_text() == "Undo: #9 Ben Szymanski gained a lap"
    ok(s.undo())
    assert s.rows() == [] and s.staged() == [[ids[12]]]
    ok(s.undo())
    assert s.staged() == []


def test_undo_after_the_completing_click_takes_back_one_click(store, make_race, ids, house):
    s, last = _chase_last_click(store, make_race, ids)
    ok(last(s))
    ok(s.undo())
    assert s.rows() == [] and s.staged() == [[ids[7]], [ids[12]], [ids[33]]]
    assert not s.standings().is_complete and s.state_label() == "Racing"
    ok(s.undo())
    assert s.staged() == [[ids[7]], [ids[12]]]

    p = LiveRace(store, make_race("points", [7, 12, 33, 9], house.points(2)))
    ok(p.click(ids[12]))
    ok(p.record_sprint())
    for bib in (9, 33, 12, 7):
        ok(p.click(ids[bib]))
    assert p.state == "provisional"
    ok(p.undo())
    assert list(p.recorded_sprints()) == [1]
    assert p.staged() == [[ids[9]], [ids[33]], [ids[12]]]
    assert p.task().kind == "final_sprint"


def test_undo_reverses_a_staged_tie_and_an_unplace_exactly(store, make_race, ids, house):
    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(3)))
    for bib in (7, 12, 33):
        ok(s.click(ids[bib]))
    ok(s.tie_above(ids[33]))
    assert s.staged() == [[ids[7]], [ids[12], ids[33]]]
    ok(s.undo())
    assert s.staged() == [[ids[7]], [ids[12]], [ids[33]]]
    ok(s.click(ids[12]))  # off
    assert s.staged() == [[ids[7]], [ids[33]]]
    ok(s.undo())
    assert s.staged() == [[ids[7]], [ids[12]], [ids[33]]]


# ----- two windows on one file -----------------------------------------------


def test_a_second_window_is_refused_and_reloaded_not_overwritten(store, make_race, ids):
    race_id = chase(make_race)
    a = LiveRace(store, race_id)
    b = LiveRace(store, race_id)
    ok(a.click(ids[7]))
    with pytest.raises(StoreError, match="Another window changed this race"):
        b.click(ids[12])
    assert LiveRace(store, race_id).staged() == [[ids[7]]]
    assert b.staged() == [[ids[7]]], "the refused window reloaded"
    ok(b.click(ids[12]))
    assert LiveRace(store, race_id).staged() == [[ids[7]], [ids[12]]]


# ----- a database error is a StoreError --------------------------------------


def test_a_sqlite_error_in_the_controller_surfaces_as_a_store_error(store, make_race, ids):
    s = LiveRace(store, chase(make_race))

    @contextmanager
    def broken():
        raise sqlite3.OperationalError("disk I/O error")
        yield  # pragma: no cover

    store._write = broken
    try:
        with pytest.raises(StoreError, match="disk I/O error"):
            s.click(ids[7])
    finally:
        del store._write
    assert rc.LiveRace(store, s.race_id).staged() == []


@pytest.mark.parametrize("step", ["undo", "click", "record", "act"])
def test_a_refused_write_leaves_the_undo_stack_as_the_file_has_it(
    store, make_race, ids, house, monkeypatch, step
):
    """The staged copy shares the undo stack with what is on screen, so a
    pop or push before a write that the store refuses (disk full, a lock)
    must not stick: the file is the truth and the next Undo reads it."""
    from madtracker.store import StoreError

    s = LiveRace(store, make_race("points", [7, 12, 33], house.points(3)))
    ok(s.click(ids[7]))
    ok(s.act(ids[12], "lap_gained"))
    ok(s.click(ids[33]))
    before = (s.undo_text(), s.staged(), [e.n for e in s._staged.stack])

    def refuse(*args, **kwargs):
        raise StoreError("disk full")

    monkeypatch.setattr(store, "append_batch", refuse)
    with pytest.raises(StoreError):
        if step == "undo":
            s.undo()
        elif step == "click":
            s.click(ids[12])
        elif step == "record":
            s.record_sprint()
        else:
            s.act(ids[7], "lap_lost")
    monkeypatch.undo()
    assert (s.undo_text(), s.staged(), [e.n for e in s._staged.stack]) == before
    fresh = LiveRace(store, s.race_id)
    assert fresh.screen() == s.screen()
    ok(s.undo())
    assert s.staged() == [[ids[7]]]
