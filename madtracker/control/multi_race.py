"""Multi-race standings: a points table over races drawn from one event or several.

A standings is a stored definition (``Store.get_standings``): a name, a
kind, the kind's values, the ticked events, and the races the scorer
left out. Nothing here is stored as a number. Every call replays each
counting race through ``LiveRace`` and sums the results with the
aggregate engine, the same path a race's own result takes, so the
standings can never disagree with the race sheets it is built from.

Four kinds, each one table per group. Two are for teams, over the
Madisons of the ticked events:

- The Team Omnium by Points, as the venue's scorer keeps it (the
  Oktoberfest 2026 sheet): each team's Madison totals summed as
  printed, negative and all.
- The Team Omnium by Place: each team's place in each Madison turned
  into points from a table and those summed, the omnium scoring of
  USAC 2B19(e) and the USAC glossary "OMNIUM". The 2025 book leaves the
  table to the race announcement, so the default is the older book's
  7-5-3-2-1 (USAC16 2O1) and the scorer can set another.

Two are for riders, over races of the ticked events other than the
Madison, whose entrants are teams:

- The Omnium by Place: each rider's place in each race from the same
  table, summed. Every rider who rode any counting race is in the table
  and a race not ridden adds nothing; there is no minimum, as the club
  omniums surveyed in docs/research/omnium-practices.md just sum.
- The Four-Race Omnium, the omnium of USAC 2O1 to 2O3 and UCI 3.2.247
  to 3.2.252: one Scratch Race, Tempo Race, Elimination, and Points Race
  per event, the first three scored 40-38-36 by place and the Points
  Race's own points added.
  A ticked set short of a format or with one doubled is refused, never
  guessed. A rider who misses or abandons any of the four is out of the
  omnium and listed as DNF after every finisher.

- A race keeps its own group label, so a mixed-group race makes a
  table of its own rather than being guessed into one.
- A team is its pair of riders. Team ids are per race, and the colors
  repeat and change between weekends, so the same two riders are the
  same team on every night and a pair that changes a rider is another
  team. It shows under the name and color it raced under last. A rider
  is the same rider across events by rider id, shown under the bib they
  raced under last.
- A team that rode fewer than every counting Madison of its group is
  left out of the table, as the venue's sheet leaves out a team that rode
  one night of two. A team that started and did not
  finish rode; one marked DNS or DNP did not.
- A race still in setup with nothing scored is not yet raced: it is no
  column and adds nothing, and the sheet names it so a mid-season
  standings reads right.

Pure: no Qt, reads the store only (``LiveRace`` may settle a race's
stored state, as opening the race on the surface does).
"""

from dataclasses import dataclass, field, replace

from madtracker.control.formats import format_label
from madtracker.control.groups import group_key
from madtracker.control.race import LiveRace
from madtracker.control.rulesets import race_short_name
from madtracker.dates import show_date
from madtracker.scoring import compute_aggregate
from madtracker.scoring.result import Standings
from madtracker.scoring.rules import (
    AggregateRules,
    team_omnium_rules,
    uci_omnium_rules,
    usac_omnium_rules,
)
from madtracker.store import Race, StandingsDef, Store

# Kind key to the words the dialog and the PDF show, in the dialog's
# order. One place each.
TOTALS = "team_omnium"
PLACES = "team_omnium_places"
OMNIUM = "omnium_places"
FOUR_RACE = "four_race_omnium"
KINDS = {
    TOTALS: "Team Omnium by Points",
    PLACES: "Team Omnium by Place",
    OMNIUM: "Omnium by Place",
    FOUR_RACE: "Four-Race Omnium",
}
# Each kind's defaults, which a standings' stored values sit over.
DEFAULTS = {
    TOTALS: team_omnium_rules,
    PLACES: usac_omnium_rules,
    OMNIUM: usac_omnium_rules,
    FOUR_RACE: uci_omnium_rules,
}
# The kinds whose rows are teams; the others' rows are riders.
TEAM_KINDS = frozenset({TOTALS, PLACES})
# The kinds with a Place points table the scorer sets; the Four-Race
# Omnium's table is the rulebook's.
PLACE_KINDS = frozenset({PLACES, OMNIUM})

