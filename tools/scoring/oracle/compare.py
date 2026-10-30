"""Engine against oracle over thousands of seeded random races per format.

    python tools/scoring/oracle/compare.py [--out DIR] [seeds_per_family] [family ...]

Writes results.json (counts, refusal tallies, every distinct discrepancy
with its smallest repro) and discrepancies.md (the same, readable) into
DIR, which defaults to a folder under the system temp directory so a run
never leaves files in the repo. The exit code is 1 when any family has a
discrepancy, so a clean run is exit code 0.
"""

import json
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

import gen
import oracle

from madtracker.scoring import compute_aggregate, compute_for_format, validate_for_format
from madtracker.scoring.rules import AggregateRules

CORE = (
    "rank",
    "status",
    "total",
    "gained",
    "lost",
    "adjust",
    "not_counted",
    "out_of_finish",
    "withdrawn",
)
EXTRA = ("final_place", "eliminated_at", "tied")


def engine_view(standings):
    rows = {}
    for r in standings.rows:
        rows[r.entrant_id] = {
            "rank": r.rank,
            "status": r.status,
            "total": r.total_points,
            "gained": r.laps_gained,
            "lost": r.laps_lost,
            "adjust": r.adjust_points,
            "not_counted": r.laps_not_counted,
            "out_of_finish": r.out_of_finish,
            "withdrawn": r.withdrawn,
            "final_place": r.final_sprint_place,
            "eliminated_at": r.eliminated_at,
            "tied": r.tied,
        }
    # Row order as groups: ranked rows grouped by rank, then the DNF
    # group, then each unranked status in the order listed.
    groups = []
    for r in standings.rows:
        key = (r.rank, r.status if r.rank is None else None)
        if groups and groups[-1][0] == key:
            groups[-1][1].append(r.entrant_id)
        else:
            groups.append((key, [r.entrant_id]))
    return (
        rows,
        ordered(rows, [frozenset(g) for _, g in groups]),
        [r.entrant_id for r in standings.rows],
    )


def oracle_view(fmt, rules, entrants, actions):
    rows, groups = oracle.score(fmt, rules, entrants, actions)
    for e in entrants:
        rows[e]["tied"] = (
            sum(
                1
                for x in entrants
                if rows[x]["rank"] == rows[e]["rank"] and rows[e]["rank"] is not None
            )
            > 1
        )
    groups = [frozenset(g) for g in groups if g]
    return rows, ordered(rows, groups)


def ordered(rows, groups):
    """The groups whose position in the table the register fixes: ranked
    rows, the DNF group, the unranked statuses. Where the unranked riders
    still racing sit is display only (the engine lists them first in a
    running win-and-out) and is left out of the order comparison."""
    return [
        g
        for g in groups
        if not all(rows[e]["rank"] is None and rows[e]["status"] is None for e in g)
    ]


def diff(fmt, rules, entrants, actions, fields=CORE, order=True):
    """The differing fields per entrant, and whether the order differs."""
    got_rows, got_groups, _ = engine_view(compute_for_format(fmt, rules, entrants, actions))
    want_rows, want_groups = oracle_view(fmt, rules, entrants, actions)
    out = {}
    for e in entrants:
        bad = {
            f: (want_rows[e][f], got_rows[e][f])
            for f in fields
            if want_rows[e][f] != got_rows[e][f]
        }
        if bad:
            out[e] = bad
    order_bad = order and got_groups != want_groups
    return out, order_bad


def valid_log(fmt, rules, entrants, actions):
    log = []
    for a in actions:
        if validate_for_format(fmt, rules, entrants, log, a):
            return False
        log.append(a)
    return True


def shrink(fmt, rules, entrants, actions, fields, order):
    """Greedy one-at-a-time removal of actions, then of idle entrants,
    while the engine still accepts the log and the disagreement stays."""

    def disagrees(ents, acts):
        if not valid_log(fmt, rules, ents, acts):
            return False
        try:
            d, o = diff(fmt, rules, ents, acts, fields, order)
        except Exception:
            return False
        return bool(d) or o

    changed = True
    while changed:
        changed = False
        for i in range(len(actions)):
            trial = actions[:i] + actions[i + 1 :]
            if disagrees(entrants, trial):
                actions = trial
                changed = True
                break
    # idle entrants
    changed = True
    while changed:
        changed = False
        for e in list(entrants):
            trial = [x for x in entrants if x != e]
            if len(trial) < 1:
                continue
            if any(e in gen_named(a) for a in actions):
                continue
            if disagrees(trial, actions):
                entrants = trial
                changed = True
                break
    return entrants, actions


