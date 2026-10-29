"""Multi-race standings in the store: the definition, its links, and a step from an older file."""

import os
import sqlite3
import sys

import pytest

from madtracker.store import (
    DuplicateStandingsNameError,
    NeedsUpdateError,
    NotFoundError,
    Store,
    StoreError,
    close_database,
    integrity_check,
    open_database,
)


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "t.sqlite")
    yield s
    s.close()


def test_add_list_get_and_the_defaults(store):
    b = store.add_standings("rumble 2026-27")
    a = store.add_standings("  Oktoberfest 2 Day Omnium ", rules={"absent_points": 0})
    assert b.kind == "team_omnium" and b.rules == {}, "None stores the kind's defaults as {}"
    assert a.name == "Oktoberfest 2 Day Omnium" and a.rules == {"absent_points": 0}
    assert a.event_ids == [] and a.excluded_race_ids == []
    assert a.created_utc == a.updated_utc
    assert [s.name for s in store.list_standings()] == [
        "Oktoberfest 2 Day Omnium",
        "rumble 2026-27",
    ]
    assert store.get_standings(a.standings_id) == a


def test_a_blank_name_or_kind_is_refused(store):
    with pytest.raises(ValueError):
        store.add_standings("   ")
    with pytest.raises(ValueError):
        store.add_standings("Omnium", kind=" ")
    s = store.add_standings("Omnium")
    with pytest.raises(ValueError):
        store.update_standings(s.standings_id, name="​")
    assert store.get_standings(s.standings_id).name == "Omnium"


def test_a_second_standings_with_the_same_name_is_refused_without_case(store):
    store.add_standings("Oktoberfest 2 Day Omnium")
    with pytest.raises(DuplicateStandingsNameError, match="named Oktoberfest 2 Day Omnium already"):
        store.add_standings("  oktoberfest 2 day OMNIUM ")
    assert len(store.list_standings()) == 1


def test_a_rename_onto_another_standings_is_refused_and_onto_itself_is_not(store):
    store.add_standings("Rumble 2026-27")
    s = store.add_standings("Weekend")
    with pytest.raises(DuplicateStandingsNameError):
        store.update_standings(s.standings_id, name="RUMBLE 2026-27", event_ids=[])
    assert store.get_standings(s.standings_id).name == "Weekend"
    assert store.update_standings(s.standings_id, name="WEEKEND").name == "WEEKEND"


def test_missing_standings_is_not_found(store):
    with pytest.raises(NotFoundError):
        store.get_standings(99)
    with pytest.raises(NotFoundError):
        store.update_standings(99, name="X")
    with pytest.raises(NotFoundError):
        store.remove_standings(99)


def test_update_replaces_lists_whole_and_orders_events_by_date(store):
    late = store.add_event("Saturday", "2026-10-17")
    early = store.add_event("Friday", "2026-10-16")
    r1 = store.add_race(early.event_id, "Madison", "madison")
    r2 = store.add_race(late.event_id, "Madison", "madison")
    s = store.add_standings("Omnium")
    s = store.update_standings(
        s.standings_id,
        event_ids=[late.event_id, early.event_id, late.event_id],
        excluded_race_ids=[r2.race_id, r1.race_id],
    )
    assert s.event_ids == [early.event_id, late.event_id], "oldest first, a repeat once"
    assert s.excluded_race_ids == [r1.race_id, r2.race_id]
    s = store.update_standings(s.standings_id, event_ids=[late.event_id], excluded_race_ids=[])
    assert s.event_ids == [late.event_id] and s.excluded_race_ids == []
    s = store.update_standings(s.standings_id, name="Weekend", rules={"absent_points": 1})
    assert (s.name, s.rules, s.event_ids) == ("Weekend", {"absent_points": 1}, [late.event_id])


def test_an_event_or_race_that_does_not_exist_is_refused_and_nothing_changes(store):
    event = store.add_event("Friday", "2026-10-16")
    s = store.add_standings("Omnium")
    store.update_standings(s.standings_id, event_ids=[event.event_id])
    with pytest.raises(StoreError):
        store.update_standings(s.standings_id, name="New", event_ids=[event.event_id, 999])
    with pytest.raises(StoreError):
        store.update_standings(s.standings_id, excluded_race_ids=[999])
    kept = store.get_standings(s.standings_id)
    assert kept.name == "Omnium" and kept.event_ids == [event.event_id]


def test_deleting_an_event_or_race_leaves_the_definition(store):
    keep = store.add_event("Friday", "2026-10-16")
    gone = store.add_event("Saturday", "2026-10-17")
    r_keep = store.add_race(keep.event_id, "Madison", "madison")
    r_gone = store.add_race(keep.event_id, "Second Madison", "madison")
    store.add_race(gone.event_id, "Madison", "madison")
    s = store.add_standings("Omnium")
    store.update_standings(
        s.standings_id,
        event_ids=[keep.event_id, gone.event_id],
        excluded_race_ids=[r_keep.race_id, r_gone.race_id],
    )
    store.delete_race(r_gone.race_id)
    store.delete_event(gone.event_id)
    s = store.get_standings(s.standings_id)
    assert s.event_ids == [keep.event_id] and s.excluded_race_ids == [r_keep.race_id]


