"""Helpers shared by the engines: status folding, lap counting, finish
order lookup, the non-finisher tail of a standings table, and the
validation checks every format needs.

Non-finisher ranking follows UCI 3.3.012 A because it is the only
rulebook text that says where a DNF goes relative to the finishers:
riders withdrawn by the commissaires or stopped by a mishap share one
tied rank right after the last finisher. USAC enters them as DNF
(1M6(d)) and the format articles call them "not placed" (2C4, 2M8(a)),
which the export renders as DNF either way, so ranking them as a group
costs nothing under USAC and is right under UCI. DQ, DNS and DNP
get no rank in either book.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from .actions import (
    RULING_KINDS,
    SCORING_KINDS,
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
from .result import Standing, rank_groups

# Listing order of the unranked tail, after the DNF group.
UNRANKED_STATUSES = ("DNP", "DQ", "DNS")


def statuses(actions: Iterable[Action]) -> dict[int, Status]:
    """The current status per entrant. The last Status action wins, so a
    correction is a new action, not an edit (a DQ after a DNF reads as
    DQ); clearing a status is a void."""
    out: dict[int, Status] = {}
    for action in actions:
        if isinstance(action, Status):
            out[action.entrant_id] = action
    return out


def out_of_finish(actions: Iterable[Action]) -> set[int]:
    """Entrants a mishap kept out of the finish (USAC 2M7(b)). The sprint
    points engine ranks them on what they hold; a status on the same
    entrant wins, as it does for anyone."""
    return {action.entrant_id for action in actions if isinstance(action, OutOfFinish)}


def withdrawn(actions: Iterable[Action]) -> list[int]:
    """Entrants withdrawn, in the order of their withdrawal (USAC 2O3(e),
    1M6(d)). The engines rank them after every finisher by that order,
    the latest highest; a status on the same entrant wins, as it does
    for anyone."""
    out: list[int] = []
    for action in actions:
        if isinstance(action, Withdrawn) and action.entrant_id not in out:
            out.append(action.entrant_id)
    return out


# The entry is read in the formats that place a withdrawn rider by the
# moment (USAC 2O3(e), 1M6(d)); the others refuse it by name.
WITHDRAWN_REFUSAL = (
    "Withdrawn is scored in a race placed at the line, a Points Race, a Madison,"
    " or a Tempo Race only"
)


def lap_counts(actions: Iterable[Action]) -> dict[int, tuple[int, int]]:
    """(laps gained, laps lost) per entrant that has either.

    A LapNotCounted takes one gained lap back, as if it had never been
    recorded; validate_common refuses one with nothing to take, so the
    floor at zero only guards a log written past that check.
    """
    gained: dict[int, int] = {}
    lost: dict[int, int] = {}
    for action in actions:
        if isinstance(action, LapGained):
            for eid in action.entrant_ids:
                gained[eid] = gained.get(eid, 0) + 1
        elif isinstance(action, LapLost):
            for eid in action.entrant_ids:
                lost[eid] = lost.get(eid, 0) + 1
        elif isinstance(action, LapNotCounted):
            for eid in action.entrant_ids:
                gained[eid] = max(0, gained.get(eid, 0) - 1)
    return {eid: (gained.get(eid, 0), lost.get(eid, 0)) for eid in gained.keys() | lost.keys()}


def laps_cancelled(actions: Iterable[Action]) -> dict[int, int]:
    """Laps ruled not to count, per entrant; validate_common refuses one with
    nothing to cancel, so each is a lap gained that was struck."""
    out: dict[int, int] = {}
    for action in actions:
        if isinstance(action, LapNotCounted):
            for eid in action.entrant_ids:
                out[eid] = out.get(eid, 0) + 1
    return out


def laps_to_cancel(actions: Iterable[Action], entrant_id: int) -> int:
    """How many of this entrant's gained laps still stand to be ruled not counted."""
    n = 0
    for action in actions:
        if isinstance(action, LapGained) and entrant_id in action.entrant_ids:
            n += 1
        elif isinstance(action, LapNotCounted) and entrant_id in action.entrant_ids:
            n = max(0, n - 1)
    return n


def penalty_of(actions: Iterable[Action], entrant_id: int) -> int:
    """This entrant's penalty standing, in points, 0 or more.

    The rulings sum: each entry is the difference between the penalty
    the scorer set and the one before it, so the sum is the number the
    scorer last set and the sheet's Penalty column shows.
    """
    return max(0, -adjustments(actions).get(entrant_id, 0))


def adjustments(actions: Iterable[Action]) -> dict[int, int]:
    """The officials' points rulings summed per entrant (negative for a penalty)."""
    out: dict[int, int] = {}
    for action in actions:
        if isinstance(action, PointsAdjusted):
            out[action.entrant_id] = out.get(action.entrant_id, 0) + action.points
    return out


# The entry that ends a race early is read in the formats whose rules
# let the results stand (USAC 2M6, 2N5); the others refuse it by name.
RESULTS_STAND_REFUSAL = "Only a Points Race or Madison can end early with its result as-is"