# The format whose races a Team Omnium sums (control/formats.py).
MADISON = "madison"
# The Four-Race Omnium's races in the order they are ridden (USAC 2O1;
# UCI 3.2.247): the Points Race last, since its points are summed raw
# and its final sprint breaks a tie.
FOUR_RACE_FORMATS = ("chase", "tempo", "elimination", "points")
FOUR_RACE_NEED = (
    "A Four-Race Omnium needs one Scratch Race, one Tempo Race, one Elimination, "
    "and one Points Race for every group on each event."
)
# An event with none of the four: one line under its heading, worded
# apart from a group's line so it is not read as one.
FOUR_RACE_NONE = "No Scratch Race, Tempo Race, Elimination, or Points Race"
# A group with no label, as the sheet and the dialog head its table.
NO_GROUP = "No Group"


def rider_kind(kind: str) -> bool:
    """True when the kind's rows are riders, False when they are teams."""
    return kind not in TEAM_KINDS


def race_counts(kind: str, format_key: str) -> bool:
    """Whether a race of ``format_key`` is a candidate for a standings of ``kind``."""
    if kind in TEAM_KINDS:
        return format_key == MADISON
    if kind == FOUR_RACE:
        return format_key in FOUR_RACE_FORMATS
    return format_key != MADISON


@dataclass(frozen=True)
class RaceColumn:
    """One race a standings can draw on, with what the sheet prints about it."""

    race_id: int
    event_id: int
    event_name: str
    event_date: str  # ISO, as stored
    race_name: str
    group: str
    # "setup" (nothing scored), "running" (scored but not complete),
    # "provisional" (complete), or "final"
    state: str
    excluded: bool
    format: str = ""


@dataclass(frozen=True)
class MultiRaceRow:
    rank: int | None
    # The team's name, or the rider's when the kind's rows are riders.
    team: str
    color: str | None  # hex or a color name, as the board takes it
    riders: list[str]  # a team's pair; empty on a rider's row
    # One per column of the group's table; None where the team did not ride.
    per_race: list[int | float | None]
    total: int | float
    status: str  # "" or the aggregate engine's DNF / DQ
    # A rider's bib, the one they raced under last; None on a team's row.
    bib: int | None = None
    # The omnium penalty taken off the total, in points; 0 for none.
    penalty: int = 0
    # The rider's id, the penalty's key; None on a team's row.
    rider_id: int | None = None


@dataclass(frozen=True)
class GroupTable:
    group: str
    columns: list[RaceColumn]  # the counting races, by event date then program order
    rows: list[MultiRaceRow]
    riders: bool = False  # the rows are riders, not teams


@dataclass(frozen=True)
class Refusal:
    """Why there is no table: the rule, then each event short of it with a line per group.

    The rule leads in the refusal's red; the events under it are detail,
    laid out as the sheet's notes are, one line per fix.
    """

    lead: str
    # (the event's heading, "Race Night 12 (2026-Oct-16)", and its lines)
    nights: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def text(self) -> str:
        """The whole refusal as plain lines, for the tooltip and the tests."""
        parts = [self.lead]
        for heading, lines in self.nights:
            parts.append("\n".join([heading, *lines]))
        return "\n\n".join(parts)


@dataclass(frozen=True)
class MultiRaceTable:
    standings_id: int
    name: str
    kind: str
    kind_label: str
    detail: str  # how the kind scores, the sheet's sentence under the title
    state: str  # "final" once every counting race is final and none is still to race
    groups: list[GroupTable]
    left_out: list[RaceColumn]  # unticked by the scorer
    not_yet_raced: list[RaceColumn]  # in setup with nothing scored
    events: list[tuple[int, str, str]]  # (event_id, name, ISO date), oldest first
    # The count, "3 of 4 Madisons raced over 2 events": the dialog's line,
    # and the sheet's with the kind's name before it.
    counted: str = ""
    # Why there is no table: the Four-Race Omnium's ticked races short of
    # a format or with one doubled. None when the tables stand.
    refusal: Refusal | None = None
    # Running with riders not yet placed, and no column yet: a place
    # kind has no place to score for them.
    racing: list[RaceColumn] = field(default_factory=list)


