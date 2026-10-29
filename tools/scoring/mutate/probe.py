"""Seeded random scenarios through every engine; prints one line per
scenario (compute output plus every validate() answer). Run under two
PYTHONPATHs and diff: a differing line is an input that exposes the mutant.
Candidate actions are appended only when validate() accepts them, so the
logs stay legal; a refused candidate's problems are printed too."""

import random
import sys

from madtracker.scoring import aggregate, elimination, placings, sprint_points, win_and_out
from madtracker.scoring.actions import (
    Eliminated,
    FinishOrder,
    LapGained,
    LapLost,
    LapNotCounted,
    OutOfFinish,
    PointsAdjusted,
    SprintResult,
    Status,
)
from madtracker.scoring.result import Standing, Standings
from madtracker.scoring.rules import (
    AggregateRules,
    EliminationRules,
    PlacingsRules,
    SprintPointsRules,
    WinAndOutRules,
    team_omnium_rules,
    uci_omnium_rules,
    usac_omnium_rules,
)

N = int(sys.argv[1]) if len(sys.argv) > 1 else 150
STATUS = ("DNS", "DNF", "DQ", "DNP")


def groups_of(rng, riders, partial=True, ties=True, empty=True):
    riders = list(riders)
    rng.shuffle(riders)
    if partial and riders and rng.random() < 0.4:
        riders = riders[: rng.randint(0, len(riders))]
    out, i = [], 0
    while i < len(riders):
        if empty and rng.random() < 0.1:
            out.append([])
        k = rng.choice([1, 1, 1, 2, 3]) if ties else 1
        out.append(riders[i : i + k])
        i += k
    return out


def run(engine, rules, riders, candidates):
    """Append each candidate that validates; report the rest's problems and
    the standings after every accepted action."""
    log, lines = [], []
    for cand in candidates:
        problems = engine.validate(rules, riders, log, cand)
        if problems:
            lines.append(f"refused {cand!r}: {problems}")
        else:
            log.append(cand)
            s = engine.compute(rules, riders, log)
            lines.append(f"after {cand!r}: {s!r}")
    return lines


def placings_scenario(rng):
    riders = list(range(1, rng.randint(2, 6) + 1))
    rules = PlacingsRules(
        laps_count_for_ranking=rng.random() < 0.7, lapped_riders_placed_by_laps=rng.random() < 0.6
    )
    cands = []
    for _ in range(rng.randint(0, 5)):
        r = rng.choice(riders)
        cands.append(
            rng.choice(
                [
                    LapGained([r]),
                    LapLost([r]),
                    LapNotCounted([r]),
                    Status(entrant_id=r, status=rng.choice(STATUS)),
                    SprintResult(1, [[r]]),
                    OutOfFinish(entrant_id=r),
                    PointsAdjusted(entrant_id=r, points=-1),
                ]
            )
        )
    cands.append(FinishOrder(groups_of(rng, riders)))
    for _ in range(rng.randint(0, 2)):
        r = rng.choice(riders)
        cands.append(
            rng.choice(
                [
                    Status(entrant_id=r, status=rng.choice(STATUS)),
                    LapNotCounted([r]),
                    LapGained([r]),
                ]
            )
        )
    return run(placings, rules, riders, cands)


def elimination_scenario(rng):
    riders = list(range(1, rng.randint(2, 7) + 1))
    rules = EliminationRules(survivors=rng.choice([1, 2, 2, 3]), final_by_sprint=rng.random() < 0.8)
    cands, n = [], 1
    for _ in range(rng.randint(1, 8)):
        pick = rng.random()
        if pick < 0.6:
            k = rng.choice([0, 1, 1, 1, 2])
            cands.append(Eliminated(n, rng.sample(riders, min(k, len(riders)))))
            n += rng.choice([1, 1, 1, 0, 2])
        elif pick < 0.85:
            cands.append(Status(entrant_id=rng.choice(riders), status=rng.choice(STATUS)))
        else:
            cands.append(
                rng.choice(
                    [
                        LapGained([rng.choice(riders)]),
                        SprintResult(1, [[rng.choice(riders)]]),
                        OutOfFinish(entrant_id=rng.choice(riders)),
                    ]
                )
            )
    cands.append(
        FinishOrder(groups_of(rng, rng.sample(riders, min(len(riders), rng.randint(1, 3)))))
    )
    cands.append(Status(entrant_id=rng.choice(riders), status=rng.choice(STATUS)))
    return run(elimination, rules, riders, cands)


