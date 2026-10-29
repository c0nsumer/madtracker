"""BikeReg entries export: parse it, plan it against the rider database, apply the plan.

Three steps so the scorer sees every decision before anything is written:
``parse`` reads the CSV into plain rows, ``plan_import`` decides per row
which rider it is and which bib and group to propose, and
``apply_import`` writes only the rows the scorer ticked. No Qt here, so
the matching rules are tested without a display.

Nothing here merges two people on its own; the scorer decides in the
preview. A row is a rider on file when its USAC License or UCI ID is
that rider's and the names resemble each other, or when its exact name
is one rider's and nothing tells them apart: no USAC License or UCI ID
given differently, birth years at most a year apart (a late birthday
shifts racing age), and a stored id the row lacks only when both birth
years are known.
An id on file for someone with a different name, an id two rows give
to two people, or a possible match already on tonight's roster, is a
conflict: the row stays a new rider, unticked, with the other rider
offered. A new row with a rider of the same name on file is "New?",
unticked too, until the scorer picks the rider or New.

The importer never invents a bib. Bibs are handed out by the venue
for each event, outside this program, so a number the program made up
would be on no rider's back. A row's bib is the file's, or None: the
rider goes on the roster without one, and the bib is typed in later,
in the preview or on the roster. A number another rider on the roster
already wears is let in too (riders in different races may share one);
the preview says so, and the race field is where a clash is refused.

The columns read are BikeReg's own: Last Name, First Name, Bib, USAC
License, UCI Code, "Age on 12/31/YYYY" (racing age, which gives the
USAC age class), Category (the BikeReg entry category, such as
"Cat 4/5 (SemiPro C)").
Every other column is ignored. The export arrives with blank bibs,
licenses that are sometimes not numbers ("INTL-CAN" for a foreign rider,
whose UCI code then carries the id), and an age header whose text
carries the season year ("Age on 12/31/2026"), so it is matched by
prefix.
"""

import csv
import io
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from madtracker.control.groups import event_spellings, follow_group, group_key
from madtracker.control.riders import (
    SAME_NAME,
    SWAPPED_NAME,
    UCI_ID,
    USAC_LICENSE,
    Candidate,
    RiderIndex,
    first_key,
    is_unset,
    name_key,
    rank,
    rank_names,
)
from madtracker.control.roster import roster_bib_refusal
from madtracker.inputs import BIB_MAX, clean_line, is_ascii_digits, is_blank, usac_license
from madtracker.store import (
    DuplicateError,
    NotFoundError,
    Rider,
    Store,
)

REQUIRED_COLUMNS = ("Last Name", "First Name")
AGE_PREFIX = "Age on"


class ImportFormatError(ValueError):
    """The file is not a BikeReg entries export the importer can read."""


@dataclass(frozen=True, slots=True)
class ImportRow:
    """One registration, cleaned. ``line`` is the 1-based CSV line."""

    first: str
    last: str
    bib: int | None = None
    usac_license: str | None = None
    uci_id: str | None = None
    racing_age: int | None = None
    birth_year: int | None = None
    local_group: str | None = None
    category: str | None = None
    line: int = 0
    # The USAC License cell as written when it is not a number
    # ("INTL-CAN"), so the preview can say why the license is blank.
    license_text: str | None = None
    # The Bib cell as written when it is not a bib (0, -4, 1e30, a
    # 20-digit number), so the preview can say why the bib is blank.
    bib_text: str | None = None

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()


@dataclass(slots=True)
class ImportPlan:
    """What applying one row would do. The preview edits ``bib`` and ``group``.

    action is "new" (no rider matched), "match" (a rider matched and the
    row adds nothing) or "update" (a rider matched and ``changes`` lists
    the fields the row would change, as field: (old, new)). matched_by
    is "license", "uci", "name", or "chosen" when the scorer picked the
    rider in the preview.

    A change is a fill when the database has no value there, and a
    difference when both have one: a fill is applied as it stands, since
    a blank is not a disagreement, and a difference is never applied
    until the scorer settles it. ``resolved`` holds
    the value chosen for each difference, the database's or the file's.
    """

    row: ImportRow
    action: str
    rider_id: int | None = None
    matched_by: str | None = None
    changes: dict[str, tuple[object, object]] = field(default_factory=dict)
    bib: int | None = None
    group: str | None = None
    already_entered: bool = False
    note: str = ""
    # Riders on file who may be this person, offered in the preview's
    # Action cell; empty for a row matched with certainty.
    candidates: list[Candidate] = field(default_factory=list)
    # An id on the row that is on file for another rider, or a rider the
    # file gives two ids; the preview leaves such a row unticked.
    conflict: str = ""
    resolved: dict[str, object] | None = None
    # A later row of a rider whose rows in the file disagree on the group
    # or the bib: the preview starts it unticked, so the scorer picks
    # which registration is tonight's rather than the last row winning.
    start_unticked: bool = False
    # A new row with a rider on file of the same name: it starts unticked,
    # like a conflict, until the scorer picks the rider or says New.
    possible_match: bool = False
    # The scorer chose New in the Status list, which answers that question.
    chosen_new: bool = False

    @property
    def fills(self) -> dict[str, tuple[object, object]]:
        return {name: pair for name, pair in self.changes.items() if is_unset(pair[0])}

    @property
    def disputes(self) -> dict[str, tuple[object, object]]:
        return {name: pair for name, pair in self.changes.items() if not is_unset(pair[0])}

    @property
    def status(self) -> str:
        """What the preview calls the row: one of STATUS_TEXT's keys.

        A conflict is named first, since the row starts unticked for it,
        whatever else it would do.
        """
        if self.conflict:
            return "conflict"
        if self.rider_id is None:
            return "check" if self.possible_match else "new"
        if self.disputes:
            return "review"
        return "update" if self.fills else "on_file"

    @property
    def needs_review(self) -> bool:
        """A matched row with a difference not yet settled."""
        return self.rider_id is not None and bool(self.disputes) and self.resolved is None

    def fields(self) -> dict[str, object]:
        """The rider columns applying the row writes: the fills, and each difference as settled."""
        out = {name: new for name, (_old, new) in self.fills.items()}
        for name, (old, _new) in self.disputes.items():
            value = (self.resolved or {}).get(name, old)
            if value != old:
                out[name] = value
        return out

    @property
    def differences(self) -> list[str]:
        out = []
        for name, (old, new) in self.changes.items():
            label = _FIELD_LABELS[name]
            if is_unset(old):
                out.append(f"{label}: {_show(old)} -> {_show(new)}")
            elif self.resolved is None:
                out.append(f"{label}: {_show(old)} or {_show(new)}")
            elif self.resolved.get(name, old) == old:
                out.append(f"{label}: {_show(old)} kept")
            else:
                out.append(f"{label}: {_show(old)} -> {_show(new)}")
        return out


