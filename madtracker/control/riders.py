"""Riders who may be the same person: the import preview's candidates and Merge riders.

One person can reach the database twice: a registration spells the
name another way ("José" and "Jose", "Smith-Jones" and "Smith Jones",
"Ann M." and "Ann"), a license number changes, or a rider races on a
UCI ID one season and a USAC License the next. Nothing here merges on
its own. These rules only rank who might be the same, so the scorer
can say so; a wrong guess offered is one click to ignore, a wrong
guess applied is two people's results under one name.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

from madtracker.store import Rider, Store

MAX_CANDIDATES = 3

# The two ids a rider may carry, named as the license names them and in
# Title Case, since each is a particular credential: the USA Cycling
# license number (rulebook 1A5(b)) and the UCI's 11-digit id (1A4(b)(i)).
USAC_LICENSE = "USAC License"
UCI_ID = "UCI ID"
ID_TIPS = {
    USAC_LICENSE: "The license number on the front of a USA Cycling license.",
    UCI_ID: "The 11-digit UCI ID, for riders on an international license or from another country.",
}

# Ranks, best first. An exact normalized name is the strongest hint; an
# initial or a shared birth year only narrows a common last name. A
# first and last name typed in each other's boxes is the weakest: it is
# offered so the rider on file is seen, never believed on its own.
SAME_NAME, SAME_INITIAL, SAME_BIRTH_YEAR, SWAPPED_NAME = range(4)

# Why a rider is listed first in Merge riders. Every rank needs the same
# last name, which the list already shows, so the words name only what
# else agrees.
MATCH_TEXT = {
    SAME_NAME: "Same name",
    SAME_INITIAL: "Same initial",
    SAME_BIRTH_YEAR: "Same birth year",
    SWAPPED_NAME: "Names swapped",
}


# The keys are pure functions of a string, and planning an import ranks
# every row against every rider on file, normalizing both names each
# time: 60 rows by 300 riders would be 60,000 normalizations and 108 ms per
# plan, and the preview plans again when its event changes. Cached, the
# riders' names are normalized once.
_KEY_CACHE = 8192


@lru_cache(maxsize=_KEY_CACHE)
def _plain(text: str | None) -> str:
    """Case folded, accents stripped, hyphens, apostrophes and periods as spaces."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    bare = "".join(c for c in decomposed if not unicodedata.combining(c))
    bare = re.sub(r"[-'’.]", " ", bare.casefold())
    return " ".join(bare.split())


@lru_cache(maxsize=_KEY_CACHE)
def first_key(first: str | None) -> str:
    """The first word of a first name: a middle name or initial after it is ignored."""
    words = _plain(first).split()
    return words[0] if words else ""


@lru_cache(maxsize=_KEY_CACHE)
def last_key(last: str | None) -> str:
    """The last name with no spaces, so "O'Brien", "OBrien" and "O Brien" agree."""
    return _plain(last).replace(" ", "")


def name_key(first: str | None, last: str | None) -> tuple[str, str]:
    return (first_key(first), last_key(last))


@dataclass(frozen=True, slots=True)
class Candidate:
    rider: Rider
    rank: int

    @property
    def label(self) -> str:
        """The rider's name, with the one detail that tells two namesakes apart.

        "#" means a bib everywhere else in the app, so an id is named for
        what it is. The id is unique, so it comes first; with none, the
        birth year is the next best thing the database knows. With
        neither, two namesakes read the same, since inventing a
        difference would be worse than showing none.
        """
        return f"Same as {self.who}"

    @property
    def who(self) -> str:
        """The label without "Same as ", for a sentence that names the rider."""
        r = self.rider
        name = r.name
        if r.usac_license:
            return f"{name} ({USAC_LICENSE} {r.usac_license})"
        if r.uci_id:
            return f"{name} ({UCI_ID} {r.uci_id})"
        if r.birth_year is not None:
            return f"{name} (born {r.birth_year})"
        return name


def rank(first: str, last: str, birth_year: int | None, rider: Rider) -> int | None:
    """How likely ``rider`` is the person named, as a rank; None when unlikely."""
    return rank_names(first, last, birth_year, rider.first_name, rider.last_name, rider.birth_year)


def rank_names(
    first: str,
    last: str,
    birth_year: int | None,
    other_first: str,
    other_last: str,
    other_birth_year: int | None,
) -> int | None:
    """``rank`` for two names, so two rows of one file can be compared as a row and a rider are."""
    f, ln = name_key(first, last)
    rf, rl = name_key(other_first, other_last)
    if ln and f and last_key(first) == rl and first_key(last) == rf and ln != rl:
        # "O'Brien Siobhan" for Siobhan O'Brien: each name in the other's box.
        return SWAPPED_NAME
    if not ln or ln != rl:
        return None
    if f and f == rf:
        return SAME_NAME
    if f and rf and f[0] == rf[0]:
        return SAME_INITIAL
    if birth_year is not None and birth_year == other_birth_year:
        return SAME_BIRTH_YEAR
    return None


def candidates(
    first: str,
    last: str,
    birth_year: int | None,
    riders: Iterable[Rider],
    *,
    exclude: Iterable[int] = (),
    limit: int | None = MAX_CANDIDATES,
) -> list[Candidate]:
    """Stored riders who may be this person, best first, at most ``limit``."""
    skip = set(exclude)
    found = []
    for r in riders:
        if r.rider_id in skip:
            continue
        how = rank(first, last, birth_year, r)
        if how is not None:
            found.append(Candidate(r, how))
    found.sort(key=lambda c: (c.rank, last_key(c.rider.last_name), first_key(c.rider.first_name)))
    return found if limit is None else found[:limit]