def gen_named(a):
    if hasattr(a, "places"):
        return [e for g in a.places for e in g]
    if hasattr(a, "entrant_ids"):
        return list(a.entrant_ids)
    return [a.entrant_id]


def signature(fmt, d, order_bad, actions):
    fields = sorted({f for bad in d.values() for f in bad})
    kinds = tuple(sorted({a.kind for a in actions}))
    return (fmt, tuple(fields), order_bad, kinds)


def run_family(family, seeds):
    stats = gen.new_stats()
    counts = Counter()
    found = {}
    for seed in range(seeds):
        fmt, rules, entrants, actions = gen.generate(family, seed, stats)
        counts["races"] += 1
        counts["actions"] += len(actions)
        if not actions:
            counts["empty"] += 1
        try:
            d, order_bad = diff(fmt, rules, entrants, actions, CORE + EXTRA, True)
        except Exception as exc:  # the engine or the oracle raised
            counts["raised"] += 1
            key = (fmt, "raised", repr(exc)[:80])
            found.setdefault(key, {"count": 0, "seed": seed, "size": 10**9})
            found[key]["count"] += 1
            continue
        core_bad = {e: {f: v for f, v in bad.items() if f in CORE} for e, bad in d.items()}
        core_bad = {e: v for e, v in core_bad.items() if v}
        extra_bad = {e: {f: v for f, v in bad.items() if f in EXTRA} for e, bad in d.items()}
        extra_bad = {e: v for e, v in extra_bad.items() if v}
        if not core_bad and not order_bad and not extra_bad:
            counts["agree"] += 1
            continue
        if core_bad or order_bad:
            counts["disagree_core"] += 1
            fields = CORE
            use_order = True
            d_use = core_bad
        else:
            counts["disagree_extra_only"] += 1
            fields = EXTRA
            use_order = False
            d_use = extra_bad
        key = signature(fmt, d_use, order_bad, actions)
        if key in found:
            found[key]["count"] += 1
            # keep the smallest seed's example; shrink only once
            continue
        s_entrants, s_actions = shrink(fmt, rules, entrants, list(actions), fields, use_order)
        s_d, s_order = diff(fmt, rules, s_entrants, s_actions, fields, use_order)
        key = signature(fmt, s_d, s_order, s_actions)
        if key in found:
            found[key]["count"] += 1
            continue
        found[key] = {
            "count": 1,
            "seed": seed,
            "fmt": fmt,
            "rules": repr(rules),
            "entrants": s_entrants,
            "actions": [repr(a) for a in s_actions],
            "diff": {
                str(e): {f: [repr(v[0]), repr(v[1])] for f, v in bad.items()}
                for e, bad in s_d.items()
            },
            "order_differs": s_order,
            "engine_order": engine_view(compute_for_format(fmt, rules, s_entrants, s_actions))[2],
            "oracle_groups": [sorted(g) for g in oracle_view(fmt, rules, s_entrants, s_actions)[1]],
            "kind": "core" if fields is CORE else "extra",
        }
    return stats, counts, found


# ---- aggregate (team omnium)