# The preview's word for each status, in the order the count line names them.
STATUS_TEXT = {
    "new": "New",
    "check": "New?",
    "on_file": "On file",
    "update": "Update",
    "review": "Review",
    "conflict": "Conflict",
}


class UnreviewedError(ValueError):
    """A ticked row's differences were not settled before applying."""


@dataclass(slots=True)
class ImportResult:
    created: list[int] = field(default_factory=list)
    updated: list[int] = field(default_factory=list)
    entered: list[tuple[int, int | None]] = field(default_factory=list)
    adjusted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    # Riders this import put on or kept on the roster who still have no bib.
    no_bib: int = 0
    # False for an import that only kept the riders, with no event's roster.
    event: bool = True

    def summary(self) -> str:
        created, updated = len(self.created), len(self.updated)
        parts = [
            f"{created} new rider{'' if created == 1 else 's'}",
            f"{updated} rider{'' if updated == 1 else 's'} updated",
        ]
        if self.event:
            parts.append(f"{len(self.entered)} on the event's roster")
        text = ", ".join(parts) + "."
        if self.adjusted:
            text += f" {len(self.adjusted)} adjusted."
        if self.skipped:
            text += f" {len(self.skipped)} skipped."
        if self.no_bib:
            text += (
                " 1 rider has no bib yet."
                if self.no_bib == 1
                else f" {self.no_bib} riders have no bib yet."
            )
        return text


_FIELD_LABELS = {
    "first_name": "first name",
    "last_name": "last name",
    "usac_license": USAC_LICENSE,
    "uci_id": UCI_ID,
    "birth_year": "birth year",
}


def _show(value: object) -> str:
    return "none" if is_unset(value) else str(value)


# ----- parse -----------------------------------------------------------------


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _digits(value: str | None, *, license: bool = False) -> str | None:
    """Licenses and UCI IDs are stored as digit strings: a UCI ID is too long
    to trust to a spreadsheet's number format, and its leading zeros are
    part of it (it is always 11 digits). Anything else ("INTL-CAN",
    "pending") is not an id.

    A USAC License is spelled by ``inputs.usac_license``, the same
    function the store applies to a typed one, so "0710004" in the file
    finds the 710004 on file.
    """
    value = _clean(value)
    if value is None:
        return None
    compact = value.replace(" ", "")
    if not is_ascii_digits(compact):
        return None
    if license:
        return usac_license(compact)
    return compact


def _int(value: str | None, low: int, high: int) -> int | None:
    """A whole number in low..high, else None.

    Through float, because Excel writes 7 as "7.0"; "inf", "1e400" and a
    20-digit bib are no number a rider wears or is aged, so they read as
    blank rather than overflow SQLite's integer on Apply.
    """
    value = _clean(value)
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if not low <= number <= high:
        return None
    return int(number)


def derive_group(category: str | None) -> str | None:
    """The local group from a BikeReg entry category.

    Some venues' categories put the venue group in the last parentheses,
    "Cat 1/2/3 (Group A)". Age-banded categories put an age note there
    instead, "Young Juniors (14 and under)", and the group is the text
    before it; an age note is recognized by starting with a digit.
    """
    category = _clean(category)
    if category is None:
        return None
    match = re.search(r"\(([^()]*)\)[^()]*$", category)
    if match is None:
        return category
    inner = match.group(1).strip()
    if inner and not inner[0].isdigit():
        return inner
    before = category[: match.start()].strip()
    return before or inner or None


def _header_year(header: str) -> int | None:
    match = re.search(r"(\d{4})\s*$", header)
    return int(match.group(1)) if match else None


NOT_CSV = "not a CSV file. If it is an Excel workbook, save it as CSV first."
NOT_BIKEREG = "not a BikeReg entries export (no Last Name / First Name columns)"
# Far past any entries export: a file this big is something else, refused
# before it is read into memory.
MAX_BYTES = 20 * 1024 * 1024
TOO_BIG = "it is larger than 20 MB, so it is not an entries export"
# A racing age the importer believes; outside it the age is left blank.
AGE_RANGE = (1, 120)
# Longer than any real name: a cell this long, or one with a line break
# in it, is a quote that was never closed swallowing the rows after it.
NAME_MAX = 100


