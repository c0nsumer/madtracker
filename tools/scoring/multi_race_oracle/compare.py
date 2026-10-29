"""Compare the oracle with multi_race.compute over generated seasons.

    python compare.py --seeds 200 [--start 0] [--kind four_race_omnium]
                      [--basetemp DIR] [--keep] [--strict] [--seed N --dump]

Each seed builds a season in its own folder under ``--basetemp``, runs
both computations, and diffs them. A core difference (refusal, state,
membership, ranks, statuses, per-race points, totals, penalties, the
left-out / not-yet-raced / racing sets, DNF before DQ) is a failure and
the seed's folder is kept with a ``diff.txt``. A display difference
(names, bibs, colors, group spelling, the count line) is reported and
fails only with ``--strict``. The exit code is the number of failing
seeds, capped at 125.

``--seed N --dump`` prints both tables for one seed.
"""

import argparse
import shutil
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import oracle as O  # noqa: E402
import season  # noqa: E402

from madtracker.control import multi_race  # noqa: E402
from madtracker.store import Store  # noqa: E402

DEFAULT_BASETEMP = Path(tempfile.gettempdir()) / "madtracker-scoring" / "multi-race-oracle"


def apply_mutant(name: str) -> None:
    """A known-wrong change to the program, to show the oracle catches it (a self-check).

    Each mutant is one rule the register has a row for; the comparer
    must report core mismatches under it on a modest seed count.
    """
    import madtracker.scoring.aggregate as A
    from madtracker.scoring import rules as RU

    if name == "no-countback":
        # R-TEAM-3: the 2B19(e) countback dropped; ties share the rank.
        orig = A.compute

        def patched(rules, entrants, races, penalties=None):
            if rules.tie_break == "most_firsts_then_last_race":
                rules = RU.AggregateRules.from_dict({**rules.to_dict(), "tie_break": "none"})
            return orig(rules, entrants, races, penalties)

        A.compute = patched
        multi_race.compute_aggregate = patched
    elif name == "beyond-table":
        # R-TEAM-5: a place past the table scores 1, not 0.
        orig = RU.usac_omnium_rules
        multi_race.DEFAULTS[multi_race.PLACES] = lambda: RU.AggregateRules.from_dict(
            {**orig().to_dict(), "points_beyond_table": 1}
        )
        multi_race.DEFAULTS[multi_race.OMNIUM] = multi_race.DEFAULTS[multi_race.PLACES]
    elif name == "no-minimum":
        # R-TEAM-4: a team that rode one night of two stays in.
        orig_rode = multi_race._rode

        def patched(per_race):
            rode = orig_rode(per_race)
            every = set().union(*rode) if rode else set()
            return [every for _ in rode]

        multi_race._rode = patched
    elif name == "dnf-out":
        # R-RIDER-2: a rider who DNFs a race is left out of the Omnium by Place.
        orig = multi_race._rode
        multi_race._rode = lambda per_race: [
            {r.entrant_id for r in st.rows if r.status is None} for st in per_race
        ]
    elif name == "twenty-first":
        # R-OMNI-1: 21st scores 0 instead of 1.
        orig = RU.uci_omnium_rules
        multi_race.DEFAULTS[multi_race.FOUR_RACE] = lambda: RU.AggregateRules.from_dict(
            {**orig().to_dict(), "points_beyond_table": 0}
        )
    elif name == "penalty-after":
        # R-OMNI-5: the penalty shown but not taken off before ranking.
        orig = A.compute

        def patched(rules, entrants, races, penalties=None):
            return orig(rules, entrants, races, None)

        A.compute = patched
        multi_race.compute_aggregate = patched
    else:
        raise SystemExit(f"unknown mutant {name}")


MUTANTS = ("no-countback", "beyond-table", "no-minimum", "dnf-out", "twenty-first", "penalty-after")


def refused(table) -> bool:
    """True when the table is refused, whatever shape ``refusal`` takes (str, object, None)."""
    r = table.refusal
    if r is None:
        return False
    if isinstance(r, str):
        return bool(r.strip())
    for attr in ("lead", "text"):
        if hasattr(r, attr):
            return bool(getattr(r, attr))
    return bool(r)


def _row_key(row, riders: bool):
    if riders:
        return row.rider_id
    return tuple(sorted(row.riders)) or ("team", row.team)


