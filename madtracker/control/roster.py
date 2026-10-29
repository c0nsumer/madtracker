"""Who is in a race, and the one place a bib is checked.

The scoring engines know entrants only by ``entrant_id``. For individual
formats that is the rider_id, because bibs are reissued every event and a
rider's identity must not change when the roster desk swaps a number.
For madison and other team formats it is the team_id. Bibs, names and
colors are presentation: they live here, outside the action log, so a bib
corrected on the roster never rewrites a recorded result.

The bib map covers the whole event, not just the start list, so a bib
that exists tonight but is not in this race gets a message naming the
rider instead of a bare "unknown bib".

A bib is unique within a race's field, not within the event: the
venue hands out numbers per race night and two riders who never
share a race may wear the same one. A rider may also be on the roster
with no bib until the venue assigns it. Both are let in at the
roster and stopped here, at the field: ``bib_clash`` refuses a second
rider with a number already in a field, and ``field_refusal`` is why a
field cannot be scored yet (a rider without a bib, or a clash that came
in through a group fill). Every path that puts riders in a field goes
through these two, so the rule lives in one place.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from madtracker.control.describe import who
from madtracker.control.groups import canonical_group, follow_group
from madtracker.inputs import BIB_MAX, clean_line, is_ascii_digits, is_blank, read_int
from madtracker.store import Store


class EntryError(ValueError):
    """A rider the app cannot put in this race. The message is for the scorer."""


# The longest team name a scorer can type. Six names this long still
# leave room for every team's riders on the board's start list.
TEAM_NAME_MAX = 40


def team_name_problem(name: str) -> str | None:
    """Why a team name will not do, or None.

    A number on the board beside the riders' plates reads as a bib.
    """
    if is_blank(name):
        return "The team needs a name"
    name = clean_line(name)
    if name.isdigit():
        return f"Team name {name!r} would read as a bib; use a color or a word"
    return None


@dataclass(frozen=True)
class Entrant:
    """One scored unit: a rider, or a team of riders."""

    entrant_id: int
    bibs: tuple[int, ...]
    names: tuple[str, ...]
    team: str | None = None
    color: str | None = None
    color_hex: str | None = None

    @property
    def is_team(self) -> bool:
        return self.team is not None

    @property
    def short(self) -> str:
        """What the confirmation line uses: the bib, or the team's name."""
        if self.team is not None:
            return self.team
        return str(self.bibs[0]) if self.bibs else f"#{self.entrant_id}"


@dataclass(frozen=True)
class RosterBib:
    """A bib worn tonight, possibly by a rider who is not in this race."""

    bib: int | None
    rider_id: int
    name: str


class Roster:
    """The race's entrants, by id and by bib."""

    def __init__(self, entrants: Iterable[Entrant], roster_bibs: Iterable[RosterBib] = ()) -> None:
        self.entrants: tuple[Entrant, ...] = tuple(entrants)
        self._by_id: dict[int, Entrant] = {e.entrant_id: e for e in self.entrants}
        # A number may be worn by several riders tonight, in different races.
        self._worn: dict[int, list[RosterBib]] = {}
        for m in roster_bibs:
            if m.bib is not None:
                self._worn.setdefault(m.bib, []).append(m)
        self.is_team = any(e.is_team for e in self.entrants)
        self._bib_to_entrant: dict[int, int] = {}
        # A clash in the field leaves the number out of the lookup: the
        # race is refused anyway (field_refusal), and a typed number must
        # never find the wrong rider.
        clashed: set[int] = set()
        for e in self.entrants:
            for bib in e.bibs:
                owner = self._bib_to_entrant.get(bib)
                if owner is not None and owner != e.entrant_id:
                    clashed.add(bib)
                self._bib_to_entrant[bib] = e.entrant_id
        for bib in clashed:
            del self._bib_to_entrant[bib]

    @property
    def noun(self) -> str:
        return "team" if self.is_team else "rider"

    @property
    def ids(self) -> list[int]:
        return [e.entrant_id for e in self.entrants]

    def get(self, entrant_id: int) -> Entrant | None:
        return self._by_id.get(entrant_id)

    def short(self, entrant_id: int) -> str:
        e = self._by_id.get(entrant_id)
        return e.short if e else f"#{entrant_id}"

    def resolve(self, token: str) -> int | None:
        """The entrant a bib or a team's name or color names; None when nobody does.

        The mockups and the tests name riders this way. Raises EntryError
        when a bib is worn by someone here tonight who is not in this race.
        """
        token = token.strip()
        if is_ascii_digits(token) and len(token) <= 9:
            bib = int(token)
            found = self._bib_to_entrant.get(bib)
            if found is not None:
                return found
            where = "on a team in this race" if self.is_team else "in this race"
            if any(bib in e.bibs for e in self.entrants):
                raise EntryError(f"Bib {bib} is worn by two {self.noun}s in this race")
            event = self._worn.get(bib, [])
            if len(event) == 1:
                raise EntryError(f"{who(bib, event[0].name)} is not {where}")
            if event:
                raise EntryError(f"Bib {bib} is not {where}")
            return None
        word = token.casefold()
        for field in ("team", "color"):
            for e in self.entrants:
                if (getattr(e, field) or "").casefold() == word:
                    return e.entrant_id
        return None


