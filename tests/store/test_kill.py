"""Nothing acknowledged is lost when the process dies without warning.

What this proves: between append_action() returning and the process being
killed, the action is already in the WAL and survives. What it cannot
prove: that the drive honored the fsync. SIGKILL leaves the operating
system's page cache intact, so this test exercises the commit-before-
acknowledge ordering and SQLite's crash recovery, not power loss. The
drive side (write-cache flushing left on, no USB sticks for the live
file) is a venue checklist item.
"""

import random
import subprocess
import sys
from pathlib import Path

import pytest

from madtracker.store import Store

HELPER = Path(__file__).with_name("kill_helper.py")
REPO_ROOT = Path(__file__).resolve().parents[2]


def run_and_kill(db_path: Path, lines_to_read: int) -> list[int]:
    proc = subprocess.Popen(
        [sys.executable, "-u", str(HELPER), str(db_path)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    acknowledged: list[int] = []
    try:
        for _ in range(lines_to_read):
            line = proc.stdout.readline()
            if not line:
                err = proc.stderr.read()
                pytest.fail(f"helper exited early: {err}")
            acknowledged.append(int(line))
    finally:
        proc.kill()  # SIGKILL on POSIX, TerminateProcess on Windows: no cleanup runs
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()
    return acknowledged


@pytest.mark.parametrize("attempt", range(4))
def test_acknowledged_actions_survive_sigkill(tmp_path, attempt):
    db_path = tmp_path / f"kill-{attempt}.sqlite"
    rng = random.Random()
    wanted = rng.randint(3, 12)
    acknowledged = run_and_kill(db_path, wanted)
    assert len(acknowledged) == wanted

    # The -wal file is normally left behind by the kill; reopening replays it.
    store = Store.open(db_path)
    try:
        assert store.integrity_check() == []
        race = store.races(store.events()[0].event_id)[0]
        stored = [e.action_id for e in store.actions(race.race_id)]
        # Every acknowledged action is present. The process may have committed
        # more that the parent never read (printed into the pipe, or not yet
        # printed, before the kill landed); extra rows are allowed, missing
        # rows are the failure.
        assert set(acknowledged) <= set(stored)
        assert stored == list(range(1, len(stored) + 1))
        # The recovered database is fully usable, not just readable.
        store.append_action(race.race_id, "note", {"after": "recovery"}, 1)
    finally:
        store.close()
