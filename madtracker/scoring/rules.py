"""Scoring rules as configuration, with the rulebook as the one preset.

Each engine takes one frozen rules object. A race stores its rules as
JSON (``to_dict`` / ``rules_from_dict``) together with the ruleset name
and ``replay.RULES_VERSION`` so a replay years later gives the same
answer even if the preset changes (plan 4.4).

USAC and UCI score every format the same way: the points tables, the
lap value, the tie-breaks, the elimination order. They differ only in
conduct rules and in the sprint interval by track length, and neither
reaches the scoring once the scorer records each sprint as it is
called. So one preset, ``rulebook``, is built in.
A venue's house values (a lap worth 10, a points table that awards six places)
live in a stored ruleset (``madtracker.control.rulesets``) made from
the rulebook and edited in the app.

What the engine needs per race, and nothing more: how many sprints
(points, madison, tempo), so it knows which is the final and doubles
it; how many places and which direction (win-and-out); how many
survivors ride the final (elimination). Track length, total laps and
sprint intervals are commentary and belong in the race name.
"""

from dataclasses import asdict, dataclass, fields
from typing import Any, ClassVar

PRESETS = ("rulebook",)

# The edition every article cited here, in docs/scoring-rules.md and in
# the research notes refers to, named as the book names itself: its
# name in its introduction and Appendix C ("This Rulebook is published by
# USA Cycling"; "USA Cycling Rulebook and Policies"; the running footer
# spells it "Rule Book"), and the
# version and effective date on its updates page
# (the book says a page's revision is the version in its footer; the
# track chapter's pages still read 07•25, since 8•25 changed only the
# collegiate and records chapters). It changes only when the values are
# re-audited against a newer rulebook, and the built-in ruleset's label
# and tooltip are built from it so the name never drifts from the audit.
RULEBOOK_TITLE = "USA Cycling Rulebook"
RULEBOOK_VERSION = "8•25"
RULEBOOK_EDITION = f"version {RULEBOOK_VERSION} (effective 2025-Aug-19)"
RULEBOOK_CITATION = f"{RULEBOOK_TITLE}, {RULEBOOK_EDITION}"
RULEBOOK_YEAR = "2025"

# UCI 3.2.250, USAC 2O3(a): 40, 38, 36 ... 2 for places 1 to 20, then 1.
UCI_OMNIUM_PLACE_POINTS = tuple(42 - 2 * p for p in range(1, 21))

# USAC 2M2(f)(ii), UCI 3.2.118: a lap gained or lost is 20 points.
RULEBOOK_LAP_POINTS = 20


def _tuple_or_none(value: Any) -> tuple[int, ...] | None:
    return None if value is None else tuple(int(v) for v in value)


class _Rules:
    """Shared JSON round-trip. Tuples become lists in the dict and come
    back as tuples, which keeps the dataclasses hashable and frozen."""

    engine: ClassVar[str] = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)  # type: ignore[call-overload]
        data["engine"] = self.engine
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_Rules":
        names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass(frozen=True)
class PlacingsRules(_Rules):
    """Races ranked by the line: scratch (chase), handicap, unknown
    distance, chariot, keirin and match sprint finals.

    laps_count_for_ranking: laps gained sort ahead of finish order
    (USAC 2C5, UCI 3.2.178). Off for chariot, keirin and sprint finals,
    where nobody laps anybody.
    lapped_riders_placed_by_laps: a rider on negative laps who is still in
    the finish order is placed by laps down (USAC 2C4, the rulebook
    value). Off, a lapped rider must leave the track (UCI 3.2.177) and
    so ranks in the DNF group if the scorer still records them at the line.
    """

    engine: ClassVar[str] = "placings"
    laps_count_for_ranking: bool = True
    lapped_riders_placed_by_laps: bool = True


