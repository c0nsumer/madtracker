"""Sprint points engine: points race, madison and tempo.

Everything here is rank-by-points. The rules object supplies the sprint
count and the points tables; the engine applies the rules the two
books share (UCI 3.2.118, 3.2.119, 3.2.125, 3.2.161, 3.2.162;
USAC 2M2(f), 2M2(g), 2M3(d), 2N2(g), 2N2(h)):

- A tie in a sprint shares the place and its points and the next place
  is skipped: two tied for first both score 5 and nobody scores 3.
- A lap gained at a sprint adds the lap points and the sprint points.
- Laps are only points, never a sort key. A rider a lap down can win.
- A tie on total is broken by the place in the final sprint, read from
  the full FinishOrder, not just the scoring places.
- A rider marked DNF keeps the points shown and ranks in the DNF group
  after every finisher (UCI 3.3.012 A). DNS, DQ and DNP are never ranked.
- A race ended with its results standing (RaceEnded, USAC 2M6, 2N5:
  "Race stopped after 80%: Let results stand") is complete on the
  sprints ridden. No sprint doubles and there is no final-sprint place,
  so riders level on points share the rank.
- A race the officials shortened (RaceShortened, USAC 1G4(b)) is
  scored on the count it was shortened to: the last sprint under that
  count is the final sprint, doubled with the finish order and breaking
  ties on its places (USAC 2M2(f), 2M2(g)), as the last sprint after
  the full distance. The latest entry is the count in force.
- A points penalty the officials rule (PointsAdjusted, USAC 8D5(b))
  comes off the total and nothing else; a lap ruled not counted
  (LapNotCounted) takes back a lap gained and its points. Both may come
  after the finish order, as rulings do.

The final sprint is the sprint numbered by the count in force. Its
places come from a SprintResult with that number when the scorer entered
one, otherwise from the FinishOrder, so one full-order entry at the line
can serve as both the final sprint and the tie-break order. A race with
no sprint count takes no entries: without it the engine cannot know
which sprint doubles, and scoring the finish as one more sprint would
invent a sprint nobody rode. The finish order is refused until every
earlier sprint is in, and the race is complete only once the finish
order is recorded, because the tie-break reads the full order of
everyone still in (UCI 3.2.119, USAC 2M2(g)), which a SprintResult
that awards four places does not give.

A rider kept out of the finish by a mishap (OutOfFinish, USAC 2M7(b),
2M8(a)) is not marked and is not in the finish order, so the ranking
above already places them on their points and laps, below anyone level
with them who has a final-sprint place (USAC 2M2(g)). The entry is taken
only once every sprint but the last is recorded, since before that the
rider could still return, and it takes the rider out of the field the
finish order must name.

A withdrawn rider (Withdrawn, USAC 2O3(e), 1M6(d)) is out of the field
from that moment: no later sprint names them, and they rank after
every finisher, among the withdrawn by the moment, the latest highest,
never on points. The points and laps held stay as figures on the row.
"""

from collections.abc import Sequence
from dataclasses import replace

from ._common import (
    active_entrants,
    adjustments,
    assemble,
    group_by_key,
    lap_counts,
    laps_cancelled,
    last_finish_order,
    out_of_finish,
    place_map,
    race_ended,
    shortened_count,
    statuses,
    validate_common,
    withdrawn,
)
from .actions import (
    Action,
    Eliminated,
    FinishOrder,
    LapGained,
    OutOfFinish,
    RaceEnded,
    RaceShortened,
    SprintResult,
    Status,
    Withdrawn,
)
from .result import Standing, Standings, rank_groups
from .rules import SprintPointsRules

_UNPLACED = 10**6


def award(places: Sequence[Sequence[int]], table: Sequence[int]) -> dict[int, int]:
    """Points per entrant for one sprint.

    A tied group all take the points of the place they tied for and the
    next len(group) - 1 places go unawarded (UCI 3.2.118, USAC 2M2(f)(i)).
    An empty group is a place the judges did not call: nobody takes it.
    """
    out: dict[int, int] = {}
    index = 0
    for group in places:
        points = table[index] if index < len(table) else 0
        for eid in group:
            out[eid] = points
        index += max(1, len(group))
    return out


def _sprint_results(actions: Sequence[Action]) -> tuple[dict[int, SprintResult], list[str]]:
    """Sprint number to result, last entry per number winning, with a
    note for each replaced entry so a re-entered sprint is visible."""
    out: dict[int, SprintResult] = {}
    notes: list[str] = []
    for action in actions:
        if isinstance(action, SprintResult):
            if action.sprint_no in out:
                notes.append(f"Sprint {action.sprint_no} was entered twice; the later entry counts")
            out[action.sprint_no] = action
    return out, notes


