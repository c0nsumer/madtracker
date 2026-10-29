"""Run the click monkey over many seeds, one child process per seed.

    python tools/click_monkey/run.py --seeds 20 --steps 500
    python tools/click_monkey/run.py --seed 7 --steps 500 --replay

Each seed runs in its own process, so a crash, a hang or a leak in one
cannot spoil the next, and the parent reports it with the step the
child had reached. ``--replay`` runs one seed in this process and prints
every step with what the fakes answered. The exit code is the number of
failing seeds.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def child(seed: int, steps: int | None, tmp: Path, out: Path | None, verbose: bool) -> int:
    from dataclasses import asdict

    from monkey import Monkey

    trail_file = tmp / "trail.txt"

    def say(text: str) -> None:
        print(text, flush=True)

    m = Monkey(seed, steps, tmp, say=say)
    m.trail_file = trail_file
    trail_file.write_text("")
    if verbose:
        os.environ["MONKEY_VERBOSE"] = "1"
    result = m.run()
    m.dispose()
    if out is not None:
        out.write_text(json.dumps(asdict(result)))
    return 1 if result.failures else 0


def parent(args) -> int:
    seeds = (
        [args.seed] if args.seed is not None else list(range(args.first, args.first + args.seeds))
    )
    base = Path(args.tmp) if args.tmp else Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    failing = 0
    for seed in seeds:
        tmp = Path(tempfile.mkdtemp(prefix=f"monkey-{seed}-", dir=base))
        home = tmp / "home"
        home.mkdir()
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONPATH"] = str(REPO)
        # Nothing the run writes may reach the person's own settings or data folder.
        env["HOME"] = str(home)
        env["XDG_CONFIG_HOME"] = str(home / "config")
        env["XDG_DATA_HOME"] = str(home / "data")
        env["XDG_CACHE_HOME"] = str(home / "cache")
        out = tmp / "result.json"
        cmd = [
            sys.executable,
            str(HERE / "run.py"),
            "--child",
            "--seed",
            str(seed),
            "--tmp",
            str(tmp),
            "--json",
            str(out),
        ]  # noqa: E501
        if args.steps is not None:
            cmd += ["--steps", str(args.steps)]
        log = tmp / "child.log"
        started = time.monotonic()
        with open(log, "w") as f:
            try:
                rc = subprocess.run(
                    cmd, stdout=f, stderr=subprocess.STDOUT, env=env, timeout=args.timeout
                ).returncode  # noqa: E501
            except subprocess.TimeoutExpired:
                rc = "timeout"
        trail = (tmp / "trail.txt").read_text().splitlines() if (tmp / "trail.txt").exists() else []
        if out.exists():
            result = json.loads(out.read_text())
            fails = result["failures"]
            peak = result["peak_rss"] / 1024**2
            print(
                f"seed {seed}: {result['steps']} steps, {len(fails)} failures, peak {peak:.0f} MB, {time.monotonic() - started:.0f} s",
                flush=True,
            )  # noqa: E501
            for f_ in fails:
                print(
                    f"  seed {seed} step {f_['step']} [{f_['name']}] {f_['kind']}: {f_['what'][:4000]}",
                    flush=True,
                )  # noqa: E501
            bad = bool(fails)
        else:
            tail = log.read_text(errors="replace")[-3000:]
            print(f"seed {seed}: child ended without a result (exit {rc})", flush=True)
            print("  last steps: " + " | ".join(trail[-5:]), flush=True)
            print("  " + tail.replace("\n", "\n  "), flush=True)
            bad = True
        failing += bad
        if bad and args.keep:
            print(f"  kept {tmp}", flush=True)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"{failing} of {len(seeds)} seeds failed", flush=True)
    return failing


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )  # noqa: E501
    p.add_argument("--seeds", type=int, default=20, help="how many seeds, from --first")
    p.add_argument("--first", type=int, default=0, help="the first seed")
    p.add_argument("--seed", type=int, help="one seed only")
    p.add_argument("--steps", type=int, help="steps per seed (default: random, 200 to 2000)")
    p.add_argument("--replay", action="store_true", help="run --seed here, printing every step")
    p.add_argument("--tmp", help="where each seed's files go (default: the system temp folder)")
    p.add_argument("--keep", action="store_true", help="keep a failing seed's files")
    p.add_argument("--timeout", type=int, default=1200, help="seconds before a seed counts as hung")
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--json", help=argparse.SUPPRESS)
    args = p.parse_args()
    sys.path.insert(0, str(HERE))
    if args.child:
        return child(args.seed, args.steps, Path(args.tmp), Path(args.json), verbose=False)
    if args.replay:
        if args.seed is None:
            p.error("--replay needs --seed")
        base = Path(args.tmp) if args.tmp else Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f"monkey-{args.seed}-", dir=base))
        print(f"files in {tmp}", flush=True)
        return child(args.seed, args.steps, tmp, None, verbose=True)
    return parent(args)


if __name__ == "__main__":
    sys.exit(main())