def race_ended(actions: Iterable[Action]) -> RaceEnded | None:
    """The entry that ended the race with its results standing, when there is one."""
    found = None
    for action in actions:
        if isinstance(action, RaceEnded):
            found = action
    return found


# The entry that shortens a race is read in the formats with a sprint
# count (USAC 1G4(b)); the others carry no count to shorten, so a
# shortened one is entered as it is ridden and the entry is refused.
SHORTEN_REFUSAL = "Shorten Race is scored in a Points Race, Madison, or Tempo Race only"


def shortened_count(actions: Iterable[Action]) -> int | None:
    """The sprint count the officials shortened the race to, the latest entry's, or None."""
    found = None
    for action in actions:
        if isinstance(action, RaceShortened):
            found = action.sprint_count
    return found


def last_finish_order(actions: Iterable[Action]) -> FinishOrder | None:
    """A second FinishOrder replaces the first: the scorer re-entered the
    line after a correction. validate() flags it so the UI can ask."""
    found = None
    for action in actions:
        if isinstance(action, FinishOrder):
            found = action
    return found


def place_map(places: Sequence[Sequence[int]]) -> dict[int, int]:
    """Entrant to 1-based place. A tied inner list shares its place and
    the next place is skipped; an empty inner list skips a place."""
    out: dict[int, int] = {}
    place = 1
    for group in places:
        for eid in group:
            out[eid] = place
        place += max(1, len(group))
    return out


def active_entrants(entrants: Sequence[int], status: Mapping[int, Status]) -> list[int]:
    return [eid for eid in entrants if eid not in status]


def with_status(row: Standing, mark: Status) -> Standing:
    """The row carrying its status code and the officials' reason as a note."""
    row = replace(row, status=mark.status)
    if mark.reason:
        row = row.with_note(f"{mark.status}: {mark.reason}")
    return row


def assemble(
    entrants: Sequence[int],
    rows: Mapping[int, Standing],
    status: Mapping[int, Status],
    *,
    ranked: Sequence[Standing] = (),
    leading_unranked: Sequence[int] = (),
    next_rank: int | None = None,
    withdrawn: Sequence[int] = (),
) -> tuple[Standing, ...]:
    """Build the display-ordered table from an engine's ranked rows.

    Order: ``leading_unranked`` (entrants still racing, rank None),
    ``ranked`` as given, the withdrawn at ``next_rank`` on, the DNF
    group after them as one tied group (UCI 3.3.012 A), then DNP, DQ and
    DNS rows unranked, then any entrant the engine did not place,
    unranked with a note so nobody vanishes from the sheet.

    ``withdrawn`` is in withdrawal order. Each takes "the next available
    rank determined by the number of riders remaining on the track at
    this moment" (USAC 2O3(e)), so the latest withdrawn ranks highest
    and no two share a rank; before the finish the riders still racing
    count as the finishers ahead of them, which is the same rank. A
    withdrawn rider with a status is listed by the status, which wins.
    """
    if next_rank is None:
        next_rank = len(leading_unranked) + len(ranked) + 1
    out: list[Standing] = [replace(rows[eid], rank=None) for eid in leading_unranked]
    out.extend(ranked)
    # An engine may rank a statused entrant itself (an elimination places
    # a DNF as out at that moment); that row must not appear a
    # second time in the status tail.
    seen = {row.entrant_id for row in out}

    left = [eid for eid in reversed(withdrawn) if eid not in status and eid not in seen]
    for eid in left:
        out.append(replace(rows[eid], rank=next_rank, tied=False, withdrawn=True))
        next_rank += 1
    seen.update(left)

    dnf = [
        with_status(rows[eid], status[eid])
        for eid in entrants
        if eid in status and status[eid].status == "DNF" and eid not in seen
    ]
    dnf_ranked, _ = rank_groups([dnf], start=next_rank)
    out.extend(dnf_ranked)
    seen.update(row.entrant_id for row in dnf_ranked)

    for code in UNRANKED_STATUSES:
        for eid in entrants:
            if eid in status and status[eid].status == code and eid not in seen:
                out.append(with_status(rows[eid], status[eid]))
                seen.add(eid)

    for eid in entrants:
        if eid not in seen:
            out.append(replace(rows[eid], rank=None).with_note("Not placed"))
    return tuple(out)


def group_by_key(items: Iterable[tuple[tuple, int]]) -> list[list[int]]:
    """Split (sort key, entrant) pairs, already sorted, into groups of
    equal keys. Equal keys are a true tie and share a rank."""
    groups: list[list[int]] = []
    last_key: tuple | None = None
    for key, eid in items:
        if groups and key == last_key:
            groups[-1].append(eid)
        else:
            groups.append([eid])
            last_key = key
    return groups


# Validation


def referenced_ids(action: Action) -> list[int]:
    """Every entrant an action names, duplicates kept so they can be flagged."""
    if isinstance(action, SprintResult | FinishOrder):
        return [eid for group in action.places for eid in group]
    if isinstance(action, LapGained | LapLost | LapNotCounted | Eliminated):
        return list(action.entrant_ids)
    if isinstance(action, Status | OutOfFinish | Withdrawn | PointsAdjusted):
        return [action.entrant_id]
    return []


