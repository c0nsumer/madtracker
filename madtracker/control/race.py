"""One race being scored: the task for the moment, what a click does, the result.

``LiveRace`` is the controller behind the scoring surface (docs/design.md
section 7) and the review (section 8). Its API, in the order a night
uses it:

- ``LiveRace(store, race_id)`` loads the race, its field and its rules;
  ``reload()`` re-reads them after the setup screen changed something.
- ``task()`` is what a click does right now and the one line that says
  so; ``state_label()`` is the word at the right of the state line.
- ``click(entrant_id)`` does the task on that rider or team.
- ``rider_actions(entrant_id)`` lists the actions on a rider's menu and
  ``act(entrant_id, key)`` applies one.
- ``move_staged(entrant_id, key)`` moves a staged rider (a sprint's
  badge, a finish order's row) up, down, or to a place; a staged
  action, undone like a click.
- ``record_sprint()`` writes the staged sprint of a points race, or the
  replacement for a reopened sprint.
- ``review_actions(entrant_id)`` and ``review(entrant_id, key)`` are the
  result row's menu; ``reopen_sprint(n)`` reopens a recorded sprint for
  correction, staged exactly as scored; ``cancel_edit()`` drops it;
  ``mark_final()`` and ``reopen()`` move the race between provisional
  and final.
- ``undo_text()`` names what ``undo()`` will take back.
- ``screen()`` is everything the surface draws, as plain data, and
  ``view()`` is what the scoreboard feed reads.

Every scorer action is one ``Store.append_batch`` call: its rows, the
voids of the rows it replaces, the race's state and the staged order
are written in one transaction, so a power cut leaves the action whole
or absent. Entries are validated against the log as it would stand
before anything is written. A result is always a replay of the live
log, and the stored state is settled from that replay after every
action and on every load, so it cannot drift from the result.

Clicks that do not yet make an entry (the places of a sprint before
Record sprint, the finish order of a chase before the last rider) are
the staged order. A chase's has two ends: the places clicked from the
front, and the riders the card's Place Last put in from the back, which
are numbered from the field left rather than stored with a place. It
lives in the data file's setting table with the race's action counter
and its undo stack, so a crash loses nothing and a reopen shows the
badges as they were; it is not an entry, so it never appears in the log.

Undo follows one total order of actions. Each action takes the next
number from the counter; its log rows carry ``[action N]`` in their
note, and its entry on the undo stack keeps the staged order as it was
before it. Undo takes back the newest action: a staged click by
putting the staged order back, a log action by voiding the rows it
appended and appending again the rows it voided (tagged ``[undo of
N]``), in one transaction. The rows it restores go back to their place
in the order: every live row after the first of them is written again
behind it, each copy tagged ``[from N]`` with the row it stands for, so
the live log replays exactly as it did before the action. An undo is
never itself undone, so the log stays a straight line. Because each
action restores the staged order from before it, Undo after the click
that completed a finish takes back that one click, not the whole
finish, and its button names that click as it would any staged one.
"""

import copy
import functools
import re
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, NamedTuple

from madtracker.board import payloads as P
from madtracker.board.payloads import ordinal
from madtracker.control import race_screen, rulesets
from madtracker.control.describe import (
    OUT_OF_FINISH,
    STATUS_WORDS,
    WITHDRAWN,
    race_ended_note,
    race_shortened_note,
    who,
)
from madtracker.control.formats import NO_LAP_FORMATS, TEAM_FORMATS
from madtracker.control.race_screen import Card, ResultRow, Screen
from madtracker.control.race_words import (
    ACTION_CODES,
    BREAK_TIE,
    CANCEL_CORRECTION,
    CONFLICT_TEXT,
    CORRECTION_OPEN,
    EMPTY_FIELD,
    FINAL_TEXT,
    KEPT_IN_ORDER,
    MOVE_TO,
    MOVES,
    NO_MOVE,
    NO_TEAMS,
    NOBODY_LEFT,
    NOTHING_TO_UNDO,
    NOTHING_TO_UNDO_LABEL,
    PENALTY,
    PLACE_LAST,
    PLACE_LAST_LABEL,
    RACE_ACTIONS,
    REENTERED,
    REOPEN_FIRST,
    REST_TOGETHER_LABEL,
    RESTORED,
    REVIEW_ACTIONS,
    REVIEW_TEXT,
    RIDER_ACTIONS,
    SAID,
    TIE_ABOVE,
    TIE_BELOW,
    TIES,
    UNDO,
    UNDO_REST,
    UNDO_WORDS,
    move_how,
    undo_moved,
    undo_race_ended,
    undo_shortened,
    undo_swapped,
    undo_tied,
)
from madtracker.control.roster import (
    Entrant,
    Roster,
    RosterBib,
    field_refusal,
    field_rows,
    individual_entrants,
    team_entrants,
)
from madtracker.dates import show_time
from madtracker.scoring import actions_from_rows, compute_for_format, validate_for_format
from madtracker.scoring import rules as R
from madtracker.scoring._common import laps_to_cancel, penalty_of, shortened_count, with_results
from madtracker.scoring.actions import (
    RULING_KINDS,
    SCORING_KINDS,
    Action,
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    LapNotCounted,
    OutOfFinish,
    PointsAdjusted,
    RaceEnded,
    RaceShortened,
    SprintResult,
    Status,
    Withdrawn,
)
from madtracker.scoring.replay import FORMAT_ENGINE, RESULTS_STAND_FORMATS, SHORTEN_FORMATS
from madtracker.scoring.result import Standing, Standings
from madtracker.store import VOID_KIND, Race, Store, StoreError
from madtracker.store import Action as Row
from madtracker.store.store import ConflictError

# The words and the surface's data have their own modules; the app and
# the tests import these names from here, beside LiveRace.
__all__ = [
    "BREAK_TIE",
    "CANCEL_CORRECTION",
    "CORRECTION_OPEN",
    "Card",
    "EMPTY_FIELD",
    "FINAL_TEXT",
    "MOVES",
    "MOVE_TO",
    "NOTHING_TO_UNDO_LABEL",
    "NO_MOVE",
    "PENALTY",
    "PLACE_LAST",
    "REOPEN_FIRST",
    "REST_TOGETHER_LABEL",
    "REVIEW_ACTIONS",
    "REVIEW_TEXT",
    "RIDER_ACTIONS",
    "ResultRow",
    "Screen",
    "TIES",
    "UNDO_REST",
    "UNDO_WORDS",
    "undo_moved",
    "undo_tied",
]

# Where laps count toward the result (points, madison, the finish-order
# formats): Gained a lap and Lost a lap are on the rider's menu there.
LAP_KINDS = frozenset({"points", "madison", "placings"})

_ACTION = re.compile(r"\[action (\d+)\]")
_UNDO_OF = re.compile(r"\[undo of (\d+)\]")
_FROM = re.compile(r"\[from (\d+)\]")
_TAGS = re.compile(r"\[(?:action|undo of|from) \d+\]")
# validate_common's refusal once the finish is in; a correction replaces
# an entry rather than adding one, so it is checked in its own context.
_AFTER_FINISH = "The finish order is already recorded; void it before entering more"
# The same refusal once the race ended with its results standing.
_AFTER_END = "The race has ended with its results standing; undo that first"
_RACE_OVER = (_AFTER_FINISH, _AFTER_END)
# The elimination engine's refusal of an out that leaves nobody. A move of
# the outs keeps who is out and changes only their order, so the riders
# left after the last out are the riders left before the move, and the
# refusal can find nothing the move added.
_NOBODY_LEFT = "Eliminating them would leave nobody in the race"


def _dnf_after_finish(problem: str) -> bool:
    """The refusal of a DNF after the finish: a re-appended one within a correction is fine."""
    return problem.endswith(
        ("cannot be marked DNF after the finish order", "cannot be marked DNF after the race's end")
    )


STAGED_KEY = "race/{race_id}/staged"


def action_tag(n: int) -> str:
    return f"[action {n}]"


def undo_tag(n: int) -> str:
    return f"[undo of {n}]"


def from_tag(n: int) -> str:
    return f"[from {n}]"


def _tag_part(note: str) -> tuple[str, str]:
    """(the note's own words and tags, the correction's words after SAID).

    The words after SAID carry riders' and teams' names, which are the
    scorer's text and may hold anything in brackets, so tags are read only
    from the part before them.
    """
    head, found, said = note.partition(f" {SAID} ")
    return head, f"{SAID} {said}" if found else ""


def origin(row: Row) -> int:
    """The row's place in the replay order: the id of the row it copies, else its own.

    The live log in id order is also in origin order: a new row has the
    largest origin, and Undo writes its rows again in origin order.
    """
    found = _FROM.search(_tag_part(row.operator_note or "")[0])
    return int(found.group(1)) if found else row.action_id


def note_parts(note: str | None) -> tuple[str, int | None, int | None]:
    """(the words to show, the action that owns the row, the action an undo took back)."""
    if not note:
        return "", None, None
    head, said = _tag_part(note)
    action = _ACTION.search(head)
    undone = _UNDO_OF.search(head)
    words = " ".join(f"{_TAGS.sub('', head)} {said}".split())
    return (
        words,
        (int(action.group(1)) if action else None),
        (int(undone.group(1)) if undone else None),
    )


def _store_errors(method: Callable) -> Callable:
    """A database error inside an action reaches the window as a StoreError.

    The window shows a StoreError in the red line and keeps running;
    a raw sqlite3 error would escape it.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    return wrapper


def penalty_points(key: str) -> int | None:
    """The points in a "points_penalty:5" key; None unless a whole number, 0 or more."""
    try:
        n = int(key[len(PENALTY) :])
    except ValueError:
        return None
    return n if n >= 0 else None


def local_time(utc_iso: str) -> str:
    """A stored UTC stamp as the log's clock, the sheets' with seconds: "9:45:12 PM"."""
    try:
        return show_time(datetime.fromisoformat(utc_iso).astimezone(), seconds=True)
    except ValueError:
        return utc_iso


def starts_race(action: Action) -> bool:
    """Whether recording ``action`` in setup means the race is under way.

    Everything does except a DNS: a rider who did not start is a
    pre-race call, and a race with only DNS marks has not started.
    """
    if isinstance(action, Status):
        return action.status != "DNS"
    return action.kind in SCORING_KINDS or action.kind in RULING_KINDS


def default_rules(format_key: str, ruleset_name: str, store: Store | None = None) -> R._Rules:
    """The named ruleset's rules for a format, for a race saved without rules JSON.

    A name that is neither built in nor stored (a ruleset deleted since,
    or a file from another laptop) falls back to the rulebook rather
    than failing to open the race.
    """
    if format_key not in FORMAT_ENGINE:
        raise ValueError(f"Unknown race format {format_key!r}")
    try:
        return rulesets.rules_for(store, ruleset_name, format_key)
    except rulesets.RulesetError:
        return rulesets.rules_for(None, rulesets.BUILTIN, format_key)


def rules_for_race(race: Race, store: Store | None = None) -> R._Rules:
    """Stored rules laid over the ruleset defaults.

    A race whose rules JSON carries an engine is taken as written, which
    is what makes a replay years later reproducible. A partial dict fills
    the rest from the ruleset rather than failing to open the race.
    """
    stored = dict(race.rules or {})
    if "engine" in stored:
        return R.rules_from_dict(stored)
    base = default_rules(race.format, race.rules_preset, store).to_dict()
    base.update(stored)
    return R.rules_from_dict(base)


def kind_for(engine: str, is_team: bool) -> str:
    """Which surface the race uses: placings, elimination, points, madison or win_and_out."""
    if engine == "elimination":
        return "elimination"
    if engine == "sprint_points":
        return "madison" if is_team else "points"
    if engine == "win_and_out":
        return "win_and_out"
    return "placings"


@dataclass(frozen=True)
class RaceView:
    """Everything the board feed renders, with no store attached."""

    race_id: int
    title: str
    group: str
    format_key: str
    # The format as the race's ruleset named it, for the board's header.
    format_name: str
    engine: str
    state: str
    rules: R._Rules
    roster: Roster
    standings: Standings
    actions: tuple[Action, ...]

    @property
    def kind(self) -> str:
        return kind_for(self.engine, self.roster.is_team)


@dataclass(frozen=True)
class Task:
    """What a click does now, and the one line that says so.

    ``kind``: order (clicks build a finish order), out (a click puts a
    rider out), winner (one click decides the elimination), lap (a click
    names a win-and-out lap winner), sprint (clicks badge a sprint for
    Record sprint), final_sprint (clicks order the last sprint, which
    completes on the last click), review, final,
    none, blocked (the field cannot be scored yet; ``text`` says why and
    where to fix it).
    """

    kind: str
    text: str
    sprint_no: int | None = None
    record: bool = False
    record_enabled: bool = False
    editing: bool = False

    @property
    def stages(self) -> bool:
        return self.kind in ("order", "sprint", "final_sprint")


@dataclass(frozen=True)
class Outcome:
    ok: bool
    message: str = ""
    # (clicked, needed, sprint number) when record_sprint(ask_short=True)
    # stopped short of recording so the scorer can be asked first.
    short: tuple[int, int, int] | None = None
    # The sprint a correction reopened is no longer live, so the correction
    # has nothing left to replace and the caller cancels it.
    edit_gone: bool = False


@dataclass
class _OutUnit:
    """One row of the elimination order: the riders it put out, and whether it moves."""

    row: Row | None
    ids: list[int]
    shown: list[int]
    movable: bool


@dataclass(frozen=True)
class LogRow:
    time: str
    text: str
    voided: bool
    race_id: int
    race_name: str = ""


class _UndoEntry(NamedTuple):
    """One undoable action on the stack; see ``_Staged``.

    Immutable because copies of the staged order share their entries
    rather than copying the stack, which grows by one for every click of
    the race's life. ``before`` is read only through ``_Staged.restored``,
    which copies what it takes from it.
    """

    n: int
    kind: str
    before: dict[str, Any]
    text: str


@dataclass
class _Staged:
    """The staged order, the action counter and the undo stack, as one setting.

    ``groups`` are the places clicked from the front, 1st first.
    ``tail`` are the riders placed from the back, last place first: it
    is positional, so a rider who leaves the race closes the places up
    and the numbers shown are counted from the field left, never stored.
    ``sprint`` is the recorded sprint being corrected; ``edit_from`` is
    the first action number of that
    correction and ``edit_before`` the staged order to go back to when
    it is cancelled. ``n`` is the number of the newest action. Each
    ``stack`` entry is one undoable action: its number, ``kind``
    (staged: the setting alone; log: rows tagged with its number), the
    staged order ``before`` it, and the Undo button's ``text``.
    """

    groups: list[list[int]] = field(default_factory=list)
    tail: list[list[int]] = field(default_factory=list)
    sprint: int | None = None
    edit_from: int | None = None
    edit_before: dict | None = None
    n: int = 0
    stack: list[_UndoEntry] = field(default_factory=list)

    @property
    def editing(self) -> bool:
        """A recorded sprint is reopened."""
        return self.sprint is not None

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "groups": self.groups,
                "tail": self.tail,
                "sprint": self.sprint,
                "edit_from": self.edit_from,
                "edit_before": self.edit_before,
            }
        )

    def to_json(self) -> dict[str, Any]:
        # Stored as one object per entry; the entries are shared, never
        # copied, as nothing writes to an entry after push.
        return {**self.snapshot(), "n": self.n, "stack": [e._asdict() for e in self.stack]}

    @classmethod
    def from_json(
        cls, data: dict[str, Any], n: int = 0, stack: list[_UndoEntry] | None = None
    ) -> "_Staged":
        sprint = data.get("sprint")
        edit_from = data.get("edit_from")
        return cls(
            groups=[[int(e) for e in g] for g in data.get("groups") or [] if g],
            tail=[[int(e) for e in g] for g in data.get("tail") or [] if g],
            sprint=int(sprint) if sprint is not None else None,
            edit_from=int(edit_from) if edit_from is not None else None,
            edit_before=copy.deepcopy(data.get("edit_before")),
            n=int(data.get("n", n)),
            stack=(
                [_UndoEntry(int(e["n"]), e["kind"], e["before"], e["text"]) for e in data["stack"]]
                if "stack" in data
                else list(stack or [])
            ),
        )

    def restored(self, snapshot: dict[str, Any]) -> "_Staged":
        """This counter and stack with the staged order put back to ``snapshot``."""
        return _Staged.from_json(snapshot, self.n, self.stack)

    def copy(self) -> "_Staged":
        """A copy to build on: the staged order copied, the stack's entries shared."""
        return self.restored(self.snapshot())

    def push(self, kind: str, before: dict[str, Any], text: str) -> int:
        self.n += 1
        self.stack.append(_UndoEntry(self.n, kind, before, text))
        return self.n


