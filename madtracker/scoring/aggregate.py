"""Aggregate engine: standings over several races' standings.

Covers the team madison omnium (each team's madison totals
summed across the named races), generic overall-for-the-day scoring
with a points-per-place table and the USAC 2B19(e) tie-break, and the
UCI omnium table (UCI 3.2.250 to 3.2.252, USAC 2O3). Unlike the other
engines it takes finished Standings, not actions: the races are scored
first and this table sits over their results.

Output rows reuse ``sprint_points`` as the per-race points column and
``final_sprint_place`` as the place in the last race, so the same
standings table widget shows the work. ``penalties`` are omnium-level
deductions by entrant (USAC 2O3(e): 40 points for two laps down in the
Scratch Race or Tempo Race), taken off the total before ranking and
carried as a negative ``adjust_points``; they belong to the omnium, not
to any race, so no race's own result changes.
"""

from collections.abc import Mapping, Sequence
from functools import cmp_to_key

from .result import Standing, Standings, rank_groups
from .rules import AggregateRules


def _num(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _race_points(rules: AggregateRules, index: int, row: Standing | None) -> int | float:
    if row is None:
        return rules.absent_points
    summed = rules.points_by_place is None or index in rules.sum_total_races
    # A race that placed a rider who then left it (an Elimination puts a
    # DNF out at that moment, USAC 2E3(d)(i), 2E4) gave them a place the
    # sheet prints, and the table scores that place.
    if row.status is not None and not row.placed:
        # A DNF keeps the points it scored (UCI 3.3.012 A), so a summed
        # race carries them on; a place table has no place to convert.
        if row.status == "DNF" and summed:
            return row.total_points
        return rules.status_points(row.status)
    if summed:
        # The total as it stands, ranked or not: a Madison with a lap
        # gained and no sprint yet has points to carry (R-TEAM-1), and
        # ranks come only with the first sprint.
        return row.total_points
    if row.rank is None:
        return 0
    if row.rank <= len(rules.points_by_place):
        return rules.points_by_place[row.rank - 1]
    return rules.points_beyond_table


def compute(
    rules: AggregateRules,
    entrants: Sequence[int],
    races: Sequence[Standings],
    penalties: Mapping[int, int] | None = None,
) -> Standings:
    penalties = penalties or {}
    per_race: dict[int, list[Standing | None]] = {}
    for eid in entrants:
        per_race[eid] = []
        for standings in races:
            try:
                per_race[eid].append(standings.by_entrant(eid))
            except KeyError:
                per_race[eid].append(None)

    rows: dict[int, Standing] = {}
    excluded: set[int] = set()
    for eid in entrants:
        points = tuple(
            _num(_race_points(rules, i, row) * rules.multiplier(i))
            for i, row in enumerate(per_race[eid])
        )
        notes: list[str] = []
        missed = [
            i + 1 for i, row in enumerate(per_race[eid]) if row is None or row.status is not None
        ]
        mark = None
        if missed and rules.must_finish_all:
            excluded.add(eid)
            notes.append("Not ranked: did not finish every race")
            # The sheet prints the code for a rider out of the omnium:
            # DQ when disqualified in a race, otherwise DNF (USAC 2O2(c),
            # 2O3(d): placed after the last rider as DNF).
            dq = any(row is not None and row.status == "DQ" for row in per_race[eid])
            mark = "DQ" if dq else "DNF"
        last = per_race[eid][-1] if per_race[eid] else None
        penalty = int(penalties.get(eid, 0))
        rows[eid] = Standing(
            entrant_id=eid,
            status=mark,
            total_points=_num(sum(points) - penalty),
            sprint_points=points,  # type: ignore[arg-type]
            adjust_points=-penalty,
            final_sprint_place=last.final_sprint_place if last is not None else None,
            notes=tuple(notes),
        )

    def place(eid: int, index: int) -> int | None:
        row = per_race[eid][index]
        return None if row is None or not row.placed else row.rank

    max_place = max((place(eid, i) or 0 for eid in entrants for i in range(len(races))), default=0)

    def compare(a: int, b: int) -> int:
        sign = 1 if rules.direction == "high" else -1
        ta, tb = rows[a].total_points, rows[b].total_points
        if ta != tb:
            return -sign if ta > tb else sign
        if rules.tie_break == "most_firsts_then_last_race":
            # USAC 2B19(e): most firsts, then seconds, and so on; then the
            # better place in the last race, or the nearest earlier race in
            # which at least one of the tied riders placed.
            for p in range(1, max_place + 1):
                ca = sum(1 for i in range(len(races)) if place(a, i) == p)
                cb = sum(1 for i in range(len(races)) if place(b, i) == p)
                if ca != cb:
                    return -1 if ca > cb else 1
            for i in reversed(range(len(races))):
                pa, pb = place(a, i), place(b, i)
                if pa is None and pb is None:
                    continue
                if pa is None:
                    return 1
                if pb is None:
                    return -1
                if pa != pb:
                    return -1 if pa < pb else 1
                return 0
        elif rules.tie_break == "last_race_final_sprint" and races:
            # UCI 3.2.252: the final sprint of the points race decides.
            fa = rows[a].final_sprint_place
            fb = rows[b].final_sprint_place
            if fa != fb:
                if fa is None:
                    return 1
                if fb is None:
                    return -1
                return -1 if fa < fb else 1
        return 0

    ordered = sorted((eid for eid in entrants if eid not in excluded), key=cmp_to_key(compare))
    groups: list[list[int]] = []
    for eid in ordered:
        if groups and compare(groups[-1][0], eid) == 0:
            groups[-1].append(eid)
        else:
            groups.append([eid])
    ranked, _ = rank_groups([[rows[eid] for eid in group] for group in groups])
    # The DNF group, then DQ, as every sheet lists a race's tail (R-NF-2).
    tail = sorted(
        (rows[eid] for eid in entrants if eid in excluded), key=lambda r: r.status == "DQ"
    )
    return Standings(
        rows=tuple(ranked + tail),
        is_complete=all(s.is_complete for s in races) if races else False,
    )


def validate(
    rules: AggregateRules, entrants: Sequence[int], races: Sequence[Standings]
) -> list[str]:
    problems: list[str] = []
    if rules.multipliers is not None and len(rules.multipliers) < len(races):
        problems.append(
            f"{len(races)} races but {len(rules.multipliers)} multipliers; missing ones count 1"
        )
    for index in rules.sum_total_races:
        if index >= len(races):
            problems.append(f"sum_total_races names race {index} but only {len(races)} were given")
    known = set(entrants)
    for i, standings in enumerate(races, start=1):
        for row in standings.rows:
            if row.entrant_id not in known:
                problems.append(f"Race {i} has entrant {row.entrant_id} who is not in the omnium")
        if not standings.is_complete:
            problems.append(f"Race {i} is not complete")
    return problems