def _bib_order(bib: int | None) -> tuple[bool, int]:
    return (bib is None, bib or 0)


def individual_entrants(rows: Iterable[tuple[int, int | None, str]]) -> list[Entrant]:
    """Entrants from (rider_id, bib, name) start-list rows, in bib order.

    A rider without a bib has no bibs and sorts last.
    """
    return [
        Entrant(entrant_id=rid, bibs=() if bib is None else (bib,), names=(name,))
        for rid, bib, name in sorted(rows, key=lambda r: _bib_order(r[1]))
    ]


def team_entrants(
    teams: Iterable[tuple[int, str, str, str | None, Iterable[int]]],
    riders: Mapping[int, tuple[int | None, str]],
) -> list[Entrant]:
    """Entrants from (team_id, name, color, color_hex, member rider_ids) rows.

    ``riders`` maps rider_id to (bib, name) for the event. A team's label
    is its name, falling back to its color, because venues name their
    madison teams by jersey color and the P3 editor may store either.
    """
    out = []
    for team_id, name, color, color_hex, members in teams:
        # Members with a bib first, so bibs and names pair up by position.
        known = sorted((riders[m] for m in members if m in riders), key=lambda r: r[0] is None)
        out.append(
            Entrant(
                entrant_id=team_id,
                bibs=tuple(b for b, _ in known if b is not None),
                names=tuple(n for _, n in known),
                team=name or color or f"Team {team_id}",
                color=color or None,
                color_hex=color_hex,
            )
        )
    return out


# ----- putting a rider on the roster -------------------------------------------


def last_group(store: Store, rider_id: int) -> str:
    """The group a rider had at their most recent event, offered as Choose Riders ticks them on.

    Only the group carries over, never the bib: the venue hands bibs
    out for each event, so last event's number says nothing about the
    one on the rider's back tonight.
    """
    last = store.last_entry(rider_id)
    return (last.local_group if last is not None else "") or ""


def _rider_name(store: Store, rider_id: int) -> str:
    return store.rider(rider_id).name


def no_bib_text(count: int) -> str:
    """``3 riders have no bib.``"""
    return "1 rider has no bib." if count == 1 else f"{count} riders have no bib."


ROSTER_HINT = "Edit Event > Roster."


def field_refusal(rows: Iterable[tuple[int, int | None, str]]) -> str:
    """Why a field of (rider_id, bib, name) rows cannot be scored yet, or "".

    A rider without a bib, or two riders with one number, would make the
    officials' calls and the typed numbers name nobody or the wrong
    rider. The fix is on the roster, so the line says where.
    """
    rows = list(rows)
    missing = sum(1 for _, bib, _ in rows if bib is None)
    if missing:
        return f"{no_bib_text(missing)} {ROSTER_HINT}"
    clash = field_clashes(rows)
    if clash:
        bib, names = clash[0]
        count = "two" if len(names) == 2 else str(len(names))
        return f"Bib {bib} is worn by {count} riders in this race. {ROSTER_HINT}"
    return ""


