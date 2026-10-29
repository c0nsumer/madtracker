"""Placings engine: races ranked by the order across the line.

Covers the scratch race (often called "Chase"), handicap (USAC 2D5:
run as a scratch race after the start), unknown distance, chariot,
keirin finals and match sprint finals: any heat or final the judges
rank at the line, with laps gained or lost sorting first when the
rules say so (USAC 2C5 "Finish", UCI 3.2.178).

Inputs: LapGained, LapLost, LapNotCounted, FinishOrder, Status,
Withdrawn. Sprint results, eliminations and points rulings are rejected
by validate().

A withdrawn rider (Withdrawn, USAC 2O3(e), 1M6(d)) is out of the field
the finish order names and ranks after every finisher, among the
withdrawn by the moment of it, the latest highest; the row prints its
number. Laps count for nothing there: the rank is the moment's.
"""

from collections.abc import Sequence
from dataclasses import replace

from ._common import (
    RESULTS_STAND_REFUSAL,
    SHORTEN_REFUSAL,
    active_entrants,
    assemble,
    group_by_key,
    lap_counts,
    laps_cancelled,
    last_finish_order,
    place_map,
    statuses,
    validate_common,
    withdrawn,
)
from .actions import (
    Action,
    Eliminated,
    FinishOrder,
    LapNotCounted,
    OutOfFinish,
    PointsAdjusted,
    RaceEnded,
    RaceShortened,
    SprintResult,
    Status,
)
from .result import Standing, Standings, rank_groups
from .rules import PlacingsRules

_UNPLACED = 10**6  # sorts after every real place


def compute(rules: PlacingsRules, entrants: Sequence[int], actions: Sequence[Action]) -> Standings:
    status = dict(statuses(actions))
    laps = lap_counts(actions)
    cancelled = laps_cancelled(actions)
    finish = last_finish_order(actions)
    gone = withdrawn(actions)

    rows: dict[int, Standing] = {}
    for eid in entrants:
        gained, lost = laps.get(eid, (0, 0))
        rows[eid] = Standing(
            entrant_id=eid,
            laps_gained=gained,
            laps_lost=lost,
            laps_not_counted=cancelled.get(eid, 0),
        )

    # UCI 3.2.177: a lapped rider leaves the track at once. If the scorer
    # still recorded them at the line, they rank with the withdrawn riders
    # rather than among the finishers (UCI 3.3.012 A). Under USAC 2C4 the
    # same rider is placed by laps down, which the sort below does. A
    # rider marked Withdrawn is placed by that moment already, laps or
    # not, so the conversion leaves them alone.
    if rules.laps_count_for_ranking and not rules.lapped_riders_placed_by_laps:
        for eid in active_entrants(entrants, status):
            if rows[eid].net_laps < 0 and eid not in gone:
                status[eid] = Status(
                    entrant_id=eid,
                    status="DNF",
                    reason="lapped, must leave the track (UCI 3.2.177)",
                )

    active = [eid for eid in active_entrants(entrants, status) if eid not in gone]
    if finish is None:
        return Standings(
            rows=assemble(entrants, rows, status, leading_unranked=active, withdrawn=gone),
            remaining_entrants=tuple(active),
            is_complete=False,
        )

    places = place_map(finish.places)
    for eid in active:
        rows[eid] = replace(rows[eid], final_sprint_place=places.get(eid))

    def key(eid: int) -> tuple:
        place = places.get(eid, _UNPLACED)
        if rules.laps_count_for_ranking:
            return (-rows[eid].net_laps, place)
        return (place,)

    # Riders the judges could not place share the next rank after the
    # placed riders on the same lap (USAC 1M6(a) equal placing).
    ordered = sorted(((key(eid), eid) for eid in active), key=lambda pair: pair[0])
    groups = group_by_key(ordered)
    ranked, next_rank = rank_groups([[rows[eid] for eid in group] for group in groups])
    for group in groups:
        if len(group) > 1 and any(eid not in places for eid in group):
            ranked = [
                r.with_note("Shared place: not separated by the judges")
                if r.entrant_id in group and r.entrant_id not in places
                else r
                for r in ranked
            ]
    return Standings(
        rows=assemble(entrants, rows, status, ranked=ranked, next_rank=next_rank, withdrawn=gone),
        remaining_entrants=(),
        is_complete=True,
    )


def validate(
    rules: PlacingsRules, entrants: Sequence[int], actions: Sequence[Action], new_action: Action
) -> list[str]:
    problems = validate_common(entrants, actions, new_action)
    if isinstance(new_action, SprintResult):
        problems.append("Sprint results are not scored in a placings race; enter the finish order")
    if isinstance(new_action, Eliminated):
        problems.append("Eliminations are not scored in a placings race")
    if isinstance(new_action, OutOfFinish):
        # No points to place the rider on: USAC 2C5(b) says such a rider
        # "will not appear in the final placings", and the scorer marks
        # them as the officials rule.
        problems.append("Out of the finish is scored in a Points Race, Madison, or Tempo Race only")
    if isinstance(new_action, PointsAdjusted):
        problems.append("A points penalty is scored in a Points Race, Madison, or Tempo Race only")
    if isinstance(new_action, RaceEnded):
        # The Scratch Race's stoppage rule is a restart or a rerun (USAC 2C).
        problems.append(RESULTS_STAND_REFUSAL)
    if isinstance(new_action, RaceShortened):
        # No sprint count to shorten: a shortened Scratch Race is entered
        # as it finishes (USAC 1G4(b)).
        problems.append(SHORTEN_REFUSAL)
    if isinstance(new_action, LapNotCounted) and not rules.laps_count_for_ranking:
        problems.append("Laps do not count in this race")
    if isinstance(new_action, FinishOrder) and not new_action.places:
        problems.append("The finish order is empty")
    return problems
