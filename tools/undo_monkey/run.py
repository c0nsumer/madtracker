"""The undo monkey: a scorer who enters, corrects, and undoes at random, checked after every step.

Each walk builds one race in a fresh data file and plays a random walk of
the controller's own offers (``LiveRace``: card clicks, Record Sprint, the
card and row menus, sprint corrections, Place Last, Place the Rest
Together, End Race, Mark Final, Reopen) with Undo about a third of the
time, sometimes all the way back to the empty log. At the empty log the
race may be set up again, as Edit Race allows then (the field, the teams,
the count), and scored on. After every operation it checks the stored
state, the staged order a reopened window reads, the screen against an
independent replay, the append-only log, and that an Undo of the
operation (tried on a copy of the file) puts everything back. See
README.md for the checks and the command line.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import shutil
import sqlite3
import sys
import tempfile
import traceback
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from madtracker.control import rulesets  # noqa: E402
from madtracker.control.race import LiveRace, Outcome  # noqa: E402
from madtracker.control.race_words import (  # noqa: E402
    FINAL_TEXT,
    MOVE_TO,
    MOVES,
    PENALTY,
    REOPEN_FIRST,
    RIDER_ACTIONS,
    TIES,
    UNDO,
)
from madtracker.scoring import compute_for_format  # noqa: E402
from madtracker.scoring import rules as R  # noqa: E402
from madtracker.store import Store, StoreError  # noqa: E402

# Invented names only: never a real rider.
FIRST = ["Arlo", "Bexa", "Corin", "Dalia", "Emrys", "Fenna", "Galo", "Hesper", "Ivo", "Juna",
         "Kael", "Lisbet", "Moro", "Nell", "Oskel", "Pim"]  # fmt: skip
LAST = ["Quillan", "Rendt", "Sorvik", "Tamsk", "Ulbrin", "Vesk", "Wrenfold", "Yarrow",
        "Zelkin", "Abernook", "Brisk", "Coldmere", "Dunhallow", "Eskett", "Fallowby", "Grint"]  # fmt: skip
COLORS = ["Blue", "Red", "Orange", "Yellow", "Black", "Green"]

FORMATS = ("chase", "handicap", "elimination", "miss_and_out", "points", "madison", "tempo",
           "win_and_out")  # fmt: skip
# Operations whose success pushes exactly one entry on the undo stack.
UNDOABLE = {"click", "record", "act", "row", "place_last", "rest", "end_race"}


class Break(Exception):
    def __init__(self, check: str, message: str, before: Any = None, after: Any = None):
        super().__init__(message)
        self.check, self.message, self.before, self.after = check, message, before, after


def house_points(sprints):
    table = (10, 7, 5, 3, 2, 1)
    return R.SprintPointsRules(
        sprint_count=sprints,
        intermediate_points=table,
        final_points=tuple(2 * p for p in table),
        lap_gained_points=10,
        lap_lost_points=10,
    )


def house_madison(sprints):
    return R.SprintPointsRules(
        sprint_count=sprints, lap_gained_points=10, lap_lost_points=10, scored_unit="team"
    )


# Riders on the roster but in no race: the field an edit at the empty
# log can draw on.
SPARES = 2


def build_race(store: Store, fmt: str, rng: random.Random) -> tuple[int, str, dict[int, int]]:
    """A race of ``fmt`` the way tests/control/conftest.py's make_race builds one.

    Returns the race, its description, and the roster as bib to rider id,
    the field's riders first.
    """
    event = store.add_event("Monkey Night", "2026-10-25")
    team = fmt == "madison"
    n = rng.randint(3, 6) * 2 if team else rng.randint(4, 12)
    drawn = rng.sample(range(1, 99), n + SPARES)
    bibs, spare = drawn[:n], drawn[n:]
    ids = {}
    for bib in [*bibs, *spare]:
        rider = store.add_rider(rng.choice(FIRST), rng.choice(LAST))
        store.add_entry(event.event_id, rider.rider_id, bib)
        ids[bib] = rider.rider_id
    store_fmt = fmt
    if fmt == "chase":
        rules, note = R.placings_rules(), ""
    elif fmt == "handicap":
        rules, note = rulesets.rules_for(store, rulesets.BUILTIN, "handicap"), ""
    elif fmt == "miss_and_out":
        store_fmt = "elimination"
        rules, note = rulesets.rules_for(store, rulesets.BUILTIN, "elimination"), ""
    elif fmt == "elimination":
        survivors = rng.choice([1, 2, 2, 3])
        rules = R.EliminationRules(survivors=survivors, final_by_sprint=survivors > 1)
        note = f"survivors={survivors}"
    elif fmt == "points":
        sprints = rng.choice([2, 3, 3, 4, 5])
        rules, note = house_points(sprints), f"sprints={sprints}"
    elif fmt == "madison":
        sprints = rng.choice([2, 3, 4])
        rules, note = house_madison(sprints), f"sprints={sprints}"
    elif fmt == "tempo":
        sprints = rng.choice([3, 4, 6])
        rules, note = R.tempo_rules(sprint_count=sprints), f"sprints={sprints}"
    elif fmt == "win_and_out":
        places = rng.randint(1, min(5, n - 1))
        direction = rng.choice(["forward", "forward", "reverse"])
        rules, note = R.win_and_out_rules(places, direction), f"places={places} {direction}"
    else:
        raise ValueError(fmt)
    race = store.add_race(event.event_id, "Race", store_fmt, rules=rules.to_dict())
    for bib in bibs:
        store.add_race_entry(race.race_id, ids[bib])
    if team:
        for k in range(n // 2):
            t = store.add_team(race.race_id, COLORS[k], color=COLORS[k])
            store.add_team_member(t.team_id, ids[bibs[2 * k]])
            store.add_team_member(t.team_id, ids[bibs[2 * k + 1]])
    desc = f"{n // 2} teams" if team else f"{n} riders" + (f" {note}" if note else "")
    return race.race_id, desc, ids


# ----- facts -------------------------------------------------------------


def canon(action) -> str:
    return json.dumps([action.kind, action.to_payload()], sort_keys=True)


def strip(screen):
    return replace(screen, undo_text="", undo_enabled=False, undo_who="")


@dataclass
class Facts:
    actions: list[str]
    order: list[str]
    staged: list
    tail: list
    editing: int | None
    raw: dict
    state: str
    screen: Any
    stack: list = field(default_factory=list)

    def same(self, other: Facts, *, stack: bool = False, order: bool = False) -> list[str]:
        """The facts that differ. ``order`` compares the live log's order
        too: an Undo puts the log back exactly, since an Elimination's DNF
        is an out where its row stands."""
        out = []
        for name in ("actions", "staged", "tail", "editing", "raw", "state"):
            if getattr(self, name) != getattr(other, name):
                out.append(name)
        if order and self.order != other.order:
            out.append("order")
        if self.screen != other.screen:
            out.append("screen")
        if stack and self.stack != other.stack:
            out.append("stack")
        return out


def facts(w: LiveRace) -> Facts:
    w._refresh_race()
    acts = [canon(a) for a in w.actions()]
    return Facts(
        actions=sorted(acts),
        order=acts,
        staged=w.staged(),
        tail=w.staged_tail(),
        editing=w.editing_sprint,
        raw=w._staged.snapshot(),
        state=w.race.state,
        screen=strip(w.screen()),
        stack=[(e.n, e.kind, e.text) for e in w._staged.stack],
    )


def diff_text(a: Facts, b: Facts, names: list[str]) -> str:
    lines = []
    for name in names:
        x, y = getattr(a, name), getattr(b, name)
        if name == "screen":
            for f in x.__dataclass_fields__:
                if getattr(x, f) != getattr(y, f):
                    lines.append(
                        f"  screen.{f}:\n    want {getattr(x, f)!r}\n    got  {getattr(y, f)!r}"
                    )
        else:
            lines.append(f"  {name}:\n    want {x!r}\n    got  {y!r}")
    return "\n".join(lines)


def log_rows(store: Store, race_id: int) -> list[tuple]:
    return [
        (
            r.action_id,
            r.action_uuid,
            r.kind,
            json.dumps(r.payload, sort_keys=True),
            r.voids_action_id,
            r.operator_note,
        )  # fmt: skip
        for r in store.actions(race_id)
    ]


# ----- the walk ----------------------------------------------------------


class Walk:
    def __init__(self, seed: int, fmt: str, ops: int, tmp: Path, *, verbose=False, clone_every=1):
        self.seed, self.fmt, self.ops_wanted = seed, fmt, ops
        self.rng = random.Random(f"{seed}:{fmt}")
        self.tmp = tmp
        self.verbose = verbose
        self.clone_every = clone_every
        self.path = tmp / "race.sqlite"
        self.store = Store.open(self.path)
        self.race_id, self.desc, self.roster = build_race(self.store, fmt, self.rng)
        self.edits = 0
        self.w1 = LiveRace(self.store, self.race_id)
        # The undo stack's entries by number: the facts before the action
        # that pushed it, or None where they are not one operation's.
        self.hist: dict[int, Facts | None] = {}
        self.log = log_rows(self.store, self.race_id)
        self.voided: set[int] = set()
        self.ops_done = 0
        self.keys: dict[str, int] = {}
        self.trace: list[str] = []
        self.notes: dict[str, int] = {}
        self.stats: dict[str, int] = {}
        self.undo_run = 0

    def close(self):
        self.store.close()

    def note(self, what: str):
        self.notes[what] = self.notes.get(what, 0) + 1

    # -- choosing ---------------------------------------------------------

    def choose(self, w: LiveRace) -> tuple[str, tuple]:
        rng = self.rng
        sc = w.screen()
        if self.undo_run:
            self.undo_run -= 1
            return "undo", ()
        if sc.final:
            r = rng.random()
            if r < 0.5:
                return "reopen", ()
            if r < 0.6:
                return "final_battery", ()
            return "undo", ()
        if rng.random() < 0.02:
            self.undo_run = 2000
            return "undo", ()
        if rng.random() < 0.35:
            return "undo", ()
        if self.at_start(w) and rng.random() < 0.3:
            return "edit", ()
        menu = []
        ids = list(w.roster.ids)
        cards = [c.entrant_id for c in sc.cards]
        if cards:
            menu += [("click", 30)]
        menu += [("click_any", 2)]
        if sc.record:
            menu += [("record", 14 if sc.record_enabled else 1)]
        card_acts = [(c.entrant_id, k) for c in sc.cards for k, _ in c.actions]
        row_acts = [(r.entrant_id, k) for r in sc.rows if r.entrant_id for k, _ in r.actions]
        if card_acts:
            menu += [("act", 10)]
        if row_acts:
            menu += [("row", 12)]
        if sc.open_sprints:
            menu += [("reopen_sprint", 5)]
        if w.editing:
            menu += [("cancel", 4), ("record", 6)]
        if sc.rest_together:
            menu += [("rest", 3)]
        if w.kind == "placings":
            menu += [("place_last", 3)]
        if sc.race_actions:
            menu += [("end_race", 2)]
        if sc.mark_final:
            menu += [("mark_final", 3)]
        menu += [("refusal", 1)]
        total = sum(wt for _, wt in menu)
        pick = rng.uniform(0, total)
        name = menu[-1][0]
        for option, wt in menu:
            pick -= wt
            if pick <= 0:
                name = option
                break
        if name == "click":
            return "click", (rng.choice(cards),)
        if name == "click_any":
            return "click", (rng.choice(ids),)
        if name in ("act", "row"):
            eid, key = rng.choice(card_acts if name == "act" else row_acts)
            if key == "points_penalty":
                key = f"{PENALTY}{rng.choice([0, 0, 1, 2, 3, 5, 10, 20])}"
            return name, (eid, key)
        if name == "reopen_sprint":
            return name, (rng.choice(sc.open_sprints),)
        if name == "place_last":
            return name, (rng.choice(cards or ids),)
        if name == "refusal":
            # Something the controller does not offer now: it must refuse and change nothing.
            k = rng.choice(
                ["dnf", "dq", "lap_gained", "move_up", "tie_above", "points_penalty:3", "withdrawn"]
            )
            return "refusal", (rng.choice(ids), k)
        return name, ()

    @staticmethod
    def at_start(w: LiveRace) -> bool:
        """At the start list with nothing staged: what Edit Race opens unlocked for."""
        return not (w.actions() or w._staged.groups or w._staged.tail or w.editing)

    def edit(self, w: LiveRace) -> Outcome:
        """Set the race up again at the empty log: the field, the teams, or the count.

        What the race dialog's Save writes (``Store.save_race``): a rider
        out and a spare in, two teams' riders traded, a team out or a
        spare pair in, a count up or down. The window is read again, as
        the app reloads the live race after Edit Event.
        """
        rng = self.rng
        store = w.store
        race = store.race(self.race_id)
        field = [e.rider_id for e in store.race_entries(self.race_id)]
        spare = [r for r in self.roster.values() if r not in field]
        teams = None
        what = []
        if w.team_format:
            shapes = [
                (t.name, t.color, t.color_hex, list(t.members)) for t in store.teams(self.race_id)
            ]
            free = [c for c in COLORS if c not in {t[0] for t in shapes}]
            moves = (
                ["trade"]
                + (["drop"] if len(shapes) > 2 else [])
                + (["add"] if len(spare) >= 2 and free else [])
            )
            move = rng.choice(moves)
            if move == "trade" and len(shapes) >= 2:
                a, b = rng.sample(range(len(shapes)), 2)
                shapes[a][3][1], shapes[b][3][1] = shapes[b][3][1], shapes[a][3][1]
            elif move == "drop":
                shapes.pop(rng.randrange(len(shapes)))
            elif move == "add":
                shapes.append((free[0], free[0], None, spare[:2]))
            what.append(f"teams {move}")
            teams = shapes
            field = [m for t in shapes for m in t[3]]
        else:
            move = rng.choice(["swap", "swap", "drop", "add"] if spare else ["drop"])
            if move == "drop" and len(field) > 3:
                field.remove(rng.choice(field))
            elif move == "add" and spare:
                field.append(rng.choice(spare))
            elif move == "swap" and spare:
                field.remove(rng.choice(field))
                field.append(rng.choice(spare))
            what.append(f"field {move}")
        rules = dict(race.rules or {})
        if rng.random() < 0.5:
            if "sprint_count" in rules:
                rules["sprint_count"] = max(2, min(6, rules["sprint_count"] + rng.choice([-1, 1])))
                what.append(f"sprints={rules['sprint_count']}")
            elif "places" in rules:
                rules["places"] = max(1, min(len(field) - 1, rules["places"] + rng.choice([-1, 1])))
                what.append(f"places={rules['places']}")
        store.save_race(race.event_id, self.race_id, {"rules": rules}, field, teams)
        w.reload()
        self.edits += 1
        return Outcome(True, "edited: " + ", ".join(what))

    # -- doing ------------------------------------------------------------

    def do(self, w: LiveRace, name: str, args: tuple):
        if name == "edit":
            return self.edit(w)
        if name == "click":
            return w.click(*args)
        if name == "record":
            out = w.record_sprint(ask_short=True)
            if out.short is not None:
                out = w.record_sprint()
            return out
        if name == "act":
            return w.act(*args)
        if name == "row":
            return self.row_action(w, *args)
        if name == "reopen_sprint":
            return w.reopen_sprint(*args)
        if name == "cancel":
            w.cancel_edit()
            return Outcome(True)
        if name == "rest":
            return w.place_rest_together()
        if name == "place_last":
            return w.place_last(*args)
        if name == "end_race":
            return w.end_race()
        if name == "mark_final":
            return w.mark_final()
        if name == "reopen":
            return w.reopen()
        if name == "undo":
            return w.undo()
        if name == "refusal":
            eid, key = args
            offered = [k for k, _ in w.rider_actions(eid)] + [k for k, _ in w.review_actions(eid)]
            bare = "points_penalty" if key.startswith(PENALTY) else key
            if bare in offered:
                return None
            return w.act(eid, key)
        raise ValueError(name)

    @staticmethod
    def row_action(w: LiveRace, eid: int, key: str):
        """The app's row_action dispatch (app.py): staged moves, rider actions, review."""
        moves = key in (*TIES, *MOVES) or key.startswith(MOVE_TO)
        if moves and not w.standings().is_complete:
            staged = {e for g in [*w.staged(), *w.staged_tail()] for e in g}
            if eid in staged:
                return w.move_staged(eid, key)
        if key in RIDER_ACTIONS or key.startswith(PENALTY):
            return w.act(eid, key)
        return w.review(eid, key)

    # -- one step ---------------------------------------------------------

    def step(self):
        w = self.w1
        name, args = self.choose(w)
        if name == "final_battery":
            self.final_battery(w)
            self.ops_done += 1
            return
        if name == "undo" and self.undo_run and not w.can_undo():
            self.undo_run = 0
        before = facts(w)
        top = w._staged.stack[-1] if w._staged.stack else None
        edit_undone = w._edit_undone()
        undo_label = w.undo_text()
        was_editing = w._staged.editing
        edit_before = copy.deepcopy(w._staged.edit_before)
        edit_from = w._staged.edit_from
        stack_ns = {e.n for e in w._staged.stack}
        log_entries_in_edit = [
            e.n
            for e in w._staged.stack
            if e.kind == "log" and edit_from is not None and e.n >= edit_from
        ]
        label = f"{name}{args}"
        try:
            out = self.do(w, name, args)
        except StoreError as exc:
            raise Break(
                "exception", f"{label}: StoreError {exc}\n{traceback.format_exc()}"
            ) from None
        except Break:
            raise
        except Exception as exc:  # noqa: BLE001
            raise Break(
                "exception", f"{label}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            ) from None
        self.ops_done += 1
        if out is None:
            return
        self.stats[name] = self.stats.get(name, 0) + 1
        if name in ("act", "row", "refusal"):
            # Per menu key, so a run shows each entry was tried, and taken.
            key = args[1].split(":")[0]
            tally = f"{name} {key} {'ok' if out.ok else 'no'}"
            self.keys[tally] = self.keys.get(tally, 0) + 1
        self.trace.append(
            f"{self.ops_done:4d} {label} -> {'ok' if out.ok else 'no'} {out.message[:90]!r}"
        )
        if self.verbose:
            print(self.trace[-1])
        after = facts(w)
        self.check_common(w, label, before, after)
        new_entries = [e for e in w._staged.stack if e.n not in stack_ns]

        if not out.ok:
            if name == "record" and was_editing and not w._staged.editing:
                # record_sprint cancels a correction whose sprint is gone.
                self.note("record refused and cancelled the correction")
                return
            diffs = before.same(after, stack=True)
            if diffs:
                raise Break(
                    "refusal",
                    f"{label} refused ({out.message!r}) yet changed things",
                    before,
                    diff_text(before, after, diffs),
                )
            return

        if name == "refusal":
            raise Break(
                "refusal",
                f"{label}: an action the menus do not offer was recorded: {out.message!r}",
            )

        if name == "edit":
            # (j) the race set up again has no entry and is in setup.
            if w.actions() or w.race.state != "setup":
                raise Break("j", f"{label}: the edited race is not at its start list")
            field = {e.rider_id for e in w.store.race_entries(self.race_id)}
            if w.team_format:
                members = {m for t in w.store.teams(self.race_id) for m in t.members}
                if members != field:
                    raise Break("j", f"{label}: the teams' riders are not the field")
            elif set(w.roster.ids) != field:
                raise Break("j", f"{label}: the window's roster is not the field")
            self.hist.clear()
            return

        if name in UNDOABLE:
            if len(new_entries) != 1:
                raise Break("e", f"{label} succeeded with {len(new_entries)} new undo entries")
            entry = new_entries[0]
            text = w.undo_text()
            if not text.startswith(UNDO) or text == UNDO:
                raise Break("e", f"{label}: undo_text after it is {text!r}")
            self.hist[entry.n] = before
            self.clone_undo(label, before)
        elif name == "reopen_sprint":
            for e in new_entries:
                self.hist[e.n] = None
            if not w._staged.editing:
                raise Break("h", f"{label} succeeded but no correction is open")
            eb = w._staged.edit_before or {}
            if (eb.get("groups"), eb.get("tail")) != (before.raw["groups"], before.raw["tail"]):
                raise Break(
                    "h", f"{label}: edit_before {eb!r} is not the order before it {before.raw!r}"
                )
        elif name in ("mark_final", "reopen"):
            if new_entries:
                raise Break("e", f"{label} pushed an undo entry")
            if before.actions != after.actions or before.raw != after.raw:
                raise Break("e", f"{label} changed the log or the staged order")
            if name == "mark_final":
                if after.state != "final":
                    raise Break("g", f"{label}: state is {after.state}")
                self.final_battery(w)
        elif name == "undo":
            if edit_undone:
                self.check_cancel(
                    label, w, before, after, edit_before, log_entries_in_edit, "undo-cancel"
                )
            else:
                if top is None:
                    raise Break("e", f"{label} succeeded with an empty stack")
                if undo_label != top.text:
                    raise Break(
                        "e", f"{label}: the label said {undo_label!r}, the entry is {top.text!r}"
                    )
                if [e.n for e in w._staged.stack] != [n for n in sorted(stack_ns) if n != top.n]:
                    raise Break("e", f"{label}: the stack did not lose exactly entry {top.n}")
                want = self.hist.pop(top.n, None)
                if want is not None:
                    diffs = want.same(after, order=True)
                    if diffs:
                        raise Break(
                            "e",
                            f"{label} of {top.text!r} did not restore the facts before it",
                            want,
                            diff_text(want, after, diffs),
                        )
        elif name == "cancel":
            if was_editing:
                self.check_cancel(
                    label, w, before, after, edit_before, log_entries_in_edit, "cancel"
                )
        if name == "record" and was_editing and not w._staged.editing:
            eb = edit_before or {}
            if (w._staged.groups, w._staged.tail) != (eb.get("groups"), eb.get("tail")):
                raise Break(
                    "h",
                    f"{label}: the correction recorded but the clicks before it did not come back",
                    eb,
                    w._staged.snapshot(),
                )

    def check_cancel(self, label, w, before, after, edit_before, log_ns, how):
        if w._staged.editing:
            raise Break("h", f"{label}: {how} left the correction open")
        if before.actions != after.actions:
            raise Break("h", f"{label}: {how} changed the log")
        eb = edit_before or {}
        if (w._staged.groups, w._staged.tail) != (eb.get("groups"), eb.get("tail")):
            raise Break(
                "h",
                f"{label}: {how} did not bring back the clicks of the sprint in progress",
                eb,
                w._staged.snapshot(),
            )
        kept = {e.n: e for e in w._staged.stack}
        for n in log_ns:
            if n not in kept or kept[n].kind != "log":
                raise Break("h", f"{label}: {how} dropped the Undo of log entry {n}")
            self.hist[n] = None
        for n in list(self.hist):
            if n not in kept:
                self.hist.pop(n)
        self.note(f"{how} with {len(log_ns)} log entries kept")

    def check_common(self, w: LiveRace, label: str, before: Facts, after: Facts):
        store = w.store
        # (a) the stored state is the one the log settles to.
        stored = store.race(self.race_id).state
        want = w._settled_state(w.actions(), stored)
        if stored != want:
            raise Break("a", f"{label}: stored state {stored!r}, the log says {want!r}")
        # (d) the log only grows; a void is never undone.
        rows = log_rows(store, self.race_id)
        if rows[: len(self.log)] != self.log:
            raise Break("d", f"{label}: the log was rewritten")
        self.log = rows
        voided = {r[4] for r in rows if r[4] is not None}
        if not self.voided <= voided:
            raise Break("d", f"{label}: a void went away")
        self.voided = voided
        live_ids = {r.action_id for r in store.live_actions(self.race_id)}
        if live_ids & voided:
            raise Break("d", f"{label}: a voided row is live")
        # (b) a window opened now reads the same staged order and screen.
        other_store = Store.open(self.path)
        try:
            fresh = LiveRace(other_store, self.race_id)
            got = facts(fresh)
            full_a, full_b = w.screen(), fresh.screen()
            if fresh._staged.to_json() != w._staged.to_json():
                raise Break(
                    "b",
                    f"{label}: the stored staged order differs from the window's",
                    w._staged.to_json(),
                    fresh._staged.to_json(),
                )
            diffs = after.same(got, stack=True)
            if full_a != full_b and "screen" not in diffs:
                diffs.append("screen (undo fields)")
            if diffs:
                raise Break(
                    "b",
                    f"{label}: a reopened window differs",
                    after,
                    diff_text(after, got, [d for d in diffs if d != "screen (undo fields)"])
                    or f"{full_a.undo_text!r} vs {full_b.undo_text!r}",
                )
        finally:
            other_store.close()
        # (c) the screen's rows are the engine's replay of the log.
        self.check_rows(w, label)
        # (f) nothing in the log or staged is out of Undo's reach.
        if w.race.state == "final":
            if w.can_undo() or w.undo_text() != REOPEN_FIRST:
                raise Break(
                    "g", f"{label}: final, yet can_undo={w.can_undo()} text={w.undo_text()!r}"
                )
        else:
            anything = bool(
                w.actions() or w.staged() or w.staged_tail() or w._staged.groups or w._staged.tail
            )
            if anything and not w.can_undo():
                raise Break(
                    "f", f"{label}: the log or the staged order holds something and Undo is off"
                )
            if not anything and w.can_undo():
                self.note("Undo on with an empty log and nothing staged")
            if not w.can_undo() and w._staged.stack:
                raise Break("f", f"{label}: Undo off with entries on the stack")

    def check_rows(self, w: LiveRace, label: str):
        acts = w.actions()
        st = compute_for_format(w.format_key, w.rules, w.roster.ids, acts)
        sc = w.screen()
        by = {r.entrant_id: r for r in st.rows}
        seen = set()
        for row in sc.rows:
            if row.entrant_id is None or row.staged:
                continue
            seen.add(row.entrant_id)
            s = by.get(row.entrant_id)
            if s is None:
                raise Break("c", f"{label}: row for {row.entrant_id} the engine does not rank")
            if (row.status or None) != s.status:
                raise Break(
                    "c", f"{label}: {row.entrant_id} status {row.status!r} vs engine {s.status!r}"
                )
            if sc.points:
                if row.total != int(s.total_points):
                    raise Break(
                        "c",
                        f"{label}: {row.entrant_id} total {row.total} vs engine {s.total_points}",
                    )
                want = s.status or (str(s.rank) if s.rank is not None else "")
            elif s.status and not s.placed:
                want = s.status
            else:
                want = str(s.rank) if s.rank is not None else ""
            if row.place_text != want:
                raise Break(
                    "c", f"{label}: {row.entrant_id} place {row.place_text!r} vs engine {want!r}"
                )
            if row.laps != s.net_laps:
                raise Break(
                    "c", f"{label}: {row.entrant_id} laps {row.laps} vs engine {s.net_laps}"
                )
        missing = [
            r.entrant_id
            for r in st.rows
            if (r.rank is not None or r.status) and r.entrant_id not in seen
        ]
        if sc.points:
            missing = [r.entrant_id for r in st.rows if r.entrant_id not in seen]
        if missing:
            raise Break("c", f"{label}: the engine ranks {missing} and the screen has no row")

    def clone_undo(self, label: str, before: Facts):
        """(e) on a copy of the file: Undo now puts back the facts before the operation."""
        if self.clone_every > 1 and self.rng.randrange(self.clone_every):
            return
        path = self.tmp / "clone.sqlite"
        for p in self.tmp.glob("clone.sqlite*"):
            p.unlink()
        dst = sqlite3.connect(path)
        self.store.connection.backup(dst)
        dst.close()
        clone = Store.open(path)
        try:
            c = LiveRace(clone, self.race_id)
            out = c.undo()
            if not out.ok:
                raise Break("e", f"{label}: Undo right after it refused: {out.message!r}")
            got = facts(c)
            diffs = before.same(got, order=True)
            if diffs:
                raise Break(
                    "e",
                    f"{label}: Undo right after it did not restore the facts before it",
                    before,
                    diff_text(before, got, diffs),
                )
        finally:
            clone.close()

    def final_battery(self, w: LiveRace):
        """(g) a final race refuses every entry with the final refusal; Undo says reopen first."""
        if w.race.state != "final":
            return
        ids = list(w.roster.ids)
        eid = self.rng.choice(ids)
        tries = {
            "click": lambda: w.click(eid),
            "record": lambda: w.record_sprint(),
            "act dnf": lambda: w.act(eid, "dnf"),
            "act dq": lambda: w.act(eid, "dq"),
            "act penalty": lambda: w.act(eid, f"{PENALTY}5"),
            "review dq": lambda: w.review(eid, "dq"),
            "review move_up": lambda: w.review(eid, "move_up"),
            "move_staged": lambda: w.move_staged(eid, "move_up"),
            "tie_above": lambda: w.tie_above(eid),
            "place_last": lambda: w.place_last(eid),
            "rest": lambda: w.place_rest_together(),
            "end_race": lambda: w.end_race(),
            "reopen_sprint": lambda: w.reopen_sprint(1),
            "undo": lambda: w.undo(),
        }
        before = log_rows(self.store, self.race_id)
        snap = w._staged.to_json()
        for what, call in tries.items():
            out = call()
            if out.ok:
                raise Break("g", f"final race accepted {what}: {out.message!r}")
            if out.message != FINAL_TEXT:
                self.note(f"g-wording: final race refuses {what} with {out.message!r}")
        if w.undo_text() != REOPEN_FIRST:
            raise Break("g", f"final race's undo_text is {w.undo_text()!r}")
        if log_rows(self.store, self.race_id) != before or w._staged.to_json() != snap:
            raise Break("g", "a refused entry on a final race changed the file")

    def run(self):
        while self.ops_done < self.ops_wanted:
            self.step()
        # End with a run of Undo back to the empty log, the race set up
        # again as Edit Race then allows, a short run of entries on the
        # new setup, and a run of Undo back to the empty log once more.
        self.undo_to_start()
        self.do_named(self.w1, "edit")
        for _ in range(20):
            self.step()
        self.undo_to_start()

    def undo_to_start(self):
        w = self.w1
        w.reload()
        if w.race.state == "final":
            self.do_named(w, "reopen")
        guard = 0
        while w.can_undo() and guard < 5000:
            self.do_named(w, "undo")
            guard += 1
        if w.actions() or w._staged.groups or w._staged.tail or w._staged.stack or w.editing:
            raise Break(
                "f",
                "a run of Undo stopped before the empty log",
                None,
                f"actions={w.actions()} staged={w._staged.to_json()}",
            )

    def do_named(self, w, name):
        saved = self.choose
        self.choose = lambda _w: (name, ())  # type: ignore[method-assign]
        try:
            self.step()
        finally:
            self.choose = saved  # type: ignore[method-assign]


def run_one(seed: int, fmt: str, ops_range: tuple[int, int], *, verbose=False, clone_every=1):
    rng = random.Random(f"ops:{seed}:{fmt}")
    ops = rng.randint(*ops_range)
    tmp = Path(tempfile.mkdtemp(prefix="undo-monkey-"))
    walk = None
    try:
        walk = Walk(seed, fmt, ops, tmp, verbose=verbose, clone_every=clone_every)
        walk.run()
        return None, walk
    except Break as b:
        return b, walk
    except Exception as exc:  # noqa: BLE001
        return Break("exception", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"), walk
    finally:
        if walk is not None:
            walk.close()
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seeds", type=int, default=40)
    p.add_argument("--first", type=int, default=0, help="the first seed of the range")
    p.add_argument("--seed", type=int, help="one seed")
    p.add_argument("--ops", type=int, default=300, help="most operations per walk (at least 100)")
    p.add_argument("--format", action="append", choices=FORMATS, help="formats (default all)")
    p.add_argument("--replay", action="store_true", help="print every operation of the walk")
    p.add_argument("--clone-every", type=int, default=1,
                   help="try the Undo-on-a-copy check on one in N successful operations")  # fmt: skip
    a = p.parse_args(argv)
    seeds = [a.seed] if a.seed is not None else list(range(a.first, a.first + a.seeds))
    fmts = a.format or list(FORMATS)
    ops_range = (min(100, a.ops), max(100, a.ops))
    if a.ops < 100:
        ops_range = (a.ops, a.ops)
    broken: set[int] = set()
    notes: dict[str, int] = {}
    stats: dict[str, int] = {}
    for fmt in fmts:
        bad = 0
        keys: dict[str, int] = {}
        for seed in seeds:
            b, walk = run_one(seed, fmt, ops_range, verbose=a.replay, clone_every=a.clone_every)
            if walk is not None:
                for k, v in walk.notes.items():
                    notes[k] = notes.get(k, 0) + v
                for k, v in walk.stats.items():
                    stats[k] = stats.get(k, 0) + v
                for k, v in walk.keys.items():
                    keys[k] = keys.get(k, 0) + v
            if b is not None:
                bad += 1
                broken.add(seed)
                where = f"op {walk.ops_done}" if walk else "setup"
                print(
                    f"BREAK [{b.check}] seed={seed} format={fmt} ({walk.desc if walk else ''}) {where}"
                )
                print(f"  {b.message}")
                if b.before is not None:
                    print(f"  before: {b.before!r}"[:4000])
                if b.after is not None:
                    print(f"  after:\n{b.after}"[:6000])
                if walk is not None:
                    print("  last operations:")
                    for line in walk.trace[-12:]:
                        print(f"    {line}")
                print(
                    f"  repro: python tools/undo_monkey/run.py --seed {seed} --format {fmt} --ops {a.ops} --replay"
                )
                print()
        print(f"{fmt}: {len(seeds)} seeds, {bad} breaking", flush=True)
        print(f"  menu keys: {dict(sorted(keys.items()))}", flush=True)
    print("operations:", dict(sorted(stats.items())))
    for k, v in sorted(notes.items()):
        print(f"note: {v} x {k}")
    print(f"{len(broken)} breaking seeds")
    return min(len(broken), 125)


if __name__ == "__main__":
    sys.exit(main())
