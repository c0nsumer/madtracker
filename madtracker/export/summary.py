"""One race as plain rows, shared by the PDF and the USAC CSV.

Both outputs read their place, names, license and status from here, so
the printed sheet and the file uploaded to USAC cannot disagree. Standings
come from LiveRace (a replay of the live action log) and names, bibs
and teams from its Roster; this module only adds what neither carries:
licenses, groups, which sprints have been run, and display wording.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from madtracker.control import rulesets
from madtracker.control.describe import (
    STATUS_WORDS,
    race_ended_note,
    race_shortened_note,
    row_note,
)
from madtracker.control.formats import TEAM_COLORS
from madtracker.control.race import LiveRace
from madtracker.dates import show_time
from madtracker.scoring import rules as R
from madtracker.scoring._common import statuses
from madtracker.scoring.actions import Action, FinishOrder, SprintResult
from madtracker.scoring.result import Standing, Standings
from madtracker.store import Race, Store

# Jersey colors madison teams are named by, for a team saved with a
# color name but no hex value. Anything else prints a neutral gray.
# A team saved without a hex is drawn in its color's hex from the one
# table the setup screen uses, so the sheet and the screen agree.
COLOR_HEX = {name.lower(): hex_ for name, hex_ in TEAM_COLORS.items()}
COLOR_HEX["gray"] = COLOR_HEX["grey"] = TEAM_COLORS["Silver"]
NEUTRAL_HEX = "#9aa0a6"

# Only these races are final enough to publish or upload.
FINISHED_STATES = ("provisional", "final")


@dataclass(frozen=True)
class RiderInfo:
    rider_id: int
    first: str
    last: str
    license: str
    bib: int | None
    group: str

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()


@dataclass(frozen=True)
class ResultRow:
    """One entrant's line: a rider, or a team with its members.

    place is the text for the Place column and the CSV: the integer rank,
    or DNF, DNS, DQ or DNP. A status wins over a rank because the engines
    rank the DNF group (tied, after the finishers) while USAC wants the
    word, except where the engine placed the rider by the race's own rule
    (``Standing.placed``: an elimination puts a DNF out at that moment and
    that is a place). Such a row prints its number and carries the status
    in ``note``, so the sheet says why beside the name. An unranked row
    with no status is a rider the scorer never placed; it is reported as
    DNP rather than left blank so the file never carries a rider with no
    place.
    """

    entrant_id: int
    place: str
    rank: int | None
    status: str | None
    riders: tuple[RiderInfo, ...]
    placed: bool = False
    note: str = ""
    team: str | None = None
    color_hex: str | None = None
    sprint_points: tuple[int, ...] = ()
    laps_gained: int = 0
    laps_lost: int = 0
    lap_points: int = 0
    # The officials' points rulings, negative for a penalty, 0 when none
    # (USAC 8D5(b)); the sheet prints a Penalty column only when a row has one.
    adjust_points: int = 0
    total_points: int | float = 0

    @property
    def is_finisher(self) -> bool:
        return self.placed


@dataclass(frozen=True)
class RaceSummary:
    race: Race
    kind: str
    format_label: str
    rules_line: str
    rows: tuple[ResultRow, ...]
    sprint_count: int
    is_team: bool
    # The sprints scored so far, the finish order counting as the final
    # sprint; a sprint not in it prints blank, since its 0 is not yet a fact.
    sprints_run: frozenset[int] = frozenset()
    # The last sprint ridden when the officials let the results stand
    # (USAC 2M6, 2N5), None for a race that ran its distance.
    ended_after: int | None = None
    # (set, in force) when the officials shortened the race (USAC 1G4(b)),
    # None for a race ridden to the count it was set with.
    shortened: tuple[int, int] | None = None

    @property
    def finishers(self) -> int:
        return sum(1 for row in self.rows if row.is_finisher)


def rules_in_force(rules: R._Rules, standings: Standings) -> R._Rules:
    """The race's rules with the sprint count its standings are scored on.

    A race the officials shortened (USAC 1G4(b)) is ridden, scored, and
    shown on the count it was shortened to, while the race keeps the
    count it was set with; the sheet and the board read the one in force.
    """
    count = standings.sprint_count
    if not isinstance(rules, R.SprintPointsRules) or count in (None, rules.sprint_count):
        return rules
    return replace(rules, sprint_count=count)


def shortened_from(rules: R._Rules, standings: Standings) -> tuple[int, int] | None:
    """(set, in force) for a shortened race's note, or None."""
    count = standings.sprint_count
    set_count = getattr(rules, "sprint_count", None)
    if count is None or set_count is None or count == set_count:
        return None
    return set_count, count


