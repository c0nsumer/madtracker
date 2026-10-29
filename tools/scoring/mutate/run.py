"""Every mutant of the scoring engines, one at a time, against tests/scoring.

    python tools/scoring/mutate/run.py [--out DIR] [--workers N] [--modules M ...]

Each worker has its own copy of the program under DIR (see trees.py).
For each mutation site (mutator.py) the mutated module is written into
the copy, ``pytest -q -x tests/scoring`` runs with a 120 s kill, and the
original is restored. A mutant is killed when the tests fail, survived
when they pass. Results append to DIR/results.jsonl; a site already
there is skipped, so a run cut short resumes where it stopped. The
summary at the end covers every result in the file. The exit code is 0
when the baseline passes and every job ran, whatever survived.
"""

import argparse
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mutator import enumerate_sites  # noqa: E402
from trees import (  # noqa: E402
    MODULES,
    TIMEOUT,
    env,
    make_tree,
    prove_imports,
    scoring_path,
    swapped,
)

DEFAULT_OUT = Path(tempfile.gettempdir()) / "madtracker-scoring" / "mutate"
PYTEST = [
    "-m",
    "pytest",
    "-q",
    "-x",
    "-p",
    "no:cacheprovider",
    "-o",
    "faulthandler_timeout=90",
    "tests/scoring",
]


def pytest_in(tree: Path, log: Path) -> int:
    with open(log, "w") as fh:
        return subprocess.run(
            ["timeout", "-s", "KILL", str(TIMEOUT), sys.executable, *PYTEST],
            cwd=tree,
            env=env(tree),
            stdout=fh,
            stderr=subprocess.STDOUT,
        ).returncode


def verdict(rc: int, tail: str) -> str:
    if rc in (124, 137):
        return "timeout"
    if rc == 0:
        return "survived"
    if (
        "ERROR collecting" in tail
        or "ImportError" in tail
        or "SyntaxError" in tail
        or rc in (2, 3, 4)
    ):
        return "import_error"
    return "killed"


def summary(results: Path) -> None:
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    by = {m: Counter() for m in MODULES}
    for r in rows:
        by.setdefault(r["module"], Counter())[r["status"]] += 1
    print(
        f"\n{'module':14} {'mutants':>7} {'killed':>6} {'survived':>8} {'timeout':>7} {'import':>6}"
    )
    total = Counter()
    for mod, c in by.items():
        total += c
        print(
            f"{mod:14} {c.total():7} {c['killed']:6} {c['survived']:8} {c['timeout']:7} {c['import_error']:6}"
        )
    print(
        f"{'all':14} {total.total():7} {total['killed']:6} {total['survived']:8} {total['timeout']:7} {total['import_error']:6}"
    )
    for r in rows:
        if r["status"] == "survived":
            print(
                f"  survived {r['module']}:{r['index']} L{r['lineno']} {r['kind']}: {r['before'][:70]!r} -> {r['after'][:70]!r}"
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--modules", nargs="*", default=MODULES, choices=MODULES)
    args = ap.parse_args()
    out = args.out.resolve()
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    done = set()
    if results.exists():
        done = {
            (r["module"], r["index"]) for r in map(json.loads, results.read_text().splitlines())
        }

    trees = []
    for k in range(args.workers):
        tree = make_tree(out / f"tree-{k}")
        prove_imports(tree)
        # A survivor count means nothing against tests that already fail.
        if pytest_in(tree, logs / f"baseline-{k}.log") != 0:
            print(f"baseline fails in {tree}; see {logs / f'baseline-{k}.log'}")
            return 2
        trees.append(tree)

    jobs = queue.Queue()
    for mod in args.modules:
        _, sites = enumerate_sites(scoring_path(trees[0], mod).read_text())
        for i in range(len(sites)):
            if (mod, i) not in done:
                jobs.put((mod, i))
    print(f"{jobs.qsize()} jobs, {len(done)} already in {results}", flush=True)
    lock = threading.Lock()

    def work(tree: Path) -> None:
        while True:
            try:
                mod, i = jobs.get_nowait()
            except queue.Empty:
                return
            log = logs / f"{mod}-{i}.log"
            t0 = time.time()
            with swapped(tree, mod, i) as site:
                rc = pytest_in(tree, log)
            status = verdict(rc, log.read_text()[-3000:])
            if status == "killed":
                log.unlink()  # only the interesting logs are kept
            rec = {
                "module": mod,
                "index": i,
                "kind": site.kind,
                "lineno": site.lineno,
                "before": site.before[:200],
                "after": site.after[:200],
                "status": status,
                "elapsed": round(time.time() - t0, 1),
                "rc": rc,
            }
            with lock:
                with open(results, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")
                print(
                    f"{mod}:{i} L{site.lineno} {site.kind} {status} {rec['elapsed']}s", flush=True
                )

    started = time.time()
    threads = [threading.Thread(target=work, args=(t,)) for t in trees]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"ran in {round(time.time() - started)} s", flush=True)
    summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