def test_remove_takes_the_links_with_it(store):
    event = store.add_event("Friday", "2026-10-16")
    race = store.add_race(event.event_id, "Madison", "madison")
    s = store.add_standings("Omnium")
    store.update_standings(
        s.standings_id, event_ids=[event.event_id], excluded_race_ids=[race.race_id]
    )
    store.remove_standings(s.standings_id)
    assert store.list_standings() == []
    conn = store.connection
    assert conn.execute("SELECT COUNT(*) FROM standings_event").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM standings_race_excluded").fetchone()[0] == 0
    assert store.event(event.event_id) and store.race(race.race_id), "the night is untouched"


def test_a_read_only_store_lists_standings_and_refuses_a_write(tmp_path):
    from madtracker.store.db import ReadOnlyConnection

    path = tmp_path / "ro.sqlite"
    with Store.open(path) as s:
        s.add_standings("Omnium")
    conn = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro", uri=True, autocommit=True, factory=ReadOnlyConnection
    )
    conn.row_factory = sqlite3.Row
    try:
        ro = Store(conn)
        assert [x.name for x in ro.list_standings()] == ["Omnium"]
        with pytest.raises(StoreError):
            ro.add_standings("Another")
    finally:
        conn.close()


@pytest.fixture
def older_file(tmp_path, monkeypatch):
    """A file at today's schema with one event, then a pretend version above it: (path, version).

    Every real file is at the baseline, so the step from an older file has
    nothing real to run on until a later version exists; the pretend step
    stands in for it, armed only after the file is written so the file is
    the older one. The expected-tables cache is emptied so the pretend
    table is neither expected by other tests nor missing from them.
    """
    from madtracker.store import db

    path = tmp_path / "older.sqlite"
    with Store.open(path) as s:
        s.add_event("Race Night 12", "2026-10-16")
    version = db.SCHEMA_VERSION + 1
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, (version, "CREATE TABLE later (x);")])
    monkeypatch.setattr(db, "SCHEMA_VERSION", version)
    monkeypatch.setattr(db, "_EXPECTED_TABLES", set())
    return path, version


def test_a_file_at_an_earlier_version_migrates_and_keeps_every_row(older_file):
    path, version = older_file
    conn = open_database(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "later" in tables
        assert conn.execute("SELECT name FROM event").fetchone()[0] == "Race Night 12"
        assert integrity_check(conn) == []
    finally:
        close_database(conn)
    with Store.open(path) as s:
        made = s.add_standings("Weekend")
        made = s.update_standings(made.standings_id, event_ids=[s.events()[0].event_id])
        assert len(made.event_ids) == 1


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="a read-only folder is a POSIX permission, and root ignores it",
)
def test_a_read_only_older_file_says_it_needs_updating_not_that_it_is_damaged(older_file):
    """An older file on read-only media is not refused as damaged."""
    path, _ = older_file
    folder = path.parent
    path.chmod(0o444)
    folder.chmod(0o555)
    try:
        with pytest.raises(NeedsUpdateError) as caught:
            open_database(path)
        assert "earlier version" in str(caught.value) and "read-only" in str(caught.value)
    finally:
        folder.chmod(0o755)
        path.chmod(0o644)


def test_an_older_file_another_program_holds_says_it_needs_updating(older_file):
    path, version = older_file
    holder = sqlite3.connect(path, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(NeedsUpdateError) as caught:
            open_database(path)
        assert "another program" in str(caught.value)
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    conn = open_database(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version
    finally:
        close_database(conn)


def test_an_omnium_penalty_is_one_number_per_rider_and_zero_takes_it_off(store):
    rider = store.add_rider("Ada", "Arden").rider_id
    other = store.add_rider("Bram", "Birch").rider_id
    made = store.add_standings("Four", kind="four_race_omnium")
    assert made.penalties == {}
    got = store.set_standings_penalty(made.standings_id, rider, 40)
    assert got.penalties == {rider: 40} and got.updated_utc >= made.updated_utc
    got = store.set_standings_penalty(made.standings_id, rider, 20)
    store.set_standings_penalty(made.standings_id, other, 40)
    assert store.get_standings(made.standings_id).penalties == {rider: 20, other: 40}
    assert store.set_standings_penalty(made.standings_id, rider, 0).penalties == {other: 40}
    with pytest.raises(StoreError):
        store.set_standings_penalty(made.standings_id, rider, -1)
    with pytest.raises(StoreError):
        store.set_standings_penalty(made.standings_id, 999_999, 40)
    with pytest.raises(NotFoundError):
        store.set_standings_penalty(999, rider, 40)
    # The penalty goes with the standings, and with the rider.
    store.remove_standings(made.standings_id)
    again = store.add_standings("Again", kind="four_race_omnium")
    store.set_standings_penalty(again.standings_id, other, 40)
    store.delete_rider(other)
    assert store.get_standings(again.standings_id).penalties == {}