def sprints_run(rules: R._Rules, actions: Sequence[Action]) -> tuple[frozenset[int], int | None]:
    """The sprint numbers scored so far, and the number the finish order scores as.

    One reading of the log for the sheet and the board, so the two agree
    on what "run" means: a recorded sprint, and the finish order as the
    final sprint (the race's count, or one past the highest recorded when
    the count is open).
    """
    run = {a.sprint_no for a in actions if isinstance(a, SprintResult)}
    finish = any(isinstance(a, FinishOrder) for a in actions)
    count = getattr(rules, "sprint_count", None)
    final_no = count if count is not None else (max(run, default=0) + 1 if finish else None)
    if finish and final_no is not None:
        run.add(final_no)
    return frozenset(run), final_no


def place_text(row: Standing) -> str:
    if row.placed:
        return str(row.rank)
    if row.status:
        return row.status
    return "DNP"


def status_note(row: Standing, reason: str | None) -> str:
    """Why a placed row is not a plain finish, for beside the name: the
    status it still carries, the mishap that kept the rider out of the
    final sprint (placed on points, USAC 2M8(a)), or the withdrawal that
    placed them by its moment (USAC 2O3(e), 1M6(d))."""
    if not row.placed:
        return ""
    if not row.status:
        return row_note(row.out_of_finish, row.laps_not_counted, row.withdrawn)
    words = STATUS_WORDS.get(row.status, row.status)
    reason = " ".join((reason or "").split())
    return f"{words}: {reason}" if reason else words


def format_number(value: int | float) -> str:
    """A points figure for the sheet, with the board's minus below zero."""
    from madtracker.board.payloads import total_text

    return total_text(value)


def local_clock(utc_iso: str) -> str:
    """A stored UTC stamp as the one clock every shown time uses, "9:45 PM"."""
    try:
        return show_time(datetime.fromisoformat(utc_iso).astimezone())
    except ValueError:
        return utc_iso


# The window's words for a race's state, so the sheet and the screen read
# the same beside each other.
STATE_WORDS = {
    "setup": "Start list",
    "running": "Racing",
    "provisional": "Provisional",
    "final": "Final",
}


def stand_words(after_sprint: int) -> str:
    """'Race ended after 3 sprints': a race the officials ended short of its distance."""
    return race_ended_note(after_sprint)


def state_line(
    race: Race,
    tagged: bool = False,
    ended_after: int | None = None,
    shortened: tuple[int, int] | None = None,
) -> str:
    """The gray line's state part: the window's word, with the time a result was announced.

    With ``tagged`` the heading's own tag (IN PROGRESS, PROVISIONAL,
    FINAL) already names the state, so the line carries only the time, or
    nothing: one heading must not read "IN PROGRESS" and "Racing" at once.
    A race ended with its results standing says so once, beside the state,
    since its table stops short of the sprint count the rules line names.
    A shortened race names the count it was set with beside the one the
    rules line names, so the program sheet's count reads back.
    """
    parts = [] if tagged else [STATE_WORDS.get(race.state, race.state.title())]
    if shortened is not None:
        parts.append(race_shortened_note(*shortened))
    if ended_after is not None:
        parts.append(stand_words(ended_after))
    if race.state in FINISHED_STATES and race.announced_utc:
        parts.append(f"announced {local_clock(race.announced_utc)}")
    # Only the line's first word is capitalized: "Provisional, race ended after ...".
    parts[1:] = [p[:1].lower() + p[1:] for p in parts[1:]]
    if parts:
        parts[0] = parts[0][:1].upper() + parts[0][1:]
    return ", ".join(parts)


def _points(values: tuple[int, ...]) -> str:
    return "-".join(str(v) for v in values)


def _table(values: tuple[int, ...]) -> str:
    """A sprint table as a rider reads it; one scoring place says so rather than print a lone number."""
    if len(values) == 1:
        return f"{values[0]} point{'' if values[0] == 1 else 's'} to the winner"
    return _points(values)


def sprint_words(rules: R.SprintPointsRules) -> str:
    """How a race's sprints award points, from the race's own rules: '4 sprints, 5-3-2-1, double points for the last sprint'.

    The one wording for the program and the results, so the two sheets
    never say the same race two ways. Every number comes from
    the rules the race is scored with, never the rulebook's.
    """
    parts = []
    if rules.sprint_count:
        parts.append(f"{rules.sprint_count} sprint{'' if rules.sprint_count == 1 else 's'}")
    if rules.points_by_sprint is not None:
        parts.append("points set per sprint")
        return ", ".join(parts)
    middle, last = tuple(rules.intermediate_points), tuple(rules.final_points)
    parts.append(_table(middle))
    if last == tuple(2 * p for p in middle):
        parts.append("double points for the last sprint")
    elif last != middle:
        parts.append(f"last sprint {_points(last) if len(last) > 1 else f'{last[0]} points'}")
    return ", ".join(parts)