class RiderIndex:
    """``candidates`` over one list of riders, asked of many names.

    Asking every row of every rider on file, an import of 300 rows
    against 3000 riders would be 450,000 ranks and half a second, spent again
    each time the preview's event changed. Every rank but none needs the
    rider's last-name key to be the name's last-name key, or, for a
    swapped name, its first name's; so only the riders under those two
    keys are ranked. They are ranked in the list's own order, so the
    stable sort leaves ties exactly where ``candidates`` leaves them.
    """

    def __init__(self, riders: Sequence[Rider]):
        self.riders = list(riders)
        self._by_last: dict[str, list[int]] = {}
        for i, r in enumerate(self.riders):
            self._by_last.setdefault(last_key(r.last_name), []).append(i)

    def candidates(
        self,
        first: str,
        last: str,
        birth_year: int | None,
        *,
        exclude: Iterable[int] = (),
        limit: int | None = MAX_CANDIDATES,
    ) -> list[Candidate]:
        keys = {last_key(last), last_key(first)}
        positions = sorted({i for key in keys for i in self._by_last.get(key, ())})
        return candidates(
            first,
            last,
            birth_year,
            [self.riders[i] for i in positions],
            exclude=exclude,
            limit=limit,
        )


def and_list(items: list[str]) -> str:
    """``A``, ``A and B``, ``A, B, and C``."""
    if len(items) <= 2:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"


# The rider's own values, in the order Edit rider asks for them.
RIDER_VALUES = (
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("usac_license", USAC_LICENSE),
    ("uci_id", UCI_ID),
    ("birth_year", "Birth year"),
)


@dataclass(frozen=True, slots=True)
class MergeValue:
    """One line of Merge riders: a value both records give, or a choice between two.

    ``kind`` is "rider" (``key`` a rider column), "bib" or "group" (``key``
    an event_id), "team" (``key`` a race_id) or "events" (shown, never
    chosen). ``values`` holds one value where the records agree or one is
    blank, since a blank is not a disagreement, and two, the starting
    record's first, where they differ; ``texts`` are those values as shown.
    """

    kind: str
    key: str | int | None
    label: str
    values: tuple
    texts: tuple[str, ...]

    @property
    def differs(self) -> bool:
        return len(self.values) == 2


def is_unset(value: object) -> bool:
    """A stored field with no value: None or the empty string."""
    return value is None or value == ""


def _settle(mine: object, theirs: object) -> tuple:
    """One value where the two agree or one is blank; both, mine first, where they differ."""
    if is_unset(mine):
        return () if is_unset(theirs) else (theirs,)
    if is_unset(theirs) or mine == theirs:
        return (mine,)
    return (mine, theirs)


def merge_values(store: Store, first_id: int, other_id: int) -> list[MergeValue]:
    """Every line Merge riders shows for two records, the rider's own values first.

    An event's bib and group are lines only where both records are on that
    event's roster, and a team only where they are on two teams in one
    race: anywhere else one record's entry simply moves, with nothing to
    choose.
    """
    first, other = store.rider(first_id), store.rider(other_id)
    lines = []
    for name, label in RIDER_VALUES:
        values = _settle(getattr(first, name), getattr(other, name))
        lines.append(MergeValue("rider", name, label, values, tuple(str(v) for v in values)))
    names = []
    for event in reversed(store.events()):
        entries = {e.rider_id: e for e in store.entries(event.event_id)}
        mine, theirs = entries.get(first_id), entries.get(other_id)
        if mine is None and theirs is None:
            continue
        names.append(event.name)
        if mine is None or theirs is None:
            continue
        bibs = _settle(mine.bib, theirs.bib)
        if len(bibs) == 2:
            texts = tuple(str(b) for b in bibs)
            lines.append(MergeValue("bib", event.event_id, f"Bib, {event.name}", bibs, texts))
        groups = _settle(mine.local_group, theirs.local_group)
        if len(groups) == 2:
            lines.append(
                MergeValue("group", event.event_id, f"Group, {event.name}", groups, groups)
            )
        for race in store.races(event.event_id):
            teams = store.teams(race.race_id)
            a = next((t for t in teams if first_id in t.members), None)
            b = next((t for t in teams if other_id in t.members), None)
            if a is not None and b is not None and a.team_id != b.team_id:
                lines.append(
                    MergeValue(
                        "team",
                        race.race_id,
                        f"Team, {race.name}",
                        (a.team_id, b.team_id),
                        (a.name, b.name),
                    )
                )
    events = ", ".join(names) or "None"
    lines.append(MergeValue("events", None, "Events", (events,), (events,)))
    return lines


def merge_choices(
    lines: Sequence[MergeValue], chosen: Mapping[int, int]
) -> tuple[dict[str, object], dict[int, dict[str, object]], dict[int, int]]:
    """Store.merge_riders' values, entries and teams from the lines and the picks.

    ``chosen`` maps a line's index to 0 or 1, its starting record's value
    or the other's. Every rider value is given, agreed or picked, so the
    merged record reads as the page did whichever row survives.
    """
    values: dict[str, object] = {}
    entries: dict[int, dict[str, object]] = {}
    teams: dict[int, int] = {}
    for index, line in enumerate(lines):
        if line.kind == "events" or not line.values:
            continue
        value = line.values[chosen[index]] if line.differs else line.values[0]
        if line.kind == "rider":
            values[line.key] = value
        elif line.kind == "bib":
            entries.setdefault(line.key, {})["bib"] = value
        elif line.kind == "group":
            entries.setdefault(line.key, {})["local_group"] = value
        elif line.kind == "team":
            teams[line.key] = value
    return values, entries, teams
