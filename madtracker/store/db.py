"""Opening, checking, closing and backing up the SQLite file.

Transaction control: connections are opened with autocommit=True (Python
3.12+), which turns off the sqlite3 module's legacy implicit BEGIN before
DML. The Store then issues BEGIN IMMEDIATE and COMMIT itself, so every
write is one short, visible transaction and a read outside one is a
single-statement snapshot. The legacy isolation_level=None gives the same
behavior; autocommit=True is chosen because it is the documented modern
spelling and because it also stops executescript() from committing on
its own, which is what lets a migration run atomically.

Durability pragmas, and why each: WAL plus
synchronous=FULL is the combination SQLite documents as ACID across power
loss with one fsync per commit; foreign_keys is off by default in SQLite;
busy_timeout turns a transient lock into a short wait instead of an
error; application_id marks the file as ours for import checks.
"""

import json
import os
import sqlite3
from pathlib import Path, PurePath
from urllib.parse import quote_from_bytes

from madtracker.store.migrations import FIRST_VERSION, MIGRATIONS, SCHEMA_VERSION

APPLICATION_ID = 0x4D414454  # 'MADT'
BUSY_TIMEOUT_MS = 5000


class StoreError(Exception):
    """Base class for every error the store raises on purpose."""


# SQLite's primary result codes for a file the disk will not take: full,
# an I/O error (a pulled stick, a dropped network folder), read-only, or
# gone. The extended codes (SQLITE_IOERR_WRITE, say) share the low byte.
_DISK_CODES = {
    sqlite3.SQLITE_FULL,
    sqlite3.SQLITE_IOERR,
    sqlite3.SQLITE_READONLY,
    sqlite3.SQLITE_CANTOPEN,
}
# The same failures by SQLite's own message, for an error raised without
# a code.
_DISK_WORDS = (
    "database or disk is full",
    "disk i/o error",
    "readonly database",
    "unable to open database file",
)


def disk_refusal(exc: BaseException) -> str | None:
    """Why the disk refused the file behind a StoreError: "full", "unwritable", or None.

    A refusal of the scorer's entry (a constraint, a busy lock) is None:
    the next click can succeed. A disk refusal fails every click until
    the scorer frees space or moves the file.
    """
    cause = exc.__cause__ if isinstance(exc, StoreError) else None
    if not isinstance(cause, sqlite3.Error):
        return None
    code = getattr(cause, "sqlite_errorcode", None)
    text = str(cause).lower()
    if code is not None:
        if code & 0xFF not in _DISK_CODES:
            return None
        return "full" if code & 0xFF == sqlite3.SQLITE_FULL else "unwritable"
    if not any(w in text for w in _DISK_WORDS):
        return None
    return "full" if "full" in text else "unwritable"


class IncompatibleDatabaseError(StoreError):
    """The file is not a MadTracker database, or was written by a newer app."""


class NeedsUpdateError(StoreError):
    """The file is at an older schema and cannot be brought up to date here.

    It is read-only, or another program holds it: the migration needs a
    write. The file is not damaged, and the app says so rather than
    sending the scorer to the backups.
    """


class NoWalError(StoreError):
    """The file's disk refuses WAL journaling (a network share, often): not damaged.

    Every write depends on WAL, so the file is not opened, and the app
    sends the scorer to a local copy rather than to the backups.
    """


class BackupError(StoreError):
    """The backup copy could not be written, or failed its integrity check, and was not kept."""


class ReadOnlyConnection(sqlite3.Connection):
    """A connection to a file the app may read but not write.

    Its own class, because a sqlite3.Connection takes no attributes and the
    Store has to know before a write, not from the error after it.
    """


def is_read_only(conn: sqlite3.Connection) -> bool:
    return isinstance(conn, ReadOnlyConnection)


