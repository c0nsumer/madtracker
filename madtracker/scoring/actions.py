"""Scorer actions as frozen, JSON-friendly dataclasses.

The store keeps a race as an append-only log of (kind, schema_ver,
payload) rows and hands the engines the ordered list of live rows,
voids already removed. This module defines what those rows mean. The
engines only ever read actions, never mutate them, so every class is
frozen and list-shaped fields are normalized to tuples on construction.
``to_payload`` and ``from_payload`` round-trip through plain dicts of
ints, strings and lists so the store can serialize with ``json`` and
nothing else.

Entrants are identified by an ``entrant_id``: the rider id for
individual races, the team id for a madison. Bibs and colors are
presentation and live in the store, not here, so a bib typo fixed on the
roster never changes a recorded action.

Places are a list of lists: ``[[35], [12, 18], [4]]`` reads as 35
first, 12 and 18 tied second, 4 fourth (a tie takes its place and the
next place goes unfilled, USAC 1M6(a)). This shape is shared by sprint
results and the finish order so one entry box serves both. The shape
allows an empty inner list, but nothing in the app stages one, and the
engines do not agree on it: ``place_map`` and ``sprint_points.award``
skip a place for it, while ``placings.compute`` ranks the entrants it
finds densely. Keep it out of a log.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from typing import Any, ClassVar, Self

# USAC 1M6 result codes, plus DNP which only the USAC results CSV
# defines (see docs/research/usac-results-export.md). UCI's ABD is
# recorded as DNF with a reason; the export maps the reason to a code.
STATUSES = ("DNS", "DNF", "DQ", "DNP")

# Every action kind, by its stored name. The app records scorekeeping only:
# what the officials called, never why (a relegation is entered as the
# corrected result it produces) and no lap counter (no restarts).
ACTION_TYPES: dict[str, type["Action"]] = {}


def _ids(value: Iterable[Any]) -> tuple[int, ...]:
    return tuple(int(v) for v in value)


def _places(value: Iterable[Iterable[Any]]) -> tuple[tuple[int, ...], ...]:
    return tuple(_ids(group) for group in value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


@dataclass(frozen=True)
class Action:
    """Base class. Subclasses set ``kind`` and register themselves by it."""

    kind: ClassVar[str] = ""
    SCHEMA_VER: ClassVar[int] = 1

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.kind:
            ACTION_TYPES[cls.kind] = cls

    def to_payload(self) -> dict[str, Any]:
        """The JSON-ready dict the store writes. ``kind`` is a separate column."""
        return {f.name: _jsonable(getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Self:
        return cls(**payload)


def decode_action(kind: str, schema_ver: int, payload: Mapping[str, Any]) -> Action:
    """Rebuild an action from a store row.

    A payload newer than this code is refused rather than guessed at: a
    silent misread would change a result years later, which is exactly
    what the versioned log exists to prevent.
    """
    try:
        cls = ACTION_TYPES[kind]
    except KeyError:
        raise ValueError(f"Unknown action kind {kind!r}") from None
    if schema_ver > cls.SCHEMA_VER:
        raise ValueError(
            f"Action {kind!r} schema {schema_ver} is newer than this code ({cls.SCHEMA_VER})"
        )
    return cls.from_payload(payload)


@dataclass(frozen=True)
class SprintResult(Action):
    """Places in one sprint, deepest first. Only the scoring places need
    to be entered for intermediate sprints; the final sprint needs the
    full order (UCI 3.2.119, USAC 2M2(g)), which is why FinishOrder exists
    as a separate action. In a win-and-out, sprint_no is the place lap."""

    kind: ClassVar[str] = "sprint_result"
    sprint_no: int = 0
    places: tuple[tuple[int, ...], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "places", _places(self.places))


@dataclass(frozen=True)
class LapGained(Action):
    """One lap gained by each listed entrant, as called by the officials.
    One action per lap keeps undo one action per call. ``sprint_no`` records
    that the lap was taken at a sprint; the points add either way
    (UCI 3.2.125, USAC 2M3(d))."""

    kind: ClassVar[str] = "lap_gained"
    entrant_ids: tuple[int, ...] = ()
    sprint_no: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entrant_ids", _ids(self.entrant_ids))


@dataclass(frozen=True)
class LapLost(Action):
    """One lap lost by each listed entrant."""

    kind: ClassVar[str] = "lap_lost"
    entrant_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entrant_ids", _ids(self.entrant_ids))


@dataclass(frozen=True)
class Eliminated(Action):
    """Entrants eliminated at one sprint. Several may go out together
    when the officials put them out together (UCI 3.2.223, USAC 2E3(d)(ii),
    2E3(d)(iii)); a rider lapped or abandoning between sprints is the one
    out at the next sprint (USAC 2E3(d)(i)); an empty list is the green
    flag, no elimination (UCI 3.2.223, USAC 2E3(d)(iii)). Entrants in one
    action share a place; to order them, enter separate actions with the
    same sprint_no."""

    kind: ClassVar[str] = "eliminated"
    sprint_no: int = 0
    entrant_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entrant_ids", _ids(self.entrant_ids))


@dataclass(frozen=True)
class FinishOrder(Action):
    """The full order across the line at the end of the race, with ties.
    Entrants the judges could not place are left out and share the next
    rank (USAC 1M6(a))."""

    kind: ClassVar[str] = "finish_order"
    places: tuple[tuple[int, ...], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "places", _places(self.places))


@dataclass(frozen=True)
class Status(Action):
    """A non-finisher mark. The reason is free text (mishap, withdrawn,
    pulled, by choice) because USAC collapses those into DNF while UCI
    separates DNF from ABD (USAC 1M6, UCI 3.3.012); the export maps it."""

    kind: ClassVar[str] = "status"
    entrant_id: int = 0
    status: str = "DNF"
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, not {self.status!r}")


@dataclass(frozen=True)
class OutOfFinish(Action):
    """A rider, or a madison team, kept out of the finish by a mishap.

    Free laps may not end inside the last kilometer; a rider whose free
    laps run into it cannot return and "shall appear in the final
    placings depending on the points and laps accumulated prior to the
    mishap" (USAC 2M7(b), 2N6(c)), keeping those points "for the final
    classification" (USAC 2M8(a), 2N7(a)). So this is not a status: the
    rider is placed, with a number, among the finishers, on points. It is
    its own kind rather than a Status code because every status means
    "not placed" (USAC 2C4, 2M8(a)), and because the finish order must leave the
    rider out while the sprints before it keep them. Points Race, Madison
    and Tempo Race only; a placings race has no points to rank on
    (USAC 2C5(b) says "will not appear in the final placings")."""

    kind: ClassVar[str] = "out_of_finish"
    entrant_id: int = 0


@dataclass(frozen=True)
class Withdrawn(Action):
    """A rider, or a madison team, out of the race from this moment and placed by it.

    Two readings of the rulebook give the same rank. In the omnium's
    Scratch Race and Tempo Race a rider two laps down "shall be
    withdrawn" and "will be allocated the next available rank determined
    by the number of riders remaining on the track at this moment", and
    a rider not withdrawn "will be classified as though they had been at
    the point at which they lost their second lap" (USAC 2O3(e)). In any
    race the Chief Referee may have pulled riders "placed by their
    relative positions when withdrawn" (USAC 1M6(d)). So the entry
    records a moment, not a leaving: nothing the rider does after it
    counts, and they rank after every rider still racing at the end,
    among the withdrawn by that moment, the latest highest. It is not a
    status, since every status means "not placed" (USAC 2C4, 2M8(a)),
    and the row prints its number. The points and laps held stay as
    figures. Races placed at the line, the Points Race, the Madison, and
    the Tempo Race; an Elimination puts a rider who leaves out at that
    moment instead (USAC 2E4), and a Win-and-Out has no rule for it."""

    kind: ClassVar[str] = "withdrawn"
    entrant_id: int = 0


@dataclass(frozen=True)
class PointsAdjusted(Action):
    """Points the officials took from one entrant's total, as a ruling.

    The rulebook's penalty table gives "loss of points or laps illegally
    gained" (USAC 8D5(b)) and the glossary defines a relegation as "a
    loss of position, points or time, depending on the type of race".
    The app records the number the officials named and nothing else: no
    reason, no article.
    Each entry is the difference between the penalty the scorer set and
    the one standing before it: negative as the penalty grows, positive
    as it is lowered or taken off (the officials reversed it, or it went
    on the wrong rider). The engine adds whatever sign it finds, and
    validation keeps the sum at or below zero. Points Race, Madison and
    Tempo Race only, since no other format has points to take."""

    kind: ClassVar[str] = "points_adjusted"
    entrant_id: int = 0
    points: int = 0


@dataclass(frozen=True)
class LapNotCounted(Action):
    """One lap gained by each listed entrant that the officials ruled did
    not count (a lap "illegally gained", USAC 8D5(b); a wireless Madison
    relay, 8D5(c) and 2N3(e)). It cancels the newest uncancelled LapGained
    of that entrant: the gained count drops by one and the lap's points
    with it. It differs from LapLost, which is a second event on the
    track and leaves both laps in the net count."""

    kind: ClassVar[str] = "lap_not_counted"
    entrant_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entrant_ids", _ids(self.entrant_ids))


@dataclass(frozen=True)
class RaceEnded(Action):
    """The officials ended a Points Race or Madison with the results as they stand.

    A race stopped after 80 percent of its distance is not restarted:
    "Let results stand" (USAC 2M6, 2N5). The sprints ridden score as
    they were ridden and there is no final sprint, so nothing doubles
    and there is no final-sprint place to break a tie on points; riders
    level on points share the place (USAC 1M6(a)). ``after_sprint`` is
    the last sprint recorded when the race ended, so the log says where
    it stopped. A Tempo Race has no such table (USAC 2P5 restarts or
    reruns it), and the other formats' tables say rerun or restart."""

    kind: ClassVar[str] = "race_ended"
    after_sprint: int = 0