def rules_for(standings: StandingsDef) -> AggregateRules:
    """The kind's values: its defaults, with whatever the standings stores on top.

    An empty stored page is the kind's defaults, so a file made before a
    default changes follows the change; a value the scorer set stays.
    """
    if standings.kind not in KINDS:
        raise ValueError(f"Unknown standings kind {standings.kind!r}")
    data = DEFAULTS[standings.kind]().to_dict()
    if standings.kind != FOUR_RACE:
        # The Four-Race Omnium's table is the rulebook's: a value left
        # over from another kind never sits over it.
        data.update(standings.rules or {})
    return AggregateRules.from_dict(data)  # type: ignore[return-value]


Sessions = dict[int, LiveRace]


def _session(store: Store, race_id: int, sessions: Sessions | None) -> LiveRace:
    """The race's replay, one per ``sessions``: the state and the table read the same one."""
    if sessions is None:
        return LiveRace(store, race_id, settle=False)
    if race_id not in sessions:
        sessions[race_id] = LiveRace(store, race_id, settle=False)
    return sessions[race_id]


def _race_state(store: Store, race: Race, sessions: Sessions | None = None) -> str:
    """Setup while nothing is scored, running while scored but not complete, provisional, or final.

    Read through ``LiveRace``, which settles a stored state the log no
    longer supports (a race marked final and then reopened by undo) as
    the surface does, so the standings never read a stale "final".
    """
    return _session(store, race.race_id, sessions).state


def candidate_races(
    store: Store, standings: StandingsDef, sessions: Sessions | None = None
) -> list[RaceColumn]:
    """Every race the kind can count in the ticked events, oldest event first, each in program order."""
    excluded = set(standings.excluded_race_ids)
    out: list[RaceColumn] = []
    # event_ids come oldest first from the store.
    for event_id in standings.event_ids:
        event = store.event(event_id)
        for race in store.races(event_id):
            if not race_counts(standings.kind, race.format):
                continue
            out.append(
                RaceColumn(
                    race_id=race.race_id,
                    event_id=event_id,
                    event_name=event.name,
                    event_date=event.event_date,
                    race_name=race_short_name(race),
                    group=race.group_label,
                    state=_race_state(store, race, sessions),
                    excluded=race.race_id in excluded,
                    format=race.format,
                )
            )
    return out


@dataclass
class _Team:
    """A pair of riders across races, with how it last showed."""

    entrant_id: int
    name: str = ""
    color: str | None = None
    riders: tuple[str, ...] = ()


@dataclass
class _Rider:
    """A rider across races, with the name and bib they last showed under."""

    name: str = ""
    bib: int | None = None


def _rode(per_race: list[Standings]) -> list[set[int]]:
    """Who rode each race: a DNF or DQ rode and keeps what it scored; a DNS or DNP did not."""
    return [{r.entrant_id for r in st.rows if r.status not in ("DNS", "DNP")} for st in per_race]