def open_database(path: str | os.PathLike[str]) -> sqlite3.Connection:
    """Open (creating if needed) the database at path, fully configured and migrated."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, autocommit=True, timeout=BUSY_TIMEOUT_MS / 1000)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        _check_identity(conn)
        # journal_mode is persistent in the file but is re-asserted on every
        # open in case some other tool switched it; it cannot be changed
        # inside a transaction, hence before any BEGIN.
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if mode.lower() != "wal":
            raise NoWalError(f"could not enable WAL journaling (got {mode!r})")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        _migrate(conn)
    except sqlite3.OperationalError as exc:
        conn.close()
        if ("locked" in str(exc) or "busy" in str(exc)) and _stored_version(
            db_path
        ) < SCHEMA_VERSION:
            # Another program (an older copy of this app, a viewer) holds a
            # write on a file that needs the migration; the file is whole.
            raise NeedsUpdateError(
                "The data file is from an earlier version, and another program has it"
                " open, so it cannot be updated now."
            ) from exc
        # A file or folder marked read-only (a copy off a CD, a locked
        # share, an archive folder) still holds a past night the scorer may
        # want to look at; open it for reading and refuse writes instead.
        if "readonly" not in str(exc) and "read-only" not in str(exc):
            raise
        return _open_read_only(db_path)
    except UnicodeDecodeError as exc:
        conn.close()
        # Damaged pages can put bytes that are not UTF-8 into SQLite's own
        # error text, and Python raises this decoding it; caught here, it is
        # a damaged file as every caller handles one, not a crash.
        raise StoreError("database disk image is malformed") from exc
    except BaseException:
        conn.close()
        raise
    return conn


def _file_uri(path: PurePath, query: str) -> str:
    """The SQLite URI for ``path`` with ``query``: every read-only open builds it here.

    SQLite refuses a URI with a host in it, so a UNC path keeps its
    ``//server/share`` inside the path part behind an empty authority
    (``file:////server/share/x.sqlite``). A space, ``#``, ``?``, or ``%`` in a
    folder name is percent-encoded, or SQLite would read it as the end of
    the path or as an escape.
    """
    drive = path.drive
    if len(drive) == 2 and drive[1] == ":":
        prefix, rest = "file:///" + drive, path.as_posix()[2:]
    elif drive:
        prefix, rest = "file://", path.as_posix()
    else:
        prefix, rest = "file://", str(path)
    return f"{prefix}{quote_from_bytes(os.fsencode(rest))}?{query}"


def _stored_version(db_path: Path) -> int:
    """The file's user_version through a plain read, or this app's when it cannot be read."""
    try:
        peek = sqlite3.connect(_file_uri(db_path.resolve(), "mode=ro"), uri=True, timeout=0.5)
    except sqlite3.Error:
        return SCHEMA_VERSION
    try:
        return int(peek.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error:
        return SCHEMA_VERSION
    finally:
        peek.close()


def _open_read_only(db_path: Path) -> ReadOnlyConnection:
    """Open the file for reading only: no WAL switch, no id stamp, no migration."""
    path = db_path.resolve()
    # mode=ro first, so a writer elsewhere is still seen. A WAL file in a
    # read-only folder with no -shm beside it cannot be read that way (the
    # reader must create the -shm), and immutable=1 is then the only way in.
    for query in ("mode=ro", "mode=ro&immutable=1"):
        conn = sqlite3.connect(
            _file_uri(path, query),
            uri=True,
            autocommit=True,
            timeout=BUSY_TIMEOUT_MS / 1000,
            factory=ReadOnlyConnection,
        )
        try:
            conn.row_factory = sqlite3.Row
            conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            _check_identity(conn)
        except sqlite3.OperationalError:
            conn.close()
            if "immutable" in query:
                raise
            continue
        except BaseException:
            conn.close()
            raise
        break
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            # An unmigrated file cannot be brought up to date without
            # writing; this app's tables are not all there to read.
            raise NeedsUpdateError(
                "The data file is from an earlier version and is read-only, so it"
                " cannot be updated here."
            )
        conn.execute("PRAGMA foreign_keys = ON")
    except BaseException:
        conn.close()
        raise
    return conn


def _check_identity(conn: sqlite3.Connection) -> None:
    app_id = conn.execute("PRAGMA application_id").fetchone()[0]
    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if app_id != APPLICATION_ID:
        # A brand-new file has both at zero. Anything else with a foreign
        # or missing id is some other program's database.
        has_tables = conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        if app_id != 0 or user_version != 0 or has_tables:
            raise IncompatibleDatabaseError(
                f"not a MadTracker database (application_id {app_id:#x})"
            )
    if user_version > SCHEMA_VERSION:
        raise IncompatibleDatabaseError(
            f"database schema {user_version} is newer than this app's {SCHEMA_VERSION}; "
            "upgrade the app"
        )
    if 0 < user_version < FIRST_VERSION:
        # Every file in use is at the baseline, so there is no step to
        # bring an older one up; refused here, before the baseline's
        # CREATE TABLE would fail on a table the file already has.
        raise IncompatibleDatabaseError(
            f"database schema {user_version} predates the first release; this file cannot be opened"
        )


def _migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) and "busy" not in str(exc):
                raise
            # Another program (an older copy of this app, a viewer) holds
            # a write on the file; the update waits for it, and the file
            # is whole.
            raise NeedsUpdateError(
                "The data file is from an earlier version, and another program has it"
                " open, so it cannot be updated now."
            ) from exc
        try:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {version}")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def close_database(conn: sqlite3.Connection) -> None:
    """Checkpoint the WAL into the main file, then close.

    After this, the .sqlite file alone holds every committed transaction,
    so a plain file copy made later (by the scorer, by a sync client) is
    a complete database. TRUNCATE also resets the -wal file to zero bytes;
    SQLite removes it on the last close.
    """
    try:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        # A read-only file has nothing of ours to fold in, and cannot.
        if not is_read_only(conn):
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        # A full disk fails the checkpoint. The WAL is still valid and is
        # folded in at the next open, so the close goes ahead: raising
        # here would leave the app on a closed connection, refusing every click.
        pass
    finally:
        conn.close()


_EXPECTED_TABLES: set[str] = set()


def _expected_tables() -> set[str]:
    """The tables the migrations make, read from a scratch database built by them."""
    if not _EXPECTED_TABLES:
        scratch = sqlite3.connect(":memory:", autocommit=True)
        try:
            _migrate(scratch)
            _EXPECTED_TABLES.update(
                r[0] for r in scratch.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            )
        finally:
            scratch.close()
    return _EXPECTED_TABLES


def schema_problems(conn: sqlite3.Connection) -> list[str]:
    """Tables the schema has and the file lacks: a file another tool edited.

    integrity_check passes such a file, and the first read of the missing
    table would then fail at startup, every startup, since the file is
    remembered.
    """
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            return []
        have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.DatabaseError as exc:
        return [str(exc)]
    return [f"table {name} is missing" for name in sorted(_expected_tables() - have)]


def file_problems(path: str | os.PathLike[str]) -> list[str]:
    """What would stop this file opening as a sound data file, read without changing it; [] when sound.

    Run on a backup before a restore copies it anywhere: the same checks
    an open runs (whose file it is, the integrity check, the tables this
    version has), so a backup that would open as damaged, or not open at
    all, replaces nothing.
    """
    uri = _file_uri(Path(path).absolute(), "mode=ro")
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            # Another program's file with a "backup" setting row would
            # otherwise pass the checks below, replace the scorer's file,
            # then fail to open, and the replaced file would be gone.
            if app_id != APPLICATION_ID or version == 0:
                return [f"not a MadTracker data file (application_id {app_id:#x})"]
            if version > SCHEMA_VERSION:
                return [f"made by a newer version (schema {version})"]
            if version < FIRST_VERSION:
                return [f"predates the first release (schema {version})"]
            return integrity_check(conn) + schema_problems(conn)
        finally:
            conn.close()
    except (sqlite3.Error, UnicodeDecodeError) as exc:
        return [str(exc)]


def is_empty_database(path: str | os.PathLike[str]) -> bool:
    """True for an SQLite file with nothing in it: no tables, not marked as ours.

    What a copy of the live file alone looks like when the night is
    still in the -wal beside the original. Anything that cannot be read
    is not "empty" here; opening it says what it is.
    """
    uri = _file_uri(Path(path).absolute(), "mode=ro")
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            tables = conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, UnicodeDecodeError):
        return False
    return app_id == 0 and tables is None


def integrity_check(conn: sqlite3.Connection) -> list[str]:
    """Run PRAGMA integrity_check; an empty list means the file is sound."""
    try:
        rows = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        # A page bad enough that the check itself cannot walk it is the
        # worst answer the check can give, not a reason to crash the caller.
        return [str(exc)]
    if rows == ["ok"]:
        return []
    return rows


def _is_open_file(conn: sqlite3.Connection, dest: Path) -> bool:
    """Whether dest is the connection's own file or one of its side files."""
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None or not row[2]:
        return False
    main = Path(row[2]).resolve()
    names = {main} | {main.with_name(main.name + s) for s in ("-wal", "-shm", "-journal")}
    if dest.resolve() in names:
        return True
    # A file system that ignores case (Windows, the Mac's APFS) resolves
    # "Madtracker.sqlite" to a path that compares unequal to the open
    # file's and yet is the open file; the OS knows.
    try:
        return any(os.path.samefile(dest, name) for name in names if name.exists())
    except OSError:
        return False


# The setting row that makes a file a backup. It is written into the copy
# only, so it says "backup" wherever the file goes and whatever it is
# called; a restore deletes it from its copy, which is then a data file.
BACKUP_KEY = "backup"


def backup_database(
    src: sqlite3.Connection, dest: str | os.PathLike[str], mark: dict | None = None
) -> Path:
    """Write a consistent, self-contained copy of the live database to dest.

    Never a file copy: the -wal side file is part of the state and a copy
    taken mid-transaction can be corrupt. The online backup API copies a
    consistent snapshot while the app keeps running. The copy is written
    to a .partial name, switched to rollback journaling so it is one file
    with no -wal, marked as a backup with ``mark``, checked, and only then
    renamed into place; a half-written or unmarked backup can never be
    mistaken for a good one.
    """
    dest_path = Path(dest)
    if _is_open_file(src, dest_path):
        # The rename would put the copy over the live file while the
        # connection keeps writing to the unlinked one (Linux and macOS
        # allow it), and everything after the backup is lost at close.
        raise BackupError(f"{dest_path.name} is the open data file")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    partial = dest_path.with_name(dest_path.name + ".partial")
    if partial.exists():
        partial.unlink()
    try:
        dst = sqlite3.connect(partial, autocommit=True)
        try:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode = DELETE")
            dst.execute(
                "INSERT INTO setting (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (BACKUP_KEY, json.dumps(mark or {}, sort_keys=True)),
            )
            problems = integrity_check(dst)
        finally:
            dst.close()
    except sqlite3.Error as exc:
        # A write-protected stick or a full drive fails inside SQLite, not
        # in the file system calls above; callers handle StoreError, and a
        # raw sqlite error would escape the click that finished a race.
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        raise BackupError(f"could not write {dest_path.name}: {exc}") from exc
    if problems:
        partial.unlink(missing_ok=True)
        raise BackupError("; ".join(problems))
    os.replace(partial, dest_path)
    return dest_path


def read_backup_mark(path: str | os.PathLike[str]) -> dict | None:
    """The backup mark in the file at path, or None when it is not a backup.

    Read-only, so looking never changes the file; a file that is not a
    MadTracker database at all is simply not a backup here, and opening
    it says what it is.
    """
    uri = _file_uri(Path(path).absolute(), "mode=ro")
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute(
                "SELECT value_json FROM setting WHERE key = ?", (BACKUP_KEY,)
            ).fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, UnicodeDecodeError):
        return None
    if row is None:
        return None
    try:
        mark = json.loads(row[0])
    except ValueError:
        return {}
    return mark if isinstance(mark, dict) else {}