def rules_in_force(rules: SprintPointsRules, actions: Sequence[Action]) -> SprintPointsRules:
    """The rules with the sprint count the log puts in force.

    A shortened race (USAC 1G4(b)) doubles its new last sprint, so the
    points tables read the count it was shortened to, never the race's
    own count, which stays as it was set.
    """
    count = shortened_count(actions)
    if count is None or count == rules.sprint_count:
        return rules
    return replace(rules, sprint_count=count)


def compute(
    rules: SprintPointsRules, entrants: Sequence[int], actions: Sequence[Action]
) -> Standings:
    rules = rules_in_force(rules, actions)
    status = statuses(actions)
    laps = lap_counts(actions)
    finish = last_finish_order(actions)
    mishaps = out_of_finish(actions)
    gone = withdrawn(actions)
    adjusted = adjustments(actions)
    cancelled = laps_cancelled(actions)
    sprints, notes = _sprint_results(actions)
    ended = race_ended(actions) is not None and finish is None

    count = rules.sprint_count
    highest = max(sprints, default=0)
    # The column count the table shows: the count, or with none the
    # sprints entered (validate() refuses entries then, so this only
    # covers a log written past the refusal). A race ended with its
    # results standing shows the sprints ridden and no empty final.
    final_no = count if count is not None else highest
    columns = highest if ended else max(final_no, highest)

    points: dict[int, dict[int, int]] = {eid: {} for eid in entrants}
    for sprint_no, result in sprints.items():
        for eid, pts in award(result.places, rules.points_for_sprint(sprint_no)).items():
            if eid in points:
                points[eid][sprint_no] = pts
    if finish is not None and count is not None and final_no not in sprints:
        table = rules.points_for_sprint(final_no)
        for eid, pts in award(finish.places, table).items():
            if eid in points:
                points[eid][final_no] = pts

    final_places: dict[int, int] = {}
    if finish is not None:
        final_places = place_map(finish.places)
    elif final_no in sprints:
        final_places = place_map(sprints[final_no].places)

    rows: dict[int, Standing] = {}
    for eid in entrants:
        gained, lost = laps.get(eid, (0, 0))
        per_sprint = tuple(points[eid].get(n, 0) for n in range(1, columns + 1))
        lap_points = gained * rules.lap_gained_points - lost * rules.lap_lost_points
        adjust = adjusted.get(eid, 0)
        rows[eid] = Standing(
            entrant_id=eid,
            total_points=sum(per_sprint) + lap_points + adjust,
            sprint_points=per_sprint,
            laps_gained=gained,
            laps_lost=lost,
            lap_points=lap_points,
            adjust_points=adjust,
            laps_not_counted=cancelled.get(eid, 0),
            final_sprint_place=final_places.get(eid),
            out_of_finish=eid in mishaps and eid not in status,
        )

    def key(eid: int) -> tuple:
        row = rows[eid]
        if rules.tie_break == "final_sprint":
            return (-row.total_points, final_places.get(eid, _UNPLACED))
        return (-row.total_points,)

    active = [eid for eid in active_entrants(entrants, status) if eid not in gone]
    ordered = sorted(((key(eid), eid) for eid in active), key=lambda pair: pair[0])
    groups = group_by_key(ordered)
    ranked, next_rank = rank_groups([[rows[eid] for eid in group] for group in groups])
    ranked = [
        replace(r, rank=None, tied=False) if not sprints and finish is None else r for r in ranked
    ]

    complete = finish is not None or ended
    # The field the finish order must still name: a rider out of the
    # finish is placed already, on points.
    remaining = [eid for eid in active if eid not in mishaps]
    return Standings(
        rows=assemble(entrants, rows, status, ranked=ranked, next_rank=next_rank, withdrawn=gone),
        next_sprint_no=highest + 1,
        remaining_entrants=() if complete else tuple(remaining),
        is_complete=complete,
        ended=ended,
        sprint_count=count,
        notes=tuple(notes),
    )


