"""End-to-end check of the store on a scratch directory.

The packaged exe runs this behind the --self-test flag, so a PyInstaller
bundle that is missing the sqlite3 extension, ships a SQLite without
WAL or JSON support, or cannot write to its data folder fails the
packaging smoke test instead of failing at the venue. The scenario is
deliberately tiny: one rider, one event, one race, a few actions, a void,
an integrity check, a backup, and a reopen of the backup.
"""

import os
from pathlib import Path

from madtracker.store.store import Store


def run_selftest(tmp_dir: str | os.PathLike[str]) -> list[str]:
    """Exercise the store under tmp_dir; return a list of failures, empty on success.

    Failures are returned rather than raised so the caller can print all
    of them and choose its own exit code. Each message names the step.
    """
    failures: list[str] = []
    base = Path(tmp_dir)
    db_path = base / "selftest.sqlite"
    backup_path = base / "selftest-backup.sqlite"
    step = "open"
    try:
        store = Store.open(db_path)
        try:
            step = "rider"
            rider = store.add_rider("Test", "Rider", usac_license="000001")
            if store.find_rider_by_license("000001") != rider:
                failures.append("rider: find_by_license did not return the added rider")

            step = "event"
            event = store.add_event("Self-test event", "2026-01-01", venue="Nowhere")
            entry = store.add_entry(event.event_id, rider.rider_id, bib=7, local_group="GroupA")
            if entry.local_group != "GroupA":
                failures.append("event: entry did not keep its group")

            step = "race"
            race = store.add_race(
                event.event_id,
                "Self-test chase",
                "placings",
                group_label="GroupA",
                rules={"laps": 10},
                rules_version="selftest",
            )
            store.add_race_entry(race.race_id, rider.rider_id)
            if store.race(race.race_id).rules != {"laps": 10}:
                failures.append("race: rules did not round-trip through JSON")

            step = "actions"
            first = store.append_action(race.race_id, "started", {"bibs": [7]}, 1)
            second = store.append_action(race.race_id, "finish_order", {"order": [7]}, 1)
            store.void_action(race.race_id, second, note="self-test undo")
            third = store.append_action(race.race_id, "finish_order", {"order": [7]}, 1)
            live = [e.action_id for e in store.live_actions(race.race_id)]
            if live != [first, third]:
                failures.append(f"actions: live_actions returned {live}, expected {[first, third]}")
            if len(store.actions(race.race_id)) != 4:
                failures.append("actions: full log should hold four rows including the void")

            step = "integrity"
            problems = store.integrity_check()
            if problems:
                failures.append("integrity: " + "; ".join(problems))

            step = "backup"
            store.backup_to(backup_path)
        finally:
            store.close()

        step = "reopen backup"
        copy = Store.open(backup_path)
        try:
            copied = copy.actions(race.race_id)
            if len(copied) != 4:
                failures.append(f"reopen backup: expected 4 actions, found {len(copied)}")
            if copy.integrity_check():
                failures.append("reopen backup: integrity check failed")
        finally:
            copy.close()

        step = "clean close"
        wal = db_path.with_name(db_path.name + "-wal")
        if wal.exists() and wal.stat().st_size > 0:
            failures.append("clean close: the -wal file still holds data")
    except Exception as exc:
        failures.append(f"{step}: {type(exc).__name__}: {exc}")
    return failures