def _team_table(
    store: Store,
    rules: AggregateRules,
    group: str,
    columns: list[RaceColumn],
    sessions: Sessions | None = None,
) -> GroupTable:
    teams: dict[frozenset | tuple, _Team] = {}
    per_race: list[Standings] = []
    for column in columns:
        session = _session(store, column.race_id, sessions)
        local: dict[int, int] = {}
        for team in store.teams(column.race_id):
            # A team with nobody on it yet cannot be matched by its pair;
            # it stays its own row rather than merging with another.
            key = frozenset(team.members) if team.members else ("team", team.team_id)
            known = teams.setdefault(key, _Team(entrant_id=len(teams) + 1))
            local[team.team_id] = known.entrant_id
            entrant = session.roster.get(team.team_id)
            if entrant is not None:
                # Later races overwrite: the name and color it raced under last.
                known.name = entrant.team or entrant.short
                known.color = entrant.color_hex or (
                    entrant.color.lower() if entrant.color else None
                )
                known.riders = entrant.names
        st = session.standings()
        rows = tuple(
            replace(r, entrant_id=local[r.entrant_id]) for r in st.rows if r.entrant_id in local
        )
        per_race.append(replace(st, rows=rows))
    by_id = {t.entrant_id: t for t in teams.values()}
    # A team that rode fewer than every counting Madison is left out of
    # the table, as the venue's sheet leaves out a team that rode one
    # night of two: its one night against the others' two is no standing.
    present = _rode(per_race)
    rode_all = [eid for eid in by_id if all(eid in rode for rode in present)]
    result = compute_aggregate(rules, rode_all, per_race)
    rows = []
    for row in result.rows:
        team = by_id[row.entrant_id]
        rows.append(
            MultiRaceRow(
                rank=row.rank,
                team=team.name,
                color=team.color,
                riders=list(team.riders),
                per_race=[
                    points if row.entrant_id in present[i] else None
                    for i, points in enumerate(row.sprint_points)
                ],
                total=row.total_points,
                status=row.status or "",
            )
        )
    return GroupTable(group=group, columns=columns, rows=rows)


def _rider_table(
    store: Store,
    rules: AggregateRules,
    kind: str,
    group: str,
    columns: list[RaceColumn],
    sessions: Sessions | None = None,
    penalties: dict[int, int] | None = None,
) -> GroupTable:
    # An individual race's entrant ids are rider ids, so a rider is the
    # same row across events with no matching.
    riders: dict[int, _Rider] = {}
    per_race: list[Standings] = []
    for column in columns:
        session = _session(store, column.race_id, sessions)
        for rider_id in session.roster.ids:
            entrant = session.roster.get(rider_id)
            if entrant is None:
                continue
            # Later races overwrite: the name and bib they raced under last.
            known = riders.setdefault(rider_id, _Rider())
            known.name = entrant.names[0] if entrant.names else entrant.short
            known.bib = entrant.bibs[0] if entrant.bibs else None
        per_race.append(session.standings())
    # Everyone who rode any counting race is in the table, with nothing
    # for a race not ridden: there is no minimum. The Four-Race Omnium
    # keeps everyone on any of its fields instead: a rider who fails to
    # start one of its races has abandoned the omnium and is listed DNF
    # (USAC 2O2(c), 8D6(a)), a no-show in every race included.
    present = _rode(per_race)
    rode_any = [rid for rid in riders if any(rid in rode for rode in present)]
    if kind == FOUR_RACE:
        rode_any = list(riders)
        # The Points Race's points are summed raw, whichever column it is
        # in; the preset names the fourth of four. A tie on the total goes
        # to the final sprint of the last Points Race in the standings
        # (USAC 2O3(g)), which over two events is not the last column when
        # the second night's Points Race was left out under USAC 2O4.
        # Without any there is no final sprint to break a tie on, so
        # riders level on points share the place (USAC 1M6(a)).
        points_columns = tuple(i for i, c in enumerate(columns) if c.format == "points")
        rules = replace(
            rules,
            sum_total_races=points_columns,
            tie_break=rules.tie_break if points_columns else "none",
            final_sprint_race=points_columns[-1] if points_columns else None,
        )
    result = compute_aggregate(rules, rode_any, per_race, penalties)
    rows = []
    for row in result.rows:
        rider = riders[row.entrant_id]
        rows.append(
            MultiRaceRow(
                rank=row.rank,
                team=rider.name,
                color=None,
                riders=[],
                per_race=[
                    points if row.entrant_id in present[i] else None
                    for i, points in enumerate(row.sprint_points)
                ],
                total=row.total_points,
                status=row.status or "",
                bib=rider.bib,
                penalty=-row.adjust_points,
                rider_id=row.entrant_id,
            )
        )
    return GroupTable(group=group, columns=columns, rows=rows, riders=True)


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _counted(
    kind: str,
    counting: list[RaceColumn],
    left_out: list[RaceColumn],
    not_yet_raced: list[RaceColumn],
    events: int,
) -> str:
    """How many races are raced of those that count, over the ticked events; or why none is.

    "2 of 4 Madisons raced over 2 events": the events are the ticked ones,
    the same count the sheet's events line gives under it, so the two lines
    never contradict each other on a weekend half raced. ``not_yet_raced``
    holds the races still to run and those still running. With none
    counting, a scorer who unticked every race left them out, and the line
    says so: "no Madisons raced yet" would read false when they had been raced.
    """
    word = "race" if rider_kind(kind) else "Madison"
    if counting:
        raced = len(counting)
        total = raced + len(not_yet_raced)
        count = f"{raced} of {_count(total, word)}" if total > raced else _count(raced, word)
        return f"{count} raced over {_count(events, 'event')}"
    if left_out and not not_yet_raced:
        return f"every {word} left out"
    return f"no {word}s raced yet"


