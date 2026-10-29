"""Win-and-out engine: win-and-out, Danish (forward), Belgian (reverse).

Club formats with no rulebook article; the rules come from the venue
descriptions in docs/research/usac-track-formats.md, "Win-and-out
family". Each place lap is entered as a SprintResult whose sprint_no is
the lap number and whose first place is the lap winner. Forward: lap k
decides place k. Reverse: lap k decides place N + 1 - k. The riders left
when the places are decided fill the open places by the FinishOrder.

Each bell lap decides the next open place from the top (forward) or
from the bottom (reverse). A dead heat the officials declare is an
equal placing like any other (USAC 1M6(a), 1M4(b)): the tied riders
share the place, it uses two places, and the next bell lap is for the
next open place, so the race rings one bell fewer. Riders tied in the
finish fill share the place the same way. A place whose winner is later DNF, DQ or otherwise out stays
decided (nobody from the line can take it) but is vacated: once the
finish order is in, the places are renumbered without the gap, so the
later lap winners move up and the fill starts after the last place a
lap decided. Before the finish the vacated places already close up (a
held place moves up one for each vacated place above it), so the result
so far shows the places the finish will confirm. The DNF group ranks
after the last announced place.
"""

from collections.abc import Sequence
from dataclasses import replace

from ._common import (
    RESULTS_STAND_REFUSAL,
    SHORTEN_REFUSAL,
    WITHDRAWN_REFUSAL,
    active_entrants,
    assemble,
    last_finish_order,
    statuses,
    validate_common,
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
    Withdrawn,
)
from .result import Standing, Standings
from .rules import WinAndOutRules


def _lap_wins(actions: Sequence[Action]) -> dict[int, SprintResult]:
    out: dict[int, SprintResult] = {}
    for action in actions:
        if isinstance(action, SprintResult):
            out[action.sprint_no] = action
    return out


def _bell_places(rules: WinAndOutRules, wins: dict[int, SprintResult]) -> list[tuple[int, int]]:
    """(place, width) per lap in lap order: the place each bell decided and how many it used.

    A lap uses one place, a dead heat one per rider; a lap whose winner
    is later out still used its place (the bell was rung for it), and
    the vacated place closes up at the finish.
    """
    out = []
    used = 0
    for lap_no in sorted(wins):
        width = max(1, len(wins[lap_no].places[0]) if wins[lap_no].places else 1)
        if rules.direction == "forward":
            place = used + 1
        else:
            # Counting down from the last place; a dead heat for the top
            # place (1M4(b) re-rides it) shares 1st.
            place = max(1, rules.places - used - width + 1)
        out.append((place, width))
        used += width
    return out


def places_used(rules: WinAndOutRules, actions: Sequence[Action]) -> int:
    """How many of the race's places the bells have decided."""
    return sum(width for _, width in _bell_places(rules, _lap_wins(actions)))


