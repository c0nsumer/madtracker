"""The input fuzzer, deep tier: seeded random garbage and random scorer sessions. Minutes, not seconds.

Skipped by the everyday run (the ``fuzz`` marker is deselected in
pyproject.toml). Run it before tagging a version:

    QT_QPA_PLATFORM=offscreen pytest -q -m fuzz

Seeds are fixed so a failure repeats; FUZZ_SEEDS (a count) widens the
run, and FUZZ_SEED_BASE moves it. Each failure names its seed.
"""

import os
import random
import sys

import pytest
from apps import dispose_app
from fuzz_inputs import (
    CORPUS,
    Escapes,
    build_outputs,
    make_controller,
    quiet_qt,
    run_screen,
    screens,
    stored_problems,
)

from madtracker import applog

pytestmark = pytest.mark.fuzz

SEEDS = int(os.environ.get("FUZZ_SEEDS", "2"))
BASE = int(os.environ.get("FUZZ_SEED_BASE", "1"))
STRINGS_PER_SCREEN = 25
STEPS = 1500


def random_strings(rnd: random.Random, count: int) -> list[str]:
    """Pieces of the corpus run together, with random code points between them."""
    out = []
    for _ in range(count):
        parts = []
        for _ in range(rnd.randint(1, 4)):
            if rnd.random() < 0.7:
                parts.append(rnd.choice(CORPUS)[: rnd.choice((3, 20, 200, 20_000))])
            else:
                # Anywhere in Unicode, surrogates and private use included.
                parts.append(
                    "".join(chr(rnd.randint(0, 0x10FFFF)) for _ in range(rnd.randint(1, 8)))
                )
        out.append("".join(parts))
    return out


@pytest.fixture
def fuzzed(qapp, tmp_path, monkeypatch):
    quiet_qt(monkeypatch)
    escapes = Escapes()
    monkeypatch.setattr(sys, "excepthook", escapes)
    made = []

    def make():
        c = make_controller(qapp, tmp_path / f"run{len(made)}")
        made.append(c)
        return c

    yield make, escapes
    for c in made:
        dispose_app(c)
    applog.use_folder(None)


@pytest.mark.parametrize("seed", range(BASE, BASE + SEEDS))
def test_random_garbage_in_every_input_with_the_outputs_after_each(fuzzed, tmp_path, seed):
    """A fresh dialog per string, and the PDF and CSV after every string, not once per input."""
    make, escapes = fuzzed
    c = make()
    rnd = random.Random(seed)
    failures = []
    for name, factory in screens(c).items():
        strings = random_strings(rnd, STRINGS_PER_SCREEN)
        for text in strings:
            for line in run_screen(c, factory, [text], tmp_path / "out", escapes, fresh=True):
                failures.append(f"seed {seed}, {name}: {line}")
    assert not failures, "\n".join(failures[:20])


def _snapshot(conn) -> tuple[list, list]:
    actions = conn.execute("SELECT * FROM race_action ORDER BY action_id").fetchall()
    changes = conn.execute("SELECT * FROM race_state_change ORDER BY change_id").fetchall()
    return [tuple(r) for r in actions], [tuple(r) for r in changes]


def _screen_key(screen) -> tuple:
    return (
        screen.state_label,
        screen.task.kind,
        screen.task.text,
        screen.undo_text,
        screen.undo_enabled,
        tuple((card.entrant_id, card.badge) for card in screen.cards),
        tuple((row.entrant_id, row.place_text) for row in screen.rows),
    )


def _garbage_edit(c, rnd: random.Random) -> str:
    """A setup change mid-night with a garbage string: a rider's name, a bib, a group, a race's name."""
    from madtracker.control.roster import roster_bib_refusal, typed_bib
    from madtracker.store import StoreError

    text = rnd.choice(random_strings(rnd, 1) + list(CORPUS))
    store, event_id = c.store, c.event.event_id
    entries = store.entries(event_id)
    pick = rnd.random()
    try:
        if pick < 0.4 and entries:
            entry = rnd.choice(entries)
            field = rnd.choice(("first_name", "last_name"))
            store.update_rider(entry.rider_id, **{field: text or "X"})
        elif pick < 0.7 and entries:
            entry = rnd.choice(entries)
            bib = typed_bib(text)
            if not roster_bib_refusal(store, event_id, entry.rider_id, bib):
                store.change_bib(event_id, entry.rider_id, bib)
        elif pick < 0.85:
            race = rnd.choice(c.races)
            store.update_race(race.race_id, name=text or "Race")
        else:
            entry = rnd.choice(entries)
            store.set_entry_group(event_id, entry.rider_id, text)
    except (StoreError, ValueError):
        # Refused, as the screens refuse it; what matters is what happens next.
        pass
    # The edit is made in Edit event; Score then shows the file as it stands.
    c.close_setup()
    return f"edit {pick:.2f} {text[:20]!r}"