def validate(
    rules: SprintPointsRules, entrants: Sequence[int], actions: Sequence[Action], new_action: Action
) -> list[str]:
    problems = validate_common(entrants, actions, new_action)
    rules = rules_in_force(rules, actions)
    count = rules.sprint_count
    if count is None:
        return ["This race has no sprint count"]
    sprints, _ = _sprint_results(actions)
    mishaps = out_of_finish(actions)
    if isinstance(new_action, SprintResult):
        n = new_action.sprint_no
        if n < 1:
            problems.append("Sprint numbers start at 1")
        elif n > count:
            problems.append(f"Sprint {n} is beyond the {count} sprints in this race")
        elif n in sprints:
            problems.append(f"Sprint {n} is already recorded; void it to re-enter")
        else:
            # Sequence by number, not by log position: every sprint below
            # this one must be recorded somewhere in the log. A corrected
            # sprint sits at the end of the live log, after sprints it was
            # ridden before, and compute keys by number the same way.
            missing = next((k for k in range(1, n) if k not in sprints), None)
            if missing is not None:
                problems.append(f"Expected sprint {missing}, got {n}")
        if not any(new_action.places):
            problems.append("No places entered")
        if n == count:
            for eid in dict.fromkeys(e for g in new_action.places for e in g):
                if eid in mishaps:
                    problems.append(
                        f"Entrant {eid} is out of the finish and cannot be placed in it"
                    )
    elif isinstance(new_action, LapGained):
        if new_action.sprint_no is not None and new_action.sprint_no > count:
            problems.append(
                f"Sprint {new_action.sprint_no} is beyond the {count} sprints in this race"
            )
    elif isinstance(new_action, FinishOrder):
        # The finish is the final sprint; an earlier sprint left out would
        # silently score zero for everyone in it.
        missing = [n for n in range(1, count) if n not in sprints]
        if missing:
            problems.append(f"Sprint {missing[0]} of {count} has not been recorded")
        for eid in dict.fromkeys(e for g in new_action.places for e in g):
            if eid in mishaps:
                problems.append(f"Entrant {eid} is out of the finish and cannot be placed in it")
    elif isinstance(new_action, Withdrawn):
        # A rider out of the finish is placed on points (USAC 2M8(a));
        # the withdrawal would move them to a rank by its moment.
        if new_action.entrant_id in mishaps:
            problems.append(
                f"Entrant {new_action.entrant_id} is out of the finish and placed on points"
            )
    elif isinstance(new_action, OutOfFinish):
        eid = new_action.entrant_id
        if eid in mishaps:
            problems.append(f"Entrant {eid} is already out of the finish")
        # Only once the last kilometer can have started: every sprint but
        # the final one is in. Before that the rider may still return
        # (USAC 2M7(a)), and the entry would take them out of a sprint
        # they could ride.
        missing = [n for n in range(1, count) if n not in sprints]
        if missing:
            problems.append(
                f"Out of the finish applies during the final sprint; sprint {missing[0]}"
                f" of {count} has not been recorded"
            )
        if count in sprints and eid in {e for g in sprints[count].places for e in g}:
            problems.append(f"Entrant {eid} is placed in the final sprint")
    elif isinstance(new_action, Status) and new_action.status in ("DNS", "DNF"):
        # The rule places them (USAC 2M8(a)); a DQ may still follow a protest.
        if new_action.entrant_id in mishaps:
            problems.append(
                f"Entrant {new_action.entrant_id} is out of the finish and placed on points;"
                f" it cannot be marked {new_action.status}"
            )
    elif isinstance(new_action, Eliminated):
        problems.append("Eliminations are not scored in a Points Race, Madison, or Tempo Race")
    elif isinstance(new_action, RaceEnded):
        # Results stand on the sprints ridden (USAC 2M6, 2N5): there must
        # be some, the final sprint must not be in (then the race is
        # complete as ridden), and the entry names the sprint it stopped
        # after, so the log reads back where the race ended.
        highest = max(sprints, default=0)
        if race_ended(actions) is not None:
            problems.append("The race has already ended with its results standing")
        elif last_finish_order(actions) is not None or count in sprints:
            problems.append("The final sprint is recorded; the race is complete as ridden")
        elif not sprints:
            problems.append("No sprint is recorded, so no result can stand")
        elif new_action.after_sprint != highest:
            problems.append(f"The last sprint recorded is {highest}, not {new_action.after_sprint}")
    elif isinstance(new_action, RaceShortened):
        # The race rides on to a new, earlier finish (USAC 1G4(b)): the
        # count goes below the one in force and stays above every sprint
        # ridden, since a race stopped at a sprint already ridden is a
        # race ended with its results standing, not a shorter one.
        n = new_action.sprint_count
        highest = max(sprints, default=0)
        if race_ended(actions) is not None:
            problems.append("The race has ended with its results standing; undo that first")
        elif last_finish_order(actions) is not None or count in sprints:
            problems.append("The final sprint is recorded; the race is complete as ridden")
        elif n >= count:
            problems.append(f"The race has {count} sprints; shorten it to fewer")
        elif n < 1:
            problems.append("A race has at least one sprint")
        elif n <= highest:
            problems.append(
                f"Sprint {highest} is recorded; shorten to at least Sprint {highest + 1}"
            )
    # A PointsAdjusted of either sign scores as written: negative as the
    # penalty grows (8D5(b)), positive as it is lowered, which
    # validate_common holds to the penalty standing.
    return problems
