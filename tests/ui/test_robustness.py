"""What the scorer sees when something goes wrong: the log, the crash box, a failing file or disk."""

import shutil
import sqlite3
import sys

import pytest
from apps import dispose_app
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest

from madtracker import applog
from madtracker.control import venue
from madtracker.control.backups import marker_path
from madtracker.store import Store, StoreError
from madtracker.ui import icons, widgets


@pytest.fixture
def quiet(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(widgets, "run_menu", lambda menu, where: opened.append("menu"))
    monkeypatch.setattr(icons, "ask", lambda *a, **k: opened.append("ask:" + a[1]) or True)
    monkeypatch.setattr(icons, "choose", lambda *a, **k: opened.append("choose:" + a[1]) or a[4])
    monkeypatch.setattr(icons, "inform", lambda *a, **k: opened.append("inform:" + a[2]))
    monkeypatch.setattr(icons, "warn", lambda *a, **k: opened.append("warn:" + a[2]))
    return opened


@pytest.fixture
def make_app(qapp, tmp_path, quiet):
    from madtracker.app import AppController

    made = []

    def build(**kwargs):
        settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
        c = AppController(qapp, settings=settings, **kwargs)
        made.append(c)
        return c

    yield build
    for c in made:
        dispose_app(c)
    applog.use_folder(None)


def _result_backed_up(c) -> None:
    """Wait for a result's backup, which runs once the screen shows the result."""
    for _ in range(200):
        if not c._backup_pending:
            return
        QTest.qWait(10)
    raise AssertionError("the result's backup never ran")


def _log(c) -> str:
    applog.flush()
    return (c.data_dir / applog.LOG_NAME).read_text(encoding="utf-8")


def test_the_log_beside_the_file_records_the_session_and_the_backups(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    for eid in list(c.live.roster.ids):
        assert c.click(eid)
    _result_backed_up(c)
    log = _log(c)
    assert "MadTracker" in log and "started" in log and "Displays:" in log
    assert f"Data file: {c.data_path}" in log
    assert "Backup written: " in log


def test_an_unexpected_error_in_a_click_is_the_red_line_and_the_log(
    make_app, tmp_path, monkeypatch
):
    c = make_app(demo=True, data_dir=tmp_path / "data")

    def broken(entrant_id):
        raise RuntimeError("a bug")

    monkeypatch.setattr(c.live, "click", broken)
    assert not c.click(c.live.roster.ids[0])
    assert c.main.surface.problem.text().startswith(
        "Not recorded: something went wrong (RuntimeError)."
    )
    assert "RuntimeError: a bug" in _log(c)


def test_a_bug_after_the_entry_was_written_says_it_was_recorded(make_app, tmp_path, monkeypatch):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    *first, last = list(c.live.roster.ids)
    for eid in first:
        assert c.click(eid)
    real = c.live.click

    def broken_after(entrant_id):
        real(entrant_id)
        raise RuntimeError("a bug in the redraw")

    monkeypatch.setattr(c.live, "click", broken_after)
    assert not c.click(last)
    assert c.live.state == "provisional", "the finish is in the file"
    assert c.main.surface.problem.text().startswith(
        "Recorded, but something went wrong (RuntimeError). Check the current race."
    )


class _RefusingDisk:
    """The data file's connection with a disk that refuses every COMMIT."""

    def __init__(self, real, message):
        self.real = real
        self.message = message

    def execute(self, sql, *args):
        if sql.strip().upper().startswith("COMMIT"):
            raise sqlite3.OperationalError(self.message)
        return self.real.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self.real, name)


@pytest.mark.parametrize(
    ("message", "line", "box"),
    [
        (
            "database or disk is full",
            "Not recorded: the disk is full.",
            "The data file could not be written (the disk is full).",
        ),
        (
            "disk I/O error",
            "Not recorded: the data file could not be written.",
            "The data file could not be written. Nothing is recorded until it can be written again.",
        ),
    ],
)
def test_a_disk_that_refuses_the_file_is_one_box_and_the_red_line_on_each_click(
    make_app, tmp_path, quiet, message, line, box
):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    ids = list(c.live.roster.ids)
    real = c.store._conn
    c.store._conn = _RefusingDisk(real, message)
    try:
        for eid in ids[:2]:
            assert not c.click(eid)
            assert c.main.surface.problem.text() == line
    finally:
        c.store._conn = real
    assert [q for q in quiet if q.startswith("warn:")] == [
        q for q in quiet if q.startswith("warn:" + box)
    ]
    assert len([q for q in quiet if q.startswith("warn:")]) == 1, "one box a session"
    assert c.click(ids[0]), "the file takes the next click once the disk does"
    assert c.main.surface.problem.text() == ""


def test_an_exception_out_of_a_slot_is_logged_and_said_once(make_app, tmp_path, quiet, monkeypatch):
    from madtracker.app import install_excepthook

    c = make_app(demo=True, data_dir=tmp_path / "data")
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    install_excepthook(c)
    for _ in range(2):
        try:
            raise ValueError("from a slot")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    boxes = [q for q in quiet if q.startswith("warn:Something went wrong")]
    assert len(boxes) == 1, "one box per distinct traceback in a session"
    assert str(c.data_dir / applog.LOG_NAME) in boxes[0]
    assert _log(c).count("ValueError: from a slot") == 2


def test_a_close_whose_checkpoint_fails_still_lets_the_file_go(make_app, tmp_path, monkeypatch):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    path = c.data_path

    def full_disk(conn):
        conn.close()
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr("madtracker.store.store.close_database", full_disk)
    c.close()
    assert c.store is None and c._lock is None and not marker_path(path).exists()
    monkeypatch.undo()
    again = make_app(data_dir=tmp_path / "data")
    assert again.store is not None and again.event is not None and not again.recovered


def test_backup_now_to_a_folder_that_is_gone_says_so_and_writes_none(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    stick = tmp_path / "stick"
    assert c.backup_now(stick / "tonight.sqlite") is None
    assert not stick.exists(), "never made again on the local disk"
    assert any("the folder is not there any more" in q for q in quiet)
    assert list(venue.automatic_backup_dir(c.data_dir).glob("*.sqlite"))


def test_a_result_is_folded_into_the_main_file_at_once(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    race_id = c.live.race_id
    for eid in list(c.live.roster.ids):
        assert c.click(eid)
    assert c.live.state == "provisional"
    _result_backed_up(c)
    # The main file alone, as a copy dragged off while the program runs.
    alone = tmp_path / "copy" / "madtracker.sqlite"
    alone.parent.mkdir()
    shutil.copyfile(c.data_path, alone)
    with Store.open(alone) as copy:
        assert copy.race(race_id).state == "provisional"
        assert copy.live_actions(race_id)


def test_an_empty_copy_of_a_data_file_is_refused(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    # One page and no tables: the main file alone while the night is in -wal.
    empty = tmp_path / "empty.sqlite"
    con = sqlite3.connect(empty)
    con.execute("CREATE TABLE t (x)")
    con.execute("DROP TABLE t")
    con.commit()
    con.close()
    assert empty.stat().st_size > 0
    assert not c.open_data_file(empty)
    assert quiet[-1].startswith(f"warn:This data file is empty:\n{empty}")
    assert c.data_path != empty


def test_a_file_missing_a_table_opens_as_damaged_rather_than_crashing(make_app, tmp_path, quiet):
    seeded = make_app(demo=True, data_dir=tmp_path / "seed")
    source = seeded.data_path
    seeded.close()
    data = tmp_path / "data"
    data.mkdir()
    broken = data / source.name
    shutil.copyfile(source, broken)
    con = sqlite3.connect(broken)
    con.execute("PRAGMA foreign_keys = OFF")
    con.execute("DROP TABLE race_state_change")
    con.commit()
    con.close()
    c = make_app(data_dir=data)
    assert c.damaged and c.live is None and c.main.showing() == "empty"
    assert "it may be damaged" in c._notice
    assert "race_state_change is missing" in _log(c)


@pytest.mark.skipif(sys.platform == "win32", reason="chmod does not make a file read-only")
def test_a_read_only_file_says_so_when_it_opens(make_app, tmp_path, quiet):
    import os

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root writes into a read-only file")
    seeded = make_app(demo=True, data_dir=tmp_path / "seed")
    source = seeded.data_path
    seeded.close()
    folder = tmp_path / "ro"
    folder.mkdir()
    shutil.copyfile(source, folder / source.name)
    (folder / source.name).chmod(0o444)
    folder.chmod(0o555)
    try:
        c = make_app(data_dir=folder)
        assert c.store.read_only
        assert any(q.startswith("warn:This data file is read-only") for q in quiet)
    finally:
        folder.chmod(0o755)


def test_settings_save_on_a_file_that_refuses_says_so_on_the_dialog(
    make_app, tmp_path, monkeypatch
):
    from madtracker.ui.settings import SettingsDialog

    c = make_app(demo=True, data_dir=tmp_path / "data")

    def refuse(*args, **kwargs):
        raise StoreError("The data file is read-only.")

    monkeypatch.setattr(Store, "write_settings", refuse)
    dialog = SettingsDialog(c.store, c.data_dir, c.main)
    dialog.venue_name.setText("Riverside")
    assert not dialog.save()
    assert dialog.error.text() == "The data file is read-only."


def test_moving_a_race_on_a_file_that_refuses_says_so_under_program(
    make_app, tmp_path, monkeypatch
):
    c = make_app(demo=True, data_dir=tmp_path / "data")

    def refuse(*args, **kwargs):
        raise StoreError("The data file is read-only.")

    monkeypatch.setattr(Store, "update_race", refuse)
    c.open_setup()
    screen = c.main.setup
    assert not screen.move_race(1, c.races[1].race_id)
    assert screen.program_status.text() == "The data file is read-only."


def test_the_event_log_follows_a_renamed_rider_in_a_race_already_scored(make_app, tmp_path):
    """The log's lines are worded from the file each time they are read, so a
    rename reaches a race scored before it (the log is read through
    ``event_log``)."""
    from logbook import event_log

    c = make_app(demo=True, data_dir=tmp_path / "data")
    # An elimination records each rider out as an entry; then another race is live.
    c.select_race(c.races[1].race_id)
    out = c.live.roster.ids[0]
    assert c.click(out)
    c.select_race(c.races[0].race_id)
    c.store.update_rider(out, first_name="Renamed")
    c.refresh()
    lines = [row.text for row in event_log(c.store, c.event.event_id)]
    assert any("Eliminated: " in text and "Renamed" in text for text in lines), lines