def with_results(actions: Iterable[Action]) -> set[int]:
    """Entrants named by a scoring entry: a sprint or finish place, a lap,
    an elimination, a mishap out of the finish, or a ruling on points or
    laps. A status is not a result (it says the rider has none)."""
    kinds = SCORING_KINDS | RULING_KINDS
    return {eid for action in actions if action.kind in kinds for eid in referenced_ids(action)}


def validate_common(
    entrants: Sequence[int], actions: Sequence[Action], new_action: Action
) -> list[str]:
    """Problems every format shares. Empty means the action may be appended."""
    problems: list[str] = []
    known = set(entrants)
    ids = referenced_ids(new_action)
    for eid in dict.fromkeys(ids):
        if eid not in known:
            problems.append(f"Unknown entrant {eid}")
    dupes = sorted({eid for eid in ids if ids.count(eid) > 1})
    if dupes:
        problems.append(f"Entered more than once in this entry: {', '.join(map(str, dupes))}")

    status = statuses(actions)
    gone = withdrawn(actions)
    finished = last_finish_order(actions) is not None
    # A race ended with its results standing is over as a finish order
    # ends it: the sprints ridden are the result.
    ended = race_ended(actions) is not None
    over = "the finish order" if finished else "the race's end"

    if new_action.kind in SCORING_KINDS:
        for eid in dict.fromkeys(ids):
            if eid in status:
                problems.append(f"Entrant {eid} is {status[eid].status} and cannot be placed")
            elif eid in gone:
                # Classified from the moment of the withdrawal (USAC
                # 2O3(e)): nothing after it places the rider, and a second
                # entry would move the moment.
                what = (
                    "is already withdrawn"
                    if isinstance(new_action, Withdrawn)
                    else ("is withdrawn and cannot be placed")
                )
                problems.append(f"Entrant {eid} {what}")
        if finished:
            problems.append("The finish order is already recorded; void it before entering more")
        elif ended:
            problems.append("The race has ended with its results standing; undo that first")

    if new_action.kind in RULING_KINDS:
        # A ruling touches a total the rider holds: a DNF keeps the points
        # shown and ranks on them, the other statuses have no line to
        # change. The finish order is no bar, since rulings follow protests.
        for eid in dict.fromkeys(ids):
            if eid in status and status[eid].status != "DNF":
                problems.append(
                    f"Entrant {eid} is {status[eid].status} and has no result to change"
                )
    if isinstance(new_action, PointsAdjusted) and new_action.points == 0:
        problems.append("No points entered")
    if isinstance(new_action, PointsAdjusted) and new_action.points > 0:
        # Points only ever come back by lowering a penalty (USAC 8D5(b)
        # takes points; nothing awards them), so a positive entry may not
        # exceed the penalty standing: a total never rises above what the
        # riding earned.
        eid = new_action.entrant_id
        standing = penalty_of(actions, eid)
        if standing == 0:
            problems.append(f"Entrant {eid} has no penalty to give back")
        elif new_action.points > standing:
            problems.append(
                f"Entrant {eid}'s penalty is {standing} points; {new_action.points} cannot come back"
            )
    if isinstance(new_action, LapNotCounted):
        for eid in dict.fromkeys(ids):
            if eid in known and laps_to_cancel(actions, eid) < 1:
                problems.append(f"Entrant {eid} has no lap gained to cancel")

    if isinstance(new_action, Status):
        eid = new_action.entrant_id
        # A later status replaces an earlier one (statuses() keeps the
        # last), so a rider who left the race and is then disqualified
        # takes the DQ without the DNF being undone; only the same mark
        # twice is a slip.
        if eid in status and status[eid].status == new_action.status:
            problems.append(f"Entrant {eid} is already {status[eid].status}")
        # A DQ after the line is normal (protests, USAC 1P1); a DNS or DNF
        # after the line contradicts the recorded finish.
        if (finished or ended) and new_action.status in ("DNS", "DNF"):
            problems.append(f"Entrant {eid} cannot be marked {new_action.status} after {over}")
        # DNS is "fail to take the start line" (USAC 1M6(b)): a rider with
        # a place or a lap recorded took it. Other riders' results do not
        # matter; a no-show can be found after the race is under way.
        elif new_action.status == "DNS" and eid in with_results(actions):
            problems.append(f"Entrant {eid} has a result and cannot be marked DNS")
        # A rider who never started (USAC 1M6(b)) has no race to leave, so
        # DNF is refused on a DNS or DNP rider; a wrong DNS is undone, and
        # only a DQ may follow it.
        elif new_action.status == "DNF" and eid in status and status[eid].status in ("DNS", "DNP"):
            problems.append(
                f"Entrant {eid} is {status[eid].status} and never started; it cannot be marked DNF"
            )
        # The rule places a withdrawn rider (USAC 2O3(e), 1M6(d)); a DQ may
        # still follow a protest.
        elif new_action.status in ("DNS", "DNF") and eid in gone:
            problems.append(
                f"Entrant {eid} is withdrawn and placed by the rule;"
                f" it cannot be marked {new_action.status}"
            )
    return problems
