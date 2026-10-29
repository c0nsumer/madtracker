"""The Store: every read and write the app makes, as small explicit methods.

All SQL lives here so the UI and the scoring code never see a cursor or
a row. Every write method is one BEGIN IMMEDIATE ... COMMIT; when a
method returns, its change is on disk (WAL with synchronous=FULL). The
UI acknowledges a scorer action only after the method returns, which is
the whole durability promise. IMMEDIATE rather than DEFERRED so that a
lock conflict (a backup or export running in another connection) shows
up at BEGIN, where busy_timeout waits for it, not as a late failure at
COMMIT. Writes that belong together (a race with its field and teams,
an import) run inside ``Store.transaction()``: one commit when the block
ends, and nothing written when it fails.

Integrity rules are enforced twice on purpose: a check in Python inside
the same transaction gives the UI a specific exception to show, and the
database's own constraints and triggers remain the backstop for any
other tool that opens the file.
"""

import json
import os
import sqlite3
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from madtracker.dates import show_date
from madtracker.inputs import (
    BIB_MAX,
    clean_line,
    filter_words,
    is_blank,
    matches_filter,
    usac_license,
)
from madtracker.store.db import (
    BACKUP_KEY,
    StoreError,
    backup_database,
    close_database,
    integrity_check,
    is_read_only,
    open_database,
    schema_problems,
)

RACE_STATES = ("setup", "running", "provisional", "final")
VOID_KIND = "void"


class NotFoundError(StoreError):
    """A row the caller named does not exist."""


class DuplicateError(StoreError):
    """A uniqueness rule would be broken."""


class DuplicateEntryError(DuplicateError):
    """The rider is already entered in this event, race or team."""


class DuplicateLicenseError(DuplicateError):
    """Another rider already carries that USAC License number."""


class DuplicateUciError(DuplicateError):
    """Another rider already carries that UCI ID."""


class DuplicateTeamNameError(DuplicateError):
    """A team with that name already exists in this race."""


class DuplicateRulesetNameError(DuplicateError):
    """Another ruleset already has this name (compared without case)."""


class DuplicateStandingsNameError(DuplicateError):
    """Another standings already has this name (compared without case)."""


class EntryInUseError(StoreError):
    """The roster entry cannot go because the rider is in a race of this event."""


class RaceHasActionsError(StoreError):
    """The race cannot be deleted because scorer actions were recorded for it."""


class ConflictError(StoreError):
    """A setting changed since the caller read it: another window wrote first."""


class VoidError(StoreError):
    """The action cannot be voided: wrong race, already voided, or itself a void."""


@dataclass(frozen=True, slots=True)
class Rider:
    rider_id: int
    first_name: str
    last_name: str
    usac_license: str | None
    uci_id: str | None
    birth_year: int | None
    notes: str
    created_utc: str
    updated_utc: str

    @property
    def name(self) -> str:
        """The name every list and sentence shows: first then last."""
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True, slots=True)
class Event:
    event_id: int
    name: str
    event_date: str
    venue: str
    notes: str
    created_utc: str
    series: str = ""


@dataclass(frozen=True, slots=True)
class RosterEntry:
    event_id: int
    rider_id: int
    # None until the venue assigns one; see roster_entry in migrations.py.
    bib: int | None
    local_group: str | None


@dataclass(frozen=True, slots=True)
class Race:
    race_id: int
    event_id: int
    seq_in_event: int
    name: str
    format: str
    group_label: str
    rules_preset: str
    rules: dict[str, Any]
    rules_version: str
    usac_discipline: str | None
    usac_category: str | None
    usac_gender: str | None
    usac_class: str | None
    usac_age_group: str | None
    state: str
    announced_utc: str | None
    notes: str


@dataclass(frozen=True, slots=True)
class RaceEntry:
    """A start-list row: the entrant with the bib and group resolved through roster_entry."""

    race_id: int
    rider_id: int
    bib: int | None
    first_name: str
    last_name: str
    local_group: str | None

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True, slots=True)
class Team:
    team_id: int
    race_id: int
    name: str
    color: str
    color_hex: str | None
    seq: int
    members: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Action:
    """One row of the append-only log. payload is the parsed JSON object."""

    action_id: int
    action_uuid: str
    race_id: int
    recorded_utc: str
    kind: str
    schema_ver: int
    payload: dict[str, Any]
    voids_action_id: int | None
    operator_note: str | None


@dataclass(frozen=True, slots=True)
class StateChange:
    """A race's result becoming provisional or final, or leaving either: one row of its history."""

    change_id: int
    race_id: int
    from_state: str
    to_state: str
    recorded_utc: str
    after_action_id: int


# The moves worth a line of history: into or out of a result.
_LOGGED_STATES = frozenset({"provisional", "final"})


_RIDER_COLUMNS = (
    "rider_id, first_name, last_name, usac_license, uci_id, birth_year, notes, "
    "created_utc, updated_utc"
)
_RIDER_FIELDS = frozenset(
    {
        "first_name",
        "last_name",
        "usac_license",
        "uci_id",
        "birth_year",
        "notes",
    }
)
_EVENT_COLUMNS = "event_id, name, event_date, venue, notes, created_utc, series"
_EVENT_FIELDS = frozenset({"name", "event_date", "venue", "notes", "series"})