def sprint_scenario(rng):
    riders = list(range(1, rng.randint(2, 6) + 1))
    count = rng.choice([None, 1, 2, 3, 4])
    kind = rng.choice(["points", "madison", "tempo"])
    kw = {}
    if kind == "tempo":
        kw = dict(intermediate_points=(1,), final_points=(1,))
    rules = SprintPointsRules(
        sprint_count=count, tie_break=rng.choice(["final_sprint", "final_sprint", "none"]), **kw
    )
    cands = []
    top = (count or 2) + 1
    for n in range(1, top + 1):
        for _ in range(rng.randint(0, 2)):
            r = rng.choice(riders)
            cands.append(
                rng.choice(
                    [
                        LapGained([r], sprint_no=rng.choice([None, n, n + 1])),
                        LapLost([r]),
                        LapNotCounted([r]),
                        Status(entrant_id=r, status=rng.choice(STATUS)),
                        OutOfFinish(entrant_id=r),
                        PointsAdjusted(entrant_id=r, points=rng.choice([-3, -1, 1, 2, 0])),
                        Eliminated(1, [r]),
                    ]
                )
            )
        if rng.random() < 0.85:
            cands.append(
                SprintResult(
                    n if rng.random() < 0.9 else rng.choice([0, n - 1, n + 1]),
                    groups_of(rng, riders),
                )
            )
    cands.append(FinishOrder(groups_of(rng, riders, partial=rng.random() < 0.3)))
    for _ in range(rng.randint(0, 3)):
        r = rng.choice(riders)
        cands.append(
            rng.choice(
                [
                    Status(entrant_id=r, status=rng.choice(STATUS)),
                    LapNotCounted([r]),
                    PointsAdjusted(entrant_id=r, points=rng.choice([-2, 1, 3])),
                    SprintResult(count or 1, [[r]]),
                ]
            )
        )
    return run(sprint_points, rules, riders, cands)


def wao_scenario(rng):
    riders = list(range(1, rng.randint(2, 7) + 1))
    rules = WinAndOutRules(places=rng.randint(1, 4), direction=rng.choice(["forward", "reverse"]))
    cands = []
    for n in range(1, rules.places + 2):
        if rng.random() < 0.3:
            r = rng.choice(riders)
            cands.append(
                rng.choice(
                    [
                        Status(entrant_id=r, status=rng.choice(STATUS)),
                        Eliminated(1, [r]),
                        OutOfFinish(entrant_id=r),
                        LapNotCounted([r]),
                        PointsAdjusted(entrant_id=r, points=-1),
                    ]
                )
            )
        if rng.random() < 0.85:
            places = groups_of(
                rng, rng.sample(riders, min(len(riders), rng.randint(1, 3))), partial=False
            )
            if rng.random() < 0.1:
                places = []
            cands.append(SprintResult(n if rng.random() < 0.9 else rng.choice([0, n + 1]), places))
    cands.append(FinishOrder(groups_of(rng, riders)))
    for _ in range(rng.randint(0, 2)):
        cands.append(Status(entrant_id=rng.choice(riders), status=rng.choice(STATUS)))
    return run(win_and_out, rules, riders, cands)


def aggregate_scenario(rng):
    riders = list(range(1, rng.randint(2, 5) + 1))
    nraces = rng.randint(1, 4)
    races = []
    for _ in range(nraces):
        rows, rank = [], 1
        order = list(riders)
        rng.shuffle(order)
        for r in order:
            if rng.random() < 0.15:
                continue  # absent
            st = rng.choice([None] * 5 + list(STATUS))
            if rng.random() < 0.25:
                rank = rank  # tie with the previous
            rows.append(
                Standing(
                    entrant_id=r,
                    rank=None if st else rank,
                    status=st,
                    total_points=rng.choice([0, 0, 5, 10, 20, -20]),
                    final_sprint_place=rng.choice([None, 1, 2, 3]),
                )
            )
            if not (rng.random() < 0.25):
                rank += 1
        races.append(Standings(rows=tuple(rows), is_complete=rng.random() < 0.85))
    rules = rng.choice(
        [
            usac_omnium_rules(),
            usac_omnium_rules((7, 5, 3)),
            team_omnium_rules(),
            uci_omnium_rules(),
            AggregateRules(points_by_place=(5, 3, 2, 1), must_finish_all=True),
            AggregateRules(points_by_place=tuple(range(1, 25)), direction="low"),
            AggregateRules(
                points_by_place=(5, 3), dnf_points=1, absent_points=-1, multipliers=(1, 2)
            ),
            AggregateRules(points_by_place=(5, 3), tie_break="last_race_final_sprint"),
            AggregateRules(points_by_place=(5, 3), tie_break="none", sum_total_races=(0, 7)),
        ]
    )
    return [
        f"validate: {aggregate.validate(rules, riders, races)}",
        f"compute: {aggregate.compute(rules, riders, races)!r}",
    ]


SCENARIOS = [
    placings_scenario,
    elimination_scenario,
    sprint_scenario,
    wao_scenario,
    aggregate_scenario,
]
for i in range(N):
    for fn in SCENARIOS:
        rng = random.Random(1000 * i + SCENARIOS.index(fn))
        try:
            lines = fn(rng)
        except Exception as exc:  # a mutant may raise; that is a difference too
            lines = [f"EXC {type(exc).__name__}: {exc}"]
        print(f"## {fn.__name__} {i}")
        for line in lines:
            print(line)
