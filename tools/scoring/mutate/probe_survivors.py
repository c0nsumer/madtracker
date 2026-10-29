"""Run probe.py against every surviving mutant: does some random input tell it from the original?

    python tools/scoring/mutate/probe_survivors.py [--out DIR] [--scenarios N]

Reads DIR/results.jsonl from run.py and uses its first copy,
DIR/tree-0. The original's output is taken first in the same copy; a
survivor whose output differs is exposed (the tests miss a behavior),
one whose output matches is likely equivalent. Writes
DIR/probe_results.jsonl with the first differing line per survivor.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import DEFAULT_OUT  # noqa: E402
from trees import env, prove_imports, swapped  # noqa: E402

PROBE = Path(__file__).resolve().parent / "probe.py"


def probe(tree: Path, n: int) -> list[str]:
    proc = subprocess.run(
        [sys.executable, str(PROBE), str(n)],
        cwd=tree,
        env=env(tree),
        capture_output=True,
        text=True,
        timeout=300,
    )
    return (proc.stdout + proc.stderr).splitlines()


def first_difference(base: list[str], got: list[str]) -> dict | None:
    header = None
    for a, b in zip(base, got, strict=False):
        if a.startswith("## "):
            header = a
        if a != b:
            return {"scenario": header, "base": a[:600], "mutant": b[:600]}
    if len(got) != len(base):
        return {"scenario": "length", "base": str(len(base)), "mutant": str(len(got))}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--scenarios", type=int, default=600)
    args = ap.parse_args()
    tree = args.out / "tree-0"
    prove_imports(tree)
    base = probe(tree, args.scenarios)
    rows = [json.loads(line) for line in (args.out / "results.jsonl").read_text().splitlines()]
    with open(args.out / "probe_results.jsonl", "w") as out:
        for r in rows:
            if r["status"] != "survived":
                continue
            with swapped(tree, r["module"], r["index"]):
                first = first_difference(base, probe(tree, args.scenarios))
            r = dict(r, exposed=first is not None, first_diff=first)
            out.write(json.dumps(r) + "\n")
            out.flush()
            print(
                r["module"],
                r["index"],
                f"L{r['lineno']}",
                r["kind"],
                "EXPOSED" if first else "equivalent?",
                flush=True,
            )


if __name__ == "__main__":
    main()
