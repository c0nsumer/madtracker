"""Elimination engine: the elimination race, also called the miss-and-out (USAC 2E5).

Eliminated riders are placed in reverse order of elimination: the first
out is last (UCI 3.2.223bis, USAC 2E3(e)). One sprint may eliminate
several riders when the officials put them out together (UCI 3.2.223,
USAC 2E3(d)(ii), 2E3(d)(iii)), a rider lapped or abandoning between
sprints being the one out at the next sprint (USAC 2E3(d)(i)), or none
at all on a green flag (UCI 3.2.223, USAC 2E3(d)(iii)). Riders eliminated in one action share a
place because the rulebooks give no order between them; older USAC text
placed riders out together "equally" (USAC20 2E5). Laps gained do not
count (UCI 3.2.225, USAC 2E3(g)).

A rider who leaves the race is eliminated, not DNF: one who abandons
between sprints is one of "the riders eliminated in the next sprint"
(UCI 3.2.223, USAC 2E3(d)(i)); one who cannot rejoin after a mishap is
"eliminated at that moment" (USAC 2E4(a)(ii)), as is anyone who stops
once four or fewer are left and the race is no longer neutralized
(UCI 3.2.226, USAC 2E4(d)). The scorer records all of these as one
mark, DNF, and the engine puts the rider out at that moment, in a group
of their own, placed below whoever goes out next: crashes are the common
case, and the scorer marks the rider when it happens. A DNF marked after
the rider was already out changes nothing but the mark. A DQ, DNS or DNP
is never placed, whether or not the rider was eliminated first
(UCI 3.2.223: an eliminated rider who stays on the track may be
disqualified).

The survivors are placed by the final sprint, entered as a FinishOrder
(UCI 3.2.224, USAC 2E3(f), USAC 2E5 for miss-and-out to N riders).
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from ._common import (
    RESULTS_STAND_REFUSAL,
    SHORTEN_REFUSAL,
    WITHDRAWN_REFUSAL,
    active_entrants,
    assemble,
    last_finish_order,
    place_map,
    statuses,
    validate_common,
    with_status,
)
from .actions import (
    Action,
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    LapNotCounted,
    OutOfFinish,
    PointsAdjusted,
    RaceEnded,
    RaceShortened,
    SprintResult,
    Status,
    Withdrawn,
)
from .result import Standing, Standings, rank_groups
from .rules import EliminationRules

_UNPLACED = 10**6


def _elimination_groups(actions: Sequence[Action]) -> list[list[int]]:
    """Groups of entrants out together as the officials called them, first
    group out first. Statuses are not applied here; validate() uses this
    to know who has already been called out."""
    return [list(e.entrant_ids) for e in actions if isinstance(e, Eliminated) and e.entrant_ids]


def _placed_groups(actions: Sequence[Action], status: Mapping[int, Status]) -> list[list[int]]:
    """The groups that take places, first out first, with statuses applied.

    A DNF on a rider still in is a group of its own at that point in the
    log: out at that moment (USAC 2E4(a)(ii), 2E4(d)), unless a later
    status replaced it. A rider with an unranked status is dropped from
    any group.
    """
    # A rider the bell put out anywhere in the log is placed by that row;
    # a DNF on them changes nothing but the mark, whichever comes first.
    # (A correction re-appends the bell's rows at the end of the log, so a
    # DNF marked after the out may stand before it in replay order.)
    by_bell = {eid for action in actions if isinstance(action, Eliminated) for eid in action.entrant_ids}  # fmt: skip
    groups: list[list[int]] = []
    out: set[int] = set()
    for action in actions:
        if isinstance(action, Eliminated):
            group = [eid for eid in action.entrant_ids if eid not in out]
            out.update(group)
            groups.append(
                [eid for eid in group if eid not in status or status[eid].status == "DNF"]
            )
        elif isinstance(action, Status) and action.entrant_id not in out:
            # The latest status rules: a DNF later replaced by a DQ, DNS or
            # DNP puts nobody out, as that rider is never placed.
            if status[action.entrant_id].status != "DNF" or action.entrant_id in by_bell:
                continue
            out.add(action.entrant_id)
            groups.append([action.entrant_id])
    return [group for group in groups if group]


def _last_sprint_no(actions: Sequence[Action]) -> int:
    return max((e.sprint_no for e in actions if isinstance(e, Eliminated)), default=0)


def compute(
    rules: EliminationRules, entrants: Sequence[int], actions: Sequence[Action]
) -> Standings:
    status = statuses(actions)
    groups = _placed_groups(actions, status)
    finish = last_finish_order(actions)

    rows: dict[int, Standing] = {eid: Standing(entrant_id=eid) for eid in entrants}
    out: set[int] = set()
    for index, group in enumerate(groups, start=1):
        for eid in group:
            rows[eid] = replace(rows[eid], eliminated_at=index)
            if eid in status:
                rows[eid] = with_status(rows[eid], status[eid])
            out.add(eid)

    remaining = [eid for eid in active_entrants(entrants, status) if eid not in out]
    next_sprint_no = _last_sprint_no(actions) + 1

    # Only the survivors of the eliminations ride the final; an eliminated
    # rider in the finish order is a data entry slip that validate() flags.
    survivor_groups: list[list[int]] = []
    if finish is not None:
        places = place_map(finish.places)
        placed = sorted(
            ((places[eid], eid) for eid in remaining if eid in places), key=lambda p: p[0]
        )
        for eid in remaining:
            rows[eid] = replace(rows[eid], final_sprint_place=places.get(eid, None))
        current: list[int] = []
        last_place = None
        for place, eid in placed:
            if current and place == last_place:
                current.append(eid)
            else:
                if current:
                    survivor_groups.append(current)
                current = [eid]
                last_place = place
        if current:
            survivor_groups.append(current)
        unplaced = [eid for eid in remaining if eid not in places]
        if unplaced:
            survivor_groups.append(unplaced)
        complete = True
    elif len(remaining) <= rules.survivors and (len(remaining) <= 1 or not rules.final_by_sprint):
        # Last rider standing wins outright; a miss-and-out with no final
        # sprint shares first among the survivors.
        survivor_groups = [list(remaining)] if remaining else []
        complete = True
    else:
        complete = False

    reverse = [list(group) for group in reversed(groups)]
    if complete:
        ranked, next_rank = rank_groups(
            [[rows[eid] for eid in group] for group in survivor_groups + reverse]
        )
        table = assemble(entrants, rows, status, ranked=ranked, next_rank=next_rank)
        remaining_out: tuple[int, ...] = ()
    else:
        ranked, next_rank = rank_groups(
            [[rows[eid] for eid in group] for group in reverse], start=len(remaining) + 1
        )
        table = assemble(
            entrants,
            rows,
            status,
            ranked=ranked,
            leading_unranked=remaining,
            next_rank=next_rank,
        )
        remaining_out = tuple(remaining)
    return Standings(
        rows=table,
        next_sprint_no=next_sprint_no,
        remaining_entrants=remaining_out,
        is_complete=complete,
    )


def validate(
    rules: EliminationRules, entrants: Sequence[int], actions: Sequence[Action], new_action: Action
) -> list[str]:
    problems = validate_common(entrants, actions, new_action)
    status = statuses(actions)
    if isinstance(new_action, Eliminated):
        # A rider with a status in a bell is the engine's own shape: a DNF
        # is only the mark and a DQ, DNS or DNP leaves the rider out of the
        # group (_placed_groups), and a correction or an Undo may append
        # the bell after the mark; the scorer's click on such a rider is
        # refused before it gets here (control.race.click).
        marked = {f"Entrant {eid} is {mark.status} and cannot be placed" for eid, mark in status.items()}  # fmt: skip
        problems = [p for p in problems if p not in marked]
    out = {eid for group in _elimination_groups(actions) for eid in group}
    remaining = [eid for eid in active_entrants(entrants, status) if eid not in out]

    if isinstance(new_action, Eliminated):
        for eid in dict.fromkeys(new_action.entrant_ids):
            if eid in out:
                problems.append(f"Entrant {eid} is already eliminated")
        last = _last_sprint_no(actions)
        if new_action.sprint_no < last:
            problems.append(
                f"Sprint {new_action.sprint_no} is before the last recorded sprint {last}"
            )
        left = len(remaining) - len(set(new_action.entrant_ids) & set(remaining))
        if new_action.entrant_ids and left < 1:
            problems.append("Eliminating them would leave nobody in the race")
    elif isinstance(new_action, FinishOrder):
        for eid in dict.fromkeys(e for g in new_action.places for e in g):
            if eid in out:
                problems.append(f"Entrant {eid} was eliminated and cannot be in the final sprint")
        if len(remaining) > rules.survivors:
            problems.append(
                f"{len(remaining)} riders are still in; the final sprint is between the last"
                f" {rules.survivors}"
            )
    elif isinstance(new_action, SprintResult):
        problems.append(
            "Sprint results are not scored in an Elimination; enter eliminations and the finish order"
        )
    elif isinstance(new_action, LapGained | LapLost | LapNotCounted):
        problems.append("Laps do not count in an Elimination (UCI 3.2.225, USAC 2E3(g))")
    elif isinstance(new_action, PointsAdjusted):
        problems.append("A points penalty is scored in a Points Race, Madison, or Tempo Race only")
    elif isinstance(new_action, OutOfFinish):
        # A rider who cannot rejoin is eliminated at that moment
        # (USAC 2E4(a)(ii)): the scorer marks them DNF.
        problems.append("Out of the finish is scored in a Points Race, Madison, or Tempo Race only")
    elif isinstance(new_action, Withdrawn):
        # A rider who leaves is eliminated at that moment (USAC
        # 2E4(a)(ii), 2E4(d)): the scorer clicks them out.
        problems.append(WITHDRAWN_REFUSAL)
    elif isinstance(new_action, RaceEnded):
        # A stopped Elimination's result is the riders already out, which
        # the standings show as they stand.
        problems.append(RESULTS_STAND_REFUSAL)
    elif isinstance(new_action, RaceShortened):
        # No sprint count to shorten: a shortened Elimination is entered
        # as its bells fall (USAC 1G4(b)).
        problems.append(SHORTEN_REFUSAL)
    return problems