@dataclass(frozen=True)
class SprintPointsRules(_Rules):
    """Points race, madison and tempo.

    ``sprint_count`` is how many sprints the race has; the race editor
    sets it per race. None means the race editor has not set it yet;
    validate() refuses every entry until it is set, since the engine
    cannot tell which sprint doubles. Points per place come from
    ``intermediate_points`` and, for the sprint numbered
    ``sprint_count``, ``final_points``. ``points_by_sprint`` is an
    explicit per-sprint table that overrides both and fixes the count.

    ``lap_lost_points`` is the positive size of the penalty; the engine
    subtracts it. ``tie_break`` is "final_sprint" (UCI 3.2.119,
    USAC 2M2(g)) or "none". ``scored_unit`` is "rider" or "team" and only
    changes wording; a madison team is an entrant like any other.
    """

    engine: ClassVar[str] = "sprint_points"
    sprint_count: int | None = None
    intermediate_points: tuple[int, ...] = (5, 3, 2, 1)
    final_points: tuple[int, ...] = (10, 6, 4, 2)
    points_by_sprint: tuple[tuple[int, ...], ...] | None = None
    lap_gained_points: int = RULEBOOK_LAP_POINTS
    lap_lost_points: int = RULEBOOK_LAP_POINTS
    tie_break: str = "final_sprint"
    scored_unit: str = "rider"

    def __post_init__(self) -> None:
        object.__setattr__(self, "intermediate_points", tuple(self.intermediate_points))
        object.__setattr__(self, "final_points", tuple(self.final_points))
        if self.points_by_sprint is not None:
            object.__setattr__(
                self, "points_by_sprint", tuple(tuple(row) for row in self.points_by_sprint)
            )
            if self.sprint_count is None:
                object.__setattr__(self, "sprint_count", len(self.points_by_sprint))
        if self.sprint_count is not None:
            object.__setattr__(self, "sprint_count", int(self.sprint_count))
            if self.sprint_count < 1:
                raise ValueError("sprint_count must be at least 1")
        if self.tie_break not in ("final_sprint", "none"):
            raise ValueError(f"tie_break must be 'final_sprint' or 'none', not {self.tie_break!r}")
        if self.scored_unit not in ("rider", "team"):
            raise ValueError(f"scored_unit must be 'rider' or 'team', not {self.scored_unit!r}")

    def points_for_sprint(self, sprint_no: int) -> tuple[int, ...]:
        """The points table for one sprint. Only the sprint numbered
        ``sprint_count`` doubles."""
        if self.points_by_sprint is not None:
            if 1 <= sprint_no <= len(self.points_by_sprint):
                return self.points_by_sprint[sprint_no - 1]
            return ()
        if self.sprint_count is not None and sprint_no == self.sprint_count:
            return self.final_points
        return self.intermediate_points


@dataclass(frozen=True)
class EliminationRules(_Rules):
    """Elimination, which USAC 2E5 also calls the miss-and-out.

    ``survivors`` is how many riders ride the final sprint (2 in the
    rulebook race, USAC 2E3(f), UCI 3.2.224; a miss-and-out may be
    ridden to a specified number of survivors, USAC 2E5). ``final_by_sprint`` False means the last
    survivor standing wins with no final sprint entered (survivors=1).
    Eliminations are entered as they happen; the bell's cadence is not
    a rule the engine needs.
    """

    engine: ClassVar[str] = "elimination"
    survivors: int = 2
    final_by_sprint: bool = True


@dataclass(frozen=True)
class WinAndOutRules(_Rules):
    """Win-and-out, a club format: Danish (forward) or Belgian (reverse).

    Forward: the k-th lap winner takes place k. Reverse: the k-th lap
    winner takes place places + 1 - k. Riders without a lap win fill the
    open places by finish order (docs/research/usac-track-formats.md,
    "Win-and-out family").
    """

    engine: ClassVar[str] = "win_and_out"
    places: int = 3
    direction: str = "forward"

    def __post_init__(self) -> None:
        if self.direction not in ("forward", "reverse"):
            raise ValueError(f"direction must be 'forward' or 'reverse', not {self.direction!r}")
        if self.places < 1:
            raise ValueError("places must be at least 1")

    def place_for_lap(self, lap_no: int) -> int:
        return lap_no if self.direction == "forward" else self.places + 1 - lap_no