def _runaway(line_no: int) -> ImportFormatError:
    return ImportFormatError(
        f"line {line_no} has a name with a line break in it or over {NAME_MAX} characters."
        " A quote mark in the file is probably not closed, which joins the rows after it"
        " into one. Fix that line and import again"
    )


def _decode(raw: bytes) -> str:
    """The text of an export, whatever saved it last.

    BikeReg writes UTF-8, but the file often passes through Excel on the
    way: "Unicode Text" is UTF-16 (with a BOM, or without one and full
    of NUL bytes), plain "CSV" on Windows is cp1252 unless told
    otherwise, and a workbook renamed to .csv is a zip, which starts
    with PK.
    """
    if raw.startswith(b"PK"):
        raise ImportFormatError(NOT_CSV)
    try:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16")
        if b"\x00" in raw[:1024]:
            # No BOM: ASCII text carries its NUL in the high byte, which
            # comes second in little-endian.
            return raw.decode("utf-16-le" if raw[1:2] == b"\x00" else "utf-16-be")
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            # cp1252 leaves five bytes undefined; one stray byte in a name
            # is a "?" there, not a file refused as not CSV.
            return raw.decode("cp1252", errors="replace")
    except UnicodeDecodeError:
        raise ImportFormatError(NOT_CSV) from None


