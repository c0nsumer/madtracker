"""A backup says so inside the file: the restore question and rotation read the mark."""

import os
from datetime import datetime
from pathlib import Path

from madtracker.control.backups import (
    backups_in,
    lock_path,
    restore_question,
    rotate,
    take_backup,
    taken_on,
)
from madtracker.store import Store, read_backup_mark

WHEN = datetime(2026, 10, 10, 21, 45, 12)


def _data_file(tmp_path: Path) -> Store:
    return Store.open(tmp_path / "madtracker.sqlite")


def test_a_backup_carries_its_mark_and_the_data_file_does_not(tmp_path):
    store = _data_file(tmp_path)
    backup = store.backup_to(tmp_path / "copy.sqlite", "Race Night 12", WHEN)
    mark = read_backup_mark(backup)
    assert mark == {
        "event": "Race Night 12",
        "source": str(store.path),
        "taken_at": "2026-10-10T21:45:12",
    }
    assert read_backup_mark(store.path) is None
    store.close()


def test_the_mark_survives_a_rename_and_a_move(tmp_path):
    store = _data_file(tmp_path)
    backup = store.backup_to(tmp_path / "copy.sqlite")
    store.close()
    stick = tmp_path / "stick"
    stick.mkdir()
    renamed = backup.rename(stick / "Race Night 12.sqlite")
    assert read_backup_mark(renamed) is not None


def test_a_file_that_is_not_a_database_is_not_a_backup(tmp_path):
    junk = tmp_path / "junk.sqlite"
    junk.write_bytes(b"not a database")
    assert read_backup_mark(junk) is None
    assert read_backup_mark(tmp_path / "missing.sqlite") is None


def test_a_partial_copy_a_crash_left_is_cleared_by_the_next_backup(tmp_path):
    """A crash mid-copy leaves a .partial that rotation never names; the
    next backup into the automatic folder removes it, and leaves a chosen
    folder's files alone."""
    store = _data_file(tmp_path)
    automatic = tmp_path / "backups"
    automatic.mkdir()
    stale = automatic / "madtracker-2026-10-09-203000.sqlite.partial"
    stale.write_bytes(b"half a copy")
    chosen = tmp_path / "stick"
    chosen.mkdir()
    theirs = chosen / "madtracker-2026-10-09-203000.sqlite.partial"
    theirs.write_bytes(b"not ours to judge")
    take_backup(store, automatic, automatic_folder=True, now=WHEN)
    take_backup(store, chosen, automatic_folder=False, now=WHEN)
    assert not stale.exists()
    assert theirs.exists()
    assert len(backups_in(automatic)) == 1 and len(backups_in(chosen)) == 1
    store.close()


def test_an_old_backup_that_cannot_be_removed_does_not_fail_the_backup(tmp_path, monkeypatch):
    """The new copy is written first; a held old copy is left for the next rotation."""
    from pathlib import Path as _Path

    store = _data_file(tmp_path)
    folder = tmp_path / "backups"
    old = [
        take_backup(store, folder, automatic_folder=True, now=WHEN.replace(second=s))
        for s in range(2)
    ]
    held = old[0]
    real_unlink = _Path.unlink

    def unlink(self, missing_ok=False):
        if self == held:
            raise PermissionError(f"held by a scanner: {self}")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(_Path, "unlink", unlink)
    try:
        # keep=1 dooms the older copy alone; held, it is skipped, not raised.
        assert rotate(folder, keep=1) == []
        assert held.exists()
        newest = take_backup(store, folder, automatic_folder=True, now=WHEN.replace(second=5))
        assert newest.exists() and held.exists()
    finally:
        monkeypatch.undo()
        store.close()
    assert rotate(folder, keep=1) == old, "released, the next rotation removes it"


def test_rotation_deletes_only_marked_files_whatever_their_names(tmp_path):
    store = _data_file(tmp_path)
    folder = tmp_path / "backups"
    kept = [
        take_backup(store, folder, automatic_folder=True, now=WHEN.replace(second=s))
        for s in range(3)
    ]
    # A data file saved into the folder, named like a backup, is never
    # counted or deleted: it has no mark.
    stray = folder / "madtracker-2026-10-10-000000.sqlite"
    Store.open(stray).close()
    assert backups_in(folder) == kept
    assert rotate(folder, keep=1) == kept[:2]
    assert stray.exists() and kept[2].exists()
    store.close()


def test_the_restore_question_names_the_event_and_when():
    mark = {"event": "Race Night 12", "taken_at": "2026-10-10T21:45:12"}
    assert restore_question(mark) == (
        "This is a backup of Race Night 12, taken 2026-Oct-10 9:45 PM. Restore it as a new data file?"
    )
    assert restore_question({}) == "This is a backup. Restore it as a new data file?"


def test_the_lock_sits_beside_its_data_file():
    assert lock_path(Path("/d/madtracker.sqlite")) == Path("/d/madtracker.sqlite.lock")


def test_rotation_keeps_the_newest_twenty_and_the_last_of_each_of_ten_dates(tmp_path):
    store = _data_file(tmp_path)
    folder = tmp_path / "backups"
    nights = {}
    for night in range(1, 13):
        when = WHEN.replace(day=night)
        nights[night] = [
            take_backup(store, folder, automatic_folder=True, now=when.replace(minute=m))
            for m in range(5)
        ]
    store.close()
    # Nights 9 to 12 are the newest twenty; nights 3 to 8 keep their last.
    expected = [nights[n][-1] for n in range(3, 9)]
    expected += [path for n in range(9, 13) for path in nights[n]]
    assert backups_in(folder) == expected


def test_rotation_dates_a_backup_by_its_mark_not_its_file_time(tmp_path):
    store = _data_file(tmp_path)
    folder = tmp_path / "backups"
    taken = [
        store.backup_to(folder / f"copy-{day}-{n}.sqlite", "", WHEN.replace(day=day, minute=n))
        for day in (8, 9, 10)
        for n in range(2)
    ]
    store.close()
    # Copied off a stick: every file has the same, newer time, in order.
    for i, path in enumerate(taken):
        os.utime(path, (2_000_000_000 + i, 2_000_000_000 + i))
    assert taken_on(taken[0]) == WHEN.replace(day=8).date()
    assert rotate(folder, keep=1, dates=2) == [*taken[:3], taken[4]]
    assert backups_in(folder) == [taken[3], taken[5]]


def test_a_backup_is_named_by_when_it_was_taken():
    """Named by the time alone: the event's date beside it would read as the date twice."""
    from madtracker.control.backups import backup_name

    assert backup_name(WHEN.replace(hour=19, minute=27, second=9)) == (
        f"madtracker-{WHEN:%Y-%m-%d}-192709.sqlite"
    )
