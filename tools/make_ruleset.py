"""Write a ruleset JSON file from command-line values.

A venue's house values are not compiled into the app. This tool builds
a ruleset file from the rulebook plus the values given on the command
line, and the file is then imported once through File > Settings > Rulesets (or
kept in local/rulesets/, which is gitignored, beside the venue logo).

Run from the repo root with the venv active. Every value is optional
and defaults to the rulebook's. For example:

    python tools/make_ruleset.py --name "Club rules" --points-table 10,7,5,3,2,1 \\
        --madison-table 5,3,2,1 --lap-points 10 --out local/rulesets/club.json
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from madtracker.control import rulesets  # noqa: E402


def table(text: str) -> tuple[int, ...]:
    parts = [p for p in text.replace(",", " ").replace("-", " ").split() if p]
    if not parts or not all(p.isdigit() for p in parts):
        raise argparse.ArgumentTypeError(f"{text!r} is not a points table like 10,7,5,3,2,1")
    return tuple(int(p) for p in parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", required=True, help="the ruleset's name, as the app shows it")
    ap.add_argument("--points-table", type=table, help="points race sprint points, by place")
    ap.add_argument(
        "--points-last-single",
        action="store_true",
        help="the points race's last sprint awards the same table (default: double)",
    )
    ap.add_argument("--madison-table", type=table, help="madison sprint points, by place")
    ap.add_argument(
        "--madison-last-single",
        action="store_true",
        help="the madison's last sprint awards the same table (default: double)",
    )
    ap.add_argument("--tempo-points", type=int, help="tempo points per sprint")
    ap.add_argument("--lap-points", type=int, help="a lap gained or lost, in every sprint format")
    ap.add_argument("--lap-gained", type=int, help="a lap gained, when it differs from a lap lost")
    ap.add_argument("--lap-lost", type=int, help="a lap lost, when it differs from a lap gained")
    ap.add_argument("--survivors", type=int, help="riders in the elimination's final sprint")
    ap.add_argument("--places", type=int, help="win-and-out places awarded")
    ap.add_argument("--direction", choices=["forward", "reverse"], help="win-and-out direction")
    ap.add_argument(
        "--lapped-riders-dnf",
        action="store_true",
        help="a lapped rider who stays in ranks with the DNFs (UCI 3.2.177) instead of by laps down",
    )
    ap.add_argument("--out", type=Path, required=True, help="the JSON file to write")
    args = ap.parse_args(argv)

    doc = rulesets.apply_values(
        rulesets.builtin_ruleset(),
        points_table=args.points_table,
        points_last_double=False if args.points_last_single else None,
        madison_table=args.madison_table,
        madison_last_double=False if args.madison_last_single else None,
        tempo_points=args.tempo_points,
        lap_points=args.lap_points,
        lap_gained=args.lap_gained,
        lap_lost=args.lap_lost,
        survivors=args.survivors,
        places=args.places,
        direction=args.direction,
        lapped_riders_placed=False if args.lapped_riders_dnf else None,
    )
    doc["name"] = args.name
    problems = rulesets.validate_ruleset(doc)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    out = rulesets.export_ruleset(doc, args.out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