def normalize_program(table) -> dict:
    """multi_race.MultiRaceTable -> the comparable shape."""
    groups = []
    for g in table.groups:
        ranked, tail = [], []
        for r in g.rows:
            key = _row_key(r, g.riders)
            if r.rank is None or r.status:
                tail.append((r.status, key))
            else:
                ranked.append((r.rank, key, tuple(r.per_race), r.total, r.penalty))
        display = [(_row_key(r, g.riders), r.team, r.bib, r.color, tuple(r.riders)) for r in g.rows]
        groups.append(
            {
                "gkey": O.gkey(g.group),
                "label": g.group,
                "races": [c.race_id for c in g.columns],
                "ranked": sorted(ranked, key=lambda t: (t[0], repr(t[1]))),
                "tail": tail,
                "display": sorted(display, key=lambda t: repr(t[0])),
            }
        )
    return {
        "refused": refused(table),
        "state": table.state,
        "counted": table.counted,
        "groups": groups,
        "left_out": sorted(c.race_id for c in table.left_out),
        "not_yet": sorted(c.race_id for c in table.not_yet_raced),
        "racing": sorted(c.race_id for c in table.racing),
        "events": [e[0] for e in table.events],
    }


def normalize_oracle(table: O.OTable) -> dict:
    groups = []
    for g in table.groups:
        ranked, tail = [], []
        for r in g.rows:
            if r.rank is None or r.status:
                tail.append((r.status, r.key))
            else:
                ranked.append((r.rank, r.key, tuple(r.per_race), r.total, r.penalty))
        display = [(r.key, r.name, r.bib, r.color, tuple(r.riders)) for r in g.rows]
        groups.append(
            {
                "gkey": O.gkey(g.label),
                "label": g.label,
                "races": g.race_ids,
                "ranked": sorted(ranked, key=lambda t: (t[0], repr(t[1]))),
                "tail": tail,
                "display": sorted(display, key=lambda t: repr(t[0])),
            }
        )
    return {
        "refused": table.refused,
        "state": table.state,
        "counted": table.counted,
        "groups": groups,
        "left_out": sorted(table.left_out),
        "not_yet": sorted(table.not_yet_raced),
        "racing": sorted(table.racing),
        "events": table.events,
    }


def diff(prog: dict, orc: dict) -> tuple[list[str], list[str]]:
    """(core differences, display differences), each a list of lines."""
    core, show = [], []
    for k in ("refused", "state", "left_out", "not_yet", "racing", "events"):
        if prog[k] != orc[k]:
            core.append(f"{k}: program {prog[k]!r} vs oracle {orc[k]!r}")
    if prog["counted"] != orc["counted"]:
        show.append(f"counted: program {prog['counted']!r} vs oracle {orc['counted']!r}")
    pg = {g["gkey"]: g for g in prog["groups"]}
    og = {g["gkey"]: g for g in orc["groups"]}
    if list(pg) != list(og):
        core.append(f"groups: program {list(pg)} vs oracle {list(og)}")
    for key in pg.keys() & og.keys():
        a, b = pg[key], og[key]
        if a["races"] != b["races"]:
            core.append(f"group {key}: columns program {a['races']} vs oracle {b['races']}")
        if a["ranked"] != b["ranked"]:
            core.append(f"group {key}: ranked rows differ")
            sa, sb = set(a["ranked"]), set(b["ranked"])
            for t in sorted(sa - sb, key=lambda t: (t[0], repr(t[1]))):
                core.append(f"  program only: {t}")
            for t in sorted(sb - sa, key=lambda t: (t[0], repr(t[1]))):
                core.append(f"  oracle only:  {t}")
        if sorted(a["tail"], key=repr) != sorted(b["tail"], key=repr):
            core.append(f"group {key}: tail program {a['tail']} vs oracle {b['tail']}")
        statuses = [s for s, _ in a["tail"]]
        if "DQ" in statuses and "DNF" in statuses:
            if statuses.index("DQ") < len(statuses) - 1 - statuses[::-1].index("DNF"):
                core.append(f"group {key}: a DQ row precedes a DNF row: {statuses}")
        if a["display"] != b["display"]:
            show.append(f"group {key}: display differs")
            for x, y in zip(a["display"], b["display"], strict=False):
                if x != y:
                    show.append(f"  program {x}\n  oracle  {y}")
        if a["label"] != b["label"]:
            show.append(f"group {key}: label program {a['label']!r} vs oracle {b['label']!r}")
    return core, show


