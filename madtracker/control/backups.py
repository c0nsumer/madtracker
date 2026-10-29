"""Automatic backups and the clean-close marker.

Backups go through ``Store.backup_to`` (SQLite's online backup), never a
file copy, because the live database's -wal file is part of its state.
They are taken when a race reaches provisional or final and on a clean
close: the two moments a result exists that the scorer would hate to
retype. Rotation runs only in the automatic folder. It keeps the newest
``KEEP`` files, plus the last backup of each of the last ``KEEP_DATES``
dates: a night of eighteen races writes about 37 backups, so a count
alone would keep less than one night, and the copy wanted when damage is found
next week is last week's. The date is the one in the backup's mark,
since a copy moved or restored from a stick gets a new modification
time; a backup without one falls back to its modification time. A folder the scorer chose is theirs; the app never
deletes anything in it.

The automatic folder beside the data file is always written. A chosen
folder is an extra copy, not a replacement: at the venue it is usually a
USB stick, and with the stick pulled a replacement folder would mean no
backup was written anywhere. ``run_backup`` takes both and reports a
failed extra copy as a warning, so the scorer hears about the stick
while the automatic copy still lands. The app passes the chosen folder
only for the end-of-night copies (close, Backup Now): the folder is
never pruned, and the file is cumulative, so one copy a night is the
whole night.

The marker file answers one question when a data file opens: did its
last session end through the normal close path? It is created on open
and removed on clean close (quit, or switching to another data file),
so a power cut or a crash leaves it behind. It cannot tell a crash from
a second copy of the app that is still running on the same file, so the
app also holds a lock file (``lock_path``) while a file is open and
refuses a file another window holds.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from madtracker import applog
from madtracker.dates import show_date_time
from madtracker.store import Store, StoreError, read_backup_mark

KEEP = 20
KEEP_DATES = 10
PREFIX = "madtracker-"
# What a data file held before a restore replaced it. Rotation never
# deletes one: as an ordinary backup it would be gone after twenty more
# results that night, and it is the only way back from a wrong pick.
BEFORE_RESTORE = PREFIX + "before-restore-"
UNCLEAN_NOTICE = (
    "The last session did not close cleanly. Your entries were recovered; check the current race."
)


def backup_name(now: datetime | None = None, prefix: str = PREFIX) -> str:
    """'madtracker-2026-10-15-192719.sqlite': named by when it was taken.

    The name is for people only (rotation reads the mark inside), so it
    sorts in time order; the event it holds is in its mark, which the
    restore question names. The event's date beside the time would read
    as the same date twice on its own night.
    """
    return f"{prefix}{(now or datetime.now()).strftime('%Y-%m-%d-%H%M%S')}.sqlite"


def backups_in(folder: Path) -> list[Path]:
    """The backups in folder, oldest first by modification time.

    A backup is a file that carries the mark, whatever its name: a data
    file saved into this folder, or a restored copy, is never rotated away.
    """
    if not os.path.isdir(folder):
        return []
    files = [p for p in folder.glob("*.sqlite") if p.is_file() and read_backup_mark(p) is not None]
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))


def restore_question(mark: dict) -> str:
    """What opening a backup asks: which event, from when, then whether to restore."""
    event = str(mark.get("event") or "").strip()
    try:
        taken = show_date_time(datetime.fromisoformat(str(mark.get("taken_at"))))
    except ValueError:
        taken = ""
    what = "This is a backup"
    if event:
        what += f" of {event}"
    if taken:
        what += f", taken {taken}"
    return f"{what}. Restore it as a new data file?"


def taken_on(path: Path, mark: dict | None = None) -> date:
    """The date a backup was taken: its mark's, else its modification time's."""
    mark = read_backup_mark(path) if mark is None else mark
    try:
        return datetime.fromisoformat(str((mark or {}).get("taken_at"))).date()
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime).date()


def rotate(folder: Path, keep: int = KEEP, dates: int = KEEP_DATES) -> list[Path]:
    """Keep the newest ``keep`` backups and the last of each of the last ``dates`` dates.

    Deletes the rest and returns what was removed; one that cannot be
    removed is logged and left for the next rotation. A copy taken before
    a restore (``BEFORE_RESTORE``) is neither counted nor deleted.
    """
    files = [p for p in backups_in(folder) if not p.name.startswith(BEFORE_RESTORE)]
    last_of: dict[date, Path] = {}
    for path in files:
        # Oldest first, so each date ends on its last backup.
        last_of[taken_on(path)] = path
    newest_dates = sorted(last_of)[max(0, len(last_of) - dates) :]
    kept = {*files[max(0, len(files) - keep) :], *(last_of[d] for d in newest_dates)}
    removed = []
    for path in files:
        if path in kept:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            # The new copy is already written; an old one something else
            # holds (an indexer, a sync client, a scanner) waits for the
            # next rotation rather than failing the backup it follows.
            applog.warning(f"Could not remove old backup {path}: {exc}")
            continue
        removed.append(path)
    return removed


def take_backup(
    store: Store,
    folder: Path,
    *,
    automatic_folder: bool,
    event: str = "",
    now: datetime | None = None,
    before_restore: bool = False,
) -> Path:
    """Back up into folder and rotate it when it is the automatic one.

    ``before_restore`` names the copy so rotation keeps it (``BEFORE_RESTORE``).

    The automatic folder is created if missing (it lives beside the data
    file); a chosen folder is not, because a missing chosen folder means
    the drive is gone, and writing a fresh folder on whatever now has
    that letter would hide the problem. Raises OSError, StoreError or
    sqlite3.Error.
    """
    if automatic_folder:
        folder.mkdir(parents=True, exist_ok=True)
        # A copy cut short by a crash stays as a .partial under a name
        # nothing lists or rotates, so the folder would collect one per
        # crash; a stale one is cleared before the next copy is taken.
        for stale in folder.glob("*.partial"):
            try:
                stale.unlink()
            except OSError:
                pass
    elif not os.path.isdir(folder):
        raise OSError(f"backup folder {folder} is not available")
    # A result and a close can land in the same second; a numbered name
    # keeps the earlier copy instead of overwriting it.
    name = backup_name(now, BEFORE_RESTORE if before_restore else PREFIX)
    target = folder / name
    n = 2
    while target.exists():
        target = folder / name.replace(".sqlite", f"-{n}.sqlite")
        n += 1
    path = store.backup_to(target, event, now)
    if automatic_folder:
        rotate(folder)
    return path


@dataclass(frozen=True)
class BackupResult:
    """What one backup run wrote.

    ``automatic`` is the copy beside the data file. ``extra`` is the copy
    in the chosen folder, or None when there is no chosen folder or it
    failed; ``warning`` then says why, in the scorer's words.
    """

    automatic: Path
    extra: Path | None = None
    warning: str | None = None


def run_backup(
    store: Store,
    automatic_dir: Path,
    chosen_dir: Path | None,
    *,
    event: str = "",
    now: datetime | None = None,
) -> BackupResult:
    """Write the automatic copy (rotated), then the extra copy when a folder is chosen.

    Raises OSError, StoreError or sqlite3.Error only when the automatic copy fails; a
    failed extra copy comes back as ``warning``. A chosen folder that is
    the automatic folder is not written twice.
    """
    when = now or datetime.now()
    automatic = take_backup(store, automatic_dir, automatic_folder=True, event=event, now=when)
    if chosen_dir is None or str(chosen_dir).strip() == "":
        return BackupResult(automatic)
    try:
        same = chosen_dir.resolve() == automatic_dir.resolve()
    except OSError:
        same = False
    if same:
        return BackupResult(automatic)
    try:
        extra = take_backup(store, chosen_dir, automatic_folder=False, event=event, now=when)
    except (OSError, StoreError, sqlite3.Error) as exc:
        return BackupResult(
            automatic,
            None,
            f"The extra backup failed ({exc}):\n{chosen_dir}\n\n"
            f"The automatic backup was written to:\n{automatic.parent}",
        )
    return BackupResult(automatic, extra)


def marker_path(data_file: Path) -> Path:
    """The marker beside a data file: madtracker.sqlite has madtracker.open.

    Named after the file rather than fixed per folder, so two data files
    kept in one folder never answer for each other's last close.
    """
    return data_file.with_name(data_file.stem + ".open")


def lock_path(data_file: Path) -> Path:
    """The lock beside a data file: madtracker.sqlite has madtracker.sqlite.lock."""
    return data_file.with_name(data_file.name + ".lock")


def writes_over(path: Path, data_file: Path) -> bool:
    """Whether writing ``path`` would replace ``data_file`` or a file kept beside it.

    The -wal and -shm are part of the open database, and the lock and the
    marker are how the app knows the file is in use: a sheet or a copy
    written over any of them wrecks the file being scored into. A save
    box takes any name typed, whatever its filter.
    """
    data_file = Path(data_file)
    beside = (
        data_file,
        Path(f"{data_file}-wal"),
        Path(f"{data_file}-shm"),
        lock_path(data_file),
        marker_path(data_file),
    )
    return any(_same_file(path, part) for part in beside)


def open_file_refusal(path: Path, data_file: Path) -> str | None:
    """Why a save over ``path`` is refused, or None when it may go ahead.

    The one sentence every save box says: the data file is named as
    what it is, and a -wal, -shm, lock, or marker as a file that belongs
    to it, since "madtracker.sqlite-wal is the open file" reads as a
    mistake to a scorer who never typed that name.
    """
    if not writes_over(path, data_file):
        return None
    name = Path(path).name
    if _same_file(path, Path(data_file)):
        return f"{name} is the open data file. Choose another name."
    return f"{name} belongs to the open data file. Choose another name."


def _same_file(path: Path, other: Path) -> bool:
    try:
        return os.path.samefile(path, other)
    except OSError:
        return Path(path).absolute() == other.absolute()


def mark_open(data_file: Path) -> bool:
    """Create the marker; return True when one was already there (unclean last close)."""
    marker = marker_path(data_file)
    unclean = marker.exists()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"opened {datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")
    return unclean


def mark_closed(data_file: Path) -> None:
    marker_path(data_file).unlink(missing_ok=True)


def pid_alive(pid: int) -> bool:
    """Whether a process with this id is running on this machine.

    Qt's own staleness check for a lock file differs by platform (on
    Windows a lock left by a crashed copy is still refused), so the
    program asks the operating system itself before it trusts a lock.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        # Its own handle with use_last_error, so get_last_error reads the
        # error this call set, not one Python's own calls left since.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        query = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
        handle = kernel32.OpenProcess(query, False, pid)
        if not handle:
            # Access denied is a live process the user may not open;
            # any other failure is no such process.
            return ctypes.get_last_error() == 5
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