@dataclass(frozen=True)
class AggregateRules(_Rules):
    """Standings over several races' standings.

    ``points_by_place`` None sums each entrant's race totals (a club's
    team madison omnium). A table converts each race rank to points
    (USAC 2B19(e) omnium scoring; the UCI omnium's 40-38-36 table,
    UCI 3.2.250); ``points_beyond_table`` is what ranks past the end of
    the table score (1 in the UCI omnium). ``sum_total_races`` lists
    race indexes whose raw totals are added instead of converted, which
    is how the UCI omnium's final points race joins the first three
    (UCI 3.2.251). ``multipliers`` is per race index; None means 1.

    Non-finisher points and ``absent_points`` (not entered in a race)
    are per the race announcement (USAC glossary "OMNIUM"); the defaults
    score zero. A DNF row in a race whose total is summed (the team
    omnium, or a ``sum_total_races`` index) keeps the points it scored,
    as a DNF keeps its points in the race itself (UCI 3.3.012 A);
    ``dnf_points`` is only for place tables. ``must_finish_all`` leaves
    anyone with a non-finish or an absence unranked, marked DNF (or DQ
    when disqualified in a race) and listed after the ranked rows
    (San Diego's rule; the UCI omnium, UCI 3.2.251bis, USAC 2O2(c),
    2O3(d)). ``direction`` "high" or "low"
    (USAC 7C3 junior low-points omnium).

    ``tie_break``: "most_firsts_then_last_race" (USAC 2B19(e)),
    "last_race_final_sprint" (UCI 3.2.252) or "none".
    ``final_sprint_race`` is the race index whose final sprint
    "last_race_final_sprint" reads; None reads the last race given.
    """

    engine: ClassVar[str] = "aggregate"
    points_by_place: tuple[int, ...] | None = None
    points_beyond_table: int = 0
    sum_total_races: tuple[int, ...] = ()
    multipliers: tuple[float, ...] | None = None
    dns_points: int = 0
    dnf_points: int = 0
    dq_points: int = 0
    dnp_points: int = 0
    absent_points: int = 0
    must_finish_all: bool = False
    direction: str = "high"
    tie_break: str = "most_firsts_then_last_race"
    final_sprint_race: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "points_by_place", _tuple_or_none(self.points_by_place))
        object.__setattr__(self, "sum_total_races", tuple(int(v) for v in self.sum_total_races))
        if self.multipliers is not None:
            object.__setattr__(self, "multipliers", tuple(self.multipliers))
        if self.direction not in ("high", "low"):
            raise ValueError(f"direction must be 'high' or 'low', not {self.direction!r}")
        if self.tie_break not in ("most_firsts_then_last_race", "last_race_final_sprint", "none"):
            raise ValueError(f"unknown tie_break {self.tie_break!r}")

    def multiplier(self, race_index: int) -> float:
        if self.multipliers is None or race_index >= len(self.multipliers):
            return 1
        return self.multipliers[race_index]

    def status_points(self, status: str | None) -> int:
        return {
            "DNS": self.dns_points,
            "DNF": self.dnf_points,
            "DQ": self.dq_points,
            "DNP": self.dnp_points,
        }.get(status or "", 0)


RULES_CLASSES: dict[str, type[_Rules]] = {
    cls.engine: cls
    for cls in (PlacingsRules, SprintPointsRules, EliminationRules, WinAndOutRules, AggregateRules)
}


def rules_from_dict(data: dict[str, Any]) -> _Rules:
    """Rebuild a rules object from its stored JSON dict."""
    try:
        cls = RULES_CLASSES[data["engine"]]
    except KeyError:
        raise ValueError(f"Unknown rules engine {data.get('engine')!r}") from None
    return cls.from_dict(data)


# Presets. One rulebook.