def lap_words(gained: int, lost: int) -> str:
    """'laps ±20', or each value when a ruleset makes them differ."""
    if gained == lost:
        return f"laps \u00b1{gained}"
    return f"lap gained +{gained}, lap lost \u2212{lost}"


def rules_line(rules: R._Rules) -> str:
    """The rules a reader needs to check the arithmetic, on one line."""
    if isinstance(rules, R.SprintPointsRules):
        return f"{sprint_words(rules)}; {lap_words(rules.lap_gained_points, rules.lap_lost_points)}"
    if isinstance(rules, R.EliminationRules):
        return f"Last rider over the line is out; {rules.survivors} riders in the final"
    if isinstance(rules, R.WinAndOutRules):
        # The direction decides who is 1st, and the sheet must show it: the
        # same clicks put the first lap's winner 1st or last of the places.
        first = "first" if rules.direction == "forward" else "last"
        return f"{rules.places} places, the {first} lap's winner takes 1st"
    if isinstance(rules, R.PlacingsRules):
        return "Placed by finish order" + (
            ", laps gained ahead" if rules.laps_count_for_ranking else ""
        )
    return ""


def _riders(store: Store, session: LiveRace) -> dict[int, RiderInfo]:
    event_id = session.race.event_id
    infos: dict[int, RiderInfo] = {}
    for entry, rider in store.entries_with_riders(event_id):
        rider_id = entry.rider_id
        infos[rider_id] = RiderInfo(
            rider_id=rider_id,
            first=rider.first_name.strip(),
            last=rider.last_name.strip(),
            license=(rider.usac_license or "").strip(),
            bib=entry.bib,
            group=(entry.local_group or "").strip(),
        )
    return infos


def build_summary(store: Store, race: Race) -> RaceSummary:
    session = LiveRace(store, race.race_id, settle=False)
    standings = session.standings()
    infos = _riders(store, session)
    is_team = session.roster.is_team
    teams = {t.team_id: t for t in store.teams(race.race_id)} if is_team else {}

    actions = session.actions()
    reasons = {eid: mark.reason for eid, mark in statuses(actions).items()}

    rules = rules_in_force(session.rules, standings)
    sprint_count = 0
    if isinstance(rules, R.SprintPointsRules):
        sprint_count = rules.sprint_count or 0
    sprint_count = max([sprint_count, *(len(s.sprint_points) for s in standings.rows)])
    ended_after = None
    if standings.ended:
        # Results stand on the sprints ridden: no empty columns for the rest.
        ended_after = max((a.sprint_no for a in actions if isinstance(a, SprintResult)), default=0)
        sprint_count = ended_after

    rows = []
    for st in standings.rows:
        team = None
        color_hex = None
        if is_team:
            t = teams.get(st.entrant_id)
            members = t.members if t else ()
            entrant = session.roster.get(st.entrant_id)
            team = entrant.short if entrant else f"Team {st.entrant_id}"
            color_hex = (t.color_hex if t else None) or COLOR_HEX.get(
                (t.color if t else "").strip().lower(), NEUTRAL_HEX
            )
        else:
            members = (st.entrant_id,)
        riders = tuple(infos[m] for m in members if m in infos)
        rows.append(
            ResultRow(
                entrant_id=st.entrant_id,
                place=place_text(st),
                rank=st.rank,
                status=st.status,
                riders=riders,
                placed=st.placed,
                note=status_note(st, reasons.get(st.entrant_id)),
                team=team,
                color_hex=color_hex,
                sprint_points=st.sprint_points,
                laps_gained=st.laps_gained,
                laps_lost=st.laps_lost,
                lap_points=st.lap_points,
                adjust_points=st.adjust_points,
                total_points=st.total_points,
            )
        )
    return RaceSummary(
        race=race,
        kind=session.kind,
        format_label=rulesets.race_format_name(race),
        rules_line=rules_line(rules),
        rows=tuple(rows),
        sprint_count=sprint_count,
        is_team=is_team,
        sprints_run=sprints_run(rules, actions)[0],
        ended_after=ended_after,
        shortened=shortened_from(session.rules, standings),
    )