def _squash_key(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


_RACE_COLUMNS = (
    "race_id, event_id, seq_in_event, name, format, group_label, rules_preset, rules_json, "
    "rules_version, usac_discipline, usac_category, usac_gender, usac_class, usac_age_group, "
    "state, announced_utc, notes"
)
_RACE_FIELDS = frozenset(
    {
        "seq_in_event",
        "name",
        "format",
        "group_label",
        "rules_preset",
        "rules",
        "rules_version",
        "usac_discipline",
        "usac_category",
        "usac_gender",
        "usac_class",
        "usac_age_group",
        "notes",
    }
)
_RULESET_COLUMNS = "ruleset_id, name, json, created_utc, updated_utc"
_ACTION_COLUMNS = (
    "action_id, action_uuid, race_id, recorded_utc, kind, schema_ver, payload_json, "
    "voids_action_id, operator_note"
)


@dataclass(frozen=True, slots=True)
class Ruleset:
    """A venue-defined ruleset: the JSON document the race editor copies from.

    ``doc`` is the parsed document (``madtracker.control.rulesets`` says
    what is in it); the store only keeps it whole and keeps ``name`` in
    step with the document's own "name" key.
    """

    ruleset_id: int
    name: str
    doc: dict[str, Any]
    created_utc: str
    updated_utc: str


@dataclass(frozen=True, slots=True)
class StandingsDef:
    """A multi-race standings as the scorer defined it: what to replay, not a result.

    ``rules`` is the kind's values as stored; empty means the kind's own
    defaults (``madtracker.control.multi_race`` says what a kind holds).
    ``event_ids`` are the ticked events, oldest first; ``excluded_race_ids``
    are the races the scorer left out, by id. ``penalties`` are the
    omnium penalties by rider id, in points, each above zero.
    """

    standings_id: int
    name: str
    kind: str
    rules: dict[str, Any]
    created_utc: str
    updated_utc: str
    event_ids: list[int]
    excluded_race_ids: list[int]
    penalties: dict[int, int]


_STANDINGS_COLUMNS = "standings_id, name, kind, rules_json, created_utc, updated_utc"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _check_bib(bib: int | None) -> None:
    if bib is not None and not 0 < bib <= BIB_MAX:
        raise ValueError(f"a bib is a number from 1 to {BIB_MAX}")


def _named(value: str, what: str) -> str:
    """A name as stored: one clean line, refused when nothing would show.

    The screens refuse a blank name first; this is the backstop, so a
    name of zero-width characters or a NUL never makes a race or an
    event nobody can find in a list.
    """
    name = clean_line(value)
    if is_blank(name):
        raise ValueError(f"{what} needs a name")
    return name


def _blank_to_none(value: str | None) -> str | None:
    """Identifiers arrive from imports as '' as often as absent; one spelling, NULL."""
    if value is None:
        return None
    value = clean_line(value)
    return value or None


def _license(value: str | None) -> str | None:
    """A USAC License as stored: USAC's own spelling, or NULL for none.

    Every path that saves a rider comes through here, so a license typed
    by hand and one imported from a file are one spelling and find each
    other. Text that is not a number is refused (``inputs.LICENSE_RULE``).
    """
    if value is None:
        return None
    return usac_license(value)


def _rider(row: sqlite3.Row) -> Rider:
    return Rider(*row)


def _event(row: sqlite3.Row) -> Event:
    return Event(*row)


def _entry(row: sqlite3.Row) -> RosterEntry:
    return RosterEntry(*row)


def _race(row: sqlite3.Row) -> Race:
    values = list(row)
    values[7] = json.loads(values[7])
    return Race(*values)


def _action(row: sqlite3.Row) -> Action:
    values = list(row)
    values[6] = json.loads(values[6])
    return Action(*values)


def _ruleset(row: sqlite3.Row) -> Ruleset:
    values = list(row)
    values[2] = json.loads(values[2])
    return Ruleset(*values)


def _refused(exc: BaseException) -> None:
    """Raise what a write that failed partway raised, as the store's refusal where it is SQLite's."""
    if isinstance(exc, (sqlite3.Error, OverflowError)) and not isinstance(exc, StoreError):
        # A constraint the schema refuses, or a number too big for
        # SQLite's integer, is the store's refusal, worded for the
        # scorer's red line, never a traceback.
        raise StoreError(f"the data file refused the write: {exc}") from exc
    raise exc


class Store:
    """All persistence for one database file. Not thread-safe; use it from one thread."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        # Milliseconds from BEGIN to COMMIT of the latest write, the number
        # the plan asks the app to log and to warn about above 200 ms. The
        # whole transaction rather than COMMIT alone because that is the
        # latency the operator feels.
        self.last_commit_ms: float = 0.0
        # How many writes are open inside each other: the outermost one
        # is the transaction, the ones inside it savepoints.
        self._depth = 0

    @classmethod
    def open(cls, path: str | os.PathLike[str]) -> "Store":
        return cls(open_database(path))

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @property
    def read_only(self) -> bool:
        """True when the file or its folder could only be opened for reading."""
        return is_read_only(self._conn)

    @property
    def path(self) -> Path:
        """The file this store writes to, for the settings screen and the backup naming."""
        for row in self._conn.execute("PRAGMA database_list"):
            if row[1] == "main":
                return Path(row[2])
        raise StoreError("no main database attached")

    def close(self) -> None:
        close_database(self._conn)

    def integrity_check(self) -> list[str]:
        return integrity_check(self._conn) + schema_problems(self._conn)

    def checkpoint(self) -> bool:
        """Fold the WAL into the main file now, without waiting on a reader; True when it ran.

        Until a clean close the night otherwise sits in the -wal file, and
        the .sqlite alone (copied by hand, or left after a crash) would open
        as an empty venue. PASSIVE never blocks: a reader elsewhere only
        means part of it waits for the next one.
        """
        if self.read_only:
            return False
        try:
            self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.Error:
            return False
        return True

    def backup_to(
        self, dest: str | os.PathLike[str], event: str = "", now: datetime | None = None
    ) -> Path:
        """A backup at dest, marked with when it was taken, from where, and the open event."""
        mark = {
            "taken_at": (now or datetime.now()).isoformat(timespec="seconds"),
            "source": str(self.path),
            "event": event,
        }
        return backup_database(self._conn, dest, mark)

    def clear_backup_mark(self) -> None:
        """Make a restored copy a data file: it is no longer a backup."""
        self.delete_setting(BACKUP_KEY)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Several write methods as one write: on disk together when the block ends, or not at all.

        Each write method is otherwise its own commit, and each commit is
        an fsync of the WAL (synchronous=FULL): a race saved with a
        12-rider field would be 13 of them, and a 60-row import up to 144,
        which is seconds on a laptop with a virus scanner watching the
        folder. A failure anywhere in the block leaves the file as it was
        before it, so a half-made race or a half-applied import cannot
        happen. Inside, each method still keeps its own all-or-nothing
        through a savepoint, so a refusal the caller catches and goes on
        from (a license kept off a rider, say) undoes only that method.
        """
        with self._write():
            yield

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        if self.read_only:
            raise StoreError("The data file is read-only.")
        if self._depth:
            with self._savepoint():
                yield self._conn
            return
        started = perf_counter()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            # Another program (a second copy of the app, a sync client)
            # held the write lock past busy_timeout. Every caller already
            # handles StoreError; a raw sqlite error would escape a slot.
            raise StoreError(f"the data file is busy: {exc}") from exc
        self._depth += 1
        try:
            yield self._conn
        except BaseException as exc:
            # A second error from ROLLBACK must not hide the one that ended
            # the block; SQLite may already have rolled back on its own.
            if self._conn.in_transaction:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            _refused(exc)
        finally:
            self._depth -= 1
        try:
            self._conn.execute("COMMIT")
        except BaseException as exc:
            # A failed COMMIT (disk full, I/O error) leaves the transaction
            # open; without this the next BEGIN would fail too and every
            # later write would be refused for a reason unrelated to it.
            # SQLite may already have rolled back on its own, and a second
            # error from ROLLBACK must not hide the first.
            if self._conn.in_transaction:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            if isinstance(exc, sqlite3.Error):
                raise StoreError(f"the data file was not written: {exc}") from exc
            raise
        self.last_commit_ms = (perf_counter() - started) * 1000.0

    @contextmanager
    def _savepoint(self) -> Iterator[None]:
        """One write method inside a transaction: undone alone when it refuses."""
        name = f"write_{self._depth}"
        self._conn.execute(f"SAVEPOINT {name}")
        self._depth += 1
        try:
            yield
        except BaseException as exc:
            self._conn.execute(f"ROLLBACK TO {name}")
            self._conn.execute(f"RELEASE {name}")
            _refused(exc)
        finally:
            self._depth -= 1
        self._conn.execute(f"RELEASE {name}")

    # ----- riders -----------------------------------------------------------

    def add_rider(
        self,
        first_name: str,
        last_name: str,
        *,
        usac_license: str | None = None,
        uci_id: str | None = None,
        birth_year: int | None = None,
        notes: str = "",
    ) -> Rider:
        usac_license = _license(usac_license)
        uci_id = _blank_to_none(uci_id)
        now = _now_utc()
        with self._write() as conn:
            self._check_license_free(usac_license, exclude_rider_id=None)
            self._check_uci_free(uci_id, exclude_rider_id=None)
            cur = conn.execute(
                "INSERT INTO rider (first_name, last_name, usac_license, uci_id, "
                "birth_year, notes, created_utc, updated_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    clean_line(first_name),
                    clean_line(last_name),
                    usac_license,
                    uci_id,
                    birth_year,
                    notes,
                    now,
                    now,
                ),
            )
            rider_id = cur.lastrowid
        return self.rider(rider_id)

    def update_rider(self, rider_id: int, **fields: Any) -> Rider:
        """Change the named columns; unknown names are a programming error, not a no-op."""
        unknown = set(fields) - _RIDER_FIELDS
        if unknown:
            raise ValueError(f"unknown rider fields: {sorted(unknown)}")
        if not fields:
            return self.rider(rider_id)
        if "usac_license" in fields:
            fields["usac_license"] = _license(fields["usac_license"])
        if "uci_id" in fields:
            fields["uci_id"] = _blank_to_none(fields["uci_id"])
        for key in ("first_name", "last_name"):
            if key in fields:
                fields[key] = clean_line(fields[key])
        with self._write() as conn:
            self.rider(rider_id)
            if "usac_license" in fields:
                self._check_license_free(fields["usac_license"], exclude_rider_id=rider_id)
            if "uci_id" in fields:
                self._check_uci_free(fields["uci_id"], exclude_rider_id=rider_id)
            assignments = ", ".join(f"{name} = ?" for name in fields)
            conn.execute(
                f"UPDATE rider SET {assignments}, updated_utc = ? WHERE rider_id = ?",
                (*fields.values(), _now_utc(), rider_id),
            )
        return self.rider(rider_id)

    def raced_in(self, rider_id: int) -> str | None:
        """The first event where the rider is in a race with any log row, or None.

        A voided row counts: the log names the rider by id and is never
        edited (design section 12), so a rider in the field of a race
        that was ever scored is history, never deleted, never merged
        away, even when Undo took every entry back. The setup lock asks
        the narrower question (``has_live_actions``), so a rider can be
        taken out of the field of a race undone to its start list; they
        are then named only by rows nothing replays or shows, and are no
        longer held here.
        """
        row = self._conn.execute(
            "SELECT m.name FROM race_entry re JOIN race r ON r.race_id = re.race_id "
            "JOIN event m ON m.event_id = r.event_id WHERE re.rider_id = ? AND (r.state != 'setup' "
            "OR EXISTS (SELECT 1 FROM race_action a WHERE a.race_id = r.race_id)) "
            "ORDER BY m.event_date, m.event_id LIMIT 1",
            (rider_id,),
        ).fetchone()
        return None if row is None else row[0]

    def event_raced(self, event_id: int) -> str | None:
        """The first race of the event with anything in its log, or that left setup; else None.

        A voided entry counts: its rows are in the log for good, and the
        log is never edited (design section 12), so the event stays. The
        setup lock asks the narrower question (``has_live_actions``).
        """
        row = self._conn.execute(
            "SELECT r.name FROM race r WHERE r.event_id = ? AND (r.state != 'setup' "
            "OR EXISTS (SELECT 1 FROM race_action a WHERE a.race_id = r.race_id)) "
            "ORDER BY r.seq_in_event LIMIT 1",
            (event_id,),
        ).fetchone()
        return None if row is None else row[0]

    def delete_event(self, event_id: int) -> None:
        """Remove an event nobody has raced in: its program, fields, teams, roster and settings.

        Refused (EntryInUseError) once any race has a log row: a scored
        race is history, and its rows are never deleted. Riders are the
        venue's and stay. The event's own settings (groups) are kept
        under event/<id>/ and its races' under race/<id>/, so
        they go with it.
        """
        with self._write() as conn:
            self.event(event_id)
            raced = self.event_raced(event_id)
            if raced is not None:
                raise EntryInUseError(f"the event has a scored race, {raced}")
            race_ids = [
                r[0]
                for r in conn.execute("SELECT race_id FROM race WHERE event_id = ?", (event_id,))
            ]
            for race_id in race_ids:
                conn.execute(
                    "DELETE FROM team_member WHERE team_id IN "
                    "(SELECT team_id FROM team WHERE race_id = ?)",
                    (race_id,),
                )
                conn.execute("DELETE FROM team WHERE race_id = ?", (race_id,))
                conn.execute("DELETE FROM race_entry WHERE race_id = ?", (race_id,))
                conn.execute("DELETE FROM setting WHERE key LIKE ?", (f"race/{race_id}/%",))
            conn.execute("DELETE FROM race WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM roster_entry WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM setting WHERE key LIKE ?", (f"event/{event_id}/%",))
            conn.execute("DELETE FROM event WHERE event_id = ?", (event_id,))

    def delete_rider(self, rider_id: int) -> None:
        """Remove a rider who has never raced, taking them off every roster and field.

        Refused once they are in a scored race. Anything short of that
        (a tick onto tonight's roster by mistake, a place in a race not
        yet run) names nobody in a log, so it goes with the rider. The
        races they were in lose their settings (the staged clicks and
        their Undo): SQLite hands the freed id to the next rider added,
        so a click kept by id would name another rider.
        """
        with self._write() as conn:
            self.rider(rider_id)
            raced = self.raced_in(rider_id)
            if raced is not None:
                raise EntryInUseError(f"rider {rider_id} has raced in {raced}")
            self._clear_race_settings_of(conn, rider_id)
            # Children first: the triggers refuse a roster entry still in a race.
            for table in ("team_member", "race_entry", "roster_entry", "rider"):
                conn.execute(f"DELETE FROM {table} WHERE rider_id = ?", (rider_id,))

    @staticmethod
    def _clear_race_settings_of(conn: sqlite3.Connection, rider_id: int) -> None:
        """Delete the settings of every race the rider is in the field of."""
        conn.execute(
            "DELETE FROM setting WHERE EXISTS (SELECT 1 FROM race_entry re"
            " WHERE re.rider_id = ? AND setting.key LIKE 'race/' || re.race_id || '/%')",
            (rider_id,),
        )

    # Ids and the like that a merge copies onto the kept rider where it has none.
    _MERGE_FILLS = ("usac_license", "uci_id", "birth_year")

    def merge_refusal(self, drop_id: int, keep_id: int | None = None) -> str:
        """Why ``drop_id`` cannot be merged into ``keep_id`` (or into anyone), or "".

        A rider in a scored race is history and stays (``raced_in``). The
        other direction is offered only when it would work: two records
        that have both raced stay two.
        """
        self.rider(drop_id)
        if keep_id is not None:
            self.rider(keep_id)
            if keep_id == drop_id:
                return "choose another rider to keep"
        raced = self.raced_in(drop_id)
        if raced is None:
            return ""
        if keep_id is not None and self.raced_in(keep_id) is not None:
            return f"rider {drop_id} and rider {keep_id} have both raced, so they can't be merged"
        return f"rider {drop_id} has raced in {raced}; merge the other record into this one instead"

    def merge_riders(
        self,
        keep_id: int,
        drop_id: int,
        *,
        values: Mapping[str, Any] | None = None,
        entries: Mapping[int, Mapping[str, Any]] | None = None,
        teams: Mapping[int, int] | None = None,
    ) -> Rider:
        """Fold ``drop_id`` into ``keep_id`` in one transaction and delete it.

        Its roster entries, keeping their bibs and groups, and its places
        in races not yet scored move to the kept rider; ids the kept rider
        lacks are filled from it. Where both are on one event's roster the
        kept entry stays and takes the spare's bib and group only where it
        has none, the same rule as the ids, and a race or team both are in
        keeps the kept rider's place. The races the spare was in lose
        their settings (the staged clicks and their Undo): a click by
        the spare's id would name nobody, or, once SQLite hands the freed
        id to the next rider added, another rider. Refused with
        ``merge_refusal``'s reason.

        Where the two differ, the scorer's choices override those rules:
        ``values`` are rider columns for the merged record, ``entries`` a
        bib and group per event (event_id: {"bib", "local_group"}), and
        ``teams`` the team kept per race (race_id: team_id). Which row
        survives is not the scorer's question, a choice of values is, so
        all of it lands in this one transaction or none of it does.
        """
        values = dict(values or {})
        unknown = set(values) - _RIDER_FIELDS
        if unknown:
            raise ValueError(f"unknown rider fields: {sorted(unknown)}")
        if "usac_license" in values:
            values["usac_license"] = _license(values["usac_license"])
        if "uci_id" in values:
            values["uci_id"] = _blank_to_none(values["uci_id"])
        with self._write() as conn:
            problem = self.merge_refusal(drop_id, keep_id)
            if problem:
                raise EntryInUseError(problem)
            keep, drop = self.rider(keep_id), self.rider(drop_id)
            self._clear_race_settings_of(conn, drop_id)
            # A race where the spare's team was chosen: the kept rider leaves
            # its own team there, so the spare's place moves to it below.
            for race_id, team_id in (teams or {}).items():
                conn.execute(
                    "DELETE FROM team_member WHERE rider_id = ? AND team_id != ? AND team_id IN ("
                    " SELECT team_id FROM team WHERE race_id = ?)",
                    (keep_id, team_id, race_id),
                )
            # Places the kept rider already holds: the spare's copy goes.
            conn.execute(
                "DELETE FROM team_member WHERE rider_id = ? AND team_id IN ("
                " SELECT t.team_id FROM team t WHERE t.race_id IN ("
                "  SELECT t2.race_id FROM team t2 JOIN team_member k ON k.team_id = t2.team_id"
                "  WHERE k.rider_id = ?))",
                (drop_id, keep_id),
            )
            conn.execute(
                "DELETE FROM race_entry WHERE rider_id = ? AND race_id IN ("
                " SELECT race_id FROM race_entry WHERE rider_id = ?)",
                (drop_id, keep_id),
            )
            conn.execute(
                "UPDATE roster_entry AS k SET"
                " bib = COALESCE(k.bib, d.bib), local_group = COALESCE(k.local_group, d.local_group)"
                " FROM roster_entry AS d"
                " WHERE k.rider_id = ? AND d.rider_id = ? AND d.event_id = k.event_id",
                (keep_id, drop_id),
            )
            for table in ("team_member", "race_entry"):
                conn.execute(
                    f"UPDATE {table} SET rider_id = ? WHERE rider_id = ?", (keep_id, drop_id)
                )
            # The spare's race places are the kept rider's now, so the
            # trigger lets its doubled roster entry go.
            conn.execute(
                "DELETE FROM roster_entry WHERE rider_id = ? AND event_id IN ("
                " SELECT event_id FROM roster_entry WHERE rider_id = ?)",
                (drop_id, keep_id),
            )
            conn.execute(
                "UPDATE roster_entry SET rider_id = ? WHERE rider_id = ?", (keep_id, drop_id)
            )
            for event_id, chosen in (entries or {}).items():
                for name in ("bib", "local_group"):
                    if name in chosen:
                        conn.execute(
                            f"UPDATE roster_entry SET {name} = ? WHERE event_id = ? AND rider_id = ?",
                            (chosen[name], event_id, keep_id),
                        )
            fills = {
                name: getattr(drop, name)
                for name in self._MERGE_FILLS
                if getattr(keep, name) in (None, "") and getattr(drop, name) not in (None, "")
            }
            fills.update(values)
            # The ids are unique, so the record giving them up goes first.
            conn.execute("DELETE FROM rider WHERE rider_id = ?", (drop_id,))
            # An id typed in Merge Riders may be a third rider's.
            if "usac_license" in values:
                self._check_license_free(values["usac_license"], exclude_rider_id=keep_id)
            if "uci_id" in values:
                self._check_uci_free(values["uci_id"], exclude_rider_id=keep_id)
            if fills:
                assignments = ", ".join(f"{name} = ?" for name in fills)
                conn.execute(
                    f"UPDATE rider SET {assignments}, updated_utc = ? WHERE rider_id = ?",
                    (*fills.values(), _now_utc(), keep_id),
                )
        return self.rider(keep_id)

    def _check_license_free(self, usac_license: str | None, exclude_rider_id: int | None) -> None:
        if usac_license is None:
            return
        row = self._conn.execute(
            "SELECT rider_id FROM rider WHERE usac_license = ?", (usac_license,)
        ).fetchone()
        if row is not None and row[0] != exclude_rider_id:
            raise DuplicateLicenseError(
                f"USAC License {usac_license} already belongs to rider {row[0]}"
            )

    def _check_uci_free(self, uci_id: str | None, exclude_rider_id: int | None) -> None:
        """A UCI ID names one person, as a license does: the import falls back to it."""
        if uci_id is None:
            return
        row = self._conn.execute(
            "SELECT rider_id FROM rider WHERE uci_id = ? ORDER BY rider_id LIMIT 1", (uci_id,)
        ).fetchone()
        if row is not None and row[0] != exclude_rider_id:
            raise DuplicateUciError(f"UCI ID {uci_id} already belongs to rider {row[0]}")

    def rider(self, rider_id: int) -> Rider:
        row = self._conn.execute(
            f"SELECT {_RIDER_COLUMNS} FROM rider WHERE rider_id = ?", (rider_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"rider {rider_id} does not exist")
        return _rider(row)

    def riders(self) -> list[Rider]:
        rows = self._conn.execute(
            f"SELECT {_RIDER_COLUMNS} FROM rider ORDER BY last_name, first_name, rider_id"
        )
        return [_rider(r) for r in rows]

    def rider_count(self) -> int:
        """How many riders the venue has, without reading them all."""
        return self._conn.execute("SELECT COUNT(*) FROM rider").fetchone()[0]

    def search_riders(self, text: str) -> list[Rider]:
        """Riders matching a filter box's text by the one rule (``inputs.matches_filter``).

        Each typed word is found anywhere in the first or last name,
        case-insensitively, so this list and the race dialog's answer
        alike. Empty text lists everyone, so one call serves both the full
        roster view and the filter box. The match runs in Python, not in
        SQL, because SQLite's lower() folds ASCII only and the names are
        few enough (thousands) to read in one go.
        """
        words = filter_words(text)
        riders = self.riders()
        if not words:
            return riders
        return [r for r in riders if matches_filter(words, r.name)]

    def find_rider_by_license(self, usac_license: str) -> Rider | None:
        """The rider holding ``usac_license`` in any spelling, or None; text that is no number finds nobody."""
        try:
            usac_license = _license(usac_license)
        except ValueError:
            return None
        if usac_license is None:
            return None
        row = self._conn.execute(
            f"SELECT {_RIDER_COLUMNS} FROM rider WHERE usac_license = ?", (usac_license,)
        ).fetchone()
        return None if row is None else _rider(row)

    def find_rider_by_uci(self, uci_id: str) -> Rider | None:
        """The rider holding this UCI ID, or None."""
        uci_id = _blank_to_none(uci_id)
        if uci_id is None:
            return None
        row = self._conn.execute(
            f"SELECT {_RIDER_COLUMNS} FROM rider WHERE uci_id = ? LIMIT 1", (uci_id,)
        ).fetchone()
        return None if row is None else _rider(row)

    # ----- events -----------------------------------------------------------

    def add_event(
        self, name: str, event_date: str, *, venue: str = "", notes: str = "", series: str = ""
    ) -> Event:
        event_date = _iso_date(event_date)
        name = _named(name, "the event")
        with self._write() as conn:
            # Two events with one name and date read the same in every
            # picker and file name; the second is almost always a double
            # click or a forgotten first try, so it is refused, not added.
            _refuse_twin_event(conn, name, event_date, None)
            cur = conn.execute(
                "INSERT INTO event (name, event_date, venue, notes, created_utc, series) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, event_date, clean_line(venue), notes, _now_utc(), clean_line(series)),
            )
            event_id = cur.lastrowid
        return self.event(event_id)

    def update_event(self, event_id: int, **fields: Any) -> Event:
        unknown = set(fields) - _EVENT_FIELDS
        if unknown:
            raise ValueError(f"unknown event fields: {sorted(unknown)}")
        if not fields:
            return self.event(event_id)
        if "event_date" in fields:
            fields["event_date"] = _iso_date(fields["event_date"])
        for key in ("series", "venue"):
            if key in fields:
                fields[key] = clean_line(fields[key])
        if "name" in fields:
            fields["name"] = _named(fields["name"], "the event")
        with self._write() as conn:
            current = self.event(event_id)
            if "name" in fields or "event_date" in fields:
                # A rename or a new date can land on another event as
                # surely as an add can, and reads just as ambiguously.
                _refuse_twin_event(
                    conn,
                    fields.get("name", current.name),
                    fields.get("event_date", current.event_date),
                    event_id,
                )
            assignments = ", ".join(f"{name} = ?" for name in fields)
            conn.execute(
                f"UPDATE event SET {assignments} WHERE event_id = ?",
                (*fields.values(), event_id),
            )
        return self.event(event_id)

    def event(self, event_id: int) -> Event:
        row = self._conn.execute(
            f"SELECT {_EVENT_COLUMNS} FROM event WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"event {event_id} does not exist")
        return _event(row)

    def events(self) -> list[Event]:
        """Newest first: the event the scorer wants is almost always tonight's."""
        rows = self._conn.execute(
            f"SELECT {_EVENT_COLUMNS} FROM event ORDER BY event_date DESC, event_id DESC"
        )
        return [_event(r) for r in rows]

    # ----- roster entries ---------------------------------------------------

    def add_entry(
        self, event_id: int, rider_id: int, bib: int | None, local_group: str | None = None
    ) -> RosterEntry:
        """Enter a rider in an event with tonight's bib, or None until it is assigned.

        The bib is not checked against the roster: riders who never share
        a race may wear one number, and the race field is where a clash is
        refused (madtracker.control.roster).
        """
        with self._write() as conn:
            self.event(event_id)
            self.rider(rider_id)
            if self._entry_or_none(event_id, rider_id) is not None:
                raise DuplicateEntryError(
                    f"rider {rider_id} is already entered in event {event_id}"
                )
            _check_bib(bib)
            conn.execute(
                "INSERT INTO roster_entry (event_id, rider_id, bib, local_group) VALUES (?, ?, ?, ?)",
                (event_id, rider_id, bib, _blank_to_none(local_group)),
            )
        return self.entry(event_id, rider_id)

    def change_bib(self, event_id: int, rider_id: int, bib: int | None) -> RosterEntry:
        """Set or clear (None) the rider's bib for this event."""
        with self._write() as conn:
            self.entry(event_id, rider_id)
            _check_bib(bib)
            conn.execute(
                "UPDATE roster_entry SET bib = ? WHERE event_id = ? AND rider_id = ?",
                (bib, event_id, rider_id),
            )
        return self.entry(event_id, rider_id)

    def set_entry_group(self, event_id: int, rider_id: int, local_group: str | None) -> RosterEntry:
        with self._write() as conn:
            self.entry(event_id, rider_id)
            conn.execute(
                "UPDATE roster_entry SET local_group = ? WHERE event_id = ? AND rider_id = ?",
                (_blank_to_none(local_group), event_id, rider_id),
            )
        return self.entry(event_id, rider_id)

    def remove_entry(self, event_id: int, rider_id: int) -> None:
        """Take a rider off the event's roster.

        A result is history (docs/design.md section 12): the rider is
        dropped from the fields and teams of races nothing was scored in,
        and refused with the race's name once they are in a scored one.
        A race whose every entry Undo took back is scored in nothing: its
        field is open again, as the race dialog's is (``has_live_actions``).
        """
        with self._write() as conn:
            self.entry(event_id, rider_id)
            races = conn.execute(
                "SELECT r.race_id, r.name, r.state FROM race_entry re "
                "JOIN race r ON r.race_id = re.race_id "
                "WHERE r.event_id = ? AND re.rider_id = ? ORDER BY r.seq_in_event, r.race_id",
                (event_id, rider_id),
            ).fetchall()
            for race_id, name, state in races:
                if state != "setup" or self.has_live_actions(race_id):
                    raise EntryInUseError(
                        f"rider {rider_id} is in {name}, which has been scored,"
                        " and cannot be removed from this event"
                    )
            for race_id, _name, _state in races:
                conn.execute(
                    "DELETE FROM team_member WHERE rider_id = ? AND team_id IN "
                    "(SELECT team_id FROM team WHERE race_id = ?)",
                    (rider_id, race_id),
                )
                conn.execute(
                    "DELETE FROM race_entry WHERE race_id = ? AND rider_id = ?",
                    (race_id, rider_id),
                )
            conn.execute(
                "DELETE FROM roster_entry WHERE event_id = ? AND rider_id = ?", (event_id, rider_id)
            )

    def _entry_or_none(self, event_id: int, rider_id: int) -> RosterEntry | None:
        row = self._conn.execute(
            "SELECT event_id, rider_id, bib, local_group FROM roster_entry "
            "WHERE event_id = ? AND rider_id = ?",
            (event_id, rider_id),
        ).fetchone()
        return None if row is None else _entry(row)

    def entry(self, event_id: int, rider_id: int) -> RosterEntry:
        found = self._entry_or_none(event_id, rider_id)
        if found is None:
            raise NotFoundError(f"rider {rider_id} is not entered in event {event_id}")
        return found

    def last_entry(self, rider_id: int) -> RosterEntry | None:
        """The rider's roster entry at their most recent event, for the group and bib suggestion."""
        row = self._conn.execute(
            "SELECT e.event_id, e.rider_id, e.bib, e.local_group FROM roster_entry e "
            "JOIN event m ON m.event_id = e.event_id WHERE e.rider_id = ? "
            "ORDER BY m.event_date DESC, m.event_id DESC LIMIT 1",
            (rider_id,),
        ).fetchone()
        return None if row is None else _entry(row)

    def entries(self, event_id: int) -> list[RosterEntry]:
        rows = self._conn.execute(
            "SELECT event_id, rider_id, bib, local_group FROM roster_entry "
            # A rider still waiting for a bib sorts after every numbered one.
            "WHERE event_id = ? ORDER BY bib IS NULL, bib, rider_id",
            (event_id,),
        )
        return [_entry(r) for r in rows]

    def entries_with_riders(self, event_id: int) -> list[tuple[RosterEntry, Rider]]:
        """The roster as ``entries`` orders it, each entry with its rider, in one read.

        A list of the roster with names would otherwise read one rider per
        row: 60 queries each time a race dialog opens or a race reloads.
        """
        columns = ", ".join(f"rd.{c.strip()}" for c in _RIDER_COLUMNS.split(","))
        rows = self._conn.execute(
            f"SELECT e.event_id, e.rider_id, e.bib, e.local_group, {columns} "
            "FROM roster_entry e JOIN rider rd ON rd.rider_id = e.rider_id "
            "WHERE e.event_id = ? ORDER BY e.bib IS NULL, e.bib, e.rider_id",
            (event_id,),
        )
        return [(_entry(r[:4]), _rider(r[4:])) for r in rows]

    # ----- races ------------------------------------------------------------

    def add_race(
        self,
        event_id: int,
        name: str,
        format: str,
        *,
        seq_in_event: int | None = None,
        group_label: str = "",
        rules_preset: str = "",
        rules: dict[str, Any] | None = None,
        rules_version: str = "",
        usac_discipline: str | None = None,
        usac_category: str | None = None,
        usac_gender: str | None = None,
        usac_class: str | None = None,
        usac_age_group: str | None = None,
        notes: str = "",
    ) -> Race:
        """Add a race; with no seq_in_event it goes after the event's last race."""
        usac_category, usac_class, usac_age_group = (
            None if v is None else clean_line(v)
            for v in (usac_category, usac_class, usac_age_group)
        )
        with self._write() as conn:
            self.event(event_id)
            if seq_in_event is None:
                last = conn.execute(
                    "SELECT COALESCE(MAX(seq_in_event), 0) FROM race WHERE event_id = ?",
                    (event_id,),
                ).fetchone()[0]
                seq_in_event = last + 1
            cur = conn.execute(
                "INSERT INTO race (event_id, seq_in_event, name, format, group_label, rules_preset, "
                "rules_json, rules_version, usac_discipline, usac_category, usac_gender, "
                "usac_class, usac_age_group, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    seq_in_event,
                    _named(name, "the race"),
                    format,
                    clean_line(group_label),
                    rules_preset,
                    json.dumps(rules or {}, sort_keys=True),
                    rules_version,
                    usac_discipline,
                    usac_category,
                    usac_gender,
                    usac_class,
                    usac_age_group,
                    notes,
                ),
            )
            race_id = cur.lastrowid
        return self.race(race_id)

    def relabel_group(
        self,
        event_id: int,
        labels: Sequence[str],
        new: str | None,
        race_ids: Sequence[int],
        race_fields: Mapping[int, Mapping[str, str]] | None = None,
    ) -> None:
        """Give every entry of the event labelled one of ``labels`` the group ``new``.

        ``race_ids`` are the event's races that take the new label too.
        ``race_fields`` gives some of them a new name or USAC Category in
        the same write: the ones that were the group's default. One
        transaction, so a rename or a delete never leaves the event with
        the group half one name and half the other. ``new`` None clears
        the group from the entries; a race's label is then "".
        """
        with self._write() as conn:
            self.event(event_id)
            if labels:
                marks = ", ".join("?" for _ in labels)
                conn.execute(
                    f"UPDATE roster_entry SET local_group = ? WHERE event_id = ?"
                    f" AND local_group IN ({marks})",
                    (_blank_to_none(new), event_id, *labels),
                )
            for race_id in race_ids:
                conn.execute(
                    "UPDATE race SET group_label = ? WHERE race_id = ? AND event_id = ?",
                    (clean_line(new), race_id, event_id),
                )
            for race_id, fields in (race_fields or {}).items():
                for column, value in fields.items():
                    if column not in ("name", "usac_category"):
                        raise ValueError(f"relabel_group cannot set {column}")
                    conn.execute(
                        f"UPDATE race SET {column} = ? WHERE race_id = ? AND event_id = ?",
                        (clean_line(value), race_id, event_id),
                    )

    def update_race(self, race_id: int, **fields: Any) -> Race:
        """Change the named columns. `rules` takes a dict; state goes through set_state."""
        unknown = set(fields) - _RACE_FIELDS
        if unknown:
            raise ValueError(f"unknown race fields: {sorted(unknown)}")
        if not fields:
            return self.race(race_id)
        if "rules" in fields:
            fields["rules_json"] = json.dumps(fields.pop("rules") or {}, sort_keys=True)
        for key in ("group_label", "usac_category", "usac_class", "usac_age_group"):
            if fields.get(key) is not None:
                fields[key] = clean_line(fields[key])
        if "name" in fields:
            fields["name"] = _named(fields["name"], "the race")
        with self._write() as conn:
            self.race(race_id)
            assignments = ", ".join(f"{name} = ?" for name in fields)
            conn.execute(
                f"UPDATE race SET {assignments} WHERE race_id = ?",
                (*fields.values(), race_id),
            )
        return self.race(race_id)

    def set_state(self, race_id: int, state: str) -> Race:
        """Move the race between setup, running, provisional and final.

        Entering 'provisional' stamps announced_utc the first time, since
        the protest window (USAC 15 minutes) runs from the announcement.
        Back in setup the race has nothing announced: Undo took every
        entry back, and the race is ridden again from its start.
        """
        if state not in RACE_STATES:
            raise ValueError(f"unknown race state {state!r}")
        with self._write() as conn:
            self._move_state(conn, race_id, state)
        return self.race(race_id)

    def _move_state(self, conn: sqlite3.Connection, race_id: int, state: str) -> None:
        race = self.race(race_id)
        announced = None if state == "setup" else race.announced_utc
        if state == "provisional" and announced is None:
            announced = _now_utc()
        conn.execute(
            "UPDATE race SET state = ?, announced_utc = ? WHERE race_id = ?",
            (state, announced, race_id),
        )
        if state != race.state and {state, race.state} & _LOGGED_STATES:
            newest = conn.execute("SELECT COALESCE(MAX(action_id), 0) FROM race_action").fetchone()
            conn.execute(
                "INSERT INTO race_state_change"
                " (race_id, from_state, to_state, recorded_utc, after_action_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (race_id, race.state, state, _now_utc(), newest[0]),
            )

    def delete_race(self, race_id: int) -> None:
        """Remove a race set up by mistake, with its settings. Refused once anything is in its log, undone or not.

        A voided row counts: the log's rows are never deleted, and they
        name the race. SQLite hands a deleted newest race's id to the next
        race added, so nothing keyed by the id may outlive the race: its
        staged clicks and undo stack (race/<id>/...) would open in the new
        race.
        """
        with self._write() as conn:
            self.race(race_id)
            has_actions = conn.execute(
                "SELECT 1 FROM race_action WHERE race_id = ? LIMIT 1", (race_id,)
            ).fetchone()
            if has_actions is not None:
                raise RaceHasActionsError(
                    f"race {race_id} has recorded actions and cannot be deleted"
                )
            conn.execute(
                "DELETE FROM team_member WHERE team_id IN "
                "(SELECT team_id FROM team WHERE race_id = ?)",
                (race_id,),
            )
            conn.execute("DELETE FROM team WHERE race_id = ?", (race_id,))
            conn.execute("DELETE FROM race_entry WHERE race_id = ?", (race_id,))
            conn.execute("DELETE FROM setting WHERE key LIKE ?", (f"race/{race_id}/%",))
            conn.execute("DELETE FROM race WHERE race_id = ?", (race_id,))

    def race(self, race_id: int) -> Race:
        row = self._conn.execute(
            f"SELECT {_RACE_COLUMNS} FROM race WHERE race_id = ?", (race_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"race {race_id} does not exist")
        return _race(row)

    def races(self, event_id: int) -> list[Race]:
        rows = self._conn.execute(
            f"SELECT {_RACE_COLUMNS} FROM race WHERE event_id = ? ORDER BY seq_in_event, race_id",
            (event_id,),
        )
        return [_race(r) for r in rows]

    def usac_values(self) -> tuple[list[str], list[str], list[str]]:
        """Every Category, Class, and Age group a race in this file has used.

        One spelling per value, the first met, sorted, so a value typed
        once is picked the same way every week after. A Category that is
        only the race's group, the default for a blank one, is left out:
        it is the venue's word, not one USAC defines.
        """
        found: tuple[dict[str, str], dict[str, str], dict[str, str]] = ({}, {}, {})
        rows = self._conn.execute(
            "SELECT usac_category, usac_class, usac_age_group, group_label FROM race"
            " ORDER BY race_id"
        )
        for category, usac_class, age_group, group in rows:
            if _squash_key(category) == _squash_key(group):
                category = None
            for seen, value in zip(found, (category, usac_class, age_group), strict=True):
                text = " ".join((value or "").split())
                if text:
                    seen.setdefault(text.casefold(), text)
        lists = [sorted(seen.values(), key=str.casefold) for seen in found]
        return lists[0], lists[1], lists[2]

    # ----- race entries and teams ------------------------------------------

    def add_race_entry(self, race_id: int, rider_id: int) -> RaceEntry:
        with self._write() as conn:
            race = self.race(race_id)
            self.entry(race.event_id, rider_id)
            exists = conn.execute(
                "SELECT 1 FROM race_entry WHERE race_id = ? AND rider_id = ?", (race_id, rider_id)
            ).fetchone()
            if exists is not None:
                raise DuplicateEntryError(f"rider {rider_id} is already in race {race_id}")
            conn.execute(
                "INSERT INTO race_entry (race_id, rider_id) VALUES (?, ?)", (race_id, rider_id)
            )
        return self._race_entry(race_id, rider_id)

    def remove_race_entry(self, race_id: int, rider_id: int) -> None:
        with self._write() as conn:
            self._race_entry(race_id, rider_id)
            conn.execute(
                "DELETE FROM team_member WHERE rider_id = ? AND team_id IN "
                "(SELECT team_id FROM team WHERE race_id = ?)",
                (rider_id, race_id),
            )
            conn.execute(
                "DELETE FROM race_entry WHERE race_id = ? AND rider_id = ?", (race_id, rider_id)
            )
            # The race's staged clicks name the rider by id, and a rider
            # added later may be given that id again.
            conn.execute("DELETE FROM setting WHERE key LIKE ?", (f"race/{race_id}/%",))

    _RACE_ENTRY_SQL = (
        "SELECT re.race_id, re.rider_id, me.bib, rd.first_name, rd.last_name, me.local_group "
        "FROM race_entry re "
        "JOIN race r ON r.race_id = re.race_id "
        "JOIN roster_entry me ON me.event_id = r.event_id AND me.rider_id = re.rider_id "
        "JOIN rider rd ON rd.rider_id = re.rider_id "
    )

    def _race_entry(self, race_id: int, rider_id: int) -> RaceEntry:
        row = self._conn.execute(
            self._RACE_ENTRY_SQL + "WHERE re.race_id = ? AND re.rider_id = ?", (race_id, rider_id)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"rider {rider_id} is not in race {race_id}")
        return RaceEntry(*row)

    def race_entries(self, race_id: int) -> list[RaceEntry]:
        """The start list in bib order, riders without a bib last, names and groups resolved."""
        rows = self._conn.execute(
            self._RACE_ENTRY_SQL
            + "WHERE re.race_id = ? ORDER BY me.bib IS NULL, me.bib, re.rider_id",
            (race_id,),
        )
        return [RaceEntry(*r) for r in rows]

    def add_team(
        self,
        race_id: int,
        name: str,
        *,
        color: str = "",
        color_hex: str | None = None,
        seq: int | None = None,
    ) -> Team:
        name = clean_line(name)
        with self._write() as conn:
            self.race(race_id)
            exists = conn.execute(
                "SELECT 1 FROM team WHERE race_id = ? AND name = ?", (race_id, name)
            ).fetchone()
            if exists is not None:
                raise DuplicateTeamNameError(f"team {name!r} already exists in race {race_id}")
            if seq is None:
                seq = (
                    conn.execute(
                        "SELECT COALESCE(MAX(seq), 0) FROM team WHERE race_id = ?", (race_id,)
                    ).fetchone()[0]
                    + 1
                )
            cur = conn.execute(
                "INSERT INTO team (race_id, name, color, color_hex, seq) VALUES (?, ?, ?, ?, ?)",
                (race_id, name, color, _blank_to_none(color_hex), seq),
            )
            team_id = cur.lastrowid
        return self.team(team_id)

    def remove_team(self, team_id: int) -> None:
        with self._write() as conn:
            self.team(team_id)
            conn.execute("DELETE FROM team WHERE team_id = ?", (team_id,))

    def add_team_member(self, team_id: int, rider_id: int) -> Team:
        with self._write() as conn:
            team = self.team(team_id)
            self._race_entry(team.race_id, rider_id)
            on_team = conn.execute(
                "SELECT t.team_id FROM team_member tm JOIN team t ON t.team_id = tm.team_id "
                "WHERE t.race_id = ? AND tm.rider_id = ?",
                (team.race_id, rider_id),
            ).fetchone()
            if on_team is not None:
                raise DuplicateEntryError(
                    f"rider {rider_id} is already on team {on_team[0]} in race {team.race_id}"
                )
            conn.execute(
                "INSERT INTO team_member (team_id, rider_id) VALUES (?, ?)", (team_id, rider_id)
            )
        return self.team(team_id)

    def team(self, team_id: int) -> Team:
        row = self._conn.execute(
            "SELECT team_id, race_id, name, color, color_hex, seq FROM team WHERE team_id = ?",
            (team_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"team {team_id} does not exist")
        return self._team_with_members(row)

    def teams(self, race_id: int) -> list[Team]:
        rows = self._conn.execute(
            "SELECT team_id, race_id, name, color, color_hex, seq FROM team "
            "WHERE race_id = ? ORDER BY seq, team_id",
            (race_id,),
        ).fetchall()
        return [self._team_with_members(r) for r in rows]

    def save_race(
        self,
        event_id: int,
        race_id: int | None,
        fields: Mapping[str, Any],
        rider_ids: Sequence[int],
        teams: Sequence[tuple[str, str, str | None, Sequence[int]]] | None = None,
    ) -> Race:
        """Add a race (``race_id`` None) or change one, with its field and teams, as one write.

        ``fields`` are add_race's arguments, ``name`` and ``format``
        included. The field becomes ``rider_ids``. ``teams`` None leaves
        the teams alone; a list of (name, color, color_hex, members) makes
        the race's teams that list in that order. A team is its riders: a
        stored team with the same riders keeps its id and takes the new
        name, color, and place, so a rename leaves the staged clicks and
        their Undo alone. A team whose riders changed is taken out before
        the rest are added, and takes the race's settings with it: SQLite
        hands its freed id to the next team added, so a click kept by id
        would name another team. Any refusal leaves the file as it was:
        never half a race.
        """
        with self.transaction():
            if race_id is None:
                values = dict(fields)
                race_id = self.add_race(
                    event_id, values.pop("name"), values.pop("format"), **values
                ).race_id
            else:
                self.update_race(race_id, **fields)
            current = {e.rider_id for e in self.race_entries(race_id)}
            for rider_id in current - set(rider_ids):
                self.remove_race_entry(race_id, rider_id)
            for rider_id in rider_ids:
                if rider_id not in current:
                    self.add_race_entry(race_id, rider_id)
                    current.add(rider_id)
            if teams is not None:
                wanted = [
                    (clean_line(name), color, _blank_to_none(hex_color), tuple(members), seq)
                    for seq, (name, color, hex_color, members) in enumerate(teams, 1)
                ]
                names = [w[0] for w in wanted]
                for name in names:
                    if names.count(name) > 1:
                        raise DuplicateTeamNameError(
                            f"team {name!r} given twice for race {race_id}"
                        )
                # Teams are matched by their riders, so one rider on two
                # teams is refused here, before two teams could merge.
                riders = [rider_id for w in wanted for rider_id in w[3]]
                if len(riders) != len(set(riders)):
                    raise DuplicateEntryError(f"a rider is on two teams in race {race_id}")

                # A team with no riders yet has only its name to be known by.
                def key(name, members):
                    return frozenset(members) if members else name

                new_riders = {key(w[0], w[3]): w for w in wanted}
                kept = []
                taken_out = False
                for t in self.teams(race_id):
                    shape = new_riders.pop(key(t.name, t.members), None)
                    if shape is None:
                        self.remove_team(t.team_id)
                        taken_out = True
                    else:
                        kept.append((t, shape))
                if taken_out:
                    with self._write() as conn:
                        conn.execute("DELETE FROM setting WHERE key LIKE ?", (f"race/{race_id}/%",))
                with self._write() as conn:
                    # Two teams that trade names would trip the one-name-per-race
                    # rule midway, so a kept team's old name is let go first.
                    for t, _ in kept:
                        conn.execute(
                            "UPDATE team SET name = ? WHERE team_id = ?",
                            (f"\0{t.team_id}", t.team_id),
                        )
                    for t, (name, color, hex_color, members, seq) in kept:
                        conn.execute(
                            "UPDATE team SET name = ?, color = ?, color_hex = ?, seq = ? "
                            "WHERE team_id = ?",
                            (name, color, hex_color, seq, t.team_id),
                        )
                        if t.members != members:
                            conn.execute("DELETE FROM team_member WHERE team_id = ?", (t.team_id,))
                            for rider_id in members:
                                self.add_team_member(t.team_id, rider_id)
                for name, color, hex_color, members, seq in new_riders.values():
                    team = self.add_team(race_id, name, color=color, color_hex=hex_color, seq=seq)
                    for rider_id in members:
                        self.add_team_member(team.team_id, rider_id)
        return self.race(race_id)

    def _team_with_members(self, row: sqlite3.Row) -> Team:
        members = tuple(
            r[0]
            for r in self._conn.execute(
                "SELECT rider_id FROM team_member WHERE team_id = ? ORDER BY rowid", (row[0],)
            )
        )
        return Team(*row, members)

    # ----- actions ----------------------------------------------------------

    def append_action(
        self,
        race_id: int,
        kind: str,
        payload: dict[str, Any],
        schema_ver: int,
        operator_note: str | None = None,
    ) -> int:
        """Record one scorer action. Returns only after the row is on disk."""
        if kind == VOID_KIND:
            raise ValueError("use void_action() to void an action")
        payload_json = json.dumps(payload, sort_keys=True)
        with self._write() as conn:
            self.race(race_id)
            cur = conn.execute(
                "INSERT INTO race_action (action_uuid, race_id, recorded_utc, kind, schema_ver, "
                "payload_json, voids_action_id, operator_note) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
                (
                    str(uuid.uuid4()),
                    race_id,
                    _now_utc(),
                    kind,
                    schema_ver,
                    payload_json,
                    operator_note,
                ),
            )
            return cur.lastrowid

    def void_action(self, race_id: int, action_id: int, note: str | None = None) -> int:
        """Undo an action by appending a void that points at it. Returns the void's id.

        A void cannot itself be voided: redo is done by appending the
        original action again, so the log stays a straight line and
        "live" is a single lookup. The target must belong to race_id so a
        stale action id from another race can never silently undo the
        wrong thing.
        """
        with self._write() as conn:
            self.race(race_id)
            self._check_void_target(conn, race_id, action_id)
            cur = conn.execute(
                "INSERT INTO race_action (action_uuid, race_id, recorded_utc, kind, schema_ver, "
                "payload_json, voids_action_id, operator_note) VALUES (?, ?, ?, ?, 1, '{}', ?, ?)",
                (str(uuid.uuid4()), race_id, _now_utc(), VOID_KIND, action_id, note),
            )
            return cur.lastrowid

    @staticmethod
    def _check_void_target(conn: sqlite3.Connection, race_id: int, action_id: int) -> None:
        # The trigger refuses the same things; checking first gives the
        # caller an exception that says which rule.
        target = conn.execute(
            "SELECT race_id, kind FROM race_action WHERE action_id = ?", (action_id,)
        ).fetchone()
        if target is None:
            raise NotFoundError(f"action {action_id} does not exist")
        if target[0] != race_id:
            raise VoidError(f"action {action_id} belongs to race {target[0]}, not {race_id}")
        if target[1] == VOID_KIND:
            raise VoidError(f"action {action_id} is a void; re-append the action to redo it")
        already = conn.execute(
            "SELECT action_id FROM race_action WHERE kind = ? AND voids_action_id = ?",
            (VOID_KIND, action_id),
        ).fetchone()
        if already is not None:
            raise VoidError(f"action {action_id} was already voided by action {already[0]}")

    def append_batch(
        self,
        race_id: int,
        appends: Sequence[tuple[str, dict[str, Any], int, str | None]] = (),
        voids: Sequence[tuple[int, str | None]] = (),
        state: str | None = None,
        settings: Mapping[str, Any] | None = None,
        expect: Mapping[str, Any] | None = None,
    ) -> list[int]:
        """One scorer action as one transaction: its rows, its voids, its state, its settings.

        ``voids`` are (action_id, operator_note) and go in first;
        ``appends`` are (kind, payload, schema_ver, operator_note) and
        follow, in order. Action ids are the order the log reads in, and
        a scorer correcting a result takes the old one away before putting
        the new one in, so the void of the old row comes before its
        replacement. A settings value of None deletes the key. ``expect``
        names settings whose stored value must still be what the caller
        read (None for absent), checked inside the transaction so two
        windows on one file cannot both write from the same starting point.
        Returns the new rows' ids, appends then voids (the order of the
        arguments, not of the writes). Nothing is written unless all of it
        is: a power cut leaves the action whole or absent, never half.
        """
        if state is not None and state not in RACE_STATES:
            raise ValueError(f"unknown race state {state!r}")
        if any(kind == VOID_KIND for kind, *_ in appends):
            raise ValueError("voids go in voids, not appends")
        try:
            with self._write() as conn:
                self.race(race_id)
                for key, wanted in (expect or {}).items():
                    row = conn.execute(
                        "SELECT value_json FROM setting WHERE key = ?", (key,)
                    ).fetchone()
                    changed = f"setting {key!r} changed since it was read"
                    if row is None:
                        if wanted is not None:
                            raise ConflictError(changed)
                        continue
                    expected = _canonical(wanted)
                    # The row was written canonical, so the strings agree
                    # unless another writer spelled it differently.
                    if row[0] != expected and _canonical(json.loads(row[0])) != expected:
                        raise ConflictError(changed)
                void_ids = []
                for action_id, note in voids:
                    self._check_void_target(conn, race_id, action_id)
                    cur = conn.execute(
                        "INSERT INTO race_action (action_uuid, race_id, recorded_utc, kind, "
                        "schema_ver, payload_json, voids_action_id, operator_note) "
                        "VALUES (?, ?, ?, ?, 1, '{}', ?, ?)",
                        (str(uuid.uuid4()), race_id, _now_utc(), VOID_KIND, action_id, note),
                    )
                    void_ids.append(cur.lastrowid)
                ids = []
                for kind, payload, schema_ver, note in appends:
                    cur = conn.execute(
                        "INSERT INTO race_action (action_uuid, race_id, recorded_utc, kind, "
                        "schema_ver, payload_json, voids_action_id, operator_note) "
                        "VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
                        (
                            str(uuid.uuid4()),
                            race_id,
                            _now_utc(),
                            kind,
                            schema_ver,
                            json.dumps(payload, sort_keys=True),
                            note,
                        ),
                    )
                    ids.append(cur.lastrowid)
                ids.extend(void_ids)
                if state is not None:
                    self._move_state(conn, race_id, state)
                for key, value in (settings or {}).items():
                    if value is None:
                        conn.execute("DELETE FROM setting WHERE key = ?", (key,))
                    else:
                        conn.execute(
                            "INSERT INTO setting (key, value_json) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                            (key, json.dumps(value, sort_keys=True)),
                        )
        except sqlite3.Error as exc:
            # A trigger's refusal or a disk error reaches the UI as a
            # StoreError like every other refusal, never as a raw sqlite3 one.
            raise StoreError(str(exc)) from exc
        return ids

    def actions(self, race_id: int) -> list[Action]:
        """Every action of the race in action_id order, voids and voided rows included."""
        rows = self._conn.execute(
            f"SELECT {_ACTION_COLUMNS} FROM race_action WHERE race_id = ? ORDER BY action_id",
            (race_id,),
        )
        return [_action(r) for r in rows]

    def live_actions(self, race_id: int) -> list[Action]:
        """The actions scoring should replay: no voids, no voided rows."""
        # A void sits in its row's race, so naming the race keeps the
        # subquery on the race index rather than the whole file's log. The
        # subquery is not correlated, so SQLite builds the voided set once
        # per call; a correlated NOT EXISTS would rescan the race's rows
        # for every live row and slow each click in a long race. The
        # IS NOT NULL matters: one NULL in a NOT IN list drops every row.
        rows = self._conn.execute(
            f"SELECT {_ACTION_COLUMNS} FROM race_action WHERE race_id = ? AND kind <> ? "
            "AND action_id NOT IN (SELECT voids_action_id FROM race_action "
            "WHERE race_id = ? AND kind = ? AND voids_action_id IS NOT NULL) "
            "ORDER BY action_id",
            (race_id, VOID_KIND, race_id, VOID_KIND),
        )
        return [_action(r) for r in rows]

    def has_live_actions(self, race_id: int) -> bool:
        """Whether the race has an entry that stands: a row that is no void and is not voided.

        The question behind a race's setup lock. Undo never deletes a row,
        so a race undone to its start list still has rows, every one of
        them a void or voided; those are never replayed, and the race is
        set up again like one never scored. ``last_action`` answers the
        other question, whether the log holds anything at all.
        """
        row = self._conn.execute(
            "SELECT 1 FROM race_action WHERE race_id = ? AND kind <> ? "
            "AND action_id NOT IN (SELECT voids_action_id FROM race_action "
            "WHERE race_id = ? AND kind = ? AND voids_action_id IS NOT NULL) LIMIT 1",
            (race_id, VOID_KIND, race_id, VOID_KIND),
        ).fetchone()
        return row is not None

    def state_changes(self, race_id: int) -> list[StateChange]:
        """The race's moves into and out of provisional and final, oldest first."""
        rows = self._conn.execute(
            "SELECT change_id, race_id, from_state, to_state, recorded_utc, after_action_id"
            " FROM race_state_change WHERE race_id = ? ORDER BY change_id",
            (race_id,),
        )
        return [StateChange(*r) for r in rows]

    def last_action(self, race_id: int) -> Action | None:
        """The newest row, void or not: what the recovery banner shows after a crash."""
        row = self._conn.execute(
            f"SELECT {_ACTION_COLUMNS} FROM race_action WHERE race_id = ? "
            "ORDER BY action_id DESC LIMIT 1",
            (race_id,),
        ).fetchone()
        return None if row is None else _action(row)

    # ----- rulesets ---------------------------------------------------------

    def add_ruleset(self, name: str, doc: dict[str, Any]) -> Ruleset:
        """Store a ruleset document under name. The name wins over doc["name"]."""
        name = clean_line(name)
        if not name:
            raise ValueError("a ruleset needs a name")
        now = _now_utc()
        with self._write() as conn:
            self._check_ruleset_name_free(name, None)
            cur = conn.execute(
                "INSERT INTO ruleset (name, json, created_utc, updated_utc) VALUES (?, ?, ?, ?)",
                (name, _ruleset_json(name, doc), now, now),
            )
            ruleset_id = cur.lastrowid
        return self.ruleset(ruleset_id)

    def update_ruleset(
        self, ruleset_id: int, *, name: str | None = None, doc: dict[str, Any] | None = None
    ) -> Ruleset:
        """Rename and/or replace the document. Either argument may be left out."""
        with self._write() as conn:
            current = self.ruleset(ruleset_id)
            new_name = current.name if name is None else clean_line(name)
            if not new_name:
                raise ValueError("a ruleset needs a name")
            self._check_ruleset_name_free(new_name, ruleset_id)
            new_doc = current.doc if doc is None else doc
            conn.execute(
                "UPDATE ruleset SET name = ?, json = ?, updated_utc = ? WHERE ruleset_id = ?",
                (new_name, _ruleset_json(new_name, new_doc), _now_utc(), ruleset_id),
            )
            if new_name != current.name:
                # A race names the ruleset it was made from; renamed, the
                # race follows, or Edit Race would find no such ruleset and put
                # the default's rules in place of the race's own.
                conn.execute(
                    "UPDATE race SET rules_preset = ? WHERE rules_preset = ?",
                    (new_name, current.name),
                )
        return self.ruleset(ruleset_id)

    def delete_ruleset(self, ruleset_id: int) -> None:
        """Remove a ruleset. Races keep their own copy of the rules, so nothing refers to it."""
        with self._write() as conn:
            self.ruleset(ruleset_id)
            conn.execute("DELETE FROM ruleset WHERE ruleset_id = ?", (ruleset_id,))

    def _check_ruleset_name_free(self, name: str, exclude_ruleset_id: int | None) -> None:
        row = self._conn.execute(
            "SELECT ruleset_id, name FROM ruleset WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is not None and row[0] != exclude_ruleset_id:
            raise DuplicateRulesetNameError(f"a ruleset named {row[1]} already exists")

    def ruleset(self, ruleset_id: int) -> Ruleset:
        row = self._conn.execute(
            f"SELECT {_RULESET_COLUMNS} FROM ruleset WHERE ruleset_id = ?", (ruleset_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"ruleset {ruleset_id} does not exist")
        return _ruleset(row)

    def ruleset_by_name(self, name: str) -> Ruleset | None:
        row = self._conn.execute(
            f"SELECT {_RULESET_COLUMNS} FROM ruleset WHERE name = ? COLLATE NOCASE",
            (name.strip(),),
        ).fetchone()
        return None if row is None else _ruleset(row)

    def rulesets(self) -> list[Ruleset]:
        rows = self._conn.execute(
            f"SELECT {_RULESET_COLUMNS} FROM ruleset ORDER BY name COLLATE NOCASE, ruleset_id"
        )
        return [_ruleset(r) for r in rows]

    # ----- multi-race standings ---------------------------------------------

    def list_standings(self) -> list[StandingsDef]:
        """Every standings in the file, by name without case."""
        rows = self._conn.execute(
            f"SELECT {_STANDINGS_COLUMNS} FROM standings ORDER BY name COLLATE NOCASE, standings_id"
        ).fetchall()
        return [self._standings(r) for r in rows]

    def get_standings(self, standings_id: int) -> StandingsDef:
        row = self._conn.execute(
            f"SELECT {_STANDINGS_COLUMNS} FROM standings WHERE standings_id = ?",
            (standings_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"standings {standings_id} does not exist")
        return self._standings(row)

    def add_standings(
        self, name: str, kind: str = "team_omnium", rules: dict[str, Any] | None = None
    ) -> StandingsDef:
        """A new standings with no events ticked. ``rules`` None stores the kind's defaults ('{}')."""
        name = _named(name, "the standings")
        kind = _kind(kind)
        now = _now_utc()
        with self._write() as conn:
            self._check_standings_name_free(name, None)
            cur = conn.execute(
                "INSERT INTO standings (name, kind, rules_json, created_utc, updated_utc) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, kind, _canonical(rules or {}), now, now),
            )
            standings_id = cur.lastrowid
        return self.get_standings(standings_id)

    def update_standings(
        self,
        standings_id: int,
        *,
        name: str | None = None,
        kind: str | None = None,
        rules: dict[str, Any] | None = None,
        event_ids: Iterable[int] | None = None,
        excluded_race_ids: Iterable[int] | None = None,
    ) -> StandingsDef:
        """Change any part of a standings; a list given replaces the stored one whole."""
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = _named(name, "the standings")
        if kind is not None:
            fields["kind"] = _kind(kind)
        if rules is not None:
            fields["rules_json"] = _canonical(rules)
        with self._write() as conn:
            self.get_standings(standings_id)
            if "name" in fields:
                self._check_standings_name_free(fields["name"], standings_id)
            fields["updated_utc"] = _now_utc()
            assignments = ", ".join(f"{column} = ?" for column in fields)
            conn.execute(
                f"UPDATE standings SET {assignments} WHERE standings_id = ?",
                (*fields.values(), standings_id),
            )
            # The foreign keys refuse an event or race that does not
            # exist, and the write turns that into the store's refusal.
            if event_ids is not None:
                conn.execute("DELETE FROM standings_event WHERE standings_id = ?", (standings_id,))
                conn.executemany(
                    "INSERT INTO standings_event (standings_id, event_id) VALUES (?, ?)",
                    [(standings_id, int(e)) for e in dict.fromkeys(event_ids)],
                )
            if excluded_race_ids is not None:
                conn.execute(
                    "DELETE FROM standings_race_excluded WHERE standings_id = ?", (standings_id,)
                )
                conn.executemany(
                    "INSERT INTO standings_race_excluded (standings_id, race_id) VALUES (?, ?)",
                    [(standings_id, int(r)) for r in dict.fromkeys(excluded_race_ids)],
                )
        return self.get_standings(standings_id)

    def set_standings_penalty(self, standings_id: int, rider_id: int, points: int) -> StandingsDef:
        """The rider's omnium penalty in ``points`` from now on; 0 takes it off."""
        points = int(points)
        if points < 0:
            raise StoreError("a penalty is 0 or more points")
        with self._write() as conn:
            self.get_standings(standings_id)
            if points == 0:
                conn.execute(
                    "DELETE FROM standings_penalty WHERE standings_id = ? AND rider_id = ?",
                    (standings_id, rider_id),
                )
            else:
                # The foreign key refuses a rider that does not exist.
                conn.execute(
                    "INSERT INTO standings_penalty (standings_id, rider_id, points) "
                    "VALUES (?, ?, ?) ON CONFLICT(standings_id, rider_id) "
                    "DO UPDATE SET points = excluded.points",
                    (standings_id, int(rider_id), points),
                )
            conn.execute(
                "UPDATE standings SET updated_utc = ? WHERE standings_id = ?",
                (_now_utc(), standings_id),
            )
        return self.get_standings(standings_id)

    def remove_standings(self, standings_id: int) -> None:
        """Delete a standings and its links. No result is stored, so nothing else changes."""
        with self._write() as conn:
            self.get_standings(standings_id)
            conn.execute("DELETE FROM standings WHERE standings_id = ?", (standings_id,))

    def _check_standings_name_free(self, name: str, exclude_standings_id: int | None) -> None:
        row = self._conn.execute(
            "SELECT standings_id, name FROM standings WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is not None and row[0] != exclude_standings_id:
            raise DuplicateStandingsNameError(f"a standings named {row[1]} already exists")

    def _standings(self, row: sqlite3.Row) -> StandingsDef:
        standings_id = row[0]
        # Oldest first, the order the columns of the table read in.
        events = self._conn.execute(
            "SELECT se.event_id FROM standings_event se JOIN event e USING (event_id) "
            "WHERE se.standings_id = ? ORDER BY e.event_date, e.event_id",
            (standings_id,),
        )
        excluded = self._conn.execute(
            "SELECT race_id FROM standings_race_excluded WHERE standings_id = ? ORDER BY race_id",
            (standings_id,),
        )
        penalties = self._conn.execute(
            "SELECT rider_id, points FROM standings_penalty WHERE standings_id = ? "
            "ORDER BY rider_id",
            (standings_id,),
        )
        return StandingsDef(
            standings_id=standings_id,
            name=row[1],
            kind=row[2],
            rules=json.loads(row[3]),
            created_utc=row[4],
            updated_utc=row[5],
            event_ids=[r[0] for r in events],
            excluded_race_ids=[r[0] for r in excluded],
            penalties={r[0]: r[1] for r in penalties},
        )

    # ----- settings ---------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value_json FROM setting WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row[0])

    def set_setting(self, key: str, value: Any) -> None:
        """Store any JSON-serializable value under key, replacing what was there."""
        value_json = json.dumps(value, sort_keys=True)
        with self._write() as conn:
            conn.execute(
                "INSERT INTO setting (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (key, value_json),
            )

    def delete_setting(self, key: str) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM setting WHERE key = ?", (key,))

    def write_settings(self, values: dict[str, Any], delete: Iterable[str] = ()) -> None:
        """Set ``values`` and delete ``delete`` in one transaction.

        Settings > Save is several keys; one by one, a failure halfway
        (a full disk, a busy file) would keep the new logo with the old name.
        """
        rows = [(key, json.dumps(value, sort_keys=True)) for key, value in values.items()]
        with self._write() as conn:
            conn.executemany(
                "INSERT INTO setting (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                rows,
            )
            conn.executemany("DELETE FROM setting WHERE key = ?", [(k,) for k in delete])


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _kind(value: str) -> str:
    """A standings kind as stored: a key such as "team_omnium" or
    "team_omnium_places", never blank.

    The store does not know which kinds exist; the control layer does,
    and refuses one it cannot score when the standings is computed.
    """
    kind = clean_line(value)
    if is_blank(kind):
        raise ValueError("a standings needs a kind")
    return kind


def _ruleset_json(name: str, doc: dict[str, Any]) -> str:
    # The column is what the list and the uniqueness check read; the
    # document carries the same name so an exported file is self-describing.
    return json.dumps({**doc, "name": name}, sort_keys=True)


def _iso_date(value: str) -> str:
    """Event dates sort as text and feed the USAC export, so they must be real ISO dates."""
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"event_date must be an ISO date (YYYY-MM-DD), not {value!r}") from exc


def _refuse_twin_event(
    conn: sqlite3.Connection, name: str, event_date: str, event_id: int | None
) -> None:
    """Raise when another event already has this name and date, case aside."""
    twin = conn.execute(
        "SELECT name FROM event WHERE name = ? COLLATE NOCASE AND event_date = ? "
        "AND event_id IS NOT ?",
        (name, event_date, event_id),
    ).fetchone()
    if twin is not None:
        raise StoreError(f"An event named {twin[0]} on {show_date(event_date)} already exists.")