def _check_preset(preset: str) -> str:
    """The canonical preset key, or ValueError for a name that is none."""
    key = preset.strip().casefold()
    if key not in PRESETS:
        raise ValueError(f"preset must be one of {PRESETS}, not {preset!r}")
    return key


def placings_rules(preset: str = "rulebook") -> PlacingsRules:
    """USAC 2C4: a lapped rider who stays in is placed by laps down."""
    _check_preset(preset)
    return PlacingsRules(laps_count_for_ranking=True, lapped_riders_placed_by_laps=True)


def points_race_rules(
    preset: str = "rulebook", *, sprint_count: int | None = None
) -> SprintPointsRules:
    """USAC 2M2(f) and UCI 3.2.118: 5-3-2-1, last sprint doubled, 20 per lap."""
    _check_preset(preset)
    return SprintPointsRules(sprint_count=sprint_count)


def madison_rules(
    preset: str = "rulebook", *, sprint_count: int | None = None
) -> SprintPointsRules:
    """USAC 2N2(g) and UCI 3.2.161: 5-3-2-1 doubled, 20 per lap, scored by team."""
    _check_preset(preset)
    return SprintPointsRules(sprint_count=sprint_count, scored_unit="team")


def tempo_rules(preset: str = "rulebook", *, sprint_count: int | None = None) -> SprintPointsRules:
    """UCI 3.2.261, 3.2.262 and USAC 2P2: every sprint is worth 1 point
    to the first rider, the final sprint included and not doubled, 20 per
    lap."""
    _check_preset(preset)
    return SprintPointsRules(sprint_count=sprint_count, intermediate_points=(1,), final_points=(1,))


def elimination_rules(preset: str = "rulebook", *, survivors: int = 2) -> EliminationRules:
    """USAC 2E3(f), UCI 3.2.224: the last two ride the final sprint."""
    _check_preset(preset)
    return EliminationRules(survivors=survivors, final_by_sprint=survivors > 1)


def win_and_out_rules(places: int = 3, direction: str = "forward") -> WinAndOutRules:
    return WinAndOutRules(places=places, direction=direction)


def team_omnium_rules() -> AggregateRules:
    """A club team omnium: each team's madison totals summed across the
    named races, as one venue's scoring sheet does. No rulebook
    article covers it; USAC leaves such schemes to the race announcement
    (USAC glossary "OMNIUM", 2B19(e))."""
    return AggregateRules(points_by_place=None)


def uci_omnium_rules() -> AggregateRules:
    """UCI 3.2.250 to 3.2.252 and USAC 2O3: 40-38-36 down to 2 for the
    first three races, 1 for 21st and below, then the points race's raw
    points added on, ties by the points race's final sprint. A rider who
    misses or abandons a race is out of the omnium and listed as DNF
    after every finisher (UCI 3.2.251bis, USAC 2O2(c), 2O3(d)). Pass the
    four races in order with the points race last.

    The two-laps-down rule (UCI 3.2.251bis, USAC 2O3(e)) deducts 40
    omnium points and keeps the rider in. It has no value here: the
    deduction is an omnium penalty on the standings, handed to the
    engine per rider, never a Points Penalty on the Points Race, which
    would change that race's own result.
    """
    return AggregateRules(
        points_by_place=UCI_OMNIUM_PLACE_POINTS,
        points_beyond_table=1,
        sum_total_races=(3,),
        # UCI 3.2.251bis, USAC 2O2(c), 2O3(d): a rider who does not start
        # or abandons a race is out of the omnium, after every finisher.
        must_finish_all=True,
        tie_break="last_race_final_sprint",
    )


def usac_omnium_rules(points_by_place: tuple[int, ...] = (7, 5, 3, 2, 1)) -> AggregateRules:
    """Overall-for-the-day scoring with the USAC 2B19(e) tie-break. The
    table defaults to the older rulebook's 7-5-3-2-1 (USAC16 2O1); the
    2025 book leaves it to the race announcement."""
    return AggregateRules(points_by_place=points_by_place)