# A table longer than this is described, not printed, on the sheet's gray
# line, which holds two lines beside the count.
TABLE_PRINTED = 12


def place_table_text(points: tuple[int, ...] | None) -> str:
    """A place table as the sheet prints it, "7-5-3-2-1"; a long one as "40 places, 40 down to 1"."""
    points = tuple(points or ())
    if not points:
        return "no place points"
    if len(points) > TABLE_PRINTED:
        return f"{len(points)} places, {points[0]} down to {points[-1]}"
    return "-".join(str(p) for p in points)


def _detail(kind: str, rules: AggregateRules) -> str:
    """How the kind scores, in a sentence or two a reader of the sheet can check against."""
    if kind == PLACES:
        table = place_table_text(rules.points_by_place)
        return f"Each team scores points for its place in each Madison, {table}, and the points are summed."
    if kind == OMNIUM:
        table = place_table_text(rules.points_by_place)
        return f"Each rider scores points for their place in each race, {table}, and the points are summed."
    if kind == FOUR_RACE:
        # USAC 2O3(a), 2O3(b), 2O3(d): the table, the Points Race carried
        # in raw, and the rider out of any race listed after the ranked rows.
        return (
            "Places in the Scratch Race, Tempo Race, and Elimination score 40, 38, 36 and so on "
            "down to 2, then 1 from 21st, and the Points Race's own points are added. "
            "A rider who does not start, does not finish, or is disqualified in any race "
            "is listed after the ranked riders, as DNF or DQ."
        )
    return "Each team's Madison totals are summed."


def _four_race_refusal(
    ticked: list[RaceColumn], left_out: list[RaceColumn], events: list
) -> Refusal | None:
    """Why the ticked races are no Four-Race Omnium, or None when each event and group has its four.

    Checked over the races still to run too, so a program set up for the
    omnium passes before its first race, and a program short of a race is
    refused before the night rather than after. A ticked event with none
    of the four (an empty night, a Madison-only one, or every race
    unticked) is refused too: an event that counts for nothing is a slip.
    The one race the scorer may leave out is a group's Points Race (USAC
    2O4: when it can't be run, or stops under 80 percent and can't
    restart, the standings after the Elimination are the final
    classification), so a Points Race unticked is no refusal, while a
    program with none at all still is, since a forgotten race would
    otherwise make a three-race omnium final on its own. Events run in
    the ticked order and groups in the order they first race, so the
    lines read down the program the scorer fixes.
    """
    nights = []
    for event in events:
        sets: dict[str, list[RaceColumn]] = {}
        for column in ticked:
            if column.event_id == event.event_id:
                sets.setdefault(group_key(column.group), []).append(column)
        unticked_points = {
            group_key(c.group)
            for c in left_out
            if c.event_id == event.event_id and c.format == "points"
        }
        lines = []
        if not sets:
            lines.append(FOUR_RACE_NONE)
        for group, columns in sets.items():
            wrong = []
            for format_key in FOUR_RACE_FORMATS:
                n = sum(1 for c in columns if c.format == format_key)
                if n == 0 and format_key == "points" and group in unticked_points:
                    continue
                if n == 0:
                    wrong.append(f"no {format_label(format_key)}")
                elif n > 1:
                    wrong.append(f"{n} {format_label(format_key)}s")
            if wrong:
                lines.append(f"{columns[0].group.strip() or NO_GROUP}: {', '.join(wrong)}")
        if lines:
            nights.append((f"{event.name} ({show_date(event.event_date)})", tuple(lines)))
    if not nights:
        return None
    return Refusal(FOUR_RACE_NEED, tuple(nights))