def coverage(prog: dict, stats: Counter) -> None:
    stats["seeds"] += 1
    stats[f"state:{prog['state']}"] += 1
    if prog["refused"]:
        stats["refused"] += 1
    stats["groups"] += len(prog["groups"])
    for g in prog["groups"]:
        if not g["label"].strip():
            stats["no-group"] += 1
        ranks = [t[0] for t in g["ranked"]]
        if len(ranks) != len(set(ranks)):
            stats["shared-rank"] += 1
        for t in g["tail"]:
            stats[f"tail:{t[0]}"] += 1
        if any(t[4] for t in g["ranked"]):
            stats["penalty-shown"] += 1
        if any(None in t[2] for t in g["ranked"]):
            stats["blank-cell"] += 1
        stats["rows"] += len(g["ranked"]) + len(g["tail"])
    if prog["left_out"]:
        stats["left-out"] += 1
    if prog["not_yet"]:
        stats["not-yet-raced"] += 1
    if prog["racing"]:
        stats["racing"] += 1


def run_seed(seed: int, basetemp: Path, kind: str | None, keep: bool, strict: bool, dump: bool):
    folder = basetemp / f"seed-{seed}"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    store = Store.open(folder / "season.sqlite")
    try:
        built = season.build(store, seed, kind)
        prog = normalize_program(multi_race.compute(store, built.standings_id))
        orc_table = O.oracle(store, built.standings_id)
        orc = normalize_oracle(orc_table)
    finally:
        store.close()
    core, show = diff(prog, orc)
    failed = bool(core) or (strict and bool(show))
    if dump:
        print(f"--- seed {seed} kind {built.kind} ---")
        print("program:", prog)
        print("oracle: ", orc)
        print("season stats:", dict(built.stats))
        print("oracle notes:", orc_table.notes)
    if failed or keep:
        lines = [f"seed {seed} kind {built.kind}", "core:", *core, "display:", *show, ""]
        lines += ["season stats: " + repr(dict(built.stats))]
        lines += ["oracle notes: " + repr(orc_table.notes)]
        lines += ["", "program: " + repr(prog), "", "oracle:  " + repr(orc)]
        lines += ["", f"repro: python {HERE / 'compare.py'} --seed {seed} --dump"]
        (folder / "diff.txt").write_text("\n".join(lines))
    else:
        shutil.rmtree(folder, ignore_errors=True)
    return built, prog, core, show


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--seed", type=int, default=None, help="one seed")
    ap.add_argument("--kind", default=None, choices=list(season.KINDS))
    ap.add_argument("--basetemp", default=str(DEFAULT_BASETEMP))
    ap.add_argument("--keep", action="store_true", help="keep every seed's folder")
    ap.add_argument("--strict", action="store_true", help="display differences fail too")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument(
        "--mutate", default=None, choices=MUTANTS, help="self-check: a known-wrong program"
    )
    args = ap.parse_args()
    if args.mutate:
        apply_mutant(args.mutate)
    basetemp = Path(args.basetemp)
    basetemp.mkdir(parents=True, exist_ok=True)
    seeds = [args.seed] if args.seed is not None else range(args.start, args.start + args.seeds)
    stats: Counter = Counter()
    season_stats: Counter = Counter()
    failures, display_only, crashes = [], [], []
    t0 = time.monotonic()
    for seed in seeds:
        try:
            built, prog, core, show = run_seed(
                seed, basetemp, args.kind, args.keep, args.strict, args.dump
            )
        except Exception:
            crashes.append(seed)
            print(f"seed {seed}: CRASH\n{traceback.format_exc()}")
            continue
        coverage(prog, stats)
        season_stats.update(built.stats)
        if core:
            failures.append(seed)
            print(f"seed {seed} ({built.kind}): CORE MISMATCH")
            for line in core:
                print("   ", line)
        elif show:
            display_only.append(seed)
            if args.strict or args.dump:
                print(f"seed {seed} ({built.kind}): display differs")
                for line in show:
                    print("   ", line)
    took = time.monotonic() - t0
    print()
    print(f"{stats['seeds']} seeds in {took:.0f} s ({took / max(1, stats['seeds']):.2f} s/seed)")
    print("coverage:", dict(sorted(stats.items())))
    print("season:  ", dict(sorted(season_stats.items())))
    print(f"core mismatches: {len(failures)} {failures[:40]}")
    print(f"display-only:    {len(display_only)} {display_only[:40]}")
    print(f"crashes:         {len(crashes)} {crashes[:40]}")
    bad = len(failures) + len(crashes) + (len(display_only) if args.strict else 0)
    return min(bad, 125)


if __name__ == "__main__":
    sys.exit(main())