def field_clashes(rows: Iterable[tuple[int, int | None, str]]) -> list[tuple[int, list[str]]]:
    """Each number worn by more than one rider in a field, with their names, in bib order."""
    by_bib: dict[int, list[str]] = {}
    for _, bib, name in rows:
        if bib is not None:
            by_bib.setdefault(bib, []).append(name)
    return [(b, names) for b, names in sorted(by_bib.items()) if len(names) > 1]


def clash_text(clashes: list[tuple[int, list[str]]]) -> str:
    """``Bib 12 is worn by Ana Ruiz and Bo Lind in this race.`` for the refusal line."""
    parts = [f"Bib {bib} is worn by {' and '.join(names)} in this race." for bib, names in clashes]
    return " ".join(parts)


def field_rows(store: Store, race_id: int) -> list[tuple[int, int | None, str]]:
    return [(e.rider_id, e.bib, e.name) for e in store.race_entries(race_id)]


def bib_clash(store: Store, race_id: int, rider_id: int, bib: int | None) -> str:
    """The refusal for putting ``rider_id`` wearing ``bib`` in a race's stored field, or ""."""
    others = [e.rider_id for e in store.race_entries(race_id)]
    return field_clash(store, store.race(race_id).event_id, rider_id, bib, others)


def field_clash(
    store: Store, event_id: int, rider_id: int, bib: int | None, field: Iterable[int]
) -> str:
    """The refusal for ``rider_id`` wearing ``bib`` beside the riders in ``field``, or "".

    ``field`` may be a dialog's ticks, not saved yet. No bib is no clash:
    that rider waits for a number, which ``field_refusal`` reports.
    """
    if bib is None:
        return ""
    bibs = {e.rider_id: e.bib for e in store.entries(event_id)}
    for other in field:
        if other != rider_id and bibs.get(other) == bib:
            return f"Bib {bib} is worn by {_rider_name(store, other)} in this race."
    return ""


def typed_bib(text: str) -> int | None:
    """The bib typed in a cell, None for a blank; ValueError worded for the scorer otherwise.

    The roster's Bib column and the import preview's read a bib the same
    way, from ASCII digits only ("²" passes str.isdigit and fails int).
    """
    text = text.strip()
    if not text:
        return None
    if not is_ascii_digits(text):
        raise ValueError(f"a bib is a number from 1 to {BIB_MAX}")
    bib = read_int(text, 1, BIB_MAX)
    if bib is None:
        raise ValueError(f"a bib is a number from 1 to {BIB_MAX}")
    return bib


def roster_bib_refusal(store: Store, event_id: int, rider_id: int, bib: int | None) -> str:
    """Why the roster cannot give ``rider_id`` this bib, or "".

    A typed number must not clash in any race the rider is already in.
    A scored race's riders keep a bib: the result names them by it, and
    a race is never scored without one.
    """
    for race in store.races(event_id):
        field = [e.rider_id for e in store.race_entries(race.race_id)]
        if rider_id not in field:
            continue
        if bib is None:
            if race.state != "setup" or store.live_actions(race.race_id):
                return f"{_rider_name(store, rider_id)} is in {race.name}, which has been scored."
            continue
        clash = bib_clash(store, race.race_id, rider_id, bib)
        if clash:
            return clash.replace("in this race.", f"in {race.name}.")
    return ""


def enter_on_roster(
    store: Store, event_id: int, rider_id: int, bib: int | None, group: str = ""
) -> None:
    """Put a rider on the event's roster with the bib on their back and the group picked.

    The group takes the event's spelling, so a typed "group a" joins the
    Group A already there instead of starting a second one. The bib may
    be None: the venue often hands numbers out after registration.
    Raises the store's refusal (StoreError or ValueError) for the caller
    to word.
    """
    group = canonical_group(store, event_id, group)
    # The entry and the races it joins are one write: one commit, and
    # never a rider on the roster but missing from their group's races.
    with store.transaction():
        store.add_entry(event_id, rider_id, bib, local_group=group or "")
        follow_group(store, event_id, [rider_id])