def run_aggregate(seeds):
    """Three kinds: the Team Omnium summed over Madisons, the Team Omnium
    by Place (7-5-3-2-1), and the UCI omnium (scratch, tempo, elimination,
    points; R-OMNI-1 to R-OMNI-4). A race's field is a subset of the
    entrants so absences happen."""
    from madtracker.scoring.rules import uci_omnium_rules

    counts = Counter()
    found = {}
    stats = gen.new_stats()
    for seed in range(seeds):
        rng = random.Random(f"aggregate:{seed}")
        entrants = rng.sample(range(1, 60), rng.randint(3, 12))
        kind = rng.choice(("sum", "place", "uci"))
        if kind == "uci":
            arules = uci_omnium_rules()
            plan = [
                ("placings", "scratch"),
                ("tempo", None),
                ("elimination", None),
                ("points", None),
            ]
        else:
            arules = AggregateRules(points_by_place=None if kind == "sum" else (7, 5, 3, 2, 1))
            plan = [("madison", None)] * rng.randint(1, 4)
        races = []
        views = []
        for i, (family, fmt) in enumerate(plan):
            field = rng.sample(entrants, rng.randint(max(1, len(entrants) - 2), len(entrants)))
            r = random.Random(f"agg-{kind}:{seed}:{i}")
            if family == "placings":
                got = gen.gen_placings(r, stats, field, fmt)
            else:
                got = gen.GENERATORS[family](r, stats, field)
            fmt_key, rules, ents, actions = got
            st = compute_for_format(fmt_key, rules, ents, actions)
            races.append(st)
            views.append(
                {
                    x.entrant_id: (
                        x.rank,
                        x.status,
                        x.total_points,
                        x.final_sprint_place,
                        x.eliminated_at is not None,
                    )
                    for x in st.rows
                }
            )
        counts["races"] += 1
        try:
            st = compute_aggregate(arules, entrants, races)
        except Exception as exc:
            counts["raised"] += 1
            found.setdefault(("aggregate", "raised", repr(exc)[:80]), {"count": 0, "seed": seed})[
                "count"
            ] += 1
            continue
        got = {x.entrant_id: (x.rank, x.total_points, x.status) for x in st.rows}
        got_order = [x.entrant_id for x in st.rows]
        want_rows, want_groups = oracle.score_aggregate(arules, entrants, views)
        want = {
            e: (want_rows[e]["rank"], want_rows[e]["total"], want_rows[e]["status"])
            for e in entrants
        }
        bad = {e: (want[e], got.get(e)) for e in entrants if want[e] != got.get(e)}
        if not bad:
            counts["agree"] += 1
            continue
        counts["disagree_core"] += 1
        fields = tuple(
            sorted(
                {
                    n
                    for w, g in bad.values()
                    for n, a, b in zip(
                        ("rank", "total", "status"), w, g or (None, None, None), strict=False
                    )
                    if a != b
                }
            )
        )
        key = ("aggregate", kind, fields)
        if key in found:
            found[key]["count"] += 1
            continue
        found[key] = {
            "count": 1,
            "seed": seed,
            "fmt": f"aggregate/{kind}",
            "rules": repr(arules),
            "entrants": entrants,
            "views": [{str(k): list(v) for k, v in view.items()} for view in views],
            "diff": {str(e): [repr(w), repr(g)] for e, (w, g) in bad.items()},
            "engine_order": got_order,
            "kind": "core",
        }
    return stats, counts, found


def main():
    args = sys.argv[1:]
    out = Path(tempfile.gettempdir()) / "madtracker-scoring" / "oracle"
    if args[:1] == ["--out"]:
        out, args = Path(args[1]), args[2:]
    out.mkdir(parents=True, exist_ok=True)
    seeds = int(args[0]) if args else 2000
    families = args[1:] or [*gen.GENERATORS, "aggregate"]
    report = {}
    for family in families:
        if family == "aggregate":
            stats, counts, found = run_aggregate(seeds)
        else:
            stats, counts, found = run_family(family, seeds)
        report[family] = {
            "counts": dict(counts),
            "accepted": dict(stats["accepted"]),
            "refused": dict(stats["refused"].most_common()),
            "validity_agreement": {
                f"engine_refuses={k[0]},oracle_refuses={k[1]}": v
                for k, v in stats["agreement"].items()
            },
            "engine_only_refusals": dict(stats["engine_only"].most_common()),
            "oracle_only_refusals": dict(stats["oracle_only"].most_common()),
            "unoffered": dict(stats["unoffered"].most_common()),
            "discrepancies": [
                {"signature": repr(k), **v}
                for k, v in sorted(found.items(), key=lambda kv: -kv[1]["count"])
            ],
        }
        print(family, dict(counts), f"{len(found)} distinct", flush=True)
    with open(out / "results.json", "w") as f:
        json.dump(report, f, indent=1, default=repr)
    with open(out / "discrepancies.md", "w") as f:
        for family, r in report.items():
            f.write(f"## {family}\n\ncounts: {r['counts']}\n\n")
            for d in r["discrepancies"]:
                f.write(f"### {d['signature']} (x{d['count']}, seed {d['seed']})\n\n")
                for k in ("fmt", "rules", "entrants", "kind"):
                    if k in d:
                        f.write(f"- {k}: {d[k]}\n")
                if "actions" in d:
                    f.write("- actions:\n")
                    for a in d["actions"]:
                        f.write(f"    {a}\n")
                if "views" in d:
                    f.write(f"- views: {d['views']}\n")
                f.write(f"- diff (oracle, engine): {d.get('diff')}\n")
                if d.get("order_differs"):
                    f.write(
                        f"- engine order: {d['engine_order']}\n- oracle groups: {d['oracle_groups']}\n"
                    )
                f.write("\n")
    found = sum(len(r["discrepancies"]) for r in report.values())
    print(f"{found} distinct discrepancies; report in {out}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