@pytest.mark.parametrize("seed", range(BASE, BASE + SEEDS))
def test_random_scorer_sessions_with_garbage_edits_keep_the_history_and_the_screen(
    fuzzed, tmp_path, seed
):
    """Clicks, rider actions, record, undo, final, reopen, row moves, switches and restarts.

    After every step: nothing escaped, no history row changed, a fresh
    read of the file shows the same screen (what a restart shows), the
    file is clean; every 100 steps, the PDF and the CSV build.
    """
    from madtracker.app import AppController
    from madtracker.control import board_feed
    from madtracker.control.race import LiveRace

    make, escapes = fuzzed
    c = make()
    rnd = random.Random(seed)
    problems: list[str] = []
    conn = c.store.connection
    before = _snapshot(conn)
    ops: list[str] = []
    for step in range(STEPS):
        live = c.live
        if live is None:
            c.select_race(rnd.choice(c.races).race_id)
            continue
        ids = list(live.roster.ids) or [0]
        eid = rnd.choice([*ids, 999_999])
        r = rnd.random()
        try:
            if r < 0.28:
                op = f"click {eid}"
                c.click(eid)
            elif r < 0.38:
                keys = [k for k, _ in live.rider_actions(eid)] if eid in live.roster.ids else []
                # A ruling's key with its points, without, and with garbage.
                stray = rnd.choice(
                    ["points_penalty:5", "points_penalty:0", "points_penalty", "points_penalty:x"]
                )
                key = rnd.choice(
                    [
                        *keys,
                        "dns",
                        "dnf",
                        "dq",
                        "lap_gained",
                        "lap_lost",
                        "place_last",
                        "lap_not_counted",
                        # A badge's moves, with a place that may not exist.
                        "move_up",
                        "move_down",
                        f"move_to:{rnd.randint(-1, 12)}",
                        stray,
                    ]
                )
                op = f"rider {eid} {key}"
                c.rider_action(eid, key)
            elif r < 0.44:
                op = "record"
                c.record_sprint()
            elif r < 0.47:
                op = "rest"
                c.place_rest_together()
            elif r < 0.62:
                op = "undo"
                c.undo()
            elif r < 0.66:
                op = "final"
                c.mark_final()
            elif r < 0.69:
                op = "reopen"
                c.reopen_race()
            elif r < 0.76:
                number = rnd.randint(0, 6)
                op = f"reopen sprint {number}"
                c.reopen_sprint(number)
            elif r < 0.77:
                op = "cancel"
                c.cancel_edit()
            elif r < 0.83:
                keys = [k for k, _ in live.review_actions(eid)] if eid in live.roster.ids else []
                # Long moves to places that may not exist are refused, never crash.
                stray = rnd.choice([f"move_to:{rnd.randint(-1, 12)}", "points_penalty:3"])
                key = rnd.choice(
                    [*keys, "move_up", "move_down", "tie_above", "lap_not_counted", stray]
                )
                op = f"row {eid} {key}"
                c.row_action(eid, key)
            elif r < 0.88:
                race_id = rnd.choice(c.races).race_id
                op = f"select {race_id}"
                c.select_race(race_id)
            elif r < 0.97:
                op = _garbage_edit(c, rnd)
            else:
                op = "restart"
                shown = _screen_key(c.live.screen()) if c.live else None
                race_id = c.live.race_id if c.live else None
                folder, settings = c.data_dir, c.settings
                dispose_app(c)
                c = AppController(c.app, settings=settings, data_dir=folder)
                conn = c.store.connection
                conn.execute("PRAGMA synchronous = OFF")
                again = _screen_key(c.live.screen()) if c.live else None
                if c.live is None or c.live.race_id != race_id or shown != again:
                    problems.append(f"seed {seed} step {step}: a restart changed the screen")
        except Exception as exc:  # reported with the step
            problems.append(f"seed {seed} step {step} {op}: raised {exc!r}")
        ops.append(op)
        for escaped in escapes.take():
            problems.append(f"seed {seed} step {step} {op}: escaped a slot\n{escaped}")
        now = _snapshot(conn)
        if now[0][: len(before[0])] != before[0] or now[1][: len(before[1])] != before[1]:
            problems.append(f"seed {seed} step {step} {op}: a history row changed")
        before = now
        if c.live is not None:
            try:
                fresh = LiveRace(c.store, c.live.race_id)
                if _screen_key(c.live.screen()) != _screen_key(fresh.screen()):
                    problems.append(f"seed {seed} step {step} {op}: the file reads differently")
                board_feed.board_for(c.live.view())
            except Exception as exc:
                problems.append(f"seed {seed} step {step} {op}: screen failed {exc!r}")
        for problem in stored_problems(c.store):
            problems.append(f"seed {seed} step {step} {op}: stored {problem}")
        if step % 100 == 99:
            try:
                build_outputs(c, tmp_path / "out")
            except Exception as exc:
                problems.append(f"seed {seed} step {step}: outputs failed {exc!r}")
        if len(problems) > 10:
            break
    assert c.store.integrity_check() == []
    tail = "\nlast steps: " + "; ".join(ops[-12:])
    assert not problems, "\n".join(problems[:10]) + tail