class LiveRace:
    # The elimination order as last read, keyed by the live rows (_out_units).
    _units_key: tuple[int, ...] = ()
    _units: tuple["_OutUnit", ...] = ()
    # The live log's standings as last replayed, keyed by the rows' uuids:
    # a row is never edited, so the same uuids are the same log, and a uuid
    # is never reused where a rolled-back action_id can be.
    _live_memo: tuple[tuple[str, ...], Standings] | None = None

    def __init__(self, store: Store, race_id: int, *, settle: bool = True) -> None:
        self.store = store
        self.race_id = race_id
        # A sheet or a standings reads the race in the state its log says
        # and writes nothing: an export must never move a race's state or
        # stamp a state change at export time.
        self._settles = settle
        self.reload()

    # Loading -----------------------------------------------------------

    @_store_errors
    def reload(self) -> None:
        """Re-read the race, the field, the rules and the staged order.

        Also settles the stored state from the replay, so a file from
        before a crash opens in the state its log says.
        """
        # A replay memoized before this read was made under the old rules and field.
        self._live_memo = None
        self.race = self.store.race(self.race_id)
        self.format_key = self.race.format
        if self.format_key not in FORMAT_ENGINE:
            raise ValueError(f"Unknown race format {self.format_key!r}")
        self.engine = FORMAT_ENGINE[self.format_key]
        self.rules = rules_for_race(self.race, self.store)
        team = self.format_key in TEAM_FORMATS or getattr(self.rules, "scored_unit", "") == "team"
        # The format, not the field: a madison whose teams are not set yet
        # has no team entrants, and is still a team race.
        self.team_format = team
        roster_bibs = []
        riders: dict[int, tuple[int | None, str]] = {}
        # One read for the roster with its names, not a query per rider.
        for entry, rider in self.store.entries_with_riders(self.race.event_id):
            name = rider.name
            riders[entry.rider_id] = (entry.bib, name)
            roster_bibs.append(RosterBib(entry.bib, entry.rider_id, name))
        field = field_rows(self.store, self.race_id)
        entrants: list[Entrant]
        if team:
            entrants = team_entrants(
                (
                    (t.team_id, t.name, t.color, t.color_hex, t.members)
                    for t in self.store.teams(self.race_id)
                ),
                riders,
            )
        else:
            entrants = individual_entrants(field)
        # Kept for the task: a field that cannot be scored waits in setup.
        self.field_problem = field_refusal(field)
        self.roster = Roster(entrants, roster_bibs)
        self.kind = kind_for(self.engine, self.roster.is_team)
        self.noun = "team" if self.roster.is_team else "rider"
        self._staged = self._read_staged()
        self._settle()

    def _settle(self) -> None:
        rows = self.rows()
        actions = self.actions(rows)
        st = self._live_standings(rows) if actions else None
        wanted = self._settled_state(actions, self.race.state, st)
        if wanted == self.race.state:
            return
        if not self._settles:
            self.race = replace(self.race, state=wanted)
            return
        try:
            self.store.append_batch(self.race_id, state=wanted)
        except StoreError:
            # A locked or read-only file still opens; the next action
            # writes the settled state with its rows.
            return
        self._refresh_race()

    def _settled_state(
        self, actions: Sequence[Action], current: str, st: Standings | None = None
    ) -> str:
        """The state the log says: provisional once complete, else running or setup.

        Final is kept only while the result is complete; it is the one
        state the log cannot say on its own. ``st`` is the replay of
        ``actions`` when the caller has it.
        """
        if actions and (st if st is not None else self.standings(actions)).is_complete:
            return "final" if current == "final" else "provisional"
        return "running" if any(starts_race(e) for e in actions) else "setup"

    @property
    def state(self) -> str:
        return self.race.state

    def _refresh_race(self) -> None:
        self.race = self.store.race(self.race_id)

    # Reading -----------------------------------------------------------

    def rows(self) -> list[Row]:
        return self.store.live_actions(self.race_id)

    def actions(self, rows: Sequence[Row] | None = None) -> list[Action]:
        rows = self.rows() if rows is None else rows
        return actions_from_rows((r.kind, r.schema_ver, r.payload) for r in rows)

    def standings(self, actions: Sequence[Action] | None = None) -> Standings:
        """The replay of ``actions``, or of the live log when left out."""
        if actions is None:
            return self._live_standings(self.rows())
        return self._replay(actions)

    def _live_standings(self, rows: Sequence[Row]) -> Standings:
        """The replay of ``rows``, the live log as just read, once per log."""
        key = tuple(r.action_uuid for r in rows)
        if self._live_memo is not None and self._live_memo[0] == key:
            return self._live_memo[1]
        st = self._replay(self.actions(rows))
        self._live_memo = (key, st)
        return st

    def _replay(self, actions: Sequence[Action]) -> Standings:
        st = compute_for_format(self.format_key, self.rules, self.roster.ids, actions)
        if not st.is_complete and self.kind != "win_and_out" and self._nobody_left(st):
            # Every rider left (DNF, DQ, DNS): no finish order can be
            # clicked, and the placings engine refuses an empty one, so
            # the statuses are the result and the race can be marked
            # final. A win-and-out records its empty finish instead
            # (act()), since its lap places are already decided.
            st = replace(st, remaining_entrants=(), is_complete=True)
        return st

    def _nobody_left(self, st: Standings) -> bool:
        return bool(self.roster.ids) and not self._active(st)

    def view(self) -> RaceView:
        actions = self.actions()
        return RaceView(
            race_id=self.race_id,
            title=rulesets.race_short_name(self.race),
            group=self.race.group_label,
            format_key=self.format_key,
            format_name=self.detail(),
            engine=self.engine,
            state=self.race.state,
            rules=self.rules,
            roster=self.roster,
            standings=self.standings(actions),
            actions=tuple(actions),
        )

    def name(self, entrant_id: int) -> str:
        """The rider's name, or the team's color, as the officials call it."""
        e = self.roster.get(entrant_id)
        if e is None:
            return f"#{entrant_id}"
        if e.is_team:
            return e.team
        return e.names[0] if e.names else e.short

    def label(self, entrant_id: int) -> str:
        """Bib and name, as the record of entries and Undo say it; a team by its color."""
        e = self.roster.get(entrant_id)
        if e is None or e.is_team or not e.bibs:
            return self.name(entrant_id)
        return who(e.bibs[0], self.name(entrant_id))

    def entry(self, entrant_id: int) -> P.Entry:
        e = self.roster.get(entrant_id)
        if e is None:
            return P.Entry(bibs=[], names=[f"#{entrant_id}"])
        color = e.color_hex or (e.color.lower() if e.color else None)
        return P.Entry(
            bibs=[str(b) for b in e.bibs],
            names=list(e.names),
            team=e.team,
            color=color if e.is_team else None,
        )

    def _active(self, st: Standings) -> list[int]:
        """Who can still be clicked: no status, not out of the finish, not withdrawn.

        A rider a mishap kept out of the finish is placed on points
        (USAC 2M8(a)), and a withdrawn rider by the moment of it (USAC
        2O3(e), 1M6(d)): a done card, no place in the finish order, and
        the finish can complete without them.
        """
        return [
            r.entrant_id
            for r in st.rows
            if r.status is None and not r.out_of_finish and not r.withdrawn
        ]

    def _field_left(self, st: Standings) -> list[int]:
        """Who a finish order must name: the engine's remaining field, else everyone active."""
        if st.remaining_entrants:
            return list(st.remaining_entrants)
        return self._active(st)

    @property
    def sprint_count(self) -> int | None:
        """The sprint count in force: the race's own, or the count the officials
        shortened it to (USAC 1G4(b)), so the task, Record Sprint, the final
        sprint, and the table's columns all follow the call."""
        return self._count_in_force()

    def _count_in_force(self, rows: Sequence[Row] | None = None) -> int | None:
        """The count in force from the live ``rows``, read when left out.

        Only the shortenings are decoded: the count is read on every task
        and every column, and a replay for it would cost the whole log.
        """
        count = getattr(self.rules, "sprint_count", None)
        if count is None or self.engine != "sprint_points":
            return count
        rows = self.rows() if rows is None else rows
        short = [r for r in rows if r.kind == RaceShortened.kind]
        return shortened_count(self.actions(short)) or count

    def _rules_in_force(self) -> R._Rules:
        """The race's rules with the count in force, for the points a sprint awards."""
        count = self.sprint_count
        if count is None or count == getattr(self.rules, "sprint_count", None):
            return self.rules
        return replace(self.rules, sprint_count=count)

    # The staged order --------------------------------------------------

    @property
    def _key(self) -> str:
        return STAGED_KEY.format(race_id=self.race_id)

    def _read_staged(self) -> _Staged:
        data = self.store.get_setting(self._key)
        # What this window last saw, so a write can tell that another
        # window wrote since (append_batch's expect).
        self._seen = data
        if isinstance(data, dict):
            if data.get("format", self.format_key) != self.format_key:
                # Edit event changed the format: chase clicks are not
                # sprint badges. Only a race with no live entries can
                # change format, so the stack holds staged clicks alone
                # and goes with them; the counter stays above every tag.
                return _Staged(n=int(data.get("n", 0)))
            return _Staged.from_json(data)
        # No setting yet: the counter still starts above every number in
        # the log, so an old tag can never be taken for a new action.
        n = 0
        for row in self.store.actions(self.race_id):
            _, action, undone = note_parts(row.operator_note)
            n = max(n, action or 0, undone or 0)
        return _Staged(n=n)

    def _write(
        self,
        staged: _Staged,
        appends: Sequence[tuple[str, dict, int, str | None]] = (),
        voids: Sequence[tuple[int, str | None]] = (),
        actions_after: Sequence[Action] | None = None,
        state: str | None = None,
    ) -> list[int]:
        """Write one action: rows, voids, settled state and staged order in one transaction.

        ``actions_after`` is the live log as it will stand, from which the
        state is settled; ``state`` overrides that (Mark final, Reopen).
        A write from a window whose view of the race is out of date is
        refused, and the window reloads.
        """
        if state is None and actions_after is not None:
            state = self._settled_state(actions_after, self.race.state)
        if state == self.race.state:
            state = None
        # The format the clicks were made in, so a format change in Set up
        # event drops them rather than reading them as the new format's.
        value = {**staged.to_json(), "format": self.format_key}
        try:
            ids = self.store.append_batch(
                self.race_id,
                appends=appends,
                voids=voids,
                state=state,
                settings={self._key: value},
                expect={self._key: self._seen},
            )
        except ConflictError:
            self.reload()
            raise StoreError(CONFLICT_TEXT) from None
        self._staged = staged.copy()
        self._seen = value
        self._refresh_race()
        return ids

    def _work(self) -> _Staged:
        """A copy of the staged order to build the next action on."""
        return self._staged.copy()

    def staged(self, st: Standings | None = None) -> list[list[int]]:
        """The staged order, dropping anyone who has left the race since.

        A sprint reopened for correction is shown exactly as
        it was scored, riders who have a status since included.
        """
        if self._staged.editing:
            return [list(g) for g in self._staged.groups]
        st = st or self.standings()
        keep = set(self._active(st))
        return [
            [e for e in g if e in keep] for g in self._staged.groups if any(e in keep for e in g)
        ]

    def staged_tail(self, st: Standings | None = None) -> list[list[int]]:
        """The riders placed from the back, last place first, dropping anyone who left since."""
        if self._staged.editing:
            return [list(g) for g in self._staged.tail]
        st = st or self.standings()
        keep = set(self._active(st))
        return [[e for e in g if e in keep] for g in self._staged.tail if any(e in keep for e in g)]

    def _placed_ids(self, st: Standings) -> set[int]:
        """Everyone with a staged place, from the front or the back."""
        return {e for g in [*self.staged(st), *self.staged_tail(st)] for e in g}

    def _staged_place(self, entrant_id: int, groups: list[list[int]]) -> int | None:
        place = 1
        for group in groups:
            if entrant_id in group:
                return place
            place += len(group)
        return None

    @property
    def editing_sprint(self) -> int | None:
        return self._staged.sprint

    @property
    def editing(self) -> bool:
        """A correction is open: a reopened sprint."""
        return self._staged.editing

    @property
    def in_progress(self) -> bool:
        """Mid-scoring: entries recorded and the result not complete, or clicks not yet an entry.

        A race in setup with nothing clicked, a provisional result and a
        final one are not in progress; leaving them loses nothing.
        """
        if self.race.state == "running":
            return True
        return self.race.state == "setup" and bool(self._staged.groups or self._staged.tail)

    # The task ----------------------------------------------------------

    def task(self, st: Standings | None = None) -> Task:
        st = st or self.standings()
        self._refresh_race()
        if self.race.state == "final":
            return Task("final", self._ended_note(st) + FINAL_TEXT)
        if not self.roster.ids:
            return Task("none", NO_TEAMS if self.team_format else EMPTY_FIELD)
        if self.field_problem and self.race.state == "setup":
            # Record sprint stays in view, disabled with the same reason.
            points = self.kind in ("points", "madison")
            return Task(
                "blocked", self.field_problem, sprint_no=1 if points else None, record=points
            )
        staged = self.staged(st)
        if self._staged.sprint is not None:
            n = self._staged.sprint
            return Task(
                "sprint",
                self._sprint_text(n),
                sprint_no=n,
                record=True,
                record_enabled=bool(staged),
                editing=True,
            )
        if st.is_complete:
            return Task("review", self._ended_note(st) + REVIEW_TEXT)
        if not self._active(st):
            return Task("none", NOBODY_LEFT)
        kind = self.kind
        if kind == "placings":
            return Task("order", f"Click {self.noun}s in the order they finish.")
        if kind == "elimination":
            left = len(st.remaining_entrants)
            survivors = getattr(self.rules, "survivors", 2)
            if left == 2 and survivors >= 2:
                return Task("winner", "Click the winner.")
            if left <= survivors:
                return Task("order", f"Final sprint: click {self.noun}s in the order they finish.")
            return Task("out", f"Click the {self.noun} who is out.")
        if kind == "win_and_out":
            if not st.remaining_entrants:
                return Task("none", NOBODY_LEFT)
            lap = st.next_sprint_no
            if lap <= self.rules.places:
                return Task("lap", f"Lap {lap}: click the winner.")
            return Task("order", "Click the rest in the order they finish.")
        n = st.next_sprint_no
        count = st.sprint_count
        if count is not None and n >= count:
            return Task("final_sprint", f"Final sprint: click every {self.noun} in order.")
        return Task(
            "sprint", self._sprint_text(n), sprint_no=n, record=True, record_enabled=bool(staged)
        )

    def _ended_note(self, st: Standings) -> str:
        """ "Race ended after 2 sprints. " before the task line's words once the
        officials ended the race early: the missing sprint columns alone do
        not say why the race is complete."""
        if not st.ended:
            return ""
        return race_ended_note(max(self.recorded_sprints(), default=0)) + ". "

    def sprint_shortfall(
        self, st: Standings | None = None, task: Task | None = None
    ) -> tuple[int, int, int] | None:
        """(clicked, needed, sprint number) when fewer riders are placed in the
        sprint being built than it awards, or None.

        A sprint awards its places to that many riders (USAC 8D), so a Record
        with fewer is nearly always an early tap, and the app asks before
        it records. It is a question and not a lock
        because the judges do sometimes call fewer (a crash in the sprint,
        a place nobody caught), and the scorer must still be able to record
        what was called. Fewer riders left than places lowers the need to
        the riders left. More clicks than places are always allowed, for a
        dead heat on the last place that scores.
        """
        st = st or self.standings()
        task = self.task(st) if task is None else task
        if task.kind != "sprint" or task.sprint_no is None:
            return None
        places = self.scoring_places(task.sprint_no)
        if not places:
            return None
        have = sum(len(group) for group in self.staged(st))
        need = min(places, len(st.remaining_entrants))
        if 0 < have < need:
            return have, need, task.sprint_no
        return None

    def scoring_places(self, n: int) -> int | None:
        """How many places sprint ``n`` awards, from the race's ruleset (4 under the rulebook).

        None outside the sprint formats, whose rules have no points table.
        """
        points_for = getattr(self._rules_in_force(), "points_for_sprint", None)
        if points_for is None:
            return None
        table = points_for(n)
        return sum(1 for points in table if points > 0)

    def _sprint_text(self, n: int) -> str:
        """The sprint's line, with how many to click, so the scorer knows where to stop.

        Clicks past the scoring places are allowed, not refused: a dead
        heat for the last place that scores is entered by clicking one
        more and tying it up. Their badges show they score nothing.
        """
        places = self.scoring_places(n)
        if places is None:
            return f"Sprint {n}: click {self.noun}s in order, then Record Sprint."
        if self.sprint_count is not None and n >= self.sprint_count:
            # A reopened final sprint: every rider, as when it was first entered.
            return f"Final sprint: click every {self.noun} in order, then Record Sprint."
        if places == 1:
            return f"Sprint {n}: click the winner, then Record Sprint."
        if places < 1:
            return f"Sprint {n}: click {self.noun}s in order, then Record Sprint."
        return f"Sprint {n}: click the first {places} {self.noun}s in order, then Record Sprint."

    def state_label(self, st: Standings | None = None) -> str:
        st = st or self.standings()
        self._refresh_race()
        if self.race.state == "final":
            return "Final"
        if self.race.state == "setup" and not self.actions() and not self._placed_ids(st):
            # Nothing entered yet is a start list, even where the engine
            # calls the field decided already (an elimination of one).
            return "Start list"
        if st.is_complete:
            return "Provisional"
        if self.race.state == "setup" and not self._placed_ids(st):
            return "Start list"
        task = self.task(st)
        if task.kind in ("winner", "final_sprint"):
            return "Final sprint"
        if task.kind == "order" and self.kind in ("elimination", "win_and_out"):
            return "Final sprint"
        return "Racing"

    # Clicks ------------------------------------------------------------

    @_store_errors
    def click(self, entrant_id: int) -> Outcome:
        """Do the task on this rider or team."""
        if self.roster.get(entrant_id) is None:
            return Outcome(False, "Not in this race.")
        st = self.standings()
        task = self.task(st)
        if task.kind == "final":
            return Outcome(False, FINAL_TEXT)
        if task.kind == "blocked":
            return Outcome(False, task.text)
        if task.kind in ("review", "none"):
            return Outcome(False, "The result is recorded. Use the row's menu to change it.")
        # Placed, out, or marked: the card holds its slot and takes no click.
        # A reopened sprint's live cards include a rider who left after it
        # was ridden, so the correction may still place them.
        refusal = self._done_refusal(entrant_id, st, task)
        if refusal is not None:
            return Outcome(False, refusal)
        if task.kind == "out":
            return self._record(
                [Eliminated(sprint_no=st.next_sprint_no, entrant_ids=(entrant_id,))]
            )
        if task.kind == "winner":
            others = [e for e in st.remaining_entrants if e != entrant_id]
            return self._record([FinishOrder(places=[[entrant_id], others])])
        if task.kind == "lap":
            actions: list[Action] = [
                SprintResult(sprint_no=st.next_sprint_no, places=[[entrant_id]])
            ]
            if len(st.remaining_entrants) == 1:
                # The last rider takes the last lap: nobody is left for a
                # finish order, so the empty one completes the result.
                actions.append(FinishOrder(places=[]))
            return self._record(actions, text=f"{UNDO}{self._short(actions[0])}")
        return self._stage_click(entrant_id, st, task)

    def _done_refusal(self, entrant_id: int, st: Standings, task: Task) -> str | None:
        """The red line for a click on a done card, or None when the card is live.

        Fires exactly when the screen shows the entrant's card done, so the
        card and the click agree on who takes a click.
        """
        if entrant_id not in race_screen.done_ids(self, st, task):
            return None
        row = race_screen.done_rows(self, st, task).get(entrant_id)
        _, status, name = race_screen.done_mark(st.by_entrant(entrant_id), row)
        who = self.label(entrant_id)
        if status:
            return f"{who} is marked {name}."
        # An elimination's out took its place at the bell; a staged row is
        # its final sprint, placed at the line.
        verb = "out" if self.kind == "elimination" and not (row and row.staged) else "placed"
        if row is None or not row.place_text.isdigit():
            return f"{who} is already {verb}."
        return f"{who} is already {verb} ({ordinal(int(row.place_text))})."

    def _edit_row(self) -> Row | None:
        """The live row of the sprint being corrected."""
        if self._staged.sprint is not None:
            return self.recorded_sprints().get(self._staged.sprint)
        return None

    def edit_field(self) -> set[int]:
        """Who the entry being corrected scored, as recorded."""
        row = self._edit_row()
        if row is None:
            return set()
        return {e for g in self.actions([row])[0].places for e in g}

    def _racing_at_edit(self, entrant_id: int, left: str) -> bool:
        """Whether a rider now DNF, or withdrawn, was still racing when the
        sprint being corrected was ridden.

        ``left`` is the status "DNF" or the kind of a Withdrawn entry. A
        rider can score a sprint and leave later, so a correction of a
        sprint ridden before their DNF or withdrawal may place them. The
        sprint's earliest row stands for when it was ridden
        (``_first_recorded``): a correction appends the sprint again at
        the end of the log, after the DNF, and voids the row before it,
        which keeps its place. The DNF's moment is its origin, since an
        Undo may have written the DNF again later in the log; a
        withdrawal's the same.
        """
        row = self._edit_row()
        if left not in ("DNF", Withdrawn.kind) or row is None:
            return False
        ridden = self._first_recorded(row)
        out = [
            origin(r)
            for r in self.rows()
            if r.payload.get("entrant_id") == entrant_id
            and (
                r.kind == Withdrawn.kind
                if left == Withdrawn.kind
                else r.kind == Status.kind and r.payload.get("status") == "DNF"
            )
        ]
        return ridden is not None and bool(out) and out[-1] > ridden

    def _first_recorded(self, row: Row) -> int:
        """The id of the row that first recorded the entry the live ``row`` stands for.

        Read back along the row's own line: a copy an Undo wrote carries
        the origin it copies, and a correction's replacement stands for
        the rows its action replaced (those are voided with the action's
        tag). A row of an earlier run of the race, one Undo took back
        and nothing restored, is off that line: the race may have been
        undone to its start list and ridden again, and that run's rows
        say nothing about when this one's sprint was ridden.
        """
        rows = self.store.actions(self.race_id)
        by_id = {r.action_id: r for r in rows}
        replaced: dict[int, list[Row]] = {}
        for r in rows:
            if r.kind != VOID_KIND or not (r.operator_note or "").startswith(REENTERED):
                continue
            owner = note_parts(r.operator_note)[1]
            target = by_id.get(r.voids_action_id)
            if owner is not None and target is not None:
                replaced.setdefault(owner, []).append(target)
        first = row.action_id
        seen: set[int] = set()
        todo = [row]
        while todo:
            r = todo.pop()
            if r.action_id in seen:
                continue
            seen.add(r.action_id)
            first = min(first, r.action_id)
            copied = origin(r)
            if copied != r.action_id and copied in by_id:
                todo.append(by_id[copied])
            owner = note_parts(r.operator_note)[1]
            if owner is not None:
                todo.extend(replaced.get(owner, ()))
        return first

    def correcting_finish_order(self) -> bool:
        """Whether the sprint being corrected is a final sprint entered as the finish order."""
        row = self._edit_row()
        return row is not None and row.kind == FinishOrder.kind

    def _lap_winners(self, actions: Sequence[Action] | None = None) -> set[int]:
        """A win-and-out's riders whose place a lap decided."""
        actions = self.actions() if actions is None else actions
        return {
            e
            for action in actions
            if isinstance(action, SprintResult)
            for group in action.places
            for e in group
        }

    def _stage_click(self, entrant_id: int, st: Standings, task: Task) -> Outcome:
        groups = self.staged(st)
        tail = self.staged_tail(st)
        if self._staged_place(entrant_id, groups) is not None:
            # A second click takes a sprint's badge off, the correction the
            # design names. A finish order's placed riders are done cards
            # and never reach here: Undo or the row's moves fix them.
            groups = [[e for e in g if e != entrant_id] for g in groups]
            text = f"{UNDO}{self.label(entrant_id)} unplaced"
            self._stage(groups, text, tail=tail)
            return Outcome(True, f"{self.name(entrant_id)} unplaced.")
        groups.append([entrant_id])
        if self._fills(groups, st, task, tail):
            # Undo puts back the staged order from before this click, so
            # the button names this click, as it would any staged one.
            text = self._click_text(entrant_id, groups, tail)
            return self._record([FinishOrder(places=self._order(groups, tail))], text=text)
        self._stage(groups, None, entrant_id, tail)
        return Outcome(True)

    @staticmethod
    def _order(groups: list[list[int]], tail: list[list[int]]) -> list[list[int]]:
        """The finish order the staged front and back make: the back turned round to follow."""
        return [list(g) for g in groups if g] + [list(g) for g in reversed(tail) if g]

    def _fills(
        self, groups: list[list[int]], st: Standings, task: Task, tail: list[list[int]] = ()
    ) -> bool:
        """Whether a finish order is full, so the click naming the last rider records it."""
        if task.kind not in ("order", "final_sprint") or task.editing:
            return False
        named = {e for g in [*groups, *tail] for e in g}
        return bool(named) and named >= set(self._field_left(st))

    def _stage(
        self,
        groups: list[list[int]],
        text: str | None,
        placed: int | None = None,
        tail: list[list[int]] | None = None,
    ) -> None:
        """Write a staged click as one action that Undo reverses exactly.

        The back of the order stays as it is unless ``tail`` gives it.
        """
        work = self._work()
        before = work.snapshot()
        work.groups = [list(g) for g in groups if g]
        if tail is not None:
            work.tail = [list(g) for g in tail if g]
        if text is None:
            text = self._click_text(placed, work.groups, work.tail)
        work.push("staged", before, text)
        self._write(work)

    def _click_text(
        self, entrant_id: int, groups: list[list[int]], tail: list[list[int]] | None = None
    ) -> str:
        """The Undo label of a click that placed ``entrant_id``: bib, name and shown place."""
        work = self._work()
        work.groups = [list(g) for g in groups if g]
        if tail is not None:
            work.tail = [list(g) for g in tail if g]
        place = ordinal(self._shown_place(entrant_id, work))
        return f"{UNDO}{self.label(entrant_id)} placed {place}"

    @_store_errors
    def place_last(self, entrant_id: int) -> Outcome:
        """Give a rider the last open place from the back of the finish order.

        The place is counted from the field left (a DNF after it closes
        the places up), and the click that makes the front and the back
        meet records the finish, as the last front click does.
        """
        st = self.standings()
        task = self.task(st)
        refusal = self._place_last_refusal(entrant_id, st, task)
        if refusal:
            return Outcome(False, refusal)
        groups = self.staged(st)
        tail = [*self.staged_tail(st), [entrant_id]]
        if self._fills(groups, st, task, tail):
            text = self._click_text(entrant_id, groups, tail)
            return self._record([FinishOrder(places=self._order(groups, tail))], text=text)
        self._stage(groups, None, entrant_id, tail)
        return Outcome(True)

    def _place_last_offered(self, entrant_id: int, st: Standings, task: Task) -> bool:
        """Whether the card's menu offers Place Last: a finish order being built, the rider unplaced."""
        if self.kind != "placings" or task.kind != "order" or task.editing or st.is_complete:
            return False
        return entrant_id in self._field_left(st) and entrant_id not in self._placed_ids(st)

    def _place_last_refusal(self, entrant_id: int, st: Standings, task: Task) -> str:
        if self._place_last_offered(entrant_id, st, task):
            return ""
        who = self.name(entrant_id)
        if self.race.state == "final":
            return FINAL_TEXT
        if self.roster.get(entrant_id) is None:
            return "Not in this race."
        if task.kind == "blocked":
            return task.text
        if self.kind != "placings":
            return f"{PLACE_LAST_LABEL} applies to a race scored by its finish order."
        if st.is_complete:
            return "The result is recorded. Use the row's menu to change it."
        row = st.by_entrant(entrant_id)
        if row.status is not None:
            return f"{who} is {row.status}. Undo takes it back."
        return f"{who} already has a place. Undo takes it back."

    def _rest_offered(self, st: Standings, task: Task) -> bool:
        """Whether Place the Rest Together shows: someone placed, two or more not."""
        if self.kind != "placings" or task.kind != "order" or task.editing or st.is_complete:
            return False
        placed = self._placed_ids(st)
        left = [e for e in self._field_left(st) if e not in placed]
        return bool(placed) and len(left) >= 2

    @_store_errors
    def place_rest_together(self) -> Outcome:
        """Record the finish with everyone unplaced as one equal placing in the middle.

        USAC 1M6(a): a group that cannot be separately placed is given
        an equal placing. The group is written in bib order, as the cards
        sit; the engine ranks a tied group as it does a dead heat.
        """
        st = self.standings()
        task = self.task(st)
        if task.kind == "blocked":
            return Outcome(False, task.text)
        if not self._rest_offered(st, task):
            if self.race.state == "final":
                return Outcome(False, FINAL_TEXT)
            if self.kind != "placings" or task.kind != "order":
                return Outcome(False, "There is no finish order to complete now.")
            if not self._placed_ids(st):
                return Outcome(False, f"Place at least one {self.noun} first.")
            return Outcome(False, f"Only one {self.noun} is left to place.")
        groups = self.staged(st)
        tail = self.staged_tail(st)
        placed = self._placed_ids(st)
        rest = sorted((e for e in self._field_left(st) if e not in placed), key=self._sort_key)
        return self._record(
            [FinishOrder(places=self._order([*groups, rest], tail))], text=UNDO_REST
        )

    def _shown_place(self, entrant_id: int, staged: _Staged) -> int:
        """The place a staged rider shows, as the result table numbers it.

        After the places a win-and-out's laps decided, not the first
        staged slot.
        """
        place = self._staged_place(entrant_id, staged.groups) or 1
        if self.kind in ("points", "madison") or staged.sprint is not None:
            return place
        current = self._staged
        self._staged = staged
        try:
            log = self.rows()
            live = self.actions(log)
            st = self._live_standings(log)
            for row in race_screen._place_rows(
                self, st, self.task(st), False, live, with_results(live)
            ):
                if row.entrant_id == entrant_id and row.staged:
                    place = int(row.place_text)
        finally:
            self._staged = current
        return place

    @_store_errors
    def tie_above(self, entrant_id: int) -> Outcome:
        """Tie a staged rider with the one placed above them."""
        self._refresh_race()
        if self.race.state == "final":
            return Outcome(False, FINAL_TEXT)
        st = self.standings()
        groups = self.staged(st)
        index = next((i for i, g in enumerate(groups) if entrant_id in g), None)
        if index is None:
            return Outcome(False, f"{self.name(entrant_id)} is not placed yet.")
        if index == 0:
            return Outcome(False, f"{self.name(entrant_id)} is first; nobody is above.")
        other = self.label(groups[index - 1][0])
        groups[index].remove(entrant_id)
        groups[index - 1].append(entrant_id)
        groups = [g for g in groups if g]
        self._stage(groups, undo_tied(self.label(entrant_id), other))
        return Outcome(True)

    @staticmethod
    def _below(groups: list[list[int]], index: int) -> int | None:
        """The rider leading the place below ``groups[index]``; None at the last place."""
        return groups[index + 1][0] if index + 1 < len(groups) else None

    @_store_errors
    def tie_below(self, entrant_id: int) -> Outcome:
        """Tie the staged rider placed just below with this one: the same tie, from above."""
        groups = self.staged(self.standings())
        index = next((i for i, g in enumerate(groups) if entrant_id in g), None)
        if index is None:
            return Outcome(False, f"{self.name(entrant_id)} is not placed yet.")
        below = self._below(groups, index)
        if below is None:
            return Outcome(False, f"{self.name(entrant_id)} is last; nobody is below.")
        return self.tie_above(below)

    def _tie_actions(self, entrant_id: int, st: Standings) -> list[tuple[str, str]]:
        """The card's ties: with the rider above when the rider leads a staged place below
        the first, with the rider below when the rider ends a place with one after it.

        Points and madison only: a finish order's placed cards are done
        while it is built, and carry their staged rows' tie instead. The
        rest of a tied place is tied with the row above already.
        """
        if self.kind not in ("points", "madison"):
            return []
        if st.is_complete and not self._staged.editing:
            return []
        groups = self.staged(st)
        index = next((i for i, g in enumerate(groups) if entrant_id in g), None)
        if index is None:
            return []
        noun = self.noun.capitalize()
        ties = []
        if index > 0 and groups[index][0] == entrant_id:
            ties.append((TIE_ABOVE, f"Tie with the {noun} Above"))
        if groups[index][-1] == entrant_id and self._below(groups, index) is not None:
            ties.append((TIE_BELOW, f"Tie with the {noun} Below"))
        return ties

    def _staged_moves(
        self, entrant_id: int, st: Standings, task: Task | None = None
    ) -> list[tuple[str, str]]:
        """The card's moves while a sprint is staged: Move Up, Move Down, Move to Place.

        A badge is the only place a sprint's order shows before Record
        Sprint, so the badge moves as a result row does; with a second
        click as the only edit, a wrong order would mean unclicking back
        to the slip and clicking everyone after it again.
        """
        task = self.task(st) if task is None else task
        if self.kind not in ("points", "madison") or task.kind not in ("sprint", "final_sprint"):
            return []
        groups = self.staged(st)
        index = next((i for i, g in enumerate(groups) if entrant_id in g), None)
        if index is None:
            return []
        return [*self._moves(groups, index), *self._long_moves(groups, index, entrant_id)]

    @staticmethod
    def _moves(groups: list[list[int]], index: int) -> list[tuple[str, str]]:
        """Move Up and Move Down for ``groups[index]``; a tied rider can leave the tie either way."""
        tied = len(groups[index]) > 1
        keys = []
        if index > 0 or tied:
            keys.append(("move_up", REVIEW_ACTIONS["move_up"]))
        if index < len(groups) - 1 or tied:
            keys.append(("move_down", REVIEW_ACTIONS["move_down"]))
        return keys

    @staticmethod
    def _long_moves(
        groups: list[list[int]], index: int, entrant_id: int, base: int = 0
    ) -> list[tuple[str, str]]:
        """A long move in one step, one per other group, named by the place it gives.

        ``base`` is the place before the first group's (0 when the groups
        start at 1st). Three groups or more: with two, Move Up and Move
        Down say it all.
        """
        if len(groups) <= 2:
            return []
        keys = []
        others = [[e for e in grp if e != entrant_id] for grp in groups]
        others = [grp for grp in others if grp]
        for g in range(len(groups)):
            if g == index:
                continue
            above = sum(len(grp) for grp in others[:g])
            keys.append((f"{MOVE_TO}{g}", f"Move to {ordinal(base + above + 1)}"))
        return keys

    @_store_errors
    def move_staged(self, entrant_id: int, key: str) -> Outcome:
        """Move a staged rider: a sprint's badge, or a finish order's row before the finish.

        One staged action with its own Undo, as a click is. The places
        clicked from the front move among themselves and so do those
        placed from the back (``tail``, which is last place first, so up
        on a tail rider is toward the front, a higher index). Neither
        crosses to the other end: the places between them are not
        decided yet.
        """
        self._refresh_race()
        if self.race.state == "final":
            return Outcome(False, FINAL_TEXT)
        if self.roster.get(entrant_id) is None:
            return Outcome(False, "Not in this race.")
        if key not in (*TIES, *MOVES) and not key.startswith(MOVE_TO):
            return Outcome(False, f"Unknown action {key!r}.")
        st = self.standings()
        task = self.task(st)
        if task.kind == "blocked":
            return Outcome(False, task.text)
        if not task.stages:
            if st.is_complete:
                return Outcome(False, "The result is recorded. Use the row's menu to change it.")
            return Outcome(False, NO_MOVE)
        groups = self.staged(st)
        tail = self.staged_tail(st)
        if key in TIES:
            # The back's places are not shared: a tie is a front move.
            if any(entrant_id in g for g in tail):
                return Outcome(False, NO_MOVE)
            return self.tie_above(entrant_id) if key == TIE_ABOVE else self.tie_below(entrant_id)
        index = next((i for i, g in enumerate(groups) if entrant_id in g), None)
        if index is not None:
            allowed = dict(
                [*self._moves(groups, index), *self._long_moves(groups, index, entrant_id)]
            )
            if key not in allowed:
                return Outcome(False, NO_MOVE)
            how = move_how(key, allowed[key])
            self._stage(
                self._regroup(groups, index, entrant_id, key),
                undo_moved(self.label(entrant_id), how),
            )
            return Outcome(True)
        index = next((i for i, g in enumerate(tail) if entrant_id in g), None)
        if index is None:
            return Outcome(False, f"{self.name(entrant_id)} is not placed yet.")
        # Best place first, as _regroup reads an order; the long moves name
        # places from the front, so the back has the two short ones.
        front_first = list(reversed(tail))
        at = len(tail) - 1 - index
        if key not in [k for k, _ in self._moves(front_first, at)]:
            return Outcome(False, NO_MOVE)
        moved = self._regroup(front_first, at, entrant_id, key)
        self._stage(
            groups, undo_moved(self.label(entrant_id), move_how(key)), tail=list(reversed(moved))
        )
        return Outcome(True)

    @_store_errors
    def record_sprint(self, *, ask_short: bool = False) -> Outcome:
        """Record the staged sprint (or the reopened entry it corrects).

        With ``ask_short``, a sprint short of its scoring places is not
        recorded: the Outcome carries the shortfall for the question, from
        the same replay, and the caller records again once answered.
        """
        st = self.standings()
        task = self.task(st)
        if ask_short:
            short = self.sprint_shortfall(st, task)
            if short is not None:
                return Outcome(False, short=short)
        if task.kind == "blocked":
            return Outcome(False, task.text)
        if not task.record:
            return Outcome(False, "There is no sprint to record now.")
        groups = self.staged(st)
        if not groups:
            return Outcome(False, f"Click the {self.noun}s in order first.")
        if task.editing:
            old = self._edit_row()
            if old is None:
                # A refusal writes nothing: the caller cancels the correction.
                return Outcome(False, f"Sprint {task.sprint_no} is not recorded.", edit_gone=True)
            if old.kind == FinishOrder.kind:
                # A final sprint entered as the finish names everyone
                # active, as when it was first entered; the log reads
                # it as one replaced order.
                missing = set(self._active(st)) - {e for g in groups for e in g}
                if missing:
                    return Outcome(
                        False,
                        f"The final sprint needs every {self.noun}: {len(missing)} not placed.",
                    )
                return self._record([FinishOrder(places=groups)], replaces=[old])
            return self._record(
                [SprintResult(sprint_no=task.sprint_no, places=groups)], replaces=[old]
            )
        return self._record([SprintResult(sprint_no=task.sprint_no, places=groups)])

    # Rider actions -----------------------------------------------------

    def rider_actions(
        self,
        entrant_id: int,
        st: Standings | None = None,
        *,
        actions: Sequence[Action] | None = None,
        task: Task | None = None,
        results: set[int] | None = None,
        known_live: bool = False,
    ) -> list[tuple[str, str]]:
        """(key, label) for the rider's menu now. Only what applies is listed.

        ``actions`` and ``task`` are the live log and the task for ``st``
        when the caller has them (the surface builds every card from
        one replay), and ``results`` is ``with_results(actions)``;
        otherwise they are read here. A caller with the log in hand
        read the race with it, so it is not read again per entrant.
        ``known_live`` is a caller that already knows the card is live
        (the surface, building every card), so the done check is not
        made again per card.
        """
        st = st or self.standings()
        if actions is None:
            self._refresh_race()
        if self.race.state == "final" or self.roster.get(entrant_id) is None:
            return []
        if self.field_problem and self.race.state == "setup":
            return []
        try:
            row = st.by_entrant(entrant_id)
        except KeyError:
            return []
        task = self.task(st) if task is None else task
        if not known_live and entrant_id in race_screen.done_ids(self, st, task):
            # A done card offers its result row's menu: two doors, one menu.
            result = race_screen.done_rows(self, st, task).get(entrant_id)
            return list(race_screen.done_actions(self, entrant_id, result, st, actions, task))
        if row.status is not None:
            # Out of the race, one thing is left: a DQ after a protest,
            # which replaces the mark. Not while a correction is open.
            if row.status != "DQ" and not self._staged.editing:
                return [("dq", RIDER_ACTIONS["dq"])]
            return []
        if (row.out_of_finish or row.withdrawn) and not st.is_complete:
            # Placed on points, or by the moment of the withdrawal, and
            # out of the field; Undo is the way back.
            return []
        if st.is_complete:
            keys = [*self._ruling_keys(entrant_id, actions), *self._dq_key()]
        else:
            keys = self._rider_keys(entrant_id, st, actions, task, results=results)
        listed = [(k, RIDER_ACTIONS[k]) for k in keys]
        # First: they belong to the sprint on screen, the rest are rare.
        # The moves before the tie, since a wrong order is the common slip.
        front = self._staged_moves(entrant_id, st, task)
        front += self._tie_actions(entrant_id, st)
        if front:
            return [*front, *listed]
        if self.kind == "placings":
            task = self.task(st) if task is None else task
            if self._place_last_offered(entrant_id, st, task):
                return [(PLACE_LAST, PLACE_LAST_LABEL), *listed]
        return listed

    def _rider_keys(
        self,
        entrant_id: int,
        st: Standings,
        actions: Sequence[Action] | None = None,
        task: Task | None = None,
        *,
        placed: bool = False,
        results: set[int] | None = None,
    ) -> list[str]:
        """The rider's own actions while the race runs, in the menu's order:
        the statuses, the laps where they count, the rulings, Disqualify.

        The card lists them, and so does the rider's row in the table, so
        a scorer who sees the wrong figure beside a name can act there.
        ``placed`` is a row that already holds a
        place (a chase's clicked riders, an elimination's outs, a
        win-and-out's lap winners): the rider has finished, so no status
        says otherwise, and what is left is a lap, a ruling, or a DQ after
        a protest.
        """
        keys = []
        if not placed:
            # Did not start is "failed to take the start line" (USAC
            # 1M6(b)): offered while this rider has nothing recorded,
            # whatever the rest of the field has done. A staged place
            # counts as recorded.
            if not self._has_result(entrant_id, st, actions, results):
                keys.append("dns")
            keys.append("dnf")
            if (
                self._final_sprint_now(st, task)
                and self._staged_place(entrant_id, self.staged(st)) is None
            ):
                keys.append("out_of_finish")
            if self._withdrawn_offered(entrant_id, st):
                keys.append("withdrawn")
        if self._laps_count():
            keys += ["lap_gained", "lap_lost"]
        keys += self._ruling_keys(entrant_id, actions)
        keys += self._dq_key()
        return keys

    def _withdrawn_offered(self, entrant_id: int, st: Standings) -> bool:
        """Whether Withdrawn is offered: a race that places by the moment of
        it (USAC 2O3(e), 1M6(d)), no sprint reopened, and no staged place.

        A correction is the order across the line as ridden, so the
        withdrawal waits for Record or Cancel, as a DQ does. A rider with a
        staged place in the sprint or finish being clicked crossed that
        line; the badge comes off first.
        """
        if self.engine not in ("placings", "sprint_points") or self._staged.editing:
            return False
        return entrant_id not in self._placed_ids(st)

    def _dq_key(self) -> list[str]:
        """Disqualify, unless a sprint is reopened.

        The correction is the order across the line and the DQ a ruling on
        the rider (USAC 1M6): entered in that order, the rider is not
        placed and the sprint points stand (R-NF-4), whatever badge the
        correction gave. So the DQ waits for Record or Cancel.
        """
        return [] if self._staged.editing else ["dq"]

    def _ruling_keys(self, entrant_id: int, actions: Sequence[Action] | None = None) -> list[str]:
        """The officials' rulings this rider can take now: a penalty where
        there are points, a lap not counted while a lap gained stands.

        None while a sprint is reopened: the cards then
        belong to that correction, and a ruling is recorded once it is
        closed.
        """
        if self._staged.editing:
            return []
        keys = []
        if self.engine == "sprint_points":
            keys.append("points_penalty")
        if self._laps_count():
            actions = self.actions() if actions is None else actions
            if laps_to_cancel(actions, entrant_id) > 0:
                keys.append("lap_not_counted")
        return keys

    def _has_result(
        self,
        entrant_id: int,
        st: Standings,
        actions: Sequence[Action] | None = None,
        results: set[int] | None = None,
    ) -> bool:
        """Whether anything is recorded or staged for this rider: a place, a lap, a mishap.

        ``results`` is ``with_results`` of the live log when the caller has
        it, so a screen of cards and rows reads the log once, not per rider.
        """
        if results is None:
            results = with_results(self.actions() if actions is None else actions)
        if entrant_id in results:
            return True
        return entrant_id in self._placed_ids(st)

    def _final_sprint_now(self, st: Standings, task: Task | None = None) -> bool:
        """Whether the final sprint of a Points Race, Madison or Tempo Race is being clicked."""
        if self.engine != "sprint_points":
            return False
        task = self.task(st) if task is None else task
        return task.kind == "final_sprint"

    @_store_errors
    def race_menu(
        self, st: Standings | None = None, task: Task | None = None
    ) -> list[tuple[str, str, str | None]]:
        """(key, label, why not) for the race's own menu, on the task line's ⋯.

        A Points Race, Madison, or Tempo Race has the menu from its first
        screen, so the task line keeps one height as the race goes; an
        item the race cannot take now is listed with its reason, never
        left out. End Race Now, Result As-Is is a Points Race or Madison
        entry, the final sprint included, since a stoppage after 80
        percent can land there (USAC 2M6, 2N5), and never a Tempo Race
        (USAC 2P5 restarts or reruns it). Shorten Race is in all three
        sprint formats (USAC 1G4(b)). Both are open from the first recorded
        sprint until the finish is in, and not while a correction is open;
        Shorten Race closes once the final sprint begins, since it has no
        later sprint to make final, and a stoppage in it is End Race.
        """
        if self.format_key not in SHORTEN_FORMATS:
            return []
        st = st or self.standings()
        if task is None:
            task = self.task(st)
        out = []
        if self.format_key in RESULTS_STAND_FORMATS:
            out.append(("end_race", RACE_ACTIONS["end_race"], self.end_race_refusal(st, task)))
        out.append(("shorten_race", RACE_ACTIONS["shorten_race"], self.shorten_refusal(st, task)))
        return out

    @_store_errors
    def race_actions(self) -> list[tuple[str, str]]:
        """(key, label) for the items of the race's menu open to it now."""
        return [(key, label) for key, label, why in self.race_menu() if why is None]

    def end_race_refusal(self, st: Standings, task: Task) -> str | None:
        """Why the race cannot end with its result as-is now, or None when it can."""
        if self.format_key not in RESULTS_STAND_FORMATS:
            return "Only a Points Race or Madison can end early with its result as-is."
        return self._race_call_refusal(st, task, "Record a sprint first; nothing stands yet.")

    def _race_call_refusal(self, st: Standings, task: Task, unrecorded: str) -> str | None:
        """Why the race's own menu is empty now, or None when it offers its items.

        ``unrecorded`` is the item's own words for a race with no sprint recorded.
        """
        self._refresh_race()
        if self.race.state == "final" or st.is_complete:
            return "The race is already complete."
        if task.editing:
            return CORRECTION_OPEN
        if (self.field_problem and self.race.state == "setup") or not self.recorded_sprints():
            return unrecorded
        return None

    def end_race(self) -> Outcome:
        """End the race with its results standing on the sprints ridden (USAC 2M6, 2N5).

        The clicks of a sprint being built are dropped: no sprint was
        ridden to the line for them. Undo reopens the race where it was.
        """
        st = self.standings()
        refusal = self.end_race_refusal(st, self.task(st))
        if refusal is not None:
            return Outcome(False, refusal)
        highest = max(self.recorded_sprints(), default=0)
        return self._record([RaceEnded(after_sprint=highest)], text=undo_race_ended(highest))

    @_store_errors
    def shorten_refusal(self, st: Standings | None = None, task: Task | None = None) -> str | None:
        """Why the race cannot be shortened now, or None when the box may ask for a count."""
        if self.format_key not in SHORTEN_FORMATS:
            return "Shorten Race is scored in a Points Race, Madison, or Tempo Race only."
        st = st or self.standings()
        if task is None:
            task = self.task(st)
        refusal = self._race_call_refusal(st, task, "Record a sprint first.")
        if refusal is not None:
            return refusal
        if self.sprint_count is None:
            return "This race has no sprint count."
        if task.kind == "final_sprint":
            if self.format_key in RESULTS_STAND_FORMATS:
                return (
                    f"The final sprint has begun; use {RACE_ACTIONS['end_race']} to stop the race."
                )
            return "The final sprint has begun."
        return None

    @_store_errors
    def shorten_bounds(self) -> tuple[int, int]:
        """(fewest, most) sprints the race can be shortened to: from the next
        sprint up to one below the count in force."""
        return max(self.recorded_sprints(), default=0) + 1, (self.sprint_count or 1) - 1

    def shorten_race(self, count: int) -> Outcome:
        """Shorten the race to ``count`` sprints; it rides on to the new final (USAC 1G4(b)).

        The clicks of the sprint being built stay: the riders were first
        across the line under either count, so in the sprint that becomes
        the final they are the first places of the finish order. Undo
        takes the latest shortening back.
        """
        refusal = self.shorten_refusal()
        if refusal is not None:
            return Outcome(False, refusal)
        lo, hi = self.shorten_bounds()
        if count < lo:
            done = lo - 1
            ridden = (
                "Sprint 1 is recorded"
                if done == 1
                else "Sprints 1 and 2 are recorded"
                if done == 2
                else f"Sprints 1 to {done} are recorded"
            )
            return Outcome(False, f"Shorten to at least Sprint {lo}; {ridden}.")
        if count > hi:
            return Outcome(False, f"The race has {hi + 1} sprints; shorten to fewer.")
        return self._record(
            [RaceShortened(sprint_count=count)], keep_staged=True, text=undo_shortened(count)
        )

    def act(self, entrant_id: int, key: str) -> Outcome:
        """Apply a rider action by key, with the same gates as the menu."""
        st = self.standings()
        allowed = [k for k, _ in self.rider_actions(entrant_id, st)]
        moves = key in TIES or key in MOVES or key.startswith(MOVE_TO)
        if moves and entrant_id in race_screen.done_ids(self, st, self.task(st)):
            # A done card's moves are its result row's: a staged row moves
            # in the staged order, any other row (an Elimination's out) in
            # the result, as the row's own menu does.
            if key not in allowed:
                return Outcome(False, self._move_refusal(entrant_id, st))
            if entrant_id in self._placed_ids(st):
                return self.move_staged(entrant_id, key)
            return self.review(entrant_id, key)
        if key in TIES:
            if key not in allowed:
                side = "above" if key == TIE_ABOVE else "below"
                return Outcome(False, f"{self.name(entrant_id)} has nobody placed just {side}.")
            return self.tie_above(entrant_id) if key == TIE_ABOVE else self.tie_below(entrant_id)
        if key == PLACE_LAST:
            return self.place_last(entrant_id)
        if key in MOVES or key.startswith(MOVE_TO):
            if key not in allowed:
                return Outcome(False, self._move_refusal(entrant_id, st))
            return self.move_staged(entrant_id, key)
        points = None
        if key.startswith(PENALTY):
            # "points_penalty:5" is the menu's key with the dialog's answer.
            points, key = penalty_points(key), "points_penalty"
        if key not in RIDER_ACTIONS:
            return Outcome(False, f"Unknown action {key!r}.")
        if key not in allowed:
            return Outcome(False, self._action_refusal(entrant_id, key, st))
        if key == "points_penalty" and points is None:
            # The menu's bare key: the dialog supplies the number.
            return Outcome(False, "Enter the penalty in points.")
        if key == "lap_gained":
            action: Action = LapGained(entrant_ids=(entrant_id,))
        elif key == "lap_lost":
            action = LapLost(entrant_ids=(entrant_id,))
        elif key == "lap_not_counted":
            action = LapNotCounted(entrant_ids=(entrant_id,))
        elif key == "points_penalty":
            # The number is the rider's penalty from now on; the log keeps
            # the difference from the penalty standing, so one Undo puts
            # the earlier number back.
            standing = penalty_of(self.actions(), entrant_id)
            if points == standing:
                if standing == 0:
                    return Outcome(False, f"{self.name(entrant_id)} has no penalty.")
                return Outcome(
                    False, f"{self.name(entrant_id)}'s penalty is already {standing} points."
                )
            action = PointsAdjusted(entrant_id=entrant_id, points=standing - (points or 0))
        elif key == "out_of_finish":
            action = OutOfFinish(entrant_id=entrant_id)
        elif key == "withdrawn":
            action = Withdrawn(entrant_id=entrant_id)
        else:
            action = Status(entrant_id=entrant_id, status=ACTION_CODES[key])
        text = f"{UNDO}{self.label(entrant_id)} {UNDO_WORDS[key]}"
        if key == "points_penalty":
            # The number too: two penalties on two riders read alike
            # otherwise. 0 is the penalty taken off.
            text = f"{text} {points}"
        # A rider action happens beside the staged order, never instead of
        # it. A rider who left the race (or the finish) leaves the staged
        # order too, and the field may now be fully placed: the finish goes
        # in with the status. A lap can do the same where a ruleset drops
        # a lapped rider (the engine marks them DNF), so a lap takes the
        # same path rather than leaving a race with nobody left to click.
        after = self.standings([*self.actions(), action])
        groups = self.staged(after)
        tail = self.staged_tail(after)
        task = self.task(after)
        if task.stages and (groups or tail) and self._fills(groups, after, task, tail):
            return self._record([action, FinishOrder(places=self._order(groups, tail))], text=text)
        if self.kind == "win_and_out" and not after.is_complete and not after.remaining_entrants:
            # The last rider in the race left: nobody is left for a lap or
            # the fill, so the empty finish completes the result, as the
            # last lap's click does.
            return self._record([action, FinishOrder(places=[])], text=text)
        work = self._work()
        work.groups = groups
        work.tail = tail
        return self._record([action], keep_staged=True, staged_after=work, text=text)

    def _move_refusal(self, entrant_id: int, st: Standings) -> str:
        """Why a card's move is not offered: the one sentence the red line says."""
        if self.race.state == "final":
            return FINAL_TEXT
        if self.roster.get(entrant_id) is None:
            return "Not in this race."
        if self.field_problem and self.race.state == "setup":
            return self.field_problem
        row = st.by_entrant(entrant_id)
        if row.status is not None:
            return f"{self.name(entrant_id)} is already {row.status}. Undo takes it back."
        task = self.task(st)
        if task.kind in ("sprint", "final_sprint"):
            if self._staged_place(entrant_id, self.staged(st)) is None:
                return f"{self.name(entrant_id)} is not placed yet."
        elif st.is_complete:
            return "The result is recorded. Use the row's menu to change it."
        return NO_MOVE

    def _laps_count(self) -> bool:
        """Whether laps gained and lost change this race's result."""
        if self.kind not in LAP_KINDS:
            return False
        if self.kind == "placings":
            return self.format_key not in NO_LAP_FORMATS and getattr(
                self.rules, "laps_count_for_ranking", True
            )
        return True

    def _action_refusal(self, entrant_id: int, key: str, st: Standings) -> str:
        who = self.name(entrant_id)
        if self.race.state == "final":
            return FINAL_TEXT
        if self.roster.get(entrant_id) is None:
            return "Not in this race."
        if self.field_problem and self.race.state == "setup":
            return self.field_problem
        row = st.by_entrant(entrant_id)
        if row.status is not None:
            if key == "dq" and row.status != "DQ":
                # Offered whenever no correction is open.
                return CORRECTION_OPEN
            return f"{who} is already {row.status}. Undo takes it back."
        if row.out_of_finish:
            return f"{who} is out of the finish (mishap). Undo takes it back."
        if row.withdrawn:
            return f"{who} is withdrawn. Undo takes it back."
        if key == "dq" and self._staged.editing:
            return CORRECTION_OPEN
        if key == "dns":
            return f"{who} has a result in this race; {self.noun}s who leave did not finish."
        if key == "points_penalty":
            if self.engine != "sprint_points":
                return "Points Penalty applies to a Points Race, Madison, or Tempo Race."
            return "Points Penalty waits until the sprint being corrected is recorded or cancelled."
        if key == "lap_not_counted":
            if not self._laps_count():
                return "Laps do not count in this race."
            if self._staged.sprint is not None:
                return "Lap Not Counted waits until the sprint being corrected is recorded or cancelled."  # noqa: E501
            return f"{who} has no lap gained to cancel."
        if st.is_complete:
            return "The result is recorded. Use the row's menu to change it."
        if key == "out_of_finish":
            if self.engine != "sprint_points":
                return f"{RIDER_ACTIONS[key]} applies to a Points Race, Madison, or Tempo Race."
            if not self._final_sprint_now(st):
                return f"{RIDER_ACTIONS[key]} applies during the final sprint."
            return (
                f"{who} is placed in the final sprint. Click the card to take the place off first."
            )
        if key == "withdrawn":
            if self.engine not in ("placings", "sprint_points"):
                return (
                    f"{RIDER_ACTIONS[key]} applies to a race placed at the line,"
                    " a Points Race, a Madison, or a Tempo Race."
                )
            if self._staged.editing:
                return CORRECTION_OPEN
            line = "finish" if self.engine == "placings" else "sprint"
            return f"{who} is placed in this {line}. Click the card to take the place off first."
        return f"{RIDER_ACTIONS[key]} does not apply here."

    # The review --------------------------------------------------------

    def recorded_sprints(self, rows: Sequence[Row] | None = None) -> dict[int, Row]:
        """Sprint (or win-and-out lap) number to the live row that scored it.

        In a points race with a count, the finish order is the final
        sprint unless that sprint was entered on its own. ``rows`` are the
        live rows when the caller has read them.
        """
        out: dict[int, Row] = {}
        finish: Row | None = None
        for row in self.rows() if rows is None else rows:
            if row.kind == SprintResult.kind:
                out[int(row.payload["sprint_no"])] = row
            elif row.kind == FinishOrder.kind:
                finish = row
        if finish is not None and self.engine == "sprint_points":
            final_no = self._count_in_force(self.rows() if rows is None else rows)
            if final_no is None:
                final_no = max(out, default=0) + 1
            if final_no not in out:
                out[final_no] = finish
        return out

    def sprint_columns(
        self, st: Standings | None = None, recorded: dict[int, Row] | None = None
    ) -> list[int]:
        """The sprint numbers the table shows as columns: every sprint of the race.

        ``recorded`` is ``recorded_sprints()`` when the caller has it.
        """
        if self.kind not in ("points", "madison"):
            return []
        recorded = self.recorded_sprints() if recorded is None else recorded
        count = self.sprint_count or 0
        columns = max([count, max(recorded, default=0)])
        if st is None and recorded:
            st = self.standings()
        if st is not None and st.ended:
            # Results stand on the sprints ridden: no empty final column.
            columns = max(recorded, default=0)
        return list(range(1, columns + 1))

    @_store_errors
    def reopen_sprint(self, number: int) -> Outcome:
        """Stage sprint ``number`` exactly as it was scored, for Record sprint to replace.

        Each scored place goes on the undo stack as if clicked, so Undo
        takes the badges off one at a time, as it would for clicks. The
        reopen itself is not an action: Cancel puts everything back.
        """
        self._refresh_race()
        if self.race.state == "final":
            return Outcome(False, FINAL_TEXT)
        if self.engine != "sprint_points":
            # A win-and-out's laps are stored as sprints too, but a lap has
            # one winner and no badges to move: staged as a sprint, a second
            # click would add a place the lap cannot hold.
            return Outcome(False, "There is no sprint to record now.")
        # Mid-race too: a wrong sprint 1 noticed during sprint 3 is fixed
        # where it is, not by undoing two sprints. The clicks already made
        # for the sprint in progress are held in edit_before and come back
        # when the correction is recorded or cancelled.
        row = self.recorded_sprints().get(number)
        if row is None:
            return Outcome(False, f"Sprint {number} is not recorded yet.")
        action = self.actions([row])[0]
        self._stage_recorded(action.places, sprint=number)
        return Outcome(True)

    def _stage_recorded(self, places: Sequence[Sequence[int]], *, sprint: int) -> None:
        """Stage sprint ``sprint``'s recorded order as if clicked (see ``reopen_sprint``)."""
        work = self._cancelled(self._work())
        work.edit_before = work.snapshot()
        work.groups, work.tail = [], []
        work.sprint, work.edit_from = sprint, work.n + 1
        for group in places:
            for k, eid in enumerate(group):
                before = work.snapshot()
                if k:
                    work.groups[-1].append(eid)
                else:
                    work.groups.append([eid])
                place = self._staged_place(eid, work.groups)
                work.push("staged", before, f"{UNDO}{self.label(eid)} placed {ordinal(place)}")
        if work.n < work.edit_from:
            work.n = work.edit_from
        self._write(work)

    @staticmethod
    def _cancelled(work: _Staged) -> _Staged:
        """``work`` with a correction in progress dropped: its clicks off the stack, its log entries kept.

        A status, a lap, or a penalty recorded while the sprint was open is
        in the log whether the correction is kept or not, so its Undo
        stays; the order it restores is the one the cancel restores, since
        the edit it was made in is gone.
        """
        if not work.editing or work.edit_before is None:
            return work
        start = work.edit_from if work.edit_from is not None else work.n + 1
        out = work.restored(work.edit_before)
        out.stack = [
            e if e.n < start else e._replace(before=work.edit_before)
            for e in out.stack
            if e.n < start or e.kind == "log"
        ]
        return out

    @_store_errors
    def cancel_edit(self) -> None:
        if not self._staged.editing:
            return
        work = self._cancelled(self._work())
        work.n += 1
        self._write(work)

    def _sections(self, st: Standings) -> list[tuple[str, list[list[int]]]]:
        """The movable parts of a result, as ordered place groups, best first.

        ``finish`` is the finish order: the whole result of a chase, the
        survivors of an elimination, the fill of a win-and-out. ``laps``
        are a win-and-out's lap winners, in place order. ``bell`` is the
        elimination order, last out first, which moves while the race
        runs and in review: a missed out is clicked when noticed and
        moved to where it belongs.
        """
        # A withdrawn row's place is the moment's, not the line's (USAC
        # 2O3(e)), so no move reaches it or passes it.
        ranked = [r for r in st.ranked() if r.status is None and not r.withdrawn]
        if self.kind in ("points", "madison"):
            return []
        if self.kind == "placings":
            # Where laps count the engine ranks by net laps before the line
            # (USAC 2C4), so a move can only reorder riders on the same lap:
            # one finish section per lap, and the moves offered name the
            # places within it, never a "Move to 1st" the ranking cannot give.
            if not self._laps_count():
                return [("finish", self._place_groups(ranked))]
            tiers: list[list[Standing]] = []
            for row in ranked:
                if tiers and tiers[-1][0].net_laps == row.net_laps:
                    tiers[-1].append(row)
                else:
                    tiers.append([row])
            return [("finish", self._place_groups(tier)) for tier in tiers]
        if self.kind == "elimination":
            survivors = [r for r in ranked if r.eliminated_at is None]
            bell = [list(u.shown) for u in self._bell() if u.shown]
            return [("finish", self._place_groups(survivors)), ("bell", bell)]
        won = self._lap_winners()
        laps = [r for r in ranked if r.entrant_id in won]
        fill = [r for r in ranked if r.entrant_id not in won]
        return [("laps", self._place_groups(laps)), ("finish", self._place_groups(fill))]

    @staticmethod
    def _place_groups(rows: list[Standing]) -> list[list[int]]:
        groups: list[list[int]] = []
        last = None
        for row in rows:
            if groups and row.rank == last:
                groups[-1].append(row.entrant_id)
            else:
                groups.append([row.entrant_id])
                last = row.rank
        return groups

    def review_actions(
        self,
        entrant_id: int,
        st: Standings | None = None,
        *,
        actions: Sequence[Action] | None = None,
        task: Task | None = None,
        results: set[int] | None = None,
    ) -> list[tuple[str, str]]:
        """(key, label) for a result row's menu: the moves that apply, the
        rider's own actions, then Disqualify.

        A complete result's rows all have one, with the rulings. While the
        race runs a row offers what the rider's card offers, less the
        staged moves and ties, which stay with the badge, so the scorer who
        sees the figure in the table can act there. An elimination's outs
        move at any time, since
        a missed out is noticed a sprint or two later.

        ``actions`` is the live log for ``st`` when the caller has it (the
        table builds every row from one replay), and ``results`` is
        ``with_results(actions)``; the race was read with them, so it is
        not read again per row.
        """
        st = st or self.standings()
        if actions is None:
            self._refresh_race()
        if self.race.state == "final" or self._staged.editing:
            return []
        if self.roster.get(entrant_id) is None:
            return []
        if self.field_problem and self.race.state == "setup":
            return []
        try:
            row = st.by_entrant(entrant_id)
        except KeyError:
            return []
        if row.status is not None:
            # A rider out of the race can still be disqualified after a
            # protest; the DQ replaces the earlier mark.
            return [("dq", REVIEW_ACTIONS["dq"])] if row.status != "DQ" else []
        if (row.out_of_finish or row.withdrawn) and not st.is_complete:
            # Placed on points, or by the moment of the withdrawal, and
            # out of the field; Undo is the way back.
            return []
        keys: list[tuple[str, str]] = []
        placed = False
        for kind, groups in self._sections(st):
            index = next((i for i, g in enumerate(groups) if entrant_id in g), None)
            if index is None:
                continue
            placed = True
            if kind != "bell" and not st.is_complete:
                continue
            keys += self._moves(groups, index)
            # Move to Place beside the other moves, then the ties, in the
            # card's order.
            if kind in ("finish", "bell"):
                base = (st.by_entrant(groups[0][0]).rank or 1) - 1
                keys += self._long_moves(groups, index, entrant_id, base)
            # Offered when the row above belongs to another place: the first
            # of a tied group can join the place above, the rest are tied
            # with the row above already. An out can share a place only
            # with riders the bell put out, not with one who did not finish.
            if kind in ("finish", "bell") and index > 0 and groups[index][0] == entrant_id:
                if kind != "bell" or self._bell_shown()[index - 1].movable:
                    keys.append(("tie_above", REVIEW_ACTIONS["tie_above"]))
            # The same tie from the row above: offered where the rider
            # leading the place below could tie up to this one.
            if kind in ("finish", "bell") and groups[index][-1] == entrant_id:
                below = self._below(groups, index)
                if (
                    below is not None
                    and st.by_entrant(below).status is None
                    and (kind != "bell" or self._bell_shown()[index].movable)
                ):
                    keys.append(("tie_below", REVIEW_ACTIONS["tie_below"]))
        if st.is_complete:
            # The rulings come with the result in hand, after a protest.
            keys += [(k, RIDER_ACTIONS[k]) for k in self._ruling_keys(entrant_id, actions)]
        else:
            own = self._rider_keys(entrant_id, st, actions, task, placed=placed, results=results)
            keys += [(k, RIDER_ACTIONS[k]) for k in own if k != "dq"]
        keys.append(("dq", REVIEW_ACTIONS["dq"]))
        return keys

    @_store_errors
    def review(self, entrant_id: int, key: str) -> Outcome:
        st = self.standings()
        offered = dict(self.review_actions(entrant_id, st))
        allowed = list(offered)
        bare = "points_penalty" if key.startswith(PENALTY) else key
        if bare in RIDER_ACTIONS:
            word = RIDER_ACTIONS[bare].rstrip(".")
        elif key.startswith(MOVE_TO):
            word = REVIEW_ACTIONS["move_to"]
        else:
            word = REVIEW_ACTIONS.get(key)
        if word is None:
            return Outcome(False, f"Unknown action {key!r}.")
        if bare not in allowed:
            if self.race.state == "final":
                return Outcome(False, FINAL_TEXT)
            out = any(r.entrant_id == entrant_id and r.status for r in st.rows)
            if bare in RIDER_ACTIONS and (bare != "dq" or out):
                # The same sentence the card gives: the row and the card
                # refuse a rider's action for the same reason.
                return Outcome(False, self._action_refusal(entrant_id, bare, st))
            if self._staged.editing:
                return Outcome(False, CORRECTION_OPEN)
            if not st.is_complete and self.kind != "elimination":
                return Outcome(False, "The result is not complete yet.")
            return Outcome(False, f"{word} does not apply to {self.name(entrant_id)}.")
        if bare in RIDER_ACTIONS:
            # A rider's action on the row is the same entry as on the card.
            return self.act(entrant_id, key)
        sections = self._sections(st)
        if key == TIE_BELOW:
            # One tie, recorded from the lower row: the rider leading the
            # place below joins this one.
            for _, groups in sections:
                index = next((i for i, g in enumerate(groups) if entrant_id in g), None)
                if index is not None and self._below(groups, index) is not None:
                    return self.review(self._below(groups, index), TIE_ABOVE)
            return Outcome(
                False, f"{REVIEW_ACTIONS[key]} does not apply to {self.name(entrant_id)}."
            )
        for kind, groups in sections:
            index = next((i for i, g in enumerate(groups) if entrant_id in g), None)
            if index is None:
                continue
            if kind == "laps":
                return self._swap_laps(entrant_id, groups, index, key)
            if kind == "bell":
                return self._move_out(entrant_id, key, move_how(key, offered.get(key, "")))
            new = self._regroup(groups, index, entrant_id, key)
            old = next((r for r in self.rows() if r.kind == FinishOrder.kind), None)
            if old is None:
                return Outcome(False, "The finish order is not recorded.")
            places = self._reline(self.actions([old])[0].places, new)
            label = self.label(entrant_id)
            if key == TIE_ABOVE:
                text = undo_tied(label, self.label(groups[index - 1][0]))
            else:
                text = undo_moved(label, move_how(key, offered.get(key, "")))
            order = FinishOrder(places=places)
            said = self._said(entrant_id, key == "tie_above", [old], [order])
            return self._record([order], replaces=[old], text=text, said=said)
        return Outcome(False, f"{REVIEW_ACTIONS[key]} does not apply to {self.name(entrant_id)}.")

    @staticmethod
    def _reline(line: Sequence[Sequence[int]], new: list[list[int]]) -> list[list[int]]:
        """The finish order with one section's riders put in their new order.

        The section's riders take the slots in the line they held before,
        in the new order, and every other rider keeps the slot the line
        gave them. A section is the riders on one lap where laps count, so
        writing the ranked order back (laps baked in) would leave a rider
        at the place a lap gave them once that lap is not counted.
        Riders of the section the line did not place go after the line.
        Riders tied in the new order are written together at the first of
        their slots, since a tie in the line is one group.
        """
        moved = {e for g in new for e in g}
        group_of = {e: i for i, g in enumerate(new) for e in g}
        order = iter(e for g in new for e in g)
        placed = {e for g in line for e in g}
        slots = [(i, e) for i, g in enumerate(line) for e in g]
        slots += [(-1, e) for e in moved - placed]
        places: list[list[int]] = []
        by_key: dict[tuple[str, int], list[int]] = {}
        for i, e in slots:
            if e in moved:
                e = next(order)
                key = ("new", group_of[e])
            else:
                key = ("line", i)
            if key in by_key:
                by_key[key].append(e)
            else:
                by_key[key] = [e]
                places.append(by_key[key])
        return places

    @staticmethod
    def _regroup(groups: list[list[int]], index: int, eid: int, key: str) -> list[list[int]]:
        groups = [list(g) for g in groups]
        group = groups[index]
        if key.startswith(MOVE_TO):
            # Out of its group, then into a place of its own at the target:
            # 1st to 3rd of [A] [B] [C] [D] gives [B] [C] [A] [D].
            group.remove(eid)
            groups = [g for g in groups if g]
            groups.insert(int(key[len(MOVE_TO) :]), [eid])
        elif key == "tie_above":
            group.remove(eid)
            groups[index - 1].append(eid)
        elif len(group) > 1:
            # Out of a tie into a place of its own, above or below the others.
            group.remove(eid)
            groups.insert(index if key == "move_up" else index + 1, [eid])
        elif key == "move_up":
            groups[index - 1], groups[index] = groups[index], groups[index - 1]
        else:
            groups[index + 1], groups[index] = groups[index], groups[index + 1]
        return [g for g in groups if g]

    # The elimination order ------------------------------------------------

    def _out_units(self) -> list[_OutUnit]:
        """The outs in log order, first out first, one unit per row that put riders out.

        A bell's row (Eliminated) is movable. A DNF on a rider still in is
        out at that moment (USAC 2E4(a)(ii), 2E4(d)): its Status row is a
        unit too, kept in its place in the sequence, which only Undo
        moves. ``shown`` is the unit's riders as the table lists them: a
        DQ, DNS or DNP rider has no place and is left out.
        """
        rows = self.rows()
        key = tuple(r.action_id for r in rows)
        if key == self._units_key:
            # Every result row asks on each repaint; one read of the log
            # serves them all. Fresh copies, since a move edits its units.
            return [_OutUnit(u.row, list(u.ids), list(u.shown), u.movable) for u in self._units]
        live = self.actions(rows)
        status = {a.entrant_id: a for a in live if isinstance(a, Status)}
        # As the engine reads the log (scoring.elimination._placed_groups): a
        # rider the bell put out anywhere is placed by that row, and a DNF
        # on them is only the mark, whichever stands first.
        by_bell = {e for a in live if isinstance(a, Eliminated) for e in a.entrant_ids}
        units: list[_OutUnit] = []
        out: set[int] = set()
        for row, action in zip(rows, live, strict=True):
            if isinstance(action, Eliminated):
                ids = [e for e in action.entrant_ids if e not in out]
                if not ids:
                    continue
                out.update(ids)
                shown = [e for e in ids if e not in status or status[e].status == "DNF"]
                units.append(_OutUnit(row, ids, shown, True))
            elif isinstance(action, Status) and action.entrant_id not in out:
                if action.status != "DNF" or action.entrant_id in by_bell:
                    continue
                if status[action.entrant_id].status != "DNF":
                    # A DQ after a protest replaced the mark: the rider has
                    # no place, so the DNF is no out to list, and a move
                    # must not write it again after the DQ.
                    continue
                out.add(action.entrant_id)
                units.append(_OutUnit(row, [action.entrant_id], [action.entrant_id], False))
        self._units_key, self._units = key, tuple(units)
        return [_OutUnit(u.row, list(u.ids), list(u.shown), u.movable) for u in units]

    def _bell(self) -> list[_OutUnit]:
        """The outs as the table lists them: last out first."""
        return list(reversed(self._out_units()))

    def _bell_shown(self) -> list[_OutUnit]:
        return [u for u in self._bell() if u.shown]

    def _move_out(self, entrant_id: int, key: str, how: str = "") -> Outcome:
        """Move an out within the elimination order, as one correction.

        The bell's rows from the first that changes to the newest are
        written again in the new order, their sprint numbers renumbered,
        and the old rows voided together, so the log replays the order
        the table shows. A DNF unit keeps its place in the sequence; an
        out may move past it. A hidden unit (every rider in it has no
        place) keeps its place between its neighbors, so the record of
        that elimination survives the move.
        """
        units = self._bell()
        shown_at = [i for i, u in enumerate(units) if u.shown]
        pos = next((i for i in shown_at if entrant_id in units[i].shown), None)
        if pos is None:
            return Outcome(False, f"{self.name(entrant_id)} is not out.")
        index = shown_at.index(pos)
        me = units[pos]
        tied = len(me.shown) > 1
        if key == "tie_above":
            if index == 0:
                return Outcome(False, f"{self.name(entrant_id)} has nobody out just above.")
            target = units[shown_at[index - 1]]
            other = self.label(target.shown[0])
            if not target.movable:
                return Outcome(
                    False,
                    f"{self.name(entrant_id)} cannot share a place with a rider who did not finish.",
                )
            me.ids.remove(entrant_id)
            me.shown.remove(entrant_id)
            target.ids.append(entrant_id)
            target.shown.append(entrant_id)
            if not me.ids:
                units.remove(me)
        elif key.startswith(MOVE_TO) or tied:
            me.ids.remove(entrant_id)
            me.shown.remove(entrant_id)
            if not me.ids:
                units.remove(me)
            # The target is an index among the shown units left; the new
            # unit goes in front of the one there, or last.
            shown_at = [i for i, u in enumerate(units) if u.shown]
            if key.startswith(MOVE_TO):
                at = int(key[len(MOVE_TO) :])
            else:
                at = index if key == "move_up" else index + 1
            if not 0 <= at <= len(shown_at):
                return Outcome(False, "There is no place to move to.")
            full_at = shown_at[at] if at < len(shown_at) else len(units)
            units.insert(full_at, _OutUnit(None, [entrant_id], [entrant_id], True))
        else:
            other = index - 1 if key == "move_up" else index + 1
            if not 0 <= other < len(shown_at):
                return Outcome(False, "There is no place to move to.")
            a, b = pos, shown_at[other]
            units[a], units[b] = units[b], units[a]
        label = self.label(entrant_id)
        text = undo_tied(label, other) if key == TIE_ABOVE else undo_moved(label, how)
        return self._rewrite_outs(
            list(reversed(units)), text, mover=entrant_id, tie=key == TIE_ABOVE
        )

    def _said(
        self, entrant_id: int, tie: bool, replaces: Sequence[Row], new: Sequence[Action]
    ) -> str:
        """The log's words for a move: the rider and the place the log would give."""
        gone = {r.action_id for r in replaces}
        would = [*self.actions([r for r in self.rows() if r.action_id not in gone]), *new]
        try:
            rank = self.standings(would).by_entrant(entrant_id).rank
        except (KeyError, ValueError):
            rank = None
        where = ordinal(rank) if rank else "a new place"
        verb = "Tied" if tie else "Moved"
        joiner = "for" if tie else "to"
        return f"{verb} {self.label(entrant_id)} {joiner} {where}"

    def _rewrite_outs(
        self, new: list[_OutUnit], text: str, mover: int | None = None, tie: bool = False
    ) -> Outcome:
        """Replace the out rows from the first changed one with ``new``, in log order.

        ``mover`` is the rider the move was about, for the log's words.
        """
        old = self._out_units()
        first = 0
        while (
            first < min(len(old), len(new))
            and new[first].row is not None
            and new[first].row.action_id == old[first].row.action_id
            and new[first].ids == self._unit_ids(old[first].row)
        ):
            first += 1
        if first == len(old) == len(new):
            return Outcome(False, "Nothing moved.")
        # The rewritten rows count on from every bell that stays, wherever
        # it stands, so none is numbered before a recorded one.
        gone = {u.row.action_id for u in old[first:]}
        base = max(
            (
                int(r.payload["sprint_no"])
                for r in self.rows()
                if r.kind == Eliminated.kind and r.action_id not in gone
            ),
            default=0,
        )
        actions: list[Action] = []
        for u in new[first:]:
            if u.movable:
                base += 1
                actions.append(Eliminated(sprint_no=base, entrant_ids=tuple(u.ids)))
            else:
                actions.append(self.actions([u.row])[0])
        # A move beside a half-staged final sprint leaves the staged clicks
        # alone: nothing about who is in the final changed.
        replaces = [u.row for u in old[first:]]
        said = self._said(mover, tie, replaces, actions) if mover is not None else None
        return self._record(
            actions, replaces=replaces, keep_staged=True, text=text, said=said, outs=True
        )

    def _unit_ids(self, row: Row) -> list[int]:
        """The riders a unit's row names: a bell's list, or a DNF's one rider."""
        action = self.actions([row])[0]
        if isinstance(action, Eliminated):
            return list(action.entrant_ids)
        return [action.entrant_id]

    def _swap_laps(self, eid: int, groups: list[list[int]], index: int, key: str) -> Outcome:
        """Move a lap winner by swapping two laps' winners, as one undoable action."""
        other = index - 1 if key == "move_up" else index + 1
        if not 0 <= other < len(groups):
            return Outcome(False, "There is no lap to swap with.")
        laps = {
            e: (int(r.payload["sprint_no"]), r)
            for n, r in self.recorded_sprints().items()
            for e in SprintResult.from_payload(r.payload).places[0]
            if r.kind == SprintResult.kind
        }
        mine, theirs = laps.get(eid), laps.get(groups[other][0])
        if mine is None or theirs is None:
            return Outcome(False, "Those places were not decided by laps.")
        new = [
            SprintResult(sprint_no=mine[0], places=[groups[other]]),
            SprintResult(sprint_no=theirs[0], places=[groups[index]]),
        ]
        said = self._said(eid, False, [mine[1], theirs[1]], new)
        text = undo_swapped(self.label(eid), self.label(groups[other][0]))
        return self._record(new, replaces=[mine[1], theirs[1]], text=text, said=said)

    @_store_errors
    def mark_final(self) -> Outcome:
        """Fix the result. Needs a complete replay, whatever the stored state says."""
        self._refresh_race()
        if self.race.state == "final":
            return Outcome(False, "Already final.")
        if self._staged.editing:
            # The surface hides Mark Final while a correction is open;
            # a call that reaches here anyway must not fix a result the
            # scorer is in the middle of changing.
            return Outcome(False, CORRECTION_OPEN)
        if not self.standings().is_complete:
            return Outcome(False, "The result is not complete yet.")
        work = self._work()
        work.n += 1
        self._write(work, state="final")
        return Outcome(True, "Marked final.")

    @_store_errors
    def reopen(self) -> Outcome:
        self._refresh_race()
        if self.race.state != "final":
            return Outcome(False, "Only a final race can be reopened.")
        work = self._work()
        work.n += 1
        self._write(work, state=self._settled_state(self.actions(), "provisional"))
        return Outcome(True, "Reopened: the result is provisional again.")

    # Recording ---------------------------------------------------------

    def _humanize(self, message: str) -> str:
        # The engines speak in entrant ids; the scorer thinks in names.
        def one(match: re.Match) -> str:
            return self.name(int(match.group(1)))

        message = re.sub(
            r"Unknown entrant (\d+)",
            lambda m: f"{self.name(int(m.group(1)))} is not in this race",
            message,
        )
        return re.sub(r"\b[Ee]ntrant (\d+)", one, message)

    def validate(self, action: Action, actions: Sequence[Action]) -> list[str]:
        raw = validate_for_format(self.format_key, self.rules, self.roster.ids, actions, action)
        return [self._humanize(p) for p in raw]

    def _record(
        self,
        new_actions: list[Action],
        replaces: Sequence[Row] = (),
        *,
        keep_staged: bool = False,
        staged_after: _Staged | None = None,
        text: str | None = None,
        said: str | None = None,
        outs: bool = False,
    ) -> Outcome:
        """Validate the log as it would stand, then write it as one action.

        Replacements are checked where the originals stood and every
        later entry is checked again after them, so a correction cannot
        quietly make the rest of the log contradict itself. Each check
        sees the entries before it plus every sprint (or lap) recorded
        after it in the log: a correction appends the corrected sprint at
        the end of the live log, so the log's order no longer says which
        sprints exist, and a check at an earlier position would otherwise
        refuse a sprint that is plainly on screen. Statuses stay in log
        order, because a rider placed before a DNF was placed. The new
        rows, the voids of the rows they replace, the settled state and
        the staged order go in one transaction, so a crash can never leave
        both a row and its replacement live.

        ``outs`` is a move of an elimination's outs (a move, a tie, a split,
        Move To): its rows are not refused for leaving nobody in the race.
        """
        self._refresh_race()
        if self.race.state == "final":
            return Outcome(False, FINAL_TEXT)
        rows = self.rows()
        swap = {r.action_id: e for r, e in zip(replaces, new_actions, strict=False)}
        # Replaced rows past the new ones are taken out with nothing in
        # their place (two outs tied into one bell), so the check sees the
        # log without them.
        removed = {r.action_id for r in replaces[len(new_actions) :]}
        rows = [r for r in rows if r.action_id not in removed]
        extra = new_actions[len(swap) :]
        first = next((i for i, r in enumerate(rows) if r.action_id in swap), len(rows))
        stands = [self.actions([row])[0] for row in rows]
        would = [
            swap.get(row.action_id) or action for row, action in zip(rows, stands, strict=True)
        ]

        def context(seq: list[Action], i: int, action: Action, tail: list[Action]) -> list[Action]:
            after = [*seq[i + 1 :], *tail]
            later = [a for a in after if isinstance(a, SprintResult)]
            # A correction or an Undo re-appends bells, and a DNF out at
            # that moment with them, after the finish order in the log;
            # they are still outs the finish must count. A bell checked at
            # its own position must not see a later bell, or its number
            # would read as late.
            if not isinstance(action, Eliminated):
                later += [a for a in after if isinstance(a, Eliminated)]
            if isinstance(action, FinishOrder):
                later += [a for a in after if isinstance(a, Status) and a.status == "DNF"]
            return [*seq[:i], *later]

        # A rider whose DNF or withdrawal came after the sprint was ridden
        # may be placed in its correction, as a click allows
        # (_racing_at_edit). Once an Undo has put the sprint back, its row
        # stands after the DNF or the withdrawal in the log, and the check
        # at that position would refuse the same correction it took before
        # the Undo.
        ridden = (
            {
                self._humanize(f"Entrant {e} is DNF and cannot be placed")
                for g in self._staged.groups
                for e in g
                if self._racing_at_edit(e, "DNF")
            }
            | {
                self._humanize(f"Entrant {e} is withdrawn and cannot be placed")
                for g in self._staged.groups
                for e in g
                if self._racing_at_edit(e, Withdrawn.kind)
            }
            if replaces and self._staged.editing
            else set()
        )
        for i, (row, action) in enumerate(zip(rows, would, strict=True)):
            if i < first:
                continue
            problems = [
                p
                for p in self.validate(action, context(would, i, action, extra))
                if p not in _RACE_OVER
                and not (row.action_id in swap and (_dnf_after_finish(p) or p in ridden))
                and not (outs and row.action_id in swap and p == _NOBODY_LEFT)
            ]
            if problems:
                # A corrected sprint, or one an Undo put back, stands at
                # the end of the log, after a status entered since the
                # sprint was ridden, so read at its own position it places
                # a rider who is now out. It was accepted when written;
                # only a contradiction this correction adds refuses it,
                # here or in a later entry.
                already = set(self.validate(stands[i], context(stands, i, stands[i], [])))
                problems = [p for p in problems if p not in already]
            if problems:
                if row.action_id in swap:
                    return Outcome(False, problems[0])
                return Outcome(
                    False,
                    f"After this correction a later entry would not stand"
                    f" ({self._text(action)}): {problems[0]}",
                )
        pending = list(would)
        for action in extra:
            problems = self.validate(action, pending)
            if replaces:
                # A correction's added row lands after the finish in the
                # log, as the rows it stands with were checked.
                problems = [p for p in problems if p not in _RACE_OVER and not _dnf_after_finish(p)]  # fmt: skip
            if outs:
                problems = [p for p in problems if p != _NOBODY_LEFT]
            if problems:
                return Outcome(False, problems[0])
            pending.append(action)

        before = self._staged.snapshot()
        if staged_after is not None:
            work = staged_after
        elif keep_staged:
            work = self._work()
        else:
            work = self._work()
            if work.editing and work.edit_before is not None:
                # A correction recorded: the sprint in progress when it was
                # opened gets its clicks back.
                work = work.restored(work.edit_before)
            else:
                work.groups, work.tail = [], []
            work.sprint = None
            work.edit_from, work.edit_before = None, None
        n = work.push("log", before, text or f"{UNDO}{self._short(new_actions[-1])}")
        tag = action_tag(n)
        appends = [
            (
                e.kind,
                e.to_payload(),
                e.SCHEMA_VER,
                f"{tag} {SAID} {said}" if said and not i else tag,
            )
            for i, e in enumerate(new_actions)
        ]
        voids = [(r.action_id, f"{REENTERED} {tag}") for r in replaces]
        # The log after the write, in replay order: the replaced rows gone,
        # the new ones at the end.
        replaced = {r.action_id for r in replaces}
        after = [*self.actions([r for r in rows if r.action_id not in replaced]), *new_actions]
        self._write(work, appends, voids, actions_after=after)
        kept = after[: len(after) - len(new_actions)]
        said = [self._text(e, [*kept, *new_actions[:i]]) for i, e in enumerate(new_actions)]
        return Outcome(True, "Recorded " + "; ".join(said))

    # Undo --------------------------------------------------------------

    def undo_text(self, st: Standings | None = None) -> str:
        """What Undo will take back, as the button's own label."""
        self._refresh_race()
        if self.race.state == "final":
            return REOPEN_FIRST
        if self._edit_undone():
            return CANCEL_CORRECTION
        if not self._staged.stack:
            return NOTHING_TO_UNDO_LABEL
        return self._staged.stack[-1].text

    def can_undo(self, st: Standings | None = None) -> bool:
        self._refresh_race()
        if self.race.state == "final":
            return False
        return self._edit_undone() or bool(self._staged.stack)

    def _edit_undone(self) -> bool:
        """A reopened sprint with every staged click of it taken back.

        The next Undo then cancels the correction rather than reaching
        past it to an entry recorded before it, where a scorer would void
        the wrong sprint.
        """
        s = self._staged
        if not s.editing:
            return False
        if s.edit_from is None or not s.stack:
            return True
        return s.stack[-1].n < s.edit_from

    @_store_errors
    def undo(self) -> Outcome:
        """Take back the newest action, whatever it was, as one transaction.

        A staged click puts the staged order back as it was. A log action
        voids the rows it appended that are still live and appends again
        the rows it voided, each keeping the tag of the action that first
        wrote it, so an earlier action's Undo still finds it. Every live
        row after the first restored one is voided and appended again
        with them, all in origin order, each copy tagged ``[from N]`` with
        the origin of the row it copies: the live log then replays exactly
        as it did before the action, which matters where a row's place is
        its moment (an Elimination's DNF is an out where it stands). The
        undo's own rows carry ``[undo of N]`` and belong to no action, so
        Undo never redoes.
        """
        self._refresh_race()
        if self.race.state == "final":
            return Outcome(False, FINAL_TEXT)
        if self._edit_undone():
            self.cancel_edit()
            return Outcome(True, "Correction cancelled.")
        if not self._staged.stack:
            return Outcome(False, NOTHING_TO_UNDO)
        work = self._work()
        entry = work.stack.pop()
        work = work.restored(entry.before)
        work.n += 1
        text = entry.text
        said = "Undone: " + (text[len(UNDO) :] if text.startswith(UNDO) else text)
        if entry.kind != "log":
            self._write(work)
            return Outcome(True, said)
        n = entry.n
        undone = undo_tag(n)
        everything = self.store.actions(self.race_id)
        by_id = {r.action_id: r for r in everything}
        live = {r.action_id for r in self.store.live_actions(self.race_id)}
        appends: list[tuple[str, dict, int, str | None]] = []
        voids: list[tuple[int, str | None]] = []
        restored: list[Row] = []
        for row in everything:
            if note_parts(row.operator_note)[1] != n:
                continue
            if row.kind != VOID_KIND:
                if row.action_id in live:
                    voids.append((row.action_id, undone))
                continue
            original = by_id.get(row.voids_action_id)
            if original is None:
                continue
            restored.append(original)
        gone = {action_id for action_id, _ in voids}
        kept = [r for r in self.rows() if r.action_id not in gone]
        moved: list[Row] = []
        if restored:
            first = min(origin(r) for r in restored)
            moved = [r for r in kept if origin(r) > first]
            voids += [(r.action_id, undone) for r in moved]
            kept = [r for r in kept if origin(r) <= first]
        again = sorted([*restored, *moved], key=origin)
        back = {r.action_id for r in restored}
        for row in again:
            owner = note_parts(row.operator_note)[1]
            word = RESTORED if row.action_id in back else KEPT_IN_ORDER
            note = f"{from_tag(origin(row))} {word} {undone}"
            if owner:
                note = f"{action_tag(owner)} {note}"
            appends.append((row.kind, row.payload, row.schema_ver, note))
        self._write(work, appends, voids, actions_after=self.actions([*kept, *again]))
        return Outcome(True, said)

    # Words -------------------------------------------------------------

    def _names(self, ids: Sequence[int]) -> str:
        return ", ".join(self.label(e) for e in ids)

    def _places_text(
        self, places: Sequence[Sequence[int]], ranks: dict[int, int | None] | None = None
    ) -> str:
        """``1st #7 Maya Petrakis, 2nd ...``; ``ranks`` gives a group's place where known."""
        parts = []
        place = 1
        for group in places:
            who = " = ".join(self.label(e) for e in group) if group else "nobody"
            if ranks and group and ranks.get(group[0]) is not None:
                place = ranks[group[0]] or place
            parts.append(f"{ordinal(place)} {who}")
            place += max(1, len(group))
        return ", ".join(parts)

    def _text(self, action: Action, before: Sequence[Action] | None = None) -> str:
        """One line for the record of entries, in names.

        ``before`` is the live log as it stood when the entry was made. A
        win-and-out's fill needs it: its riders take the places after the
        laps, so the line numbers them as the result did then, not from 1st.
        """
        if isinstance(action, SprintResult):
            if self.engine == "win_and_out":
                winners = action.places[0] if action.places else ()
                who = " = ".join(self.label(e) for e in winners)
                # The place the bell decided, as the result numbers it: a
                # dead heat earlier used two, so the lap number alone
                # would name the wrong place.
                place = None
                if before is not None and winners:
                    place = self.standings([*before, action]).by_entrant(winners[0]).rank
                if place is None:
                    place = self.rules.place_for_lap(action.sprint_no)
                return f"Lap {action.sprint_no}: {who} takes {ordinal(place)}"
            return f"Sprint {action.sprint_no}: {self._places_text(action.places)}"
        if isinstance(action, FinishOrder):
            what = "Final sprint" if self.engine in ("sprint_points", "elimination") else "Finish"
            if not any(action.places):
                # A win-and-out whose last rider took the last lap or left.
                return f"{what}: nobody left"
            ranks = None
            if self.engine == "win_and_out" and before is not None:
                ranks = self.standings([*before, action]).ranks()
            return f"{what}: {self._places_text(action.places, ranks)}"
        if isinstance(action, Eliminated):
            if not action.entrant_ids:
                return "No elimination"
            return f"Eliminated: {self._names(action.entrant_ids)}"
        if isinstance(action, LapGained):
            return f"Gained a lap: {self._names(action.entrant_ids)}"
        if isinstance(action, LapLost):
            return f"Lost a lap: {self._names(action.entrant_ids)}"
        if isinstance(action, Status):
            label = STATUS_WORDS.get(action.status, action.status)
            return f"{label}: {self.label(action.entrant_id)}"
        if isinstance(action, OutOfFinish):
            return f"{OUT_OF_FINISH}: {self.label(action.entrant_id)}"
        if isinstance(action, Withdrawn):
            return f"{WITHDRAWN}: {self.label(action.entrant_id)}"
        if isinstance(action, RaceEnded):
            return race_ended_note(action.after_sprint)
        if isinstance(action, RaceShortened):
            return race_shortened_note(None, action.sprint_count)
        if isinstance(action, PointsAdjusted):
            who = self.label(action.entrant_id)
            if before is None:
                n = abs(action.points)
                what = "points penalty" if action.points < 0 else "penalty given back"
                return f"{who}: {what}, {n} point{'' if n == 1 else 's'}"
            # The number the scorer set, and the one it replaced: the line
            # reads as the sheet's Penalty column does, not as arithmetic.
            was = penalty_of(before, action.entrant_id)
            now = was - action.points
            if now == 0:
                return f"{who}: penalty removed (was {was})"
            if was == 0:
                return f"{who}: points penalty {now}"
            return f"{who}: points penalty {now} (was {was})"
        if isinstance(action, LapNotCounted):
            return f"{self._names(action.entrant_ids)}: lap not counted"
        return action.kind

    def _short(self, action: Action) -> str:
        """The entry as the Undo button says what was done."""
        if isinstance(action, SprintResult):
            if self.engine == "win_and_out":
                # A lap's click has one winner; nothing on the surface
                # records a shared lap, which keeps the lap's own words.
                won = [e for group in action.places for e in group]
                if len(won) == 1:
                    return f"{self.label(won[0])} won Lap {action.sprint_no}"
                return f"Lap {action.sprint_no} recorded"
            return f"Sprint {action.sprint_no} recorded"
        if isinstance(action, FinishOrder):
            what = "Final sprint" if self.engine in ("sprint_points", "elimination") else "Finish"
            return f"{what} recorded"
        if isinstance(action, Eliminated):
            if not action.entrant_ids:
                return "no elimination recorded"
            return f"{self._names(action.entrant_ids)} {UNDO_WORDS['out']}"
        if isinstance(action, LapGained):
            return f"{self._names(action.entrant_ids)} {UNDO_WORDS['lap_gained']}"
        if isinstance(action, LapLost):
            return f"{self._names(action.entrant_ids)} {UNDO_WORDS['lap_lost']}"
        if isinstance(action, Status):
            word = {"DNS": "dns", "DNF": "dnf", "DQ": "dq"}.get(action.status)
            what = UNDO_WORDS[word] if word else f"marked {action.status}"
            return f"{self.label(action.entrant_id)} {what}"
        if isinstance(action, OutOfFinish):
            return f"{self.label(action.entrant_id)} {UNDO_WORDS['out_of_finish']}"
        if isinstance(action, Withdrawn):
            return f"{self.label(action.entrant_id)} {UNDO_WORDS['withdrawn']}"
        if isinstance(action, RaceEnded):
            return undo_race_ended(action.after_sprint)[len(UNDO) :]
        if isinstance(action, RaceShortened):
            return undo_shortened(action.sprint_count)[len(UNDO) :]
        if isinstance(action, PointsAdjusted):
            # The entry holds the change, not the penalty it set, so there
            # is no number to name here; act() names it when it has one.
            return f"{self.label(action.entrant_id)} penalty changed"
        if isinstance(action, LapNotCounted):
            return f"{self._names(action.entrant_ids)} {UNDO_WORDS['lap_not_counted']}"
        return self._text(action).lower()

    def log_rows(self) -> list[LogRow]:
        """(time, text, voided) for every row, voids included, oldest first."""
        rows = self.store.actions(self.race_id)
        by_id = {r.action_id: r for r in rows}
        voided = {r.voids_action_id for r in rows if r.kind == VOID_KIND}
        out = []
        # The live log as it stood before each row, for the lines that
        # depend on it (a win-and-out's fill).
        standing: dict[int, Row] = {}
        said: dict[int, str] = {}
        for r in rows:
            words, _, _ = note_parts(r.operator_note)
            if r.kind == VOID_KIND:
                target = by_id.get(r.voids_action_id)
                what = (
                    (said.get(target.action_id) or self._row_text(target))
                    if target
                    else "an earlier entry"
                )
                # A correction's void says so in its verb, so the scorer
                # can tell a moved result from one taken back by Undo;
                # the note would only repeat it.
                if words.startswith(REENTERED):
                    # The struck line above carries the detail; a long
                    # order is named, not repeated.
                    text = "Replaced: " + (self._replaced_name(target) or what)
                    words = words[len(REENTERED) :].strip()
                else:
                    text = "Undone: " + what
                standing.pop(r.voids_action_id, None)
            else:
                text = said[r.action_id] = self._row_text(r, list(standing.values()))
                standing[r.action_id] = r
                if words.startswith(SAID):
                    text = f"{words[len(SAID) :].strip()}\n{text}"
                    words = ""
            if words:
                text += f" ({words})"
            out.append(
                LogRow(local_time(r.recorded_utc), text, r.action_id in voided, self.race_id)
            )
        return out

    def _replaced_name(self, row: Row | None) -> str:
        """A long entry's name for the void's line: the order itself is struck above."""
        if row is None:
            return ""
        try:
            action = self.actions([row])[0]
        except ValueError:
            return ""
        if isinstance(action, FinishOrder):
            return (
                "the final sprint"
                if self.engine in ("sprint_points", "elimination")
                else "the finish order"
            )  # noqa: E501
        if isinstance(action, SprintResult):
            return (
                f"lap {action.sprint_no}"
                if self.engine == "win_and_out"
                else f"sprint {action.sprint_no}"
            )  # noqa: E501
        return ""

    def _row_text(self, row: Row, before: Sequence[Row] | None = None) -> str:
        try:
            action = self.actions([row])[0]
        except ValueError:
            return row.kind
        try:
            prior = self.actions(before) if before is not None else None
        except ValueError:
            prior = None
        return self._text(action, prior)

    # The surface -------------------------------------------------------

    def screen(self) -> Screen:
        return race_screen.screen(self)

    def detail(self) -> str:
        """The format, for the header beside the group: what kind of race this is.

        The ruleset's numbers ("4 sprints, 5-3-2-1, last sprint double,
        lap 10") are not here: the task line and the result table say them
        where they apply, and the sheet keeps the full rules line. The
        word is the one the race's ruleset gave the format when the race
        was made, so a venue's "Devil" reads as that here and on the board.
        """
        return rulesets.race_format_name(self.race)

    def _sort_key(self, entrant_id: int) -> tuple[int, str]:
        """Cards sort by bib (section 7): the radio calls bibs as often as names.

        A rider still waiting for a bib sorts after every numbered one.
        """
        last = 1 << 30
        e = self.roster.get(entrant_id)
        if e is None:
            return (0, "")
        if e.is_team:
            return (min(e.bibs) if e.bibs else last, e.team.casefold())
        return (e.bibs[0] if e.bibs else last, e.names[0].casefold() if e.names else "")


def live_race_id(store: Store, event_id: int) -> int | None:
    """The race to select at start: the one with the newest entry, else the first."""
    newest: tuple[int, int] | None = None
    races = store.races(event_id)
    for race in races:
        last = store.last_action(race.race_id)
        if last is not None and (newest is None or last.action_id > newest[0]):
            newest = (last.action_id, race.race_id)
    if newest is not None:
        return newest[1]
    return races[0].race_id if races else None