def _everyone_placed(session: LiveRace) -> bool:
    """Whether the race ranks every rider still in it as it stands."""
    return all(r.rank is not None for r in session.standings().rows if r.status is None)


def _omnium_order(columns: list[RaceColumn]) -> list[RaceColumn]:
    """The Four-Race Omnium's columns: each event's four in the order they are ridden."""
    events = list(dict.fromkeys(c.event_id for c in columns))
    return sorted(
        columns, key=lambda c: (events.index(c.event_id), FOUR_RACE_FORMATS.index(c.format))
    )


def compute(store: Store, standings_id: int, sessions: Sessions | None = None) -> MultiRaceTable:
    """The standings as the sheet prints them, replayed from the races now.

    ``sessions`` lends replays the caller keeps across computes; it is
    only safe while nothing can score a race, as a session reads its
    race once.
    """
    standings = store.get_standings(standings_id)
    kind = standings.kind
    rules = rules_for(standings)
    # Each race replayed once for its state and its table alike.
    sessions = {} if sessions is None else sessions
    candidates = candidate_races(store, standings, sessions)
    events = [store.event(e) for e in standings.event_ids]
    left_out = [c for c in candidates if c.excluded]
    ticked = [c for c in candidates if not c.excluded]
    not_yet_raced = [c for c in ticked if c.state == "setup"]
    # A place kind scores places, and a running race has none for the
    # riders it has not placed: an Elimination half run would rank the
    # riders already out above the riders still in. A race that ranks
    # every rider as it runs (a Points Race or Madison, by points held)
    # counts as it stands, as the totals kind always does.
    racing = [
        c
        for c in ticked
        if c.state == "running" and kind != TOTALS and not _everyone_placed(sessions[c.race_id])
    ]
    counting = [c for c in ticked if c.state != "setup" and c not in racing]
    refusal = None
    if kind == FOUR_RACE:
        refusal = _four_race_refusal(ticked, left_out, events)
        counting = _omnium_order(counting)
    # Groups in the order they first race; a label typed two ways is one group.
    by_group: dict[str, list[RaceColumn]] = {}
    for column in counting:
        by_group.setdefault(group_key(column.group), []).append(column)
    groups: list[GroupTable] = []
    if not refusal:
        for columns in by_group.values():
            if rider_kind(kind):
                # The omnium penalty is the Four-Race Omnium's rule (USAC
                # 2O3(e)); the other kinds have no article for one.
                penalties = standings.penalties if kind == FOUR_RACE else None
                groups.append(
                    _rider_table(store, rules, kind, columns[0].group, columns, sessions, penalties)
                )
            else:
                groups.append(_team_table(store, rules, columns[0].group, columns, sessions))
    # A race still to run can change every total, so a weekend half
    # raced is provisional even when each race run so far is final.
    final = (
        bool(counting)
        and not refusal
        and not not_yet_raced
        and not racing
        and all(c.state == "final" for c in counting)
    )
    counted = _counted(kind, counting, left_out, not_yet_raced + racing, len(events))
    return MultiRaceTable(
        standings_id=standings.standings_id,
        name=standings.name,
        kind=kind,
        kind_label=KINDS[kind],
        detail=_detail(kind, rules),
        state="final" if final else "provisional",
        groups=groups,
        left_out=left_out,
        not_yet_raced=not_yet_raced,
        events=[(e.event_id, e.name, e.event_date) for e in events],
        counted=counted,
        refusal=refusal,
        racing=racing,
    )
