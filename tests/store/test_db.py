"""Connection setup: pragmas, migrations, identity checks and clean close."""

import os
import sqlite3
from pathlib import Path, PureWindowsPath

import pytest

from madtracker.store import (
    APPLICATION_ID,
    SCHEMA_VERSION,
    IncompatibleDatabaseError,
    close_database,
    file_problems,
    integrity_check,
    open_database,
)
from madtracker.store.db import _file_uri
from madtracker.store.migrations import FIRST_VERSION, MIGRATIONS


def pragma(conn, name):
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def test_pragmas_after_open(tmp_path):
    conn = open_database(tmp_path / "t.sqlite")
    try:
        assert pragma(conn, "journal_mode") == "wal"
        assert pragma(conn, "synchronous") == 2  # FULL
        assert pragma(conn, "foreign_keys") == 1
        assert pragma(conn, "busy_timeout") == 5000
        assert pragma(conn, "application_id") == APPLICATION_ID
        assert pragma(conn, "user_version") == SCHEMA_VERSION
        # autocommit=True: no transaction is open until the store begins one.
        assert conn.in_transaction is False
    finally:
        close_database(conn)


def test_migrations_from_empty_and_idempotent_on_reopen(tmp_path):
    path = tmp_path / "t.sqlite"
    conn = open_database(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    close_database(conn)
    assert {
        "rider",
        "event",
        "roster_entry",
        "race",
        "race_entry",
        "team",
        "team_member",
        "race_action",
        "setting",
        "ruleset",
    } <= tables

    # A second open must find nothing to do and leave the schema as it was.
    conn = open_database(path)
    try:
        assert pragma(conn, "user_version") == SCHEMA_VERSION
        again = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert again == tables
        assert integrity_check(conn) == []
    finally:
        close_database(conn)


def test_open_creates_parent_directory(tmp_path):
    path = tmp_path / "deep" / "er" / "t.sqlite"
    conn = open_database(path)
    close_database(conn)
    assert path.exists()


def test_foreign_database_is_refused(tmp_path):
    path = tmp_path / "other.sqlite"
    other = sqlite3.connect(path)
    other.execute("CREATE TABLE x (y)")
    other.commit()
    other.close()
    with pytest.raises(IncompatibleDatabaseError):
        open_database(path)


def test_newer_schema_is_refused(tmp_path):
    path = tmp_path / "t.sqlite"
    close_database(open_database(path))
    raw = sqlite3.connect(path)
    raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    raw.close()
    with pytest.raises(IncompatibleDatabaseError, match="newer"):
        open_database(path)


def test_a_file_below_the_baseline_is_refused_before_any_table_is_made(tmp_path):
    path = tmp_path / "t.sqlite"
    close_database(open_database(path))
    raw = sqlite3.connect(path)
    raw.execute(f"PRAGMA user_version = {FIRST_VERSION - 1}")
    raw.close()
    with pytest.raises(IncompatibleDatabaseError, match="predates"):
        open_database(path)
    assert file_problems(path) == [f"predates the first release (schema {FIRST_VERSION - 1})"]
    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == FIRST_VERSION - 1, "untouched"
    raw.close()


def test_a_new_file_is_made_at_the_baseline_in_one_step(tmp_path):
    assert MIGRATIONS[0][0] == SCHEMA_VERSION == FIRST_VERSION
    conn = open_database(tmp_path / "t.sqlite")
    try:
        assert pragma(conn, "user_version") == SCHEMA_VERSION
        assert file_problems(tmp_path / "t.sqlite") == []
    finally:
        close_database(conn)


def test_clean_close_leaves_no_wal_content(tmp_path):
    path = tmp_path / "t.sqlite"
    conn = open_database(path)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "INSERT INTO event (name, event_date, created_utc) VALUES ('m', '2026-01-01', 'now')"
    )
    conn.execute("COMMIT")
    close_database(conn)
    wal = tmp_path / "t.sqlite-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    # The main file alone must hold the committed row.
    raw = sqlite3.connect(path)
    try:
        assert raw.execute("SELECT count(*) FROM event").fetchone()[0] == 1
    finally:
        raw.close()


def test_integrity_check_reports_ok_as_empty(tmp_path):
    conn = open_database(tmp_path / "t.sqlite")
    try:
        assert integrity_check(conn) == []
    finally:
        close_database(conn)


def test_a_unc_path_has_an_empty_uri_authority():
    # SQLite refuses a host in the authority, so the share stays in the path.
    uri = _file_uri(PureWindowsPath(r"\\server\share\x.sqlite"), "mode=ro")
    assert uri == "file:////server/share/x.sqlite?mode=ro"


def test_a_local_drive_path_uri_is_the_plain_file_uri():
    uri = _file_uri(PureWindowsPath(r"C:\Users\scorer\x.sqlite"), "mode=ro")
    assert uri == "file:///C:/Users/scorer/x.sqlite?mode=ro"
    spaced = _file_uri(PureWindowsPath(r"C:\Race Nights\#12.sqlite"), "mode=ro")
    assert spaced == "file:///C:/Race%20Nights/%2312.sqlite?mode=ro"


def test_a_posix_path_uri_matches_as_uri():
    if os.name == "nt":
        pytest.skip("a POSIX absolute path needs a POSIX system")
    path = Path("/home/scorer/Race Nights #12/50% x.sqlite")
    assert _file_uri(path, "mode=ro&immutable=1") == f"{path.as_uri()}?mode=ro&immutable=1"


def test_a_folder_with_a_space_hash_and_percent_opens_read_only(tmp_path):
    folder = tmp_path / "Race Nights #12 50%"
    path = folder / "t.sqlite"
    close_database(open_database(path))
    assert file_problems(path) == []