@dataclass(frozen=True)
class RaceShortened(Action):
    """The officials shortened a Points Race, Madison, or Tempo Race to fewer sprints.

    "The Chief Referee may neutralize, shorten, suspend, or cancel any
    race" (USAC 1G4(b)). A shortened race keeps racing to a new, earlier
    finish, so ``sprint_count`` is the race's count from here on: in a
    Points Race or Madison its last sprint is the final sprint, doubled
    and ridden as the finish (USAC 2M2(f), the last sprint after the
    full distance), and in a Tempo Race the finish comes that much
    sooner. A later entry lowers the count again. It is not a scoring
    kind: it changes no rider's line until a sprint is ridden under it.
    The race's own count stays as it was set, so the log keeps the
    record of the call."""

    kind: ClassVar[str] = "race_shortened"
    sprint_count: int = 0


# Kinds that score. Used by validation to refuse scoring entries once the
# finish order is recorded, and to refuse them for a rider with a status.
SCORING_KINDS = frozenset(
    {
        SprintResult.kind,
        LapGained.kind,
        LapLost.kind,
        Eliminated.kind,
        FinishOrder.kind,
        OutOfFinish.kind,
        Withdrawn.kind,
    }
)

# The officials' rulings on points and laps. They are not scoring kinds
# because a ruling comes when it comes, often after the finish order,
# when validation refuses every scoring entry; they are results all the
# same (a rider with one took the start, so no DNS), and a rider with a
# DNS, DQ or DNP has no total for one to touch. A DNF keeps the points
# shown, so a ruling on a DNF rider stands.
RULING_KINDS = frozenset({PointsAdjusted.kind, LapNotCounted.kind})