def _delimiter(header_line: str) -> str:
    """Comma, or the semicolon or tab an export was saved with.

    Excel in a locale whose decimal mark is a comma saves "CSV" with
    semicolons, and "Text (Tab delimited)" uses tabs. The header line is
    enough to tell; anything the sniffer cannot place is read as comma.
    Only the delimiter is taken from it: from one line the sniffer also
    guesses that quotes are never doubled, which would misread a quoted
    note further down.
    """
    try:
        return csv.Sniffer().sniff(header_line, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def _read_text(text_or_path: str | os.PathLike[str]) -> str:
    # A str with a line break is CSV text; any other str or a PathLike is a
    # path. Checking for the line break first means a one-line string that
    # happens to name a file is never mistaken for data, and vice versa.
    if isinstance(text_or_path, os.PathLike) or (
        isinstance(text_or_path, str) and "\n" not in text_or_path and os.path.isfile(text_or_path)
    ):
        path = Path(text_or_path)
        if path.stat().st_size > MAX_BYTES:
            raise ImportFormatError(TOO_BIG)
        text = _decode(path.read_bytes())
    else:
        text = str(text_or_path)
    return text.lstrip("﻿")


def parse(text_or_path: str | os.PathLike[str]) -> list[ImportRow]:
    """Rows of a BikeReg entries export, in file order. Rows with no name are dropped."""
    text = _read_text(text_or_path)
    lines = text.splitlines()
    reader = csv.reader(
        io.StringIO(text, newline=""), delimiter=_delimiter(lines[0] if lines else "")
    )
    try:
        header = next(reader)
    except StopIteration:
        raise ImportFormatError("the file is empty") from None
    except csv.Error:
        raise ImportFormatError(NOT_CSV) from None
    names = [h.strip().lstrip("﻿") for h in header]
    if any(c not in names for c in REQUIRED_COLUMNS):
        raise ImportFormatError(NOT_BIKEREG)
    index = {name: i for i, name in enumerate(names)}
    age_header = next((n for n in names if n.startswith(AGE_PREFIX)), None)
    season = _header_year(age_header) if age_header else None

    rows: list[ImportRow] = []
    try:
        for line_no, values in _records(reader):
            row = _row(values, index, age_header, season, line_no)
            if row is not None:
                rows.append(row)
    except csv.Error:
        # The csv module's field limit (128 KB): a binary file, or a quote
        # left open to the end of the file.
        raise ImportFormatError(NOT_CSV) from None
    return rows


def _records(reader) -> Iterable[tuple[int, list[str]]]:
    """Each record with the line it starts on, which a quoted line break moves on from."""
    start = reader.line_num + 1
    for values in reader:
        yield start, values
        start = reader.line_num + 1


def _row(
    values: list[str],
    index: dict[str, int],
    age_header: str | None,
    season: int | None,
    line_no: int,
) -> ImportRow | None:
    def col(name: str | None, _values: list[str] = values) -> str | None:
        if name is None or name not in index or index[name] >= len(_values):
            return None
        return _values[index[name]]

    raw_names = (col("First Name") or "", col("Last Name") or "")
    if any("\n" in n or "\r" in n or len(n) > NAME_MAX for n in raw_names):
        raise _runaway(line_no)
    first, last = ("" if is_blank(n) else clean_line(n) for n in raw_names)
    if not first and not last:
        return None
    usac = _digits(col("USAC License"), license=True)
    license_text = None if usac is not None else _clean(col("USAC License"))
    uci = _digits(col("UCI Code"))
    if uci is None and usac is None:
        # With no numeric USAC License, the unique number is the UCI one.
        uci = _digits(col("Unique License Number (UCI or USAC)"))
    age = _int(col(age_header), *AGE_RANGE)
    # Out of range (0, a negative, 1e30) is no bib, as a blank is.
    bib = _int(col("Bib"), 1, BIB_MAX)
    bib_cell = _clean(col("Bib"))
    category = _clean(col("Category"))
    return ImportRow(
        first=first,
        last=last,
        bib=bib,
        usac_license=usac,
        uci_id=uci,
        racing_age=age,
        # USAC 1C1: racing age is the age on December 31 of the
        # season, so it is the season year minus the birth year.
        birth_year=season - age if season is not None and age is not None else None,
        local_group=derive_group(category),
        category=category,
        line=line_no,
        license_text=license_text,
        bib_text=clean_line(bib_cell, 20) if bib is None and bib_cell else None,
    )


# ----- plan ------------------------------------------------------------------


def _name_key(first: str, last: str) -> tuple[str, str]:
    return (first.strip().casefold(), last.strip().casefold())


def _years_apart(a: int | None, b: int | None) -> bool:
    return a is not None and b is not None and abs(a - b) > 1


def _years_close(a: int | None, b: int | None) -> bool:
    """Both known and within the tolerance ``_years_apart`` allows."""
    return a is not None and b is not None and abs(a - b) <= 1


class _Context:
    """What a plan is checked against: the riders on file and the event's roster.

    With no event (event_id None) the import only keeps the riders: there
    is no roster to match bibs and groups against.
    """

    def __init__(self, store: Store, event_id: int | None):
        if event_id is not None:
            store.event(event_id)
        self.riders = store.riders()
        self.index = RiderIndex(self.riders)
        self.by_id = {r.rider_id: r for r in self.riders}
        self.by_license = {r.usac_license: r for r in self.riders if r.usac_license}
        self.by_uci = {r.uci_id: r for r in self.riders if r.uci_id}
        self.by_name: dict[tuple[str, str], list[Rider]] = {}
        for r in self.riders:
            self.by_name.setdefault(_name_key(r.first_name, r.last_name), []).append(r)
        entries = store.entries(event_id) if event_id is not None else []
        self.entries = {e.rider_id: e for e in entries}
        # One spelling per group: the event's first, then the file's first.
        spellings = event_spellings(store, event_id) if event_id is not None else []
        self.spellings = {group_key(g): g for g in spellings}

    def match(self, row: ImportRow) -> tuple[Rider | None, str | None]:
        """The rider this row certainly is, and how that is known.

        A name alone matches only when nothing on either side could tell
        two people apart: the USAC Licenses agree or the rider has none,
        the same for the UCI IDs, and the birth years are within a year or
        one is unknown. A stored id the row lacks needs both birth years
        known and within a year. A name several riders share, or birth
        years far apart, is left for the scorer to decide among the
        candidates.
        """
        found = None
        if row.usac_license and row.usac_license in self.by_license:
            found, how = self.by_license[row.usac_license], "license"
        elif row.uci_id and row.uci_id in self.by_uci:
            found, how = self.by_uci[row.uci_id], "uci"
        if found is not None:
            # A swapped name is offered as a candidate, never enough to
            # believe an id: the review would then rename the holder.
            if rank(row.first, row.last, row.birth_year, found) not in (None, SWAPPED_NAME):
                return found, how
            # The id is on file for someone whose name is nothing like
            # the row's: a mistyped number or a reissued one. If the name
            # is plainly one other rider's, the row is that rider;
            # otherwise it is a new rider. Either way _settle flags the
            # id, since taking the id at its word would rename the holder.
            named = [
                c.rider
                for c in self.index.candidates(
                    row.first, row.last, None, exclude=[found.rider_id], limit=None
                )
                if c.rank == SAME_NAME
            ]
            return (named[0], "name") if len(named) == 1 else (None, None)
        named = self.by_name.get(_name_key(row.first, row.last), [])
        # Both ids alike. One that differs from the row's tells two people
        # apart. A stored id the row lacks is a blank, which is never a
        # disagreement, so it stands aside when both birth years are known
        # and agree (the rider keeps the id). With either year unknown it
        # still says two people: a namesake junior with no license and a
        # licensed parent would otherwise be one rider.
        for name in ("usac_license", "uci_id"):
            value = getattr(row, name)
            if value:
                named = [r for r in named if getattr(r, name) in (None, value)]
            else:
                named = [
                    r
                    for r in named
                    if not getattr(r, name) or _years_close(row.birth_year, r.birth_year)
                ]
        # A late birthday can put the season's racing age a year off, so
        # only a wider gap says two people; a father and son share names.
        named = [r for r in named if not _years_apart(row.birth_year, r.birth_year)]
        if len(named) == 1:
            return named[0], "name"
        return None, None

    def name(self, rider_id: int) -> str:
        return self.by_id[rider_id].name


def plan_import(store: Store, event_id: int | None, rows: Sequence[ImportRow]) -> list[ImportPlan]:
    """Decide, per row, which rider it is and what bib and group it would get.

    Matching order is USAC License, then UCI ID, then exact first and last
    name ignoring case, with the guards in ``_Context.match``. A row that matches nobody
    carries the riders who may be the same person as ``candidates``
    (control/riders.py) and stays a new rider unless the scorer chooses
    one: a merge the scorer never saw is two people's results under one
    name.
    """
    ctx = _Context(store, event_id)
    plans: list[ImportPlan] = []
    for row in rows:
        rider, matched_by = ctx.match(row)
        entry = ctx.entries.get(rider.rider_id) if rider is not None else None
        bib = entry.bib if entry is not None and entry.bib is not None else row.bib

        group = row.local_group
        if entry is not None and entry.local_group:
            group = entry.local_group
        else:
            if group is None and rider is not None:
                # The same suggestion Choose Riders makes: the group they had
                # at their most recent event.
                last = store.last_entry(rider.rider_id)
                group = last.local_group if last is not None else None
            group = _spell(group, ctx.spellings) or None

        offered = []
        if rider is None:
            offered = ctx.index.candidates(row.first, row.last, row.birth_year)
        plans.append(
            ImportPlan(
                row=row,
                action="new",
                rider_id=None if rider is None else rider.rider_id,
                matched_by=matched_by,
                bib=bib,
                group=group,
                already_entered=entry is not None,
                candidates=offered,
            )
        )
    _settle(ctx, plans)
    return plans


def choose(
    store: Store,
    event_id: int | None,
    plans: Sequence[ImportPlan],
    index: int,
    rider_id: int | None,
) -> list[ImportPlan]:
    """The plans with row ``index`` made the scorer's choice: a rider on file, or None for new.

    Every row is settled again, since a choice can make or clear a
    conflict on another row (two rows that are now one rider).
    """
    ctx = _Context(store, event_id)
    plans = [replace(p, candidates=list(p.candidates), changes=dict(p.changes)) for p in plans]
    plan = plans[index]
    plan.rider_id = rider_id
    plan.chosen_new = rider_id is None
    plan.resolved = None
    plan.matched_by = None if rider_id is None else "chosen"
    entry = ctx.entries.get(rider_id) if rider_id is not None else None
    plan.already_entered = entry is not None
    if entry is not None and entry.bib is not None:
        # On tonight's roster already: the number on their back is that one.
        plan.bib = entry.bib
        plan.group = entry.local_group or plan.group
    _settle(ctx, plans)
    return plans


_IDS = (("usac_license", USAC_LICENSE, "by_license"), ("uci_id", UCI_ID, "by_uci"))


def _settle(ctx: _Context, plans: list[ImportPlan]) -> None:
    """Changes, conflicts, action and note of every plan, from its rider as it stands.

    An id the row brings that is on file for someone else is a
    conflict, never a silent skip: it may be a typo, a reissued
    license, or two records of one person, and only the scorer can
    tell. The change is left out, so a row ticked anyway applies as a
    plain match. The same goes for an id two rows of the file give to
    two people, eg: a parent registering two children on one license.
    """
    rows_of = _rows_of_rider(plans)
    first_with = _first_with_id(plans)
    number = {id(plan): i for i, plan in enumerate(plans, 1)}
    namesakes = _new_by_name(plans)
    seen: set[int] = set()
    for plan in plans:
        rider = ctx.by_id.get(plan.rider_id) if plan.rider_id is not None else None
        if rider is not None:
            changes, registered = _changes(plan, rider)
            conflicts = _match_conflicts(ctx, plan, rider, rows_of[rider.rider_id], changes)
            named: set[int] = set()
        else:
            changes, registered = {}, ""
            conflicts, named = _new_conflicts(ctx, plan)
        conflicts += _file_id_conflicts(ctx, plan, first_with, changes)
        notes = _row_notes(plan, rider)
        plan.start_unticked = False
        plan.possible_match = False
        if rider is None:
            notes += _new_notes(plan, named, namesakes, number)
        else:
            notes += _match_notes(
                ctx, plan, rider, registered, rows_of[rider.rider_id], number, seen
            )
        if changes != plan.changes:
            # Settled against other values, a choice no longer answers them.
            plan.resolved = None
        plan.changes = changes
        plan.conflict = "; ".join(conflicts)
        plan.note = "; ".join(notes)
        plan.action = "new" if rider is None else ("update" if changes else "match")


def _rows_of_rider(plans: list[ImportPlan]) -> dict[int, list[ImportPlan]]:
    """The rows of each matched rider, in file order."""
    rows_of: dict[int, list[ImportPlan]] = {}
    for plan in plans:
        if plan.rider_id is not None:
            rows_of.setdefault(plan.rider_id, []).append(plan)
    return rows_of


def _first_with_id(plans: list[ImportPlan]) -> dict[tuple[str, str], ImportPlan]:
    """The first row to give each id.

    A later row giving the id to someone else is a conflict on that later row.
    """
    first_with: dict[tuple[str, str], ImportPlan] = {}
    for plan in plans:
        for name, _label, _index in _IDS:
            value = getattr(plan.row, name)
            if value:
                first_with.setdefault((name, value), plan)
    return first_with


def _changes(plan: ImportPlan, rider: Rider) -> tuple[dict[str, tuple[object, object]], str]:
    """The fields the row would change on its rider, and the first name it registered under.

    The registered name is set when a rider matched by id registered
    under another form of the first name on file, and is "" otherwise.
    """
    row = plan.row
    changes: dict[str, tuple[object, object]] = {}
    registered = ""
    wanted = {
        "first_name": row.first,
        "last_name": row.last,
        "usac_license": row.usac_license,
        "uci_id": row.uci_id,
        "birth_year": row.birth_year,
    }
    for name, new in wanted.items():
        old = getattr(rider, name)
        # A blank in the export never erases what the database knows.
        if new is None or new == "" or new == old:
            continue
        if name in _NAMES and isinstance(old, str) and new.casefold() == old.casefold():
            # Case alone is never news ("tomas galloway" is a rider
            # typing fast), so the record keeps its capitals.
            continue
        if name == "first_name" and _informal(plan.matched_by, old, new):
            registered = new
            continue
        changes[name] = (old, new)
    return changes, registered


def _match_conflicts(
    ctx: _Context,
    plan: ImportPlan,
    rider: Rider,
    rows: list[ImportPlan],
    changes: dict[str, tuple[object, object]],
) -> list[str]:
    """A matched row's ids that are on file for another rider, or that its rider's rows disagree on.

    The id's change is dropped from ``changes`` for each conflict.
    """
    row = plan.row
    conflicts: list[str] = []
    for name, label, index in _IDS:
        value = getattr(row, name)
        holder = getattr(ctx, index).get(value) if value else None
        if holder is not None and holder.rider_id != rider.rider_id:
            conflicts.append(f"{label} {value} is on file for {ctx.name(holder.rider_id)}")
            changes.pop(name, None)
            # Either rider may be the one meant; both are offered.
            _offer(plan, rider)
            _offer(plan, holder)
        given = sorted({getattr(p.row, name) for p in rows} - {None})
        if len(given) > 1:
            conflicts.append(
                f"the file gives {ctx.name(rider.rider_id)} two {label}s ({', '.join(given)})"
            )
            changes.pop(name, None)
    return conflicts


def _new_conflicts(ctx: _Context, plan: ImportPlan) -> tuple[list[str], set[int]]:
    """A new row's ids on file for someone, and a possible match on tonight's roster.

    Also returns the riders a conflict already names, so the note does
    not name them again.
    """
    row = plan.row
    conflicts: list[str] = []
    named: set[int] = set()
    for name, label, index in _IDS:
        value = getattr(row, name)
        holder = getattr(ctx, index).get(value) if value else None
        if holder is not None:
            # Only a row whose name is nothing like the holder's
            # gets here; the holder is offered, never assumed.
            conflicts.append(f"{label} {value} is on file for {ctx.name(holder.rider_id)}")
            _offer(plan, holder)
            named.add(holder.rider_id)
    entered = [
        c.rider
        for c in plan.candidates
        if c.rider.rider_id in ctx.entries
        # Asked of the name itself: an id holder is offered with
        # SAME_NAME rank, though its name is nothing like the row's.
        and rank(row.first, row.last, None, c.rider) == SAME_NAME
    ]
    if entered:
        # Tonight's roster is where a duplicate hurts most: the
        # same person twice in one field, scored as two riders.
        bib = ctx.entries[entered[0].rider_id].bib
        conflicts.append(
            "possible match already on this roster "
            + ("with no bib yet" if bib is None else f"with bib {bib}")
        )
    return conflicts, named


def _file_id_conflicts(
    ctx: _Context,
    plan: ImportPlan,
    first_with: dict[tuple[str, str], ImportPlan],
    changes: dict[str, tuple[object, object]],
) -> list[str]:
    """Ids no rider has on file that an earlier row of the file gives to someone else.

    The id's change is dropped from ``changes`` for each conflict.
    """
    row = plan.row
    conflicts: list[str] = []
    for name, label, index in _IDS:
        value = getattr(row, name)
        if not value or getattr(ctx, index).get(value) is not None:
            # An id on file is answered by _match_conflicts or
            # _new_conflicts, against its holder.
            continue
        first = first_with[(name, value)]
        if first is not plan and (first.rider_id is None or first.rider_id != plan.rider_id):
            conflicts.append(f"the file gives {label} {value} to {first.row.name} too")
            changes.pop(name, None)
    return conflicts


def _row_notes(plan: ImportPlan, rider: Rider | None) -> list[str]:
    """Notes on the row's own cells: a UCI ID that is the only id, and a bib that is not one."""
    row = plan.row
    notes: list[str] = []
    if row.usac_license is None and row.uci_id:
        # The UCI ID is this rider's only id; say so, so a blank
        # license column does not read as a missing number.
        written = f" ({row.license_text})" if row.license_text else ""
        if plan.matched_by == "uci":
            how = f"matched by {UCI_ID} {row.uci_id}"
        elif rider is None:
            how = f"created with {UCI_ID} {row.uci_id}"
        else:
            how = f"{UCI_ID} {row.uci_id}"
        notes.append(f"no {USAC_LICENSE}{written}; {how}")
    if row.bib_text:
        notes.append(f'A bib is a number from 1 to {BIB_MAX}; the file has "{row.bib_text}"')
    return notes


def _new_notes(
    plan: ImportPlan,
    named: set[int],
    namesakes: dict[tuple[str, str], list[ImportPlan]],
    number: dict[int, int],
) -> list[str]:
    """A new row's possible matches and file twins; sets whether it waits for the scorer."""
    row = plan.row
    notes: list[str] = []
    # Named here, since the closed Status list hides them and
    # judging the names side by side is the point of the preview.
    maybe = [c for c in plan.candidates if c.rider.rider_id not in named]
    if maybe:
        notes.append("may be " + _or_list([c.who for c in maybe]))
    # A rider on file with this very name is the case a ticked
    # default would turn into a duplicate (a renewed license, a blank
    # one this week), so the row waits for the scorer, as a
    # conflict does. An initial or a birth year alone is too weak
    # a hint to hold a row for. Asked of the name itself, as for
    # a conflict in _new_conflicts.
    plan.possible_match = not plan.chosen_new and any(
        rank(row.first, row.last, None, c.rider) == SAME_NAME for c in maybe
    )
    plan.start_unticked = plan.possible_match
    notes += _file_twins(plan, namesakes, number)
    return notes


def _match_notes(
    ctx: _Context,
    plan: ImportPlan,
    rider: Rider,
    registered: str,
    rows: list[ImportPlan],
    number: dict[int, int],
    seen: set[int],
) -> list[str]:
    """A matched row's notes against the roster and the rider's other rows.

    Sets whether the row waits for the scorer and adds the rider to
    ``seen``, the riders an earlier row matched.
    """
    row = plan.row
    notes: list[str] = []
    if registered:
        # An id match is the authority on who this is, and the
        # name on file is the one in the results; a nickname or a
        # middle initial typed this week changes neither.
        notes.append(f"registered as {registered}")
    entry = ctx.entries.get(rider.rider_id) if plan.already_entered else None
    if entry is not None:
        # The roster's values stand; the file's are said, so a
        # re-import for a corrected category shows why nothing moved.
        if entry.bib is not None and row.bib is not None and row.bib != entry.bib:
            notes.append(f"file says bib {row.bib} (roster has {entry.bib})")
        spelled = _spell(row.local_group, ctx.spellings)
        if entry.local_group and spelled and group_key(spelled) != group_key(entry.local_group):
            notes.append(f"file says {spelled} (roster has {entry.local_group})")
    if rider.rider_id in seen:
        notes.append("same rider as an earlier row")
    disagree = _registrations(ctx, plan, rows, number)
    notes += disagree
    # The first row stays ticked; each later one waits for the scorer.
    plan.start_unticked = bool(disagree) and rider.rider_id in seen
    seen.add(rider.rider_id)
    return notes


_NAMES = ("first_name", "last_name")


def _informal(matched_by: str | None, old: object, new: str) -> bool:
    """A first name on an id match that is only another form of the one on file.

    "Mario" for Marius, "Nora M." for Nora: a rider who registers that
    way does so every week, and a Review each time asks the same
    question again (picking the file's side one week flips the name). A
    different initial may be a wrong record, so that still goes to Review,
    as do last names, ids and birth years.
    """
    if matched_by not in ("license", "uci") or not isinstance(old, str):
        return False
    mine, theirs = first_key(old), first_key(new)
    return bool(mine and theirs) and mine[0] == theirs[0]


def _or_list(items: list[str]) -> str:
    """``A``, ``A or B``, ``A, B, or C``."""
    if len(items) <= 2:
        return " or ".join(items)
    return f"{', '.join(items[:-1])}, or {items[-1]}"


def _registrations(
    ctx: _Context, plan: ImportPlan, rows: list[ImportPlan], number: dict[int, int]
) -> list[str]:
    """This rider's other rows that give another group or bib, one note each.

    A rider in two categories is the venue's call (which races tonight),
    so no row wins silently by coming last.
    """
    row = plan.row
    mine = _spell(row.local_group, ctx.spellings)
    out = []
    for other in rows:
        if other is plan:
            continue
        theirs = _spell(other.row.local_group, ctx.spellings)
        parts = []
        if mine and theirs and group_key(mine) != group_key(theirs):
            parts.append(f"as {theirs}")
        if row.bib is not None and other.row.bib is not None and row.bib != other.row.bib:
            parts.append(f"with bib {other.row.bib}")
        if parts:
            out.append(f"also registered {' '.join(parts)} (row {number[id(other)]})")
    return out


def _new_by_name(plans: list[ImportPlan]) -> dict[tuple[str, str], list[ImportPlan]]:
    """The new rows by name key, in file order.

    Two rows are SAME_NAME only when their name keys are equal and whole,
    so each row is compared with its own key's rows rather than the whole
    file: 300 rows would be 45,000 pairs.
    """
    out: dict[tuple[str, str], list[ImportPlan]] = {}
    for plan in plans:
        if plan.rider_id is None:
            out.setdefault(name_key(plan.row.first, plan.row.last), []).append(plan)
    return out


def _file_twins(
    plan: ImportPlan,
    namesakes: dict[tuple[str, str], list[ImportPlan]],
    number: dict[int, int],
) -> list[str]:
    """Other new rows with this new row's name: one person about to become two riders.

    Both rows stay ticked, since twins and namesakes exist; the note is
    there so the scorer looks. A pair whose ids differ, or whose birth
    years are far apart, is two people by the rule a name match uses.
    """
    row = plan.row
    out = []
    for other in namesakes.get(name_key(row.first, row.last), []):
        if other is plan or other.rider_id is not None:
            continue
        o = other.row
        if any(
            getattr(row, name) and getattr(o, name) and getattr(row, name) != getattr(o, name)
            for name, _label, _index in _IDS
        ):
            continue
        if _years_apart(row.birth_year, o.birth_year):
            continue
        if rank_names(row.first, row.last, None, o.first, o.last, None) == SAME_NAME:
            out.append(f"looks like row {number[id(other)]}, {o.name}")
    return out


def _offer(plan: ImportPlan, rider: Rider) -> None:
    if all(c.rider.rider_id != rider.rider_id for c in plan.candidates):
        plan.candidates.append(Candidate(rider, SAME_NAME))


def _spell(group: str | None, spellings: dict[str, str]) -> str:
    tidy = " ".join((group or "").split())
    key = group_key(tidy)
    if not key:
        return ""
    return spellings.setdefault(key, tidy)


# ----- apply -----------------------------------------------------------------


def apply_import(
    store: Store, event_id: int | None, plans: Sequence[ImportPlan], chosen: Iterable[int]
) -> ImportResult:
    """Write the chosen plans (indexes into ``plans``) as one write: every row, or none.

    One transaction: one commit for the file rather than one per rider,
    roster entry and race joined (up to 144 for 60 rows, each an fsync),
    and a failure partway (a refusal the rows below cannot settle, a
    disk error) raises with nothing written, so the scorer fixes the
    cause and imports the same file again.

    A license that turns out to be another rider's is kept off and
    reported in ``adjusted``; so is a new rider whose id is on file
    by the time the row is written (a conflict ticked anyway, or an
    earlier row of this file), who is added without that id.
    A row without a bib goes on the roster without one; the count is in
    ``no_bib``. A new bib for a rider already in a race is refused when
    another rider in that race wears it, keeping the old one, and
    reported in ``skipped``. With no event (event_id None) the riders are
    kept and nobody is put on a roster.
    """
    if event_id is not None:
        store.event(event_id)
    # Checked before anything is written: a half-applied import would
    # leave the rows before the unsettled one in and the rest out.
    for i in sorted(set(chosen)):
        if plans[i].needs_review:
            raise UnreviewedError(f"{plans[i].row.name}: review the differences first")
    result = ImportResult(event=event_id is not None)
    joining = _Joining(store, event_id)
    with store.transaction():
        for i in sorted(set(chosen)):
            plan = plans[i]
            row = plan.row
            rider_id = plan.rider_id
            license_id, uci_id = row.usac_license, row.uci_id
            withheld: list[str] = []
            if rider_id is None:
                # The plan said New and the scorer ticked New, so an id found
                # on file now (a conflict ticked anyway, or an earlier row of
                # this file that took it) stays with its holder: the row is a
                # new person, never folded into someone else's record.
                if license_id and store.find_rider_by_license(license_id) is not None:
                    withheld.append(f"{USAC_LICENSE} {license_id}")
                    license_id = None
                if uci_id and store.find_rider_by_uci(uci_id) is not None:
                    withheld.append(f"{UCI_ID} {uci_id}")
                    uci_id = None
            if plan.bib is not None and plan.bib < 1:
                result.skipped.append(f"{row.name} left out; bib {plan.bib}")
                continue
            if rider_id is None:
                rider_id = store.add_rider(
                    row.first,
                    row.last,
                    usac_license=license_id,
                    uci_id=uci_id,
                    birth_year=row.birth_year,
                ).rider_id
                result.created.append(rider_id)
                if withheld:
                    result.adjusted.append(
                        f"{row.name} added without {' or '.join(withheld)}; "
                        "it is on file for another rider"
                    )
            elif plan.action == "update" and plan.fields():
                fields = plan.fields()
                try:
                    store.update_rider(rider_id, **fields)
                except DuplicateError:
                    # An id another rider took since the plan was made
                    # stays with its holder; the rest of the row applies.
                    kept: list[tuple[str, str]] = []
                    for name, label, _index in _IDS:
                        value = fields.get(name)
                        holder = _holder(store, name, value) if value else None
                        if holder is not None and holder.rider_id != rider_id:
                            fields.pop(name)
                            kept.append((label, str(value)))
                    if fields:
                        store.update_rider(rider_id, **fields)
                    for label, value in kept:
                        result.adjusted.append(
                            f"{row.name} kept the old {label}; {value} belongs to another rider"
                        )
                result.updated.append(rider_id)

            if event_id is not None:
                _enter(store, event_id, rider_id, plan, result, joining)
        joining.flush()
    return result


def _holder(store: Store, name: str, value: object) -> Rider | None:
    """The rider on file with this id, by the column's own lookup."""
    if name == "usac_license":
        return store.find_rider_by_license(str(value))
    return store.find_rider_by_uci(str(value))


class _Joining:
    """Riders put on the roster whose group's races they have yet to join.

    ``follow_group`` reads the event's roster and every group race's
    field; called once per new entry, that would be 0.47 s of a 300-row
    import. A rider's own joins depend only on their own entry and their
    own place in each field, so the new entries wait and join together.
    They join before anything that reads the fields (a bib checked
    against a race, an entry already on the roster), and before a
    rider waiting here is seen again, so every check sees the fields
    as joining one at a time left them.
    """

    def __init__(self, store: Store, event_id: int | None):
        self.store = store
        self.event_id = event_id
        self.riders: list[int] = []

    def add(self, rider_id: int) -> None:
        self.riders.append(rider_id)

    def flush(self) -> None:
        if self.riders and self.event_id is not None:
            follow_group(self.store, self.event_id, self.riders)
        self.riders = []


def _entry_or_none(store: Store, event_id: int, rider_id: int):
    try:
        return store.entry(event_id, rider_id)
    except NotFoundError:
        return None


def _enter(
    store: Store,
    event_id: int,
    rider_id: int,
    plan: ImportPlan,
    result: ImportResult,
    joining: _Joining,
):
    row = plan.row
    entry = _entry_or_none(store, event_id, rider_id)
    group = plan.group or None
    if entry is not None:
        joining.flush()
        bib = entry.bib
        if plan.bib is not None and plan.bib != entry.bib:
            problem = roster_bib_refusal(store, event_id, rider_id, plan.bib)
            if problem:
                kept = "no bib" if entry.bib is None else f"bib {entry.bib}"
                result.skipped.append(f"{row.name} keeps {kept}; {problem}")
            else:
                bib = store.change_bib(event_id, rider_id, plan.bib).bib
        if group != entry.local_group:
            store.set_entry_group(event_id, rider_id, group)
            follow_group(store, event_id, [rider_id], entry.local_group)
        if bib is None:
            result.no_bib += 1
        return
    store.add_entry(event_id, rider_id, plan.bib, local_group=group or "")
    joining.add(rider_id)
    result.entered.append((rider_id, plan.bib))
    if plan.bib is None:
        result.no_bib += 1


def replan(plan: ImportPlan, *, bib: int | None, group: str | None) -> ImportPlan:
    """A copy of the plan with the scorer's edits from the preview."""
    return replace(plan, bib=bib, group=group)
