"""Replay whole scoring nights headless and report every invariant that broke.

    python tools/session_replay/run.py --nights 3 --seed 1
    python tools/session_replay/run.py --fast

Exit code is the number of breaks (capped at 255).
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1]))


def _sabotage_total() -> None:
    """Every points row's total one too many on the screen."""
    from dataclasses import replace

    from madtracker.control import race_screen

    rows = race_screen._points_rows

    def wrong(*a, **k):
        return [replace(r, total=(r.total or 0) + 1) for r in rows(*a, **k)]

    race_screen._points_rows = wrong


def _sabotage_state() -> None:
    """A batch that moves a race's state forgets to."""
    from madtracker.store import Store

    append = Store.append_batch

    def forgetful(self, race_id, *a, state=None, **k):
        return append(self, race_id, *a, **k)

    Store.append_batch = forgetful


def _sabotage_staged() -> None:
    """The staged order is written without its tail."""
    from madtracker.control import race

    to_json = race._Staged.to_json
    race._Staged.to_json = lambda self: {**to_json(self), "tail": []}


SABOTAGE = {"total": _sabotage_total, "state": _sabotage_state, "staged": _sabotage_staged}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nights", type=int, default=3, help="rounds of clean, messy, switch")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--fast", action="store_true", help="one round, fewer Undo checks")
    parser.add_argument("--only", choices=("clean", "messy", "switch", "storm"), action="append")
    parser.add_argument("--out", type=Path, help="keep the files here (default: a temp folder)")
    parser.add_argument("--night", type=int, help="run only this round (1-based), to repro one")
    parser.add_argument("--trace", action="store_true", help="print every step as it is taken")
    parser.add_argument("--show", type=int, default=40, help="breaks printed in full")
    parser.add_argument(
        "--sabotage",
        choices=sorted(SABOTAGE),
        help="break the app on purpose, to see the harness catch it",
    )
    parser.add_argument("--coverage", action="store_true", help="list the mishaps that fired")
    parser.add_argument(
        "--wild",
        type=float,
        default=0.08,
        help="messy night: the share of steps that pick any offered control",
    )
    args = parser.parse_args(argv)

    import harness
    import sessions
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    from madtracker.ui.look import apply_look

    qapp = QApplication.instance() or QApplication([])
    apply_look(qapp)
    harness.install_patches()
    if args.sabotage:
        SABOTAGE[args.sabotage]()

    nights = 1 if args.fast else args.nights
    undo_rate = 0.25 if args.fast else 0.6
    work = args.out or Path(tempfile.mkdtemp(prefix="madtracker-replay-"))
    work.mkdir(parents=True, exist_ok=True)
    kinds = args.only or ["clean", "messy", "switch"]
    plays = {
        "clean": sessions.clean_night,
        "messy": sessions.messy_night,
        "switch": sessions.switch_night,
        "storm": sessions.storm_night,
    }
    started = time.monotonic()
    template = harness.seed_template(work)
    totals = Counter()
    harness.REC.trace = args.trace
    rounds = [args.night - 1] if args.night else range(nights)
    for night in rounds:
        for k, kind in enumerate(kinds):
            seed = args.seed * 1000 + night * 10 + k
            name = f"{kind}-{night + 1}-seed{seed}"
            rng = random.Random(seed)
            t0 = time.monotonic()
            session = harness.Session(qapp, work, template, name, rng, undo_rate)
            session.wild = args.wild
            try:
                plays[kind](session)
            except Exception as exc:  # a harness bug or an app one; either way, a break
                import traceback

                harness.REC.add(
                    "session stopped",
                    "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:],
                )
            finally:
                session.close()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            totals["steps"] += session.steps
            totals["undo checks"] += session.undo_checks
            totals["exports"] += session.exports
            print(
                f"{name}: {session.steps} steps, {session.undo_checks} undo checks,"
                f" {time.monotonic() - t0:.0f} s, max RSS {harness.rss_mb():.0f} MB",
                flush=True,
            )

    if args.coverage:
        for what, n in sorted(harness.REC.coverage.items()):
            print(f"{n:5d}  {what}")
    breaks = harness.REC.breaks
    by_kind = Counter(b.kind for b in breaks)
    print()
    shown = 0
    seen: set[tuple[str, str]] = set()
    for b in breaks:
        sig = (b.kind, b.facts[:160])
        if sig in seen:
            continue
        seen.add(sig)
        if shown < args.show:
            print(b.line())
            shown += 1
    if by_kind:
        print()
        for kind, n in by_kind.most_common():
            print(f"{n:5d}  {kind}")
    print(
        f"\n{totals['steps']} steps, {totals['undo checks']} undo checks,"
        f" {totals['exports']} export rounds, {time.monotonic() - started:.0f} s,"
        f" max RSS {harness.rss_mb():.0f} MB"
    )
    print(f"files: {work}" if args.out else "")
    if not args.out:
        shutil.rmtree(work, ignore_errors=True)
    print(f"breaks: {len(breaks)}")
    return min(len(breaks), 255)


if __name__ == "__main__":
    sys.exit(main())