def compute(rules: WinAndOutRules, entrants: Sequence[int], actions: Sequence[Action]) -> Standings:
    status = statuses(actions)
    wins = _lap_wins(actions)
    finish = last_finish_order(actions)

    rows: dict[int, Standing] = {eid: Standing(entrant_id=eid) for eid in entrants}
    decided: set[int] = set()
    taken: dict[int, list[int]] = {}
    used = 0
    for lap_no, (place, width) in zip(sorted(wins), _bell_places(rules, wins), strict=True):
        decided.update(range(place, place + width))
        used += width
        winners = (
            [eid for eid in wins[lap_no].places[0] if eid in rows] if wins[lap_no].places else []
        )
        winners = [eid for eid in winners if eid not in status and not _placed(eid, taken)]
        if winners:
            taken[place] = winners

    remaining = [eid for eid in active_entrants(entrants, status) if not _placed(eid, taken)]
    # (place, riders, from the line): lap places first, the fill added below.
    groups: list[tuple[int, list[int], bool]] = [
        (place, taken[place], False) for place in sorted(taken)
    ]

    if finish is not None:
        # Open places in ascending order, skipping every place a lap
        # decided; a tied finish group takes the first open place and
        # consumes one open place per rider.
        open_places = (p for p in range(1, len(entrants) + len(decided) + 2) if p not in decided)
        fill_groups = [
            [eid for eid in group if eid in remaining] for group in finish.places if group
        ]
        fill_groups = [g for g in fill_groups if g]
        seen = {eid for g in fill_groups for eid in g}
        unplaced = [eid for eid in remaining if eid not in seen]
        if unplaced:
            fill_groups.append(unplaced)
        place_no = 1
        for group in fill_groups:
            place = next(open_places)
            for _ in range(len(group) - 1):
                next(open_places, None)
            for eid in group:
                rows[eid] = replace(rows[eid], final_sprint_place=place_no)
            groups.append((place, group, True))
            place_no += len(group)
        # Renumber top to bottom. A vacated place closes up because only
        # held places are counted; a tied group, from a bell or from the
        # line, is an equal placing and skips the places it used (1, 1,
        # 3; USAC 1M6(a)).
        groups.sort(key=lambda g: g[0])
        numbered: list[tuple[int, list[int], bool]] = []
        next_free = 1
        for _, group, from_line in groups:
            numbered.append((next_free, group, from_line))
            next_free += len(group)
        groups = numbered
        complete = True
        leading: list[int] = []
    else:
        complete = False
        leading = remaining
        # Close up the vacated places now, not only at the finish: a held
        # place moves up one for each vacated place above it. That is the
        # renumbering above restricted to what is decided (once the laps
        # are run the fill always lands below the lap places), so the
        # table does not reshuffle when the finish goes in. A place a lap
        # has yet to decide is not vacated and moves nobody.
        # A tied group holds one place per rider from the one it is
        # keyed by; the rest of what the bells decided is vacated.
        held = {place + i for place, group in taken.items() for i in range(len(group))}
        vacated = sorted(decided - held)
        groups = [
            (place - sum(1 for v in vacated if v < place), group, from_line)
            for place, group, from_line in groups
        ]
        # The DNF group sits after every place a lap has given and every
        # rider still racing, whichever end of the table those are at: in
        # reverse the held places are the high numbers and the riders
        # racing fill the low ones, so it is the highest held place or the
        # riders placed and racing, whichever is more, that it follows.
        held = max((place for place, _, _ in groups), default=0)
        placed_count = sum(len(group) for _, group, _ in groups)
        next_free = max(held, placed_count + len(leading)) + 1

    ranked = [
        replace(rows[eid], rank=place, tied=len(group) > 1)
        for place, group, _ in groups
        for eid in group
    ]
    return Standings(
        rows=assemble(
            entrants,
            rows,
            status,
            ranked=ranked,
            leading_unranked=leading,
            next_rank=next_free,
        ),
        # Past the places, no lap is due: the rest finish together.
        next_sprint_no=max(wins, default=0) + 1 if used < rules.places else rules.places + 1,
        remaining_entrants=() if complete else tuple(remaining),
        is_complete=complete,
    )


def _placed(eid: int, taken: dict[int, list[int]]) -> bool:
    return any(eid in group for group in taken.values())


def validate(
    rules: WinAndOutRules, entrants: Sequence[int], actions: Sequence[Action], new_action: Action
) -> list[str]:
    problems = validate_common(entrants, actions, new_action)
    wins = _lap_wins(actions)
    taken = {eid for w in wins.values() for group in w.places[:1] for eid in group}
    if isinstance(new_action, SprintResult):
        n = new_action.sprint_no
        if n < 1:
            problems.append("Lap numbers start at 1")
        elif n > rules.places:
            problems.append(f"Lap {n} is beyond the {rules.places} places in this race")
        elif places_used(rules, actions) >= rules.places:
            problems.append(
                "Every place is decided (a dead heat takes two); the rest finish together"
            )
        elif n in wins:
            problems.append(f"Lap {n} is already recorded; void it to re-enter")
        else:
            # Sequence by number, not by log position: a swapped pair of
            # laps sits at the end of the live log (control/race.py).
            missing = next((k for k in range(1, n) if k not in wins), None)
            if missing is not None:
                problems.append(f"Expected lap {missing}, got {n}")
        if not new_action.places or not new_action.places[0]:
            problems.append("No lap winner entered")
        for eid in dict.fromkeys(e for g in new_action.places for e in g):
            if eid in taken:
                problems.append(f"Entrant {eid} already took a place and has left the race")
    elif isinstance(new_action, FinishOrder):
        for eid in dict.fromkeys(e for g in new_action.places for e in g):
            if eid in taken:
                problems.append(f"Entrant {eid} already took a place and has left the race")
    elif isinstance(new_action, Eliminated):
        problems.append("Eliminations are not scored in a Win-and-Out")
    elif isinstance(new_action, OutOfFinish):
        problems.append("Out of the finish is scored in a Points Race, Madison, or Tempo Race only")
    elif isinstance(new_action, Withdrawn):
        # A club format with no rule for a pulled rider: the scorer marks
        # them as the officials call it.
        problems.append(WITHDRAWN_REFUSAL)
    elif isinstance(new_action, RaceEnded):
        problems.append(RESULTS_STAND_REFUSAL)
    elif isinstance(new_action, RaceShortened):
        # No sprint count to shorten: the places decide the laps, and a
        # shortened race is entered as it is ridden (USAC 1G4(b)).
        problems.append(SHORTEN_REFUSAL)
    elif isinstance(new_action, PointsAdjusted):
        problems.append("A points penalty is scored in a Points Race, Madison, or Tempo Race only")
    elif isinstance(new_action, LapNotCounted):
        problems.append("Laps do not count in a Win-and-Out")
    return problems
