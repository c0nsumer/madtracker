"""The app's wiring: start, files, events, exports, backups, the board (design sections 5, 9, 12)."""

import sys
from pathlib import Path

import pytest
from apps import dispose_app
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from madtracker.control import venue
from madtracker.control.copying import CopyChoice
from madtracker.control.describe import who
from madtracker.store import Store
from madtracker.ui import icons, style, widgets


@pytest.fixture
def quiet(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(widgets, "run_menu", lambda menu, where: opened.append("menu"))
    monkeypatch.setattr(icons, "ask", lambda *a, **k: opened.append("ask:" + a[1]) or True)
    # The chooser answers with its filled button, as ask answers yes.
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


def test_demo_starts_on_the_first_race_with_the_board_on_the_logo(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    assert c.event.name == "Demo Race Night"
    assert c.live is not None and c.live.race_id == c.races[0].race_id
    assert c.main.showing() == "surface"
    assert c.board.page_kind() == "logo" and not c.board_live
    assert not c.main.tv.is_live() and c.main.logo_action.isChecked()
    c.set_board_live(True)
    assert c.board.page_kind() == "pre_race" and c.main.live_action.isChecked()
    assert c.main.tv.is_live()


def test_a_plain_start_reopens_the_last_file_on_the_race_that_was_live(
    make_app, tmp_path, monkeypatch
):  # noqa: E501
    from madtracker import app as app_mod

    monkeypatch.setattr(app_mod, "DATA_FILE_KEY", "data/file")
    first = make_app(demo=True, data_dir=tmp_path / "data")
    eid = first.live.roster.ids[0]
    first.select_race(first.races[2].race_id)
    assert first.click(first.live.roster.ids[0])
    path = first.data_path
    first.close()
    # The file, not the machine, remembers the live race (design section 12).
    with Store.open(path) as s:
        assert s.get_setting("ui/live_race_id") == first.races[2].race_id
    again = make_app(data_dir=tmp_path / "data")
    assert again.data_path == path
    assert again.live.race_id == first.races[2].race_id
    assert again.main.surface.state.text() == "Racing"
    assert eid in again.live.roster.ids


def test_new_event_opens_setup_and_done_returns_to_the_race_selected(make_app, tmp_path):
    from logbook import event_log

    from madtracker.ui.window import window_title

    c = make_app(demo=True, data_dir=tmp_path / "data")
    assert c.live.act(c.live.roster.ids[0], "dns").ok
    c.refresh()
    assert c.main.undo.isEnabled()
    first_event = c.event.event_id
    event_id = c.new_event("Next Night", "2026-10-17")
    assert c.event.event_id == event_id and c.races == []
    assert c.main.showing() == "setup"
    # Last event's race leaves the board and Undo goes off; its entries
    # stay in the file under their own event.
    assert all(b._layout_name == "between" for b in c.boards)
    assert not c.main.undo.isEnabled()
    assert event_log(c.store, first_event) and not event_log(c.store, event_id)
    # The event heads the program and the title bar.
    assert c.main.program.heading.text() == "Next Night"
    assert c.main.program.date.text() == "2026-Oct-17"
    assert c.main.windowTitle() == window_title("Next Night", "2026-10-17")
    c.close_setup()
    assert c.main.showing() == "empty" and "Edit Event" in c.main.empty_text.text()
    # By name: the demo event is dated today, so its place in the list
    # moves with the calendar.
    demo = next(e for e in c.store.events() if e.name == "Demo Race Night")
    c.pick_event(demo.event_id)
    assert c.event.name == "Demo Race Night" and c.main.showing() == "surface"
    c.open_setup()
    assert c.main.showing() == "setup"
    c.select_race(c.races[3].race_id)
    c.open_setup()
    c.close_setup()
    # Score goes back to where the scorer was, not to the top of the program.
    assert c.live.race_id == c.races[3].race_id and c.main.showing() == "surface"


def test_live_waits_for_a_race_and_a_live_board_goes_back_to_the_logo(make_app, tmp_path):
    """Live never shows an empty "Up next" page: it is off until there is a
    race, on the preview's click and in the menu, and a board left on Live
    goes back to the logo."""
    from madtracker.ui.tv import TO_LIVE, TO_LOGO

    c = make_app(demo=True, data_dir=tmp_path / "data")
    tv, menu = c.main.tv, c.main.live_action
    assert tv.property("active") and menu.isEnabled() and tv.toolTip() == ""
    # Under the pointer the picture says what a click does; it flips with
    # each click and with the menu's choice, and leaves with the pointer.
    overlay = tv.preview.hover
    assert not overlay.isVisibleTo(tv.preview) and tv.hover_text() == ""
    tv.set_hover(True)
    assert overlay.isVisibleTo(tv.preview) and overlay.text() == TO_LIVE
    tv.click()
    assert c.board_live and tv.is_live() and overlay.text() == TO_LOGO
    c.main.logo_action.trigger()
    assert not tv.is_live() and overlay.text() == TO_LIVE
    tv.click()
    assert tv.is_live() and overlay.text() == TO_LOGO
    tv.set_hover(False)
    assert not overlay.isVisibleTo(tv.preview) and tv.hover_text() == ""
    tv.set_hover(True)
    event_id = c.new_event("Next Night", "2026-10-17")
    assert c.races == []
    assert not c.board_live and not tv.is_live()
    assert not tv.property("active") and not menu.isEnabled()
    assert tv.toolTip() == "No race to show yet"
    assert not overlay.isVisibleTo(tv.preview), "nothing a click would do"
    # A click with no race to show does nothing, and says nothing.
    tv.click()
    assert not c.board_live and not tv.is_live()
    race = c.store.add_race(event_id, "Scratch", "placings")
    c._reload_races()
    c.select_race(race.race_id)
    assert tv.property("active") and menu.isEnabled() and tv.toolTip() == ""
    assert overlay.isVisibleTo(tv.preview) and overlay.text() == TO_LIVE
    assert not c.board_live, "back on the logo until the scorer flips it"


def test_file_open_event_opens_the_event_chosen_in_the_dialog(make_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from madtracker.ui import setup as su

    c = make_app(demo=True, data_dir=tmp_path / "data")
    demo = c.event
    other = c.store.add_event("Next Night", "2026-12-01").event_id
    seen = []

    def run(dialog):
        seen.append(widgets.selected_id(dialog.table))
        dialog.select_event(other)
        return int(QDialog.DialogCode.Accepted) if dialog.open_chosen() else 0

    monkeypatch.setattr(su.OpenEventDialog, "exec", run)
    c.pick_event()
    assert seen == [demo.event_id], "the open event is preselected"
    assert c.event.event_id == other

    # Cancelled, the event stays as it was.
    monkeypatch.setattr(su.OpenEventDialog, "exec", lambda dialog: 0)
    c.pick_event()
    assert c.event.event_id == other


def _finish_first_race(c):
    for eid in list(c.live.roster.ids):
        assert c.click(eid)
    assert c.live.state == "provisional"


def test_export_csv_writes_the_usac_file_and_names_the_races_left_out(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    _finish_first_race(c)
    # A race that shares the scored race's name is still left out, by id.
    first = c.races[0]
    c.store.add_race(c.event.event_id, first.name, first.format)
    out = tmp_path / "usac.csv"
    assert c.export_csv(out) == out
    assert out.is_file() and out.stat().st_size > 100
    # Each race as USAC files it, the races left out, then what the upload
    # would trip on (the demo riders have no license), five named and the
    # rest counted; never the path, which the scorer just chose.
    assert quiet and quiet[-1].startswith("inform:")
    text = quiet[-1].removeprefix("inform:")
    assert str(out) not in text
    assert text.startswith("<p>The file has 1 race, as USAC will file it:</p>")
    assert f"<td style='padding-right: 16px'>{first.name}</td>" in text
    left_out = [r.name for r in c.store.races(c.event.event_id)[1:]]
    assert left_out[-1] == first.name
    assert f"<b>Not finished, so not in the file:</b> {', '.join(left_out)}." in text
    riders = len(c.live.roster.ids)
    assert riders > 5
    assert f" and {riders - 5} more.</li>" in text


def test_export_csv_offers_the_report_to_copy_as_plain_text(make_app, tmp_path, monkeypatch):
    """Copy keeps the notes once the box is closed."""
    from madtracker.ui import icons as icons_mod

    c = make_app(demo=True, data_dir=tmp_path / "data")
    _finish_first_race(c)
    said = []
    monkeypatch.setattr(icons_mod, "inform", lambda *a, **k: said.append(k.get("copy")))
    c.export_csv(tmp_path / "usac.csv")
    [text] = said
    lines = text.splitlines()
    assert lines[0] == "The file has 1 race, as USAC will file it:"
    assert lines[1] == "Race\tDiscipline\tCategory\tClass\tGender"
    assert lines[2].split("\t")[0] == c.races[0].name
    assert "Things to check before uploading:" in lines
    assert any(line.startswith("- No USAC License: ") for line in lines)
    assert "<" not in text, "plain text, not the box's markup"


def test_export_csv_asks_where_with_the_event_name_and_cancel_writes_nothing(
    make_app, tmp_path, quiet, monkeypatch
):
    from PySide6.QtWidgets import QFileDialog

    asked = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: asked.append(a) or ("", ""))
    c = make_app(demo=True, data_dir=tmp_path / "data")
    quiet.clear()
    assert c.export_csv() is None
    assert asked[0][2].endswith(
        f"{c.event.event_date} - Demo Race Night - Results - USAC Upload.csv"
    )
    assert not quiet


def test_export_pdf_writes_one_race_or_the_whole_event(make_app, tmp_path, quiet):
    from madtracker.control.exports import default_file_name, race_file_name

    c = make_app(demo=True, data_dir=tmp_path / "data")
    _finish_first_race(c)
    one = c.export_pdf(tmp_path / "one.pdf", race_id=c.races[0].race_id)
    whole = c.export_pdf(tmp_path / "whole.pdf", whole=True)
    assert one.is_file() and whole.is_file()
    assert whole.stat().st_size > 100 and one.stat().st_size > 100
    assert not quiet, "the scorer chose the place; nothing to confirm"
    event = f"{c.event.event_date} - Demo Race Night - Results"
    assert default_file_name(c.event, "pdf") == f"{event} - Overall.pdf"
    assert race_file_name(c.event, "Points A/B") == f"{event} - Points A B.pdf"


def test_export_program_writes_the_sheet_under_the_event_name(make_app, tmp_path, quiet):
    """The program, for the riders and the announcer."""
    from madtracker.control.exports import default_file_name

    c = make_app(demo=True, data_dir=tmp_path / "data")
    out = tmp_path / "program.pdf"
    assert c.export_program(out) == out
    assert out.read_bytes().startswith(b"%PDF") and not quiet
    assert c.main.export_program_action.isEnabled()
    assert c.main.export_pdf_action.isEnabled() and c.main.export_csv_action.isEnabled()
    name = f"{c.event.event_date} - Demo Race Night - Program.pdf"
    assert default_file_name(c.event, "program") == name


@pytest.fixture
def pdf_dialog(monkeypatch):
    """The Export Results PDF dialog as the app built it, cancelled so nothing is written."""
    from madtracker.ui.setup import ExportPdfDialog

    seen = []
    monkeypatch.setattr(
        ExportPdfDialog,
        "exec",
        lambda self: seen.append(self) or int(ExportPdfDialog.DialogCode.Rejected),
    )
    return seen


def test_export_pdf_lists_the_started_races_and_shows_the_selected_one(
    make_app, tmp_path, pdf_dialog
):
    """Whole event, or any started race from a list."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    _finish_first_race(c)
    # The elimination under way, then back to the first race.
    c.select_race(c.races[1].race_id)
    assert c.live.format_key == "elimination"
    assert c.click(c.live.roster.ids[0]) and c.live.state == "running"
    c.select_race(c.races[0].race_id)
    started = [(r.race_id, r.name) for r in c.store.races(c.event.event_id) if r.state != "setup"]
    assert len(started) == 2
    assert c.export_pdf() is None
    d = pdf_dialog[-1]
    listed = [(d.choice.itemData(i), d.choice.itemText(i)) for i in range(d.choice.count())]
    assert listed == started and (c.races[0].race_id, c.races[0].name) in listed
    assert d.race.isChecked() and d.race_id() == c.races[0].race_id
    # Another race picked from the list is the one exported.
    other = next(i for i in range(d.choice.count()) if d.choice.itemData(i) != c.races[0].race_id)
    d.whole.setChecked(True)
    d.choice.setCurrentIndex(other)
    d.choice.activated.emit(other)
    assert d.race.isChecked() and d.race_id() == d.choice.itemData(other)
    d.whole.setChecked(True)
    assert d.race_id() is None

    # A race not started yet is not listed: the whole event is the
    # default, and the list shows the nearest started race before it.
    later = c.races[3]
    c.select_race(later.race_id)
    c.export_pdf()
    d = pdf_dialog[-1]
    assert d.whole_event() and d.race.isEnabled()
    assert later.race_id not in [d.choice.itemData(i) for i in range(d.choice.count())]
    order = [r.race_id for r in c.races]
    before = [i for i, _ in started if order.index(i) < order.index(later.race_id)]
    assert d.choice.currentData() == before[-1] == c.races[1].race_id


def test_export_pdf_offers_only_the_event_when_nothing_has_started(make_app, tmp_path, pdf_dialog):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    for race in c.store.races(c.event.event_id):
        if race.state != "setup":
            c.store.delete_race(race.race_id)
    c.select_race(c.store.races(c.event.event_id)[0].race_id)
    c.export_pdf()
    d = pdf_dialog[-1]
    assert d.choice.count() == 0 and not d.race.isEnabled() and not d.choice.isEnabled()
    assert d.whole_event() and d.race.toolTip() == "No race has started yet."


def _result_backed_up(c) -> None:
    """Wait for a result's backup, which runs once the screen shows the result."""
    for _ in range(200):
        if not c._backup_pending:
            return
        QTest.qWait(10)
    raise AssertionError("the result's backup never ran")


def test_backups_land_when_a_result_is_recorded_and_on_request(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    folder = venue.automatic_backup_dir(c.data_dir)
    assert not folder.exists() or not list(folder.glob("*.sqlite"))
    ids = list(c.live.roster.ids)
    for eid in ids[:-1]:
        assert c.click(eid)
    _result_backed_up(c)
    assert not list(folder.glob("*.sqlite")), "no backup for a half-built order"
    assert c.click(ids[-1])
    _result_backed_up(c)
    assert len(list(folder.glob("*.sqlite"))) == 1
    copy = tmp_path / "home" / "tonight.sqlite"
    copy.parent.mkdir()
    assert c.backup_now(copy) == copy and copy.is_file()
    assert len(list(folder.glob("*.sqlite"))) == 2, "the automatic copy too"
    assert quiet[-1] == f"inform:Backup written to:\n{copy}"


def _finish_first_race(c) -> None:
    """Click the whole field: the last click makes the race provisional and backs it up."""
    ids = list(c.live.roster.ids)
    for eid in ids:
        assert c.click(eid)
    _result_backed_up(c)


def test_a_result_backs_up_after_the_click_and_before_the_next_one(make_app, tmp_path):
    """The click that makes a result answers first; its backup follows, still of that result."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    folder = venue.automatic_backup_dir(c.data_dir)
    race_id = c.live.race_id
    ids = list(c.live.roster.ids)
    for eid in ids:
        assert c.click(eid)
    assert c.main.surface.state.text() == "Provisional"
    assert c._backup_pending and not list(folder.glob("*.sqlite"))
    # An Undo before the timer takes back the completing click; the copy
    # is taken first, of the result.
    assert c.undo()
    assert c.live.state != "provisional" and not c._backup_pending
    [backup] = list(folder.glob("*.sqlite"))
    with Store.open(backup) as copy:
        assert copy.race(race_id).state == "provisional"
    # A result again, left to its timer: one more copy, and only one.
    assert c.click(ids[-1])
    assert c.live.state == "provisional"
    _result_backed_up(c)
    assert len(list(folder.glob("*.sqlite"))) == 2
    QTest.qWait(100)
    assert len(list(folder.glob("*.sqlite"))) == 2


def test_a_result_waiting_for_its_backup_is_backed_up_at_close(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    folder = venue.automatic_backup_dir(c.data_dir)
    for eid in list(c.live.roster.ids):
        assert c.click(eid)
    assert c._backup_pending
    c.close()
    assert len(list(folder.glob("*.sqlite"))) == 1


def test_an_unwritable_backups_folder_never_breaks_the_click_or_the_close(
    make_app, tmp_path, quiet
):
    from madtracker.control.backups import marker_path

    c = make_app(demo=True, data_dir=tmp_path / "data")
    # The automatic folder's name taken by a file: nothing can be written there.
    venue.automatic_backup_dir(c.data_dir).write_text("not a folder", encoding="utf-8")
    _finish_first_race(c)
    assert c.main.surface.state.text() == "Provisional"
    assert quiet[-1].startswith("warn:Automatic backup failed")
    # The copy the scorer asked for still lands; the automatic one says it failed.
    copy = tmp_path / "copy.sqlite"
    assert c.backup_now(copy) == copy
    assert any(q.startswith("warn:Automatic backup failed") for q in quiet[-2:])
    marker = marker_path(c.data_path)
    assert marker.exists()
    c.close()
    assert c.store is None and not marker.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="chmod does not make a folder read-only")
def test_a_read_only_extra_backup_folder_is_a_warning_and_scoring_goes_on(
    make_app, tmp_path, quiet
):
    import os

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root writes into a read-only folder")
    stick = tmp_path / "stick"
    stick.mkdir()
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.store.set_setting(venue.BACKUP_KEY, str(stick))
    stick.chmod(0o500)
    try:
        _finish_first_race(c)
        assert c.main.surface.state.text() == "Provisional"
        # A result backs up beside the file only; the stick is for the end of the night.
        assert not any(q.startswith("warn:") for q in quiet)
        assert list(venue.automatic_backup_dir(c.data_dir).glob("*.sqlite"))
        # A copy asked for in a folder that cannot be written says so.
        assert c.backup_now(stick / "tonight.sqlite") is None
        assert quiet[-1].startswith("warn:The backup could not be written (")
        assert quiet[-1].endswith(f":\n{stick / 'tonight.sqlite'}")
    finally:
        stick.chmod(0o700)


def test_an_extra_backup_folder_that_raises_is_a_warning_and_scoring_goes_on(
    make_app, tmp_path, monkeypatch, quiet
):
    import sqlite3

    stick = tmp_path / "stick"
    stick.mkdir()
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.store.set_setting(venue.BACKUP_KEY, str(stick))
    real = Store.backup_to

    def backup_to(self, dest, *args):
        # A drive that fails inside SQLite rather than in the file system.
        if Path(dest).parent == stick:
            raise sqlite3.OperationalError("disk I/O error")
        return real(self, dest, *args)

    monkeypatch.setattr(Store, "backup_to", backup_to)
    _finish_first_race(c)
    assert c.main.surface.state.text() == "Provisional"
    assert not any(q.startswith("warn:") for q in quiet)
    _quit(c, monkeypatch)
    assert quiet[-1].startswith(f"warn:The extra backup failed (disk I/O error):\n{stick}\n")


def test_a_failed_export_says_so_where_the_scorer_is_looking(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    taken = tmp_path / "results.pdf"
    taken.mkdir()
    assert c.export_pdf(taken, whole=True) is None
    assert quiet[-1].startswith("warn:Could not write (")
    assert f":\n{taken}\n\n" in quiet[-1]
    assert quiet[-1].endswith("If the file is open in another program, close it and try again.")
    taken = tmp_path / "results.csv"
    taken.mkdir()
    assert c.export_csv(taken) is None
    assert "warn:Could not write (" in quiet[-1] and f":\n{taken}\n\n" in quiet[-1]


def test_a_new_data_file_name_that_exists_is_refused_before_the_copy_question(
    make_app, tmp_path, quiet, monkeypatch
):
    from madtracker.ui import setup

    asked: list[str] = []
    monkeypatch.setattr(setup.CopyFileDialog, "exec", lambda self: asked.append("copy") or 0)
    c = make_app(demo=True, data_dir=tmp_path / "data")
    taken = tmp_path / "taken.sqlite"
    taken.write_bytes(b"")
    assert not c.new_data_file(taken)
    said = f"warn:This file already exists:\n{taken}\n\nUse File > Open Data File..."
    assert asked == [] and quiet[-1] == said


def test_an_empty_file_is_not_opened_as_a_data_file(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    empty = tmp_path / "empty.sqlite"
    empty.write_bytes(b"")
    assert not c.open_data_file(empty)
    assert "This is not a MadTracker data file" in quiet[-1]
    assert empty.stat().st_size == 0
    assert c.event.name == "Demo Race Night"


def test_open_data_file_under_data_dir_is_not_remembered_for_a_plain_start(make_app, tmp_path):
    from madtracker import app as app_mod

    c = make_app(demo=True, data_dir=tmp_path / "data")
    other = tmp_path / "other.sqlite"
    Store.open(other).close()
    assert c.open_data_file(other)
    assert c.settings.value(app_mod.DATA_FILE_KEY, None) is None


def test_open_demo_file_asks_first_and_cancel_changes_nothing(
    make_app, tmp_path, quiet, monkeypatch
):
    c = make_app(data_dir=tmp_path / "data")
    path = c.data_path
    monkeypatch.setattr(
        icons,
        "choose",
        lambda *a, **k: quiet.extend(["choose:" + a[1], "text:" + a[2], repr(k)]) and None,
    )
    assert not c.open_demo_file()
    assert quiet[-3] == "choose:Open Demo Data File"
    # The question says where the demo goes, the path on its own line.
    assert quiet[-2].endswith(f"reopen the demo at:\n{tmp_path / 'data' / 'demo' / 'demo.sqlite'}")
    # No demo yet: nothing previous to open.
    assert quiet[-1] == "{'disabled': ('Open Previous',)}"
    assert c.data_path == path and c.store is not None
    assert not (tmp_path / "data" / "demo").exists()


def test_open_demo_file_builds_and_opens_the_demo_for_the_session_only(
    make_app, tmp_path, quiet, monkeypatch
):
    from madtracker import app as app_mod

    monkeypatch.setattr(app_mod, "DATA_FILE_KEY", "data/file")
    c = make_app(data_dir=tmp_path / "data")
    # As a plain start does, so what the next start reopens can be checked.
    c.remember_file = True
    original = c.data_path
    c.settings.setValue(app_mod.DATA_FILE_KEY, str(original.absolute()))
    assert c.main.open_demo_action.isEnabled()
    c.main.open_demo_action.trigger()
    demo = (tmp_path / "data" / "demo" / "demo.sqlite").absolute()
    assert quiet[-1] == "choose:Open Demo Data File"
    assert c.data_path == demo and demo.is_file()
    assert c.event.name == "Demo Race Night" and len(c.races) > 1
    assert c.live is not None and c.main.showing() == "surface"
    assert "Demo Race Night" in c.main.windowTitle()
    # Never remembered: the next start comes back to the venue's file.
    assert c.settings.value(app_mod.DATA_FILE_KEY) == str(original.absolute())
    # File > Open Data File goes back now; the demo stays on disk.
    assert c.open_data_file(original)
    assert c.data_path == original.absolute() and demo.is_file()
    assert c.settings.value(app_mod.DATA_FILE_KEY) == str(original.absolute())


def test_open_previous_demo_keeps_what_was_scored_and_is_offered_only_when_there_is_one(
    make_app, tmp_path, quiet, monkeypatch
):
    from madtracker import app as app_mod

    monkeypatch.setattr(app_mod, "DATA_FILE_KEY", "data/file")
    c = make_app(data_dir=tmp_path / "data")
    c.remember_file = True
    original = c.data_path
    c.settings.setValue(app_mod.DATA_FILE_KEY, str(original.absolute()))
    offered: list[tuple] = []

    def chooser(*a, **k):
        offered.append(k.get("disabled", ()))
        return answers.pop(0)

    monkeypatch.setattr(icons, "choose", chooser)
    answers = [app_mod.CREATE_NEW]
    assert c.open_demo_file()
    demo = c.data_path
    c.store.add_rider("Kept", "Rider")
    # From inside the demo there is no previous one to open.
    answers = [None]
    assert not c.open_demo_file()
    assert offered == [("Open Previous",), ("Open Previous",)]
    # Back in the venue's file, Open Previous is offered and brings the
    # demo back as it was left, for the session only.
    assert c.open_data_file(original)
    answers = [app_mod.OPEN_PREVIOUS]
    assert c.open_demo_file()
    assert offered[-1] == () and c.data_path == demo
    assert "Kept" in [r.first_name for r in c.store.riders()]
    assert c.settings.value(app_mod.DATA_FILE_KEY) == str(original.absolute())


def test_open_demo_file_again_while_in_it_builds_it_fresh(make_app, tmp_path, quiet):
    c = make_app(data_dir=tmp_path / "data")
    assert c.open_demo_file()
    first = c.live.roster.ids[0]
    assert c.click(first)
    c.store.add_rider("Leftover", "Rider")
    assert c.open_demo_file()
    assert c.data_path == (tmp_path / "data" / "demo" / "demo.sqlite").absolute()
    assert c.event.name == "Demo Race Night" and c.live is not None
    assert not c.live._staged.groups and not c.live._staged.tail
    assert "Leftover" not in [r.first_name for r in c.store.riders()]


def test_open_demo_file_backs_up_in_its_own_folder_only(make_app, tmp_path, quiet):
    data = tmp_path / "data"
    stick = tmp_path / "stick"
    stick.mkdir()
    c = make_app(data_dir=data)
    venue.save(c.store, name="Riverside", backup=str(stick), keep_logo=True, accent="#b794ff")
    assert c.open_demo_file()
    before = sorted((data / "backups").iterdir()) if (data / "backups").exists() else []
    stuck = sorted(stick.iterdir())
    taken = c.auto_backup(extra=True)
    assert taken is not None and taken.parent == venue.automatic_backup_dir(data / "demo")
    after = sorted((data / "backups").iterdir()) if (data / "backups").exists() else []
    assert after == before and sorted(stick.iterdir()) == stuck


def test_open_demo_file_from_a_demo_start_builds_under_its_folder(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    assert c.open_demo_file()
    assert c.data_path == (tmp_path / "data" / "demo" / "demo.sqlite").absolute()
    # Again from inside the demo: the same file, never a demo inside the demo.
    assert c.open_demo_file()
    assert c.data_path == (tmp_path / "data" / "demo" / "demo.sqlite").absolute()
    assert not (tmp_path / "data" / "demo" / "demo").exists()


def test_the_next_start_after_the_demo_returns_to_the_venues_file(
    make_app, tmp_path, quiet, monkeypatch
):
    from madtracker import app as app_mod
    from madtracker.store.paths import DATA_DIR_ENV

    home = tmp_path / "home"
    monkeypatch.setenv(DATA_DIR_ENV, str(home))
    monkeypatch.setattr(app_mod, "DATA_FILE_KEY", "data/file")
    first = make_app()
    venue_file = first.data_path
    assert first.open_demo_file()
    demo = (home / "demo" / "demo.sqlite").absolute()
    assert first.data_path == demo
    first.close()
    # The next start comes back to the venue's file; the demo is still on disk.
    again = make_app()
    assert again.data_path == venue_file and again.base_dir == home and demo.is_file()
    assert again.event is None or again.event.name != "Demo Race Night"
    # Opened by hand, the demo is remembered as any file is, and the next
    # demo is still built in the same place, never inside it.
    assert again.open_data_file(demo) and again.data_path == demo
    assert again.open_demo_file() and again.data_path == demo
    assert not (home / "demo" / "demo").exists()


def test_open_demo_file_that_cannot_be_built_keeps_the_open_file(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    path = c.data_path
    # A file where the demo folder goes: the folder cannot be made.
    (tmp_path / "data" / "demo").write_bytes(b"")
    assert not c.open_demo_file()
    assert quiet[-1].startswith("warn:Could not build") and f"Still open:\n{path}" in quiet[-1]
    assert c.data_path == path and c.event.name == "Demo Race Night"


def test_open_data_file_mid_race_asks_first(make_app, tmp_path, quiet, monkeypatch):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    assert c.click(c.live.roster.ids[0])
    other = tmp_path / "other.sqlite"
    Store.open(other).close()
    monkeypatch.setattr(icons, "ask", lambda *a, **k: quiet.append("ask:" + a[1]) and False)
    assert not c.open_data_file(other)
    assert quiet[-1] == "ask:Switch Race" and c.data_path != other.absolute()
    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    assert c.open_data_file(other)
    assert c.data_path == other.absolute()


def test_a_second_copy_on_the_same_file_is_refused_and_the_first_keeps_working(make_app, tmp_path):
    from madtracker.app import ALREADY_OPEN
    from madtracker.control.backups import lock_path, marker_path

    first = make_app(demo=True, data_dir=tmp_path / "data")
    second = make_app(data_dir=tmp_path / "data")
    # No store at all: the second copy can neither score into the file
    # nor remove the first one's clean-close marker when it quits.
    assert second.store is None and second.main.showing() == "empty"
    assert second._notice == ALREADY_OPEN and not second.recovered
    second.close()
    assert marker_path(first.data_path).exists()
    assert first.click(first.live.roster.ids[0])
    path = first.data_path
    first.close()
    assert not lock_path(path).exists() and not marker_path(path).exists()
    again = make_app(data_dir=tmp_path / "data")
    assert again.store is not None and not again.recovered


def test_open_data_file_on_a_file_another_window_holds_keeps_the_current_one(
    make_app, tmp_path, quiet
):
    from madtracker.app import ALREADY_OPEN

    c = make_app(demo=True, data_dir=tmp_path / "data")
    other = make_app(demo=True, data_dir=tmp_path / "other")
    assert not c.open_data_file(other.data_path)
    assert quiet[-1].startswith("warn:" + ALREADY_OPEN)
    assert c.data_path == (tmp_path / "data" / "madtracker.sqlite").absolute()
    assert c.store is not None and c.click(c.live.roster.ids[0])


def test_a_lock_left_by_a_crashed_copy_does_not_refuse_the_file(make_app, tmp_path):
    import subprocess

    from PySide6.QtCore import QSysInfo

    from madtracker.control.backups import lock_path

    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    data = tmp_path / "data"
    data.mkdir()
    # What QLockFile writes: pid, application name, host name.
    lock_path(data / "madtracker.sqlite").write_text(
        f"{gone.pid}\n{QApplication.applicationName()}\n{QSysInfo.machineHostName()}\n"
    )
    c = make_app(data_dir=data)
    assert c.store is not None


def test_close_releases_the_lock(make_app, tmp_path):
    from madtracker.control.backups import lock_path

    c = make_app(demo=True, data_dir=tmp_path / "data")
    lock = lock_path(c.data_path)
    assert lock.exists()
    c.close()
    assert not lock.exists()


def test_switching_files_moves_the_lock(make_app, tmp_path):
    from madtracker.control.backups import lock_path

    c = make_app(demo=True, data_dir=tmp_path / "data")
    first = c.data_path
    other = tmp_path / "other.sqlite"
    Store.open(other).close()
    assert c.open_data_file(other)
    assert not lock_path(first).exists() and lock_path(other.absolute()).exists()


def test_opening_a_backup_restores_a_copy_and_leaves_the_backup_alone(make_app, tmp_path):
    from madtracker.control.backups import rotate
    from madtracker.store import read_backup_mark

    c = make_app(demo=True, data_dir=tmp_path / "data")
    backup = c.auto_backup()
    before = backup.read_bytes()
    # Restored into the backups folder itself, under a backup's kind of
    # name: the copy is a data file now, so rotation leaves it alone.
    restored = backup.parent / "madtracker-2026-10-09-120000.sqlite"
    assert c.open_data_file(backup, restore_to=restored)
    assert c.data_path == restored and c.event.name == "Demo Race Night"
    assert read_backup_mark(restored) is None
    assert c.click(c.live.roster.ids[0])
    assert backup.read_bytes() == before
    rotate(backup.parent, keep=0, dates=0)
    assert not backup.exists() and restored.exists()


def test_a_backup_renamed_on_a_stick_still_asks_to_restore(make_app, tmp_path, quiet, monkeypatch):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    current = c.data_path
    stick = tmp_path / "stick"
    stick.mkdir()
    copy = c.backup_now(stick / "Race Night.sqlite")
    monkeypatch.setattr(icons, "ask", lambda *a, **k: quiet.append("ask:" + a[2]) and False)
    assert not c.open_data_file(copy)
    assert quiet[-1].startswith("ask:This is a backup of Demo Race Night, taken ")
    assert c.data_path == current


def test_opening_a_backup_asks_and_cancel_keeps_the_current_file(
    make_app, tmp_path, quiet, monkeypatch
):
    from PySide6.QtWidgets import QFileDialog

    c = make_app(demo=True, data_dir=tmp_path / "data")
    current = c.data_path
    backup = c.auto_backup()
    monkeypatch.setattr(icons, "ask", lambda *a, **k: quiet.append("ask:" + a[2]) and False)
    assert not c.open_data_file(backup)
    assert quiet[-1].startswith("ask:This is a backup of Demo Race Night, taken ")
    assert quiet[-1].endswith(". Restore it as a new data file?")
    assert c.data_path == current
    # Restore, then Cancel in the save box: still the current file.
    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    assert not c.open_data_file(backup)
    assert c.data_path == current
    chosen = tmp_path / "data" / "night"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(chosen), ""))
    assert c.open_data_file(backup)
    assert c.data_path == chosen.with_suffix(".sqlite").absolute()


def test_a_restore_never_replaces_a_file_it_cannot_back_up_first(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    current = c.data_path
    backup = c.auto_backup()
    taken = tmp_path / "taken.sqlite"
    taken.write_bytes(b"keep")
    assert not c.open_data_file(backup, restore_to=taken)
    assert "It was not replaced." in quiet[-1] and taken.read_bytes() == b"keep"
    assert c.data_path == current


def test_a_backup_this_version_cannot_read_is_refused_before_anything_changes(
    make_app, tmp_path, quiet, monkeypatch
):
    """A backup this version cannot read is refused before it replaces the file."""
    import sqlite3

    c = make_app(demo=True, data_dir=tmp_path / "data")
    backup = c.auto_backup()
    # A backup with a table missing.
    conn = sqlite3.connect(backup)
    conn.execute("DROP TABLE team_member")
    conn.commit()
    conn.close()
    before = c.data_path.read_bytes()
    asked = []
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or True)
    assert not c.open_data_file(backup, restore_to=c.data_path)
    assert not c.open_data_file(backup)
    assert not asked, "refused before the restore question"
    assert quiet[-1].startswith(f"warn:This backup can't be restored:\n{backup}")
    assert "Nothing was changed." in quiet[-1]
    assert c.data_path.read_bytes() == before and c.store is not None


def _event_names(path):
    from madtracker.store import Store

    store = Store.open(path)
    try:
        return sorted(e.name for e in store.events())
    finally:
        store.close()


def test_a_restore_over_another_data_file_asks_and_backs_it_up_first(
    make_app, tmp_path, quiet, monkeypatch
):
    """Choosing an existing file asks to replace it, rather than refusing."""
    from PySide6.QtWidgets import QFileDialog

    from madtracker.control.backups import backups_in

    c = make_app(demo=True, data_dir=tmp_path / "data")
    backup = c.auto_backup()
    other = make_app(demo=True, data_dir=tmp_path / "other")
    other.store.add_event("Only In Other", "2026-09-01")
    target = other.data_path
    other.close()
    # Left by an unclean close: it must not be applied to the restored file.
    Path(f"{target}-wal").write_bytes(b"stale")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    answers = iter([True, False])
    monkeypatch.setattr(icons, "ask", lambda *a, **k: quiet.append("ask:" + a[2]) or next(answers))
    # Restore, then Cancel at Replace: nothing changes.
    assert not c.open_data_file(backup)
    assert quiet[-1].startswith(f"ask:This file already exists:\n{target}\n\nReplace it")
    assert "Only In Other" in _event_names(target)
    answers = iter([True, True, True])
    assert c.open_data_file(backup)
    assert c.data_path == target.absolute()
    assert "Only In Other" not in [e.name for e in c.store.events()]
    # What the file held is in its own backups folder.
    [saved] = [p for p in backups_in(target.parent / "backups")]
    assert "Only In Other" in _event_names(saved)


def test_a_restore_over_the_open_file_replaces_it_after_a_backup(
    make_app, tmp_path, quiet, monkeypatch
):
    from PySide6.QtWidgets import QFileDialog

    from madtracker.control.backups import backups_in

    c = make_app(demo=True, data_dir=tmp_path / "data")
    (tmp_path / "stick").mkdir()
    backup = c.backup_now(tmp_path / "stick" / "night.sqlite")
    assert backup is not None
    c.store.add_event("Added After", "2026-09-02")
    target = c.data_path
    before = set(backups_in(target.parent / "backups"))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    assert c.open_data_file(backup)
    assert c.data_path == target and c.store is not None
    assert "Added After" not in [e.name for e in c.store.events()]
    saved = set(backups_in(target.parent / "backups")) - before
    assert any("Added After" in _event_names(p) for p in saved)
    assert c.click(c.live.roster.ids[0]), "the restored file takes entries"


def test_another_programs_file_marked_as_a_backup_never_replaces_the_open_file(
    make_app, tmp_path, quiet
):
    """A file that passes the backup check but will not open never replaces the open file."""
    import sqlite3

    c = make_app(demo=True, data_dir=tmp_path / "data")
    target = c.data_path
    foreign = tmp_path / "foreign.sqlite"
    conn = sqlite3.connect(foreign)
    conn.execute("CREATE TABLE setting (key TEXT PRIMARY KEY, value_json TEXT)")
    conn.execute("INSERT INTO setting VALUES ('backup', '{}')")
    conn.commit()
    conn.close()
    assert not c.open_data_file(foreign, restore_to=target)
    assert quiet[-1].startswith(f"warn:This backup can't be restored:\n{foreign}")
    assert c.store is not None and c.data_path == target and target.is_file()
    assert c.event.name == "Demo Race Night"


def test_a_restore_onto_the_backup_by_another_spelling_is_refused(make_app, tmp_path, quiet):
    from madtracker.store import read_backup_mark

    c = make_app(demo=True, data_dir=tmp_path / "data")
    current = c.data_path
    backup = c.auto_backup()
    (backup.parent / "sub").mkdir()
    assert not c.open_data_file(backup, restore_to=backup.parent / "sub" / ".." / backup.name)
    assert quiet[-1].startswith("warn:That is the backup itself")
    assert c.data_path == current
    assert read_backup_mark(backup) is not None


def test_restoring_the_oldest_kept_backup_over_the_open_file_never_rotates_it_away(
    make_app, tmp_path, quiet
):
    """The copy of the open file taken first never rotates the chosen backup out of the folder."""
    import os
    from datetime import datetime, timedelta

    from madtracker.control.backups import KEEP, take_backup

    c = make_app(demo=True, data_dir=tmp_path / "data")
    folder = venue.automatic_backup_dir(c.data_dir)
    start = datetime.now() - timedelta(hours=3)
    made = []
    for i in range(KEEP):
        when = start + timedelta(minutes=i)
        made.append(take_backup(c.store, folder, automatic_folder=True, now=when))
        os.utime(made[-1], (when.timestamp(), when.timestamp()))
    c.store.add_event("Added After", "2026-09-02")
    oldest = made[0]
    assert c.open_data_file(oldest, restore_to=c.data_path)
    assert "Added After" not in [e.name for e in c.store.events()]
    # Rotation runs when the open file is backed up; the newest copies
    # are the ones kept, and the restored file holds the chosen one.
    assert c.store.integrity_check() == []


def test_a_restore_that_cannot_replace_the_open_file_opens_it_again(
    make_app, tmp_path, quiet, monkeypatch
):
    import os

    c = make_app(demo=True, data_dir=tmp_path / "data")
    (tmp_path / "stick").mkdir()
    backup = c.backup_now(tmp_path / "stick" / "night.sqlite")
    race_id = c.live.race_id
    assert c.click(c.live.roster.ids[0])
    target = c.data_path
    real_replace = os.replace

    def held(src, dst):
        # Windows: a virus scanner holding the file refuses the rename.
        if str(src).endswith(".restoring"):
            raise PermissionError(13, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", held)
    assert not c.open_data_file(backup, restore_to=target)
    assert quiet[-1].startswith("warn:Could not replace")
    assert quiet[-1].endswith(f"Still open:\n{target}")
    assert c.store is not None and c.data_path == target
    assert c.live is not None and c.live.race_id == race_id
    assert c.click(c.live.roster.ids[1]), "scoring goes on in the file"


def _failing_open_once(monkeypatch, target, after=0):
    """Store.open fails once on ``target`` (a full disk, say), after ``after`` opens, then works."""
    import madtracker.store as store_mod

    real = store_mod.Store.open.__func__
    seen = [0]

    def failing(cls, path, *a, **k):
        if Path(path).absolute() == Path(target).absolute():
            seen[0] += 1
            if seen[0] == after + 1:
                raise store_mod.StoreError("database or disk is full")
        return real(cls, path, *a, **k)

    monkeypatch.setattr(store_mod.Store, "open", classmethod(failing))


def test_a_restore_over_the_open_file_that_cannot_open_puts_it_back_and_opens_it(
    make_app, tmp_path, quiet, monkeypatch
):
    """A failed open puts the replaced file, the venue's whole history, back and opens it."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    (tmp_path / "stick").mkdir()
    backup = c.backup_now(tmp_path / "stick" / "night.sqlite")
    c.store.add_event("Added After", "2026-09-02")
    race_id = c.live.race_id
    target = c.data_path
    _failing_open_once(monkeypatch, target)
    assert not c.open_data_file(backup, restore_to=target)
    assert quiet[-1].startswith("warn:Could not open (database or disk is full)")
    assert "It was put back as it was." in quiet[-1]
    assert quiet[-1].endswith(f"Still open:\n{target}")
    assert target.is_file()
    assert c.store is not None and c.data_path == target
    assert "Added After" in [e.name for e in c.store.events()]
    assert c.live is not None and c.live.race_id == race_id
    assert c.click(c.live.roster.ids[0]), "scoring goes on in the file"


def test_a_restore_over_another_file_that_cannot_open_puts_that_file_back(
    make_app, tmp_path, quiet, monkeypatch
):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    backup = c.auto_backup()
    other = make_app(demo=True, data_dir=tmp_path / "other")
    other.store.add_event("Only In Other", "2026-09-01")
    target = other.data_path
    other.close()
    current = c.data_path
    # Its first open is the copy taken before it is replaced.
    _failing_open_once(monkeypatch, target, after=1)
    assert not c.open_data_file(backup, restore_to=target)
    assert "It was put back as it was." in quiet[-1]
    assert quiet[-1].endswith(f"Still open:\n{current}")
    assert c.data_path == current and c.store is not None
    assert "Only In Other" in _event_names(target)
    from madtracker.store import read_backup_mark

    assert read_backup_mark(target) is None, "put back as a data file, not a backup"


def test_a_restore_mid_race_asks_to_leave_before_backing_anything_up(
    make_app, tmp_path, quiet, monkeypatch
):
    """The leave-the-race question comes before Replace and its backup, so a No leaves no copy."""
    from madtracker.control.backups import backups_in

    c = make_app(demo=True, data_dir=tmp_path / "data")
    (tmp_path / "stick").mkdir()
    backup = c.backup_now(tmp_path / "stick" / "night.sqlite")
    assert c.click(c.live.roster.ids[0])
    assert c.live.in_progress
    target = c.data_path
    before = set(backups_in(venue.automatic_backup_dir(c.data_dir)))
    monkeypatch.setattr(icons, "ask", lambda *a, **k: quiet.append("ask:" + a[2]) or False)
    assert not c.open_data_file(backup, restore_to=target)
    # Named by the backup: the target's own name is the file already open.
    assert quiet[-1].endswith(f"Switch to {backup.name}?")
    assert set(backups_in(venue.automatic_backup_dir(c.data_dir))) == before
    assert not list(target.parent.glob("*.restoring"))
    assert c.store is not None and c.live.in_progress


def test_the_copy_taken_before_a_restore_names_its_event_and_outlives_rotation(
    make_app, tmp_path, quiet
):
    from madtracker.control.backups import BEFORE_RESTORE, KEEP
    from madtracker.store import read_backup_mark

    c = make_app(demo=True, data_dir=tmp_path / "data")
    (tmp_path / "stick").mkdir()
    backup = c.backup_now(tmp_path / "stick" / "night.sqlite")
    c.store.add_event("Added After", "2026-09-02")
    assert c.open_data_file(backup, restore_to=c.data_path)
    folder = venue.automatic_backup_dir(c.data_dir)
    [saved] = folder.glob(BEFORE_RESTORE + "*.sqlite")
    assert read_backup_mark(saved)["event"] == "Demo Race Night"
    for _ in range(KEEP + 1):
        c.auto_backup()
    assert saved.is_file()
    assert "Added After" in _event_names(saved)


def test_a_restore_over_the_open_file_still_writes_the_extra_copy(make_app, tmp_path, quiet):
    """The open file closes through final_backup, so the chosen folder gets the night."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    stick = tmp_path / "stick"
    stick.mkdir()
    backup = c.backup_now(stick / "night.sqlite")
    c.store.set_setting(venue.BACKUP_KEY, str(stick))
    c.store.add_event("Added After", "2026-09-02")
    assert c.open_data_file(backup, restore_to=c.data_path)
    copies = [p for p in stick.glob("madtracker-*.sqlite")]
    assert copies and "Added After" in _event_names(copies[-1])


def test_a_backup_with_flipped_bytes_is_refused_and_the_open_file_stays(make_app, tmp_path, quiet):
    """Damaged pages put bytes that are not UTF-8 into SQLite's error text; the open survives it."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    raw = bytearray(c.auto_backup().read_bytes())
    for i in range(4096 * 3, len(raw), 997):
        raw[i] ^= 0xFF
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(raw)
    current = c.data_path
    assert not c.open_data_file(bad)
    assert quiet[-1].startswith("warn:Could not open (")
    assert quiet[-1].endswith(f"Still open:\n{current}")
    assert c.store is not None and c.event.name == "Demo Race Night"


def test_a_restore_over_a_file_another_window_holds_is_refused(
    make_app, tmp_path, quiet, monkeypatch
):
    from PySide6.QtWidgets import QFileDialog

    from madtracker.app import ALREADY_OPEN

    c = make_app(demo=True, data_dir=tmp_path / "data")
    backup = c.auto_backup()
    other = make_app(demo=True, data_dir=tmp_path / "other")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(other.data_path), ""))
    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    assert not c.open_data_file(backup)
    assert quiet[-1].startswith("warn:" + ALREADY_OPEN)
    assert (
        other.store is not None
        and c.data_path == (tmp_path / "data" / "madtracker.sqlite").absolute()
    )


def test_a_backup_put_back_by_hand_opens_as_the_data_file(make_app, tmp_path):
    import shutil

    from madtracker.store import read_backup_mark

    first = make_app(demo=True, data_dir=tmp_path / "data")
    backup = first.auto_backup()
    first.close()
    home = tmp_path / "home"
    home.mkdir()
    shutil.copyfile(backup, home / "madtracker.sqlite")
    c = make_app(data_dir=home)
    assert c.store is not None and c.data_path == home / "madtracker.sqlite"
    assert read_backup_mark(c.data_path) is None


def test_a_file_with_a_damaged_page_starts_on_the_notice(make_app, tmp_path):
    import sqlite3

    seeded = make_app(demo=True, data_dir=tmp_path / "seed")
    source = seeded.data_path
    seeded.close()
    data = tmp_path / "data"
    data.mkdir()
    damaged = data / source.name
    damaged.write_bytes(source.read_bytes())
    # The race table's root page overwritten: the file opens, and the
    # first read of the event's races would fail.
    with sqlite3.connect(damaged) as con:
        page_size = con.execute("PRAGMA page_size").fetchone()[0]
        root = con.execute("SELECT rootpage FROM sqlite_master WHERE name = 'race'").fetchone()[0]
    con.close()
    with open(damaged, "r+b") as f:
        f.seek((root - 1) * page_size)
        f.write(b"\xff" * page_size)
    c = make_app(data_dir=data)
    assert c.damaged and c.live is None
    assert c.main.showing() == "empty"
    assert c._notice and "it may be damaged" in c._notice
    # The next step and where the backups are, never the raw SQLite text.
    assert str(venue.automatic_backup_dir(data)) in c._notice
    assert "malformed" not in c._notice
    # Only another file, Help and Quit: everything else would read the bad pages.
    assert not c.main.riders_action.isEnabled() and not c.main.settings_action.isEnabled()
    assert c.main.open_file_action.isEnabled() and c.main.quit_action.isEnabled()


def test_new_data_file_copies_what_was_ticked_and_never_events(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    venue.save(c.store, name="Riverside", backup="", keep_logo=True, accent="#b794ff")
    old = c.data_path
    new = tmp_path / "second.sqlite"
    assert c.new_data_file(new, CopyChoice(settings=True, logo=False, rulesets=True, riders=False))
    assert c.data_path == new and c.event is None
    assert c.main.showing() == "empty"
    assert venue.venue_name(c.store) == "Riverside" and venue.accent(c.store) == "#b794ff"
    assert c.store.rulesets() and c.store.riders() == [] and c.store.events() == []
    assert c.open_data_file(old)
    assert c.event.name == "Demo Race Night"
    taken = tmp_path / "taken.sqlite"
    taken.write_bytes(b"")
    assert not c.new_data_file(taken, CopyChoice()), "an existing file is never overwritten"
    assert c.data_path == old
    # The open file's own name is refused out loud, not passed over in silence.
    assert not c.new_data_file(old, CopyChoice())
    assert c.data_path == old and c.event.name == "Demo Race Night"


def test_a_new_data_file_opens_settings_only_when_no_settings_were_copied(
    make_app, tmp_path, monkeypatch
):
    from madtracker.app import AppController

    opened: list[str] = []
    monkeypatch.setattr(
        AppController, "edit_settings", lambda self: opened.append(self.data_path.name)
    )
    c = make_app(demo=True, data_dir=tmp_path / "data")
    venue.save(c.store, name="Riverside", backup="", keep_logo=True, accent="#b794ff")
    assert c.new_data_file(tmp_path / "copied.sqlite", CopyChoice())
    assert opened == []
    nothing = CopyChoice(settings=False, logo=False, rulesets=False, riders=False)
    assert c.new_data_file(tmp_path / "fresh.sqlite", nothing)
    assert opened == ["fresh.sqlite"]
    assert c.open_data_file(tmp_path / "copied.sqlite")
    assert opened == ["fresh.sqlite"], "opening a file never opens Settings"


def test_a_click_on_the_preview_switches_the_tv_and_the_menu_follows(make_app, tmp_path):
    """The preview is the TV's one control: a click puts
    the race up or the logo back, and the Scoreboard menu's Logo and Live
    show the same choice; a pick there moves the preview the same way."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    tv = c.main.tv
    assert not tv.is_live() and c.main.logo_action.isChecked()
    QTest.mouseClick(tv, Qt.MouseButton.LeftButton)
    assert c.board_live and tv.is_live()
    assert c.main.live_action.isChecked() and not c.main.logo_action.isChecked()
    # The pane is no button, so it flashes on its own, as every button does.
    assert tv.property("flash") is True
    QTest.qWait(style.FLASH_MS + 60)
    assert tv.property("flash") is False
    c.main.logo_action.trigger()
    assert not c.board_live and not tv.is_live()
    c.main.live_action.trigger()
    assert c.board_live and tv.is_live() and c.main.live_action.isChecked()


def test_show_board_and_display_choice(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.show()
    c.place_board()
    assert c.board.isVisible() and not c.main.none_action.isChecked()
    c.show_board(False)
    assert not c.board.isVisible() and c.main.none_action.isChecked()
    c.show_board(True)
    assert c.board.isVisible()
    c.choose_screen(None)
    assert c.preferred_screen_name() is None
    # One list: Automatic, the displays (none headless has a name), None.
    assert c.main.display_labels() == ["Automatic", "None"]
    assert c.main.display_group.actions()[0].isChecked()
    # None in the list is the board off; Automatic brings it back.
    c.main.none_action.trigger()
    assert not c.board.isVisible() and c.main.none_action.isChecked()
    c.main.display_group.actions()[0].trigger()
    assert c.board.isVisible() and c.main.display_group.actions()[0].isChecked()


def test_the_board_opens_as_a_window_on_the_scoring_windows_own_display(
    make_app, tmp_path, monkeypatch
):
    """Full screen there would cover the controls, so it is a window; the pick still stands."""
    from madtracker.board import window as board_window
    from madtracker.displays import ScreenInfo

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.show()
    here = c.main.screen()
    # The offscreen platform's one screen has no name; this one is "TV".
    g = here.geometry()
    info = ScreenInfo("TV", g.x(), g.y(), g.width(), g.height(), True, "TV")
    monkeypatch.setattr(board_window, "screen_infos", lambda screens=None: [info])
    monkeypatch.setattr(board_window, "screen_by_name", lambda n: here if n == "TV" else None)
    c.choose_screen("TV")
    assert c.board_screen == "TV" == c.preferred_screen_name()
    assert c.board.isVisible() and not c.board.isFullScreen()
    # The scoring window moves to another display: the board fills its pick again.
    monkeypatch.setattr(c.main, "screen", lambda: None)
    c._main_screen_changed(None)
    assert c.board.isVisible() and c.board.isFullScreen()

    # And back: it steps aside again, even when Qt hands back another
    # wrapper for the same display, as on Windows.
    class Same:
        def name(self):
            return here.name()

    monkeypatch.setattr(c.main, "screen", lambda: Same())
    c._main_screen_changed(None)
    assert c.board.isVisible() and not c.board.isFullScreen()


def test_escape_on_the_scoreboard_leaves_it_up(make_app, tmp_path):
    """An Alt-Tab onto the TV and an Escape leave the board up."""
    from PySide6.QtTest import QTest

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.show()
    c.place_board()
    assert c.board.isVisible()
    QTest.keyClick(c.board, Qt.Key.Key_Escape)
    assert c.board.isVisible() and not c.main.none_action.isChecked()


def test_a_hidden_scoreboard_veils_the_preview_and_a_display_pick_is_the_way_back(
    make_app, tmp_path
):
    """While the board is off the preview is veiled, a
    click on it does nothing, and the menu's Logo and Live are grayed; a
    display picked in the Scoreboard menu brings it back, on the logo."""
    from madtracker.ui.tv import HIDDEN_TIP

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.show()
    c.place_board()
    tv = c.main.tv
    c.set_board_live(True)
    c.show_board(False)
    assert not c.board.isVisible() and c.main.none_action.isChecked()
    assert tv.preview.veil.isVisible() and tv.toolTip() == HIDDEN_TIP
    tv.set_hover(True)
    assert not tv.preview.hover.isVisibleTo(tv.preview), "the veil says why; no switch to offer"
    # Grayed under "Off", not a red "Hidden".
    assert tv.preview.veil.text() == "Off" and tv.preview.grayed.isEnabled()
    assert not tv.property("active")
    assert not c.main.logo_action.isEnabled() and not c.main.live_action.isEnabled()
    was_live = c.board_live
    tv.click()
    assert not c.board.isVisible() and c.board_live == was_live, "the veil takes no click"
    assert tv.property("flash") is None, "nothing to flash for"
    # The menu's Automatic, as the scorer clicks it.
    c.main.display_group.actions()[0].trigger()
    assert c.board.isVisible() and not c.main.none_action.isChecked()
    # What was behind the veil, not the logo.
    assert c.board_live and tv.is_live(), "back to the race it was showing"
    assert not tv.preview.veil.isVisible() and tv.property("active") and tv.toolTip() == ""
    assert not tv.preview.grayed.isEnabled(), "the picture in color again"
    assert c.main.logo_action.isEnabled() and c.main.live_action.isEnabled()


def test_logo_and_live_are_grayed_while_the_board_is_hidden(make_app, tmp_path):
    """Picking Logo or Live never shows a hidden board; only a display
    picked in the list does."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.show()
    c.place_board()
    c.show_board(False)
    assert not c.main.live_action.isEnabled() and not c.main.logo_action.isEnabled()
    c.main.live_action.trigger()
    assert not c.board.isVisible() and not c.board_live
    assert c.main.none_action.isChecked()
    c.show_board(True)
    assert c.main.live_action.isEnabled() and c.main.logo_action.isEnabled()


def test_a_disconnected_scoreboard_display_shows_as_hidden(make_app, tmp_path, quiet):
    from madtracker.ui.tv import HIDDEN_TIP

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.show()
    c.place_board()
    c.board.hide()
    c._list_screens([])
    assert c.main.tv.preview.veil.isVisible() and c.main.tv.toolTip() == HIDDEN_TIP
    assert not c.main.live_action.isEnabled()


def test_the_disconnect_box_names_the_scoreboard_menu(make_app, tmp_path, quiet):
    """There is no Display submenu: the list is the menu itself."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    screen = QApplication.primaryScreen()
    c.board.show()
    c.board_screen = screen.name()
    c._screen_removed(screen)
    assert not [q for q in quiet if q.startswith("warn:")], "never inside the signal"
    QApplication.processEvents()
    (box,) = [q for q in quiet if q.startswith("warn:")]
    assert box.endswith("Reconnect it, or choose another on the Scoreboard menu.")


def test_a_fast_unplug_replug_and_unplug_posts_one_disconnect_box(make_app, tmp_path, quiet):
    """Both removals land before the box opens; the scorer dismisses it once."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    screen = QApplication.primaryScreen()
    for _ in range(2):
        c.board.show()
        c.board_screen = screen.name()
        c._screen_removed(screen)
    QApplication.processEvents()
    assert len([q for q in quiet if q.startswith("warn:")]) == 1


def test_a_display_coming_back_takes_the_board_and_closes_the_box(
    make_app, tmp_path, quiet, monkeypatch
):
    """The other half of a disconnect: the display plugged back in takes the
    board again, the disconnect box closes, and the next loss is told afresh."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    screen = QApplication.primaryScreen()
    c.board.show()
    c.board_screen = screen.name()
    c._screen_removed(screen)
    QApplication.processEvents()
    assert c._lost_display and c.board_screen is None
    placed, closed = [], []
    # The offscreen platform has one nameless primary screen, which the
    # chooser never takes for the TV; here it is the TV plugged back in.
    from madtracker import displays

    monkeypatch.setattr(displays, "choose_scoreboard_screen", lambda infos, _name: infos[0])
    monkeypatch.setattr(c, "place_board", lambda *a, **k: placed.append(True))
    monkeypatch.setattr(c, "_close_lost_display_box", lambda: closed.append(True))
    c._screen_added(screen)
    assert placed == [True] and closed == [True]
    assert not c._lost_display and c.board_wanted


def test_opening_another_event_while_live_puts_the_logo_up(make_app, tmp_path):
    """The TV never shows a race the scorer did not choose."""
    from madtracker.control.demo import OPENING_NIGHT

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.set_board_live(True)
    tonight = c.event.event_id
    c.open_event(tonight)
    assert c.board_live, "the same event again changes nothing"
    (opening,) = [e for e in c.store.events() if e.name == OPENING_NIGHT]
    c.open_event(opening.event_id)
    assert c.live is not None, "the event has a race to show"
    assert not c.board_live and not c.main.tv.is_live() and c.main.logo_action.isChecked()
    assert c.board.page_kind() == "logo"


def test_refusals_show_in_the_red_line_and_a_dq_asks_first(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    eid = c.live.roster.ids[0]
    assert c.click(eid)
    assert not c.live.act(eid, "dns").ok
    assert not c.rider_action(eid, "dns")
    assert "did not finish" in c.main.surface.problem.text()
    assert c.rider_action(eid, "dq")
    assert quiet[-1].startswith("ask:Disqualify")
    assert c.main.surface.problem.text() == ""
    assert c.live.standings().by_entrant(eid).status == "DQ"


def test_leaving_a_race_mid_scoring_asks_and_cancel_stays(make_app, tmp_path, monkeypatch):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    first, other = c.races[0].race_id, c.races[2].race_id
    c.set_board_live(True)
    assert c.click(c.live.roster.ids[0])
    assert c.live.in_progress
    live, header, kind = c.live, c.board.top_bar.header, c.board.page_kind()
    asked: list[str] = []
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or False)
    c.main.program.select(other)
    assert asked == [f"{c.races[0].name} is still being scored. Switch to {c.races[2].name}?"]
    assert c.live is live and c.live.race_id == first
    assert c.main.showing() == "surface"
    assert c.main.program.current_race_id() == first
    assert c.board.top_bar.header == header and c.board.page_kind() == kind
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or True)
    c.main.program.select(other)
    assert c.live.race_id == other and c.main.program.current_race_id() == other
    assert c.board.top_bar.header != header


def test_leaving_a_provisional_race_asks_nothing(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    for eid in list(c.live.roster.ids):
        assert c.click(eid)
    assert c.live.state == "provisional" and not c.live.in_progress
    before = list(quiet)
    c.main.program.select(c.races[2].race_id)
    assert c.live.race_id == c.races[2].race_id
    assert quiet == before


def test_done_mid_race_returns_to_the_race_being_scored(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    assert c.click(c.live.roster.ids[0])
    c.open_setup()
    assert c.main.showing() == "setup" and not quiet
    c.close_setup()
    assert c.live.race_id == c.races[2].race_id and c.main.showing() == "surface"
    assert not quiet


@pytest.mark.parametrize("answer", [True, False])
@pytest.mark.parametrize(
    "key, title, status", [("dnf", "Did Not Finish", "DNF"), ("dns", "Did Not Start", "DNS")]
)
def test_dnf_and_dns_ask_first_with_the_bib(
    make_app, tmp_path, monkeypatch, key, title, status, answer
):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    eid = c.live.roster.ids[0]
    asked = []
    monkeypatch.setattr(
        icons, "ask", lambda parent, t, text, verb: asked.append((t, text, verb)) or answer
    )
    who = c.live.label(eid)
    undo_before = c.live.undo_text()
    assert who.split()[0] == f"#{c.live.roster.get(eid).bibs[0]}"
    assert c.rider_action(eid, key) is answer
    assert asked == [(title, f"Mark {who} {title}?", title)]
    got = c.live.standings().by_entrant(eid)
    if answer:
        assert got.status == status
    else:
        # A dismissed question records nothing.
        assert got is None or got.status != status
        assert c.live.undo_text() == undo_before


@pytest.mark.parametrize("answer", [True, False])
def test_withdrawn_asks_first_with_its_own_verb(make_app, tmp_path, monkeypatch, answer):
    """The question names the mark and the button the deed: "Mark #7 ...
    Withdrawn?" with Withdraw, Cancel the default as for every question."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    eid = c.live.roster.ids[0]
    asked = []
    monkeypatch.setattr(
        icons, "ask", lambda parent, t, text, verb: asked.append((t, text, verb)) or answer
    )
    who = c.live.label(eid)
    undo_before = c.live.undo_text()
    assert c.rider_action(eid, "withdrawn") is answer
    assert asked == [("Withdrawn", f"Mark {who} Withdrawn?", "Withdraw")]
    if answer:
        assert c.live.standings().by_entrant(eid).withdrawn
        assert c.live.undo_text() == f"Undo: {who} marked Withdrawn"
    else:
        assert not c.live.standings().by_entrant(eid).withdrawn
        assert c.live.undo_text() == undo_before


def test_dnf_dns_and_disqualify_name_the_rider_the_same_way(make_app, tmp_path, monkeypatch):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    eid = c.live.roster.ids[0]
    e = c.live.roster.get(eid)
    asked = []
    monkeypatch.setattr(icons, "ask", lambda parent, t, text, verb: asked.append(text) or False)
    for key in ("dnf", "dns", "dq"):
        c.rider_action(eid, key)
    named = who(e.bibs[0], e.names[0])
    assert named.startswith("#")
    assert asked == [
        f"Mark {named} Did Not Finish?",
        f"Mark {named} Did Not Start?",
        f"Disqualify {named}?",
    ]


def test_a_badged_cards_menu_moves_the_badge_through_the_ui(make_app, tmp_path, quiet):
    """A sprint's badges move from the card's ⋯: the
    menu opens through the card's strip, a pick goes out as the card's
    action signal, and the controller moves the staged order."""
    from madtracker.control import race as rc

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)  # 6 Mile Points
    assert c.live.task().kind == "sprint"
    first, second = [w.card.entrant_id for w in c.main.surface.cards.cards[:2]]
    assert c.click(first) and c.click(second)
    card = next(w for w in c.main.surface.cards.cards if w.card.entrant_id == second)
    assert [k for k, _ in card.menu_actions[:2]] == ["move_up", "tie_above"]
    quiet.clear()
    card.dots.click()
    assert quiet == ["menu"]
    card.action.emit(second, "move_up")
    badges = {w.card.entrant_id: w.card.badge for w in c.main.surface.cards.cards}
    assert (badges[second], badges[first]) == (1, 2)
    assert c.main.undo.text() == rc.undo_moved(c.live.label(second), "up")
    assert c.main.surface.problem.text() == ""
    # Nowhere further up: the red line says so.
    assert not c.rider_action(second, "move_up")
    assert c.main.surface.problem.text() == rc.NO_MOVE
    assert c.undo()
    badges = {w.card.entrant_id: w.card.badge for w in c.main.surface.cards.cards}
    assert (badges[first], badges[second]) == (1, 2)


def test_a_staged_chase_row_moves_through_row_action(make_app, tmp_path, quiet):
    """A finish order being built is corrected in the result list, from
    either end, through the row's ⋯."""
    from madtracker.control import race as rc

    c = make_app(demo=True, data_dir=tmp_path / "data")  # the first race is the chase
    assert c.live.task().kind == "order"
    ids = [w.card.entrant_id for w in c.main.surface.cards.cards]
    first, second, back, last = ids[0], ids[1], ids[-2], ids[-1]
    assert c.click(first) and c.click(second)
    table = c.main.surface.table
    assert [k for k, _ in table.screen.rows[1].actions] == [
        "move_up", "tie_above", "lap_gained", "lap_lost", "dq"
    ]  # fmt: skip
    quiet.clear()
    assert table.open_row_menu(1)
    assert quiet == ["menu"]
    assert c.row_action(second, "move_up")
    assert [r.entrant_id for r in table.screen.rows[:2]] == [second, first]
    assert c.main.undo.text() == rc.undo_moved(c.live.label(second), "up")
    # From the back: Place Last twice, then the last rider moves up a place.
    assert c.rider_action(last, "place_last") and c.rider_action(back, "place_last")
    rows = table.screen.rows
    assert [(r.entrant_id, r.place_text) for r in rows[-2:]] == [(back, "9"), (last, "10")]
    assert [k for k, _ in rows[-1].actions] == ["move_up", "lap_gained", "lap_lost", "dq"]
    assert c.row_action(last, "move_up")
    rows = table.screen.rows
    assert [(r.entrant_id, r.place_text) for r in rows[-2:]] == [(last, "9"), (back, "10")]
    assert not c.row_action(last, "move_up")
    assert c.main.surface.problem.text() == rc.NO_MOVE
    assert c.undo()
    rows = table.screen.rows
    assert [(r.entrant_id, r.place_text) for r in rows[-2:]] == [(back, "9"), (last, "10")]


def test_laps_are_routine_and_never_ask(make_app, tmp_path, quiet):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    eid = c.live.roster.ids[0]
    quiet.clear()
    c.rider_action(eid, "lap_gained")
    c.rider_action(eid, "lap_lost")
    assert not any(q.startswith("ask:") for q in quiet)


def test_file_riders_edits_a_rider_and_the_cards_show_the_new_name(make_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from madtracker.ui import setup as su

    c = make_app(demo=True, data_dir=tmp_path / "data")
    rider_id = c.main.surface.cards.cards[0].card.entrant_id
    seen: list[su.RidersDialog] = []

    def rename(form):
        form.first.setText("Zephyrine")
        return int(QDialog.DialogCode.Accepted if form.save() else QDialog.DialogCode.Rejected)

    def run(dialog):
        seen.append(dialog)
        dialog.select_rider(rider_id)
        dialog.edit_selected()
        return int(QDialog.DialogCode.Rejected)

    monkeypatch.setattr(su.RiderForm, "exec", rename)
    monkeypatch.setattr(su.RidersDialog, "exec", run)
    c.main.riders_action.trigger()
    assert seen and seen[0].windowTitle() == "Edit Riders"
    card = next(k for k in c.main.surface.cards.cards if k.card.entrant_id == rider_id)
    assert card.card.entry.names[0].startswith("Zephyrine")
    # The setup screen, when it is up, rereads the roster too.
    c.open_setup()
    c.main.riders_action.trigger()
    names = [
        c.main.setup.roster.item(r, su.FIRST).text() for r in range(c.main.setup.roster.rowCount())
    ]
    assert any(n.startswith("Zephyrine") for n in names)


def test_file_riders_works_with_no_event_open(make_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from madtracker.ui import setup as su

    c = make_app(data_dir=tmp_path / "fresh")
    assert c.store is not None and c.event is None
    seen: list[str] = []
    monkeypatch.setattr(
        su.RidersDialog,
        "exec",
        lambda d: seen.append(d.windowTitle()) or int(QDialog.DialogCode.Rejected),
    )
    c.main.riders_action.trigger()
    assert seen == ["Edit Riders"]


def _shown(c):
    """The window on screen and laid out, so a press goes through Qt's own double-click logic."""
    c.main.show()
    c.main.resize(1600, 1000)
    # Several passes, as mockup._grab takes: the grid's refit after the
    # columns settle posts a layout request that is handled a pass later,
    # and a spot mapped before it lands on the wrong card.
    for _ in range(4):
        QApplication.processEvents()
    return c.main.windowHandle()


def _placed(c) -> int:
    """Riders placed so far in the demo chase, where each click stages one."""
    return sum(len(group) for group in c.live.staged())


def test_a_double_click_on_a_card_places_one_rider(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    window = _shown(c)
    grid = c.main.surface.cards
    # Each click rebuilds the grid. Between a real double-click's two
    # presses the event loop runs and the next rider's card moves under
    # the pointer; QTest sends both presses at once, so the test lays the
    # new grid out as soon as the first click lands.
    grid.pressed_entrant.connect(lambda _: (QApplication.sendPostedEvents(), grid.grid.activate()))
    first = grid.cards[0]
    placed = first.card.entrant_id
    spot = first.mapTo(c.main, QPoint(style.MD, first.height() // 2))
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot)
    QApplication.processEvents()
    assert _placed(c) == 1
    under = grid.body.childAt(grid.body.mapFrom(c.main, spot))
    assert under is grid.card_for(placed) and under.card.done, (
        "the placed rider's done card holds the spot, so the second press does nothing"
    )


def test_two_quick_clicks_on_two_cards_both_count(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    window = _shown(c)
    grid = c.main.surface.cards
    # The first card, then the last of the field that is left: far apart
    # on screen, so never a double-click, and both count.
    for pick in (0, -1):
        card = grid.cards[pick]
        spot = card.mapTo(c.main, QPoint(style.MD, card.height() // 2))
        QTest.mousePress(
            window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot, 75
        )
        QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot, 75
        )
        QApplication.processEvents()
    assert _placed(c) == 2


def test_a_double_click_on_undo_undoes_one_entry_and_space_repeats_nothing(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    window = _shown(c)
    for eid in list(c.live.roster.ids)[:3]:
        assert c.click(eid)
    undo = c.main.undo
    spot = undo.mapTo(c.main, undo.rect().center())
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot)
    QApplication.processEvents()
    assert _placed(c) == 2
    QTest.mouseClick(undo, Qt.MouseButton.LeftButton)
    assert _placed(c) == 1
    # The scorer's next key goes wherever focus is; Undo and the preview
    # must never hold it, or Space would undo again with no redo.
    for key in (Qt.Key.Key_Space, Qt.Key.Key_Return):
        QTest.keyClick(QApplication.focusWidget() or c.main, key)
    assert _placed(c) == 1
    tv = c.main.tv
    QTest.mouseClick(tv, Qt.MouseButton.LeftButton)
    QTest.keyClick(QApplication.focusWidget() or c.main, Qt.Key.Key_Space)
    assert c.board_live
    assert QApplication.focusWidget() not in (undo, tv)


def _double_click(window, c, widget) -> None:
    """Two real press and release pairs on one spot: Qt makes the second a double-click."""
    spot = widget.mapTo(c.main, widget.rect().center())
    # The first press well after any earlier test's click (QTest keeps one
    # clock), the second within the double-click interval.
    for delay in (1000, 10):
        QTest.mousePress(
            window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot, delay
        )
        QApplication.processEvents()
        QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot, 10
        )
        QApplication.processEvents()


def test_a_double_click_on_mark_final_marks_it_final_once(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    window = _shown(c)
    for eid in list(c.live.roster.ids):
        c.click(eid)
    QApplication.processEvents()
    assert c.live.state == "provisional"
    surface = c.main.surface
    # Reopen takes Mark final's spot, so a second press must not reopen it.
    _double_click(window, c, surface.final_button)
    assert c.live.state == "final"
    moves = [(s.from_state, s.to_state) for s in c.store.state_changes(c.live.race_id)]
    assert moves[-1] == ("provisional", "final") and ("final", "provisional") not in moves
    _double_click(window, c, surface.reopen_button)
    assert c.live.state == "provisional"
    assert c.store.state_changes(c.live.race_id)[-1].to_state == "provisional"


def test_a_double_click_on_a_cards_lap_button_gains_one_lap(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    window = _shown(c)
    points = next(r.race_id for r in c.races if r.format == "points")
    c.select_race(points)
    QApplication.processEvents()
    before = len(c.store.live_actions(points))
    _double_click(window, c, c.main.surface.cards.cards[0].lap_up)
    assert len(c.store.live_actions(points)) == before + 1


def test_two_quick_clicks_on_the_preview_both_count(make_app, tmp_path):
    """A switch flipped and flipped back is what the scorer meant: the
    preview takes a double-click as two clicks."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    window = _shown(c)
    tv = c.main.tv
    spot = tv.mapTo(c.main, tv.rect().center())
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot)
    QApplication.processEvents()
    assert not c.board_live and not tv.is_live(), "Live, then back to Logo"
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot)
    QTest.mouseClick(tv, Qt.MouseButton.LeftButton)
    assert c.board_live and tv.is_live()


@pytest.mark.skipif(sys.platform == "win32", reason="chmod does not make a file read-only")
def test_a_read_only_data_file_opens_to_look_at_a_past_night(make_app, tmp_path, quiet):
    import os

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root writes into a read-only file")
    data = tmp_path / "data"
    first = make_app(data_dir=data)
    first.new_event("Race Night 7", "2026-09-05")
    first.store.add_race(first.event.event_id, "Chase", "chase")
    path = first.store.path
    first.close()
    path.chmod(0o444)
    try:
        c = make_app(data_dir=data)
        assert c.store.read_only
        assert [m.name for m in c.store.events()] == ["Race Night 7"]
        c.open_event(c.store.events()[0].event_id)
        c.select_race(c.races[0].race_id)
        assert c.live is not None
        c.close()
    finally:
        path.chmod(0o644)


def test_a_lock_qt_calls_held_is_dropped_when_its_process_is_gone(make_app, tmp_path, monkeypatch):
    """Qt's staleness rule differs by platform; the program asks the OS about the holder itself."""
    from PySide6.QtCore import QLockFile

    from madtracker.control import backups

    data = tmp_path / "data"
    data.mkdir()
    # What QLockFile writes: pid, application name, host name (left empty here).
    backups.lock_path(data / "madtracker.sqlite").write_text("424242\npython\n\n")
    # Whatever Qt decides, the process named in the file is gone.
    monkeypatch.setattr(QLockFile, "isApparentlyStale", lambda self: False, raising=False)
    monkeypatch.setattr(backups, "pid_alive", lambda pid: False)
    c = make_app(data_dir=data)
    assert c.store is not None
    c.close()


# ----- the program's right-click menus (design section 5) --------------------------


def test_a_long_race_name_wraps_onto_a_taller_row(make_app, tmp_path):
    """The program wraps a race name rather than cutting it; a one-line race is
    program.ROW_H tall on every platform, whatever its type measures in pixels."""
    from madtracker.ui import program

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.store.update_race(c.races[0].race_id, name="SemiProA Saturday Night Scratch Race Final")
    c._after_setup_change()
    c.main.show()
    QApplication.processEvents()
    lst = c.main.program.list
    assert lst.visualItemRect(lst.item(1)).height() == program.ROW_H
    assert lst.visualItemRect(lst.item(0)).height() > program.ROW_H


def test_wrapped_race_rows_never_overlap_once_the_list_scrolls(qtbot):
    """Rows measured before the scroll bar appears never overlap the next row."""
    from madtracker.ui.program import ProgramPane, ProgramRow
    from madtracker.ui.style import stylesheet

    pane = ProgramPane()
    qtbot.addWidget(pane)
    pane.setStyleSheet(stylesheet(12))
    # Shorter than ten rows of program.ROW_H, so the list must scroll.
    pane.resize(240, 400)
    pane.show()
    QApplication.processEvents()
    names = ["Women Category 1/2/3 Scratch Race Final", "Elimination", "Points"]
    names += ["Masters 50+ Men Cat 4/5 Unknown Distance Points Race", "Handicap", "Win-and-Out"]
    names += ["Tempo Race for the Juniors Under 17", "Keirin", "Scratch", "Miss and Out"]
    rows = [ProgramRow(i + 1, n, "Group A", "provisional") for i, n in enumerate(names)]
    pane.set_has_event(True)
    pane.set_races(rows, 1)
    QApplication.processEvents()
    QApplication.processEvents()
    lst = pane.list
    assert lst.verticalScrollBar().isVisible()
    rects = [lst.visualItemRect(lst.item(i)) for i in range(lst.count())]
    for above, below in zip(rects, rects[1:], strict=False):
        assert below.top() > above.bottom(), "a wrapped row runs into the next"


def test_marking_a_race_final_keeps_a_scrolled_program_where_it_was(qtbot):
    """A changed word on a row (Final) never sends a scrolled list back to the top."""
    from madtracker.ui.program import ProgramPane, ProgramRow
    from madtracker.ui.style import stylesheet

    pane = ProgramPane()
    qtbot.addWidget(pane)
    pane.setStyleSheet(stylesheet(12))
    pane.resize(240, 400)
    pane.show()
    QApplication.processEvents()
    rows = [ProgramRow(i + 1, f"Race {i + 1}", "Group A", "provisional") for i in range(20)]
    pane.set_has_event(True)
    pane.set_races(rows, 20)
    QApplication.processEvents()
    bar = pane.list.verticalScrollBar()
    assert bar.isVisible()
    bar.setValue(bar.maximum())
    QApplication.processEvents()
    at = bar.value()
    assert at > 0
    # The last race marked final: the same races, one word changed.
    rows[-1] = ProgramRow(20, "Race 20", "Group A", "final")
    pane.set_races(rows, 20)
    QApplication.processEvents()
    assert bar.value() == at and pane.list.currentRow() == 19
    assert pane.row_texts()[-1] == ("Race 20", "Group A", "Final")
    # A race added to the end: the list is built again, where it was.
    rows.append(ProgramRow(21, "Race 21", "Group A", "setup"))
    pane.set_races(rows, 20)
    QApplication.processEvents()
    assert bar.value() == at and pane.list.currentRow() == 19


def test_edit_event_stays_up_through_settings_and_score_returns_to_the_race(
    make_app, tmp_path, monkeypatch
):
    """Only Score leaves Edit event; Undo waits, and the race is returned to."""
    import madtracker.ui.settings as settings_ui

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.open_setup()
    assert not c.main.undo.isEnabled(), "Undo would change a race the screen hides"
    monkeypatch.setattr(settings_ui, "open_settings", lambda store, d, parent: True)
    c.edit_settings()
    assert c.main.showing() == "setup" and c.main.program.setup_open()
    c.close_setup()
    assert c.main.showing() == "surface" and c.live is not None
    # Picking a race from the program while setup is open still goes to it.
    c.open_setup()
    c.select_race(c.races[1].race_id)
    assert c.main.showing() == "surface"


def test_remove_team_in_edit_race_clears_the_staged_clicks(make_app, tmp_path, monkeypatch):
    """The teams written again after a Remove Team take freed ids: clicks kept by id
    would put teams nobody clicked in the staged order and leave Undo naming the old ones."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    store = c.store
    src = next(r for r in c.races if r.format == "madison")
    c.open_setup()
    setup = c.main.setup
    copy = setup.race_dialog(None, copy_of=src.race_id)
    copy.exec = lambda: (copy.save(), copy.result())[1]
    race_id = setup.duplicate_race(src.race_id, dialog=copy)
    c.close_setup()
    c.select_race(race_id)
    for team in store.teams(race_id)[:3]:
        assert c.click(team.team_id)
    assert c.live.undo_text().startswith("Undo:")
    assert c._program_state(store.race(race_id)) == "running"
    c.open_setup()
    edit = setup.race_dialog(race_id)
    edit.teams_table.selectRow(0)
    assert edit.remove_team()
    edit.exec = lambda: (edit.save(), edit.result())[1]
    monkeypatch.setattr(setup, "race_dialog", lambda _rid: edit)
    assert setup.edit_race(race_id)
    c.close_setup()
    c.select_race(race_id)
    assert c.live.race_id == race_id
    assert c.live.staged() == []
    assert c.live.undo_text() == "Nothing to Undo"
    assert c._program_state(store.race(race_id)) == "setup"


# ----- a race undone to its start list is set up again -----------------------
#
# Design section 6: an entry Undo took back is no entry. Each test scores a
# race, undoes it back to its start list, changes what the dialog then
# offers (the field, the teams, the count), and scores it to the end. A
# twin, duplicated from the edited race and scored the same way, has no
# dead rows: the standings, the board feed, and the sheets' rows of the two
# must agree, so nothing of the first run reaches the result.


def _undo_to_start(c):
    for _ in range(200):
        if not c.main.undo.isEnabled():
            break
        assert c.undo(), c.main.surface.problem.text()
    assert c.main.surface.state.text() == "Start list"
    assert c.live.rows() == [] and c.live.staged() == [] and c.live.state == "setup"
    assert c.board.layout_name() == "pre_race"
    assert c.store.last_action(c.live.race_id) is not None, "the undone rows are kept"


def _edit_race(c, race_id, change):
    c.open_setup()
    setup = c.main.setup
    edit = setup.race_dialog(race_id)
    assert not edit.scored and all(w.isEnabled() for w in edit.locked_widgets())
    assert not edit.locked_note.isVisibleTo(edit)
    change(edit)
    edit.exec = lambda: (edit.save(), edit.result())[1]
    # Edit... opens this dialog; the screen's own opener is back afterwards.
    setup.race_dialog = lambda _rid: edit
    try:
        assert setup.edit_race(race_id), edit.error.text()
    finally:
        del setup.race_dialog
    c.close_setup()
    c.select_race(race_id)
    assert c.live.race_id == race_id and c.main.showing() == "surface"


def _twin_of(c, race_id):
    """A new race duplicated from ``race_id`` as it now stands, with no log."""
    c.open_setup()
    setup = c.main.setup
    copy = setup.race_dialog(None, copy_of=race_id)
    copy.exec = lambda: (copy.save(), copy.result())[1]
    twin = setup.duplicate_race(race_id, dialog=copy)
    c.close_setup()
    assert twin is not None and c.store.last_action(twin) is None
    return twin


def _play(live, script):
    for step in script:
        op, token, *rest = step
        eid = live.roster.resolve(token) if token is not None else None
        if op == "click":
            out = live.click(eid)
        elif op == "record":
            out = live.record_sprint()
        elif op == "act":
            out = live.act(eid, rest[0])
        elif op == "end":
            out = live.end_race()
        elif op == "final":
            out = live.mark_final()
        else:
            raise ValueError(op)
        assert out.ok, (step, out.message)


def _play_in_app(c, script):
    """The same script through the app's own entry points, the board live."""
    for step in script:
        op, token, *rest = step
        eid = c.live.roster.resolve(token) if token is not None else None
        if op == "click":
            done = c.click(eid)
        elif op == "record":
            done = c.record_sprint()
        elif op == "act":
            done = c.rider_action(eid, rest[0])
        elif op == "end":
            done = c.race_action("end_race")
        elif op == "final":
            done = c.mark_final()
        else:
            raise ValueError(op)
        assert done, (step, c.main.surface.problem.text())


def _result_shape(store, race_id):
    from madtracker.export.summary import build_summary

    s = build_summary(store, store.race(race_id))
    rows = [
        (
            r.place,
            r.status,
            tuple(x.name for x in r.riders),
            r.team,
            r.sprint_points,
            r.laps_gained,
            r.laps_lost,
            r.adjust_points,
            r.total_points,
            r.note,
        )
        for r in s.rows
    ]
    return (s.kind, s.rules_line, s.sprint_count, s.sprints_run, s.ended_after, s.shortened, rows)


def _board_shape(view):
    from dataclasses import asdict

    from madtracker.control import board_feed

    layout, payload = board_feed.board_for(view)
    shape = asdict(payload)
    shape["header"].update(race_id=0, title="")
    return layout, shape


def _same_as_twin(c, race_id, script):
    from madtracker.control.race import LiveRace

    twin = _twin_of(c, race_id)
    _play(LiveRace(c.store, twin), script)
    c.select_race(race_id)
    assert c.live.race_id == race_id
    assert _result_shape(c.store, race_id) == _result_shape(c.store, twin)
    assert _board_shape(c.live.view()) == _board_shape(LiveRace(c.store, twin).view())
    assert c.main.surface.state.text() == "Final"
    assert c.board.layout_name() == _board_shape(c.live.view())[0]
    live_ids = {r.entrant_id for r in c.live.standings().rows}
    assert live_ids == set(c.live.roster.ids), "every row is a current entrant"
    assert len(c.store.actions(race_id)) > len(c.live.rows()), "the dead rows are still there"


def _names_in_csv(c, tmp_path):
    """The riders the USAC CSV lists, as "First Last"."""
    import csv

    path = c.export_csv(tmp_path / "usac.csv")
    assert path is not None
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {f"{r['Rider First Name']} {r['Rider Last Name']}" for r in rows}


def _rider_named(c, first, last):
    return next(
        x.rider_id for x in c.store.riders() if (x.first_name, x.last_name) == (first, last)
    )


def test_a_scratch_race_undone_to_its_start_takes_a_new_field(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.set_board_live(True)
    race_id = c.races[0].race_id
    c.select_race(race_id)
    out = c.live.roster.resolve("45")
    out_name = c.live.name(out)
    _play_in_app(c, [("click", "7"), ("click", "12"), ("act", "33", "dnf")])
    assert c.main.surface.state.text() == "Racing"
    _undo_to_start(c)
    in_ = _rider_named(c, "Marcus", "Delgado")

    def change(edit):
        edit.set_in_field(out, False)
        edit.set_in_field(in_, True)

    _edit_race(c, race_id, change)
    assert out not in c.live.roster.ids and in_ in c.live.roster.ids
    assert c.main.surface.state.text() == "Start list" and len(c.main.surface.cards.cards) == 10
    script = [("click", b) for b in ("7", "12", "4", "9", "19", "22", "33", "38", "51", "3")]
    _play_in_app(c, script)
    assert c.main.surface.state.text() == "Provisional"
    assert c.mark_final()
    _same_as_twin(c, race_id, [*script, ("final", None)])
    csv = _names_in_csv(c, tmp_path)
    assert "Marcus Delgado" in csv and out_name not in csv
    assert c.export_pdf(tmp_path / "one.pdf", race_id=race_id) is not None


def test_an_elimination_undone_to_its_start_loses_a_rider(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.set_board_live(True)
    race_id = c.races[1].race_id
    c.select_race(race_id)
    out = c.live.roster.resolve("3")
    out_name = c.live.name(out)
    _play_in_app(c, [("click", "3"), ("click", "5"), ("act", "8", "dnf")])
    assert c.board.layout_name() == "elimination"
    _undo_to_start(c)
    _edit_race(c, race_id, lambda edit: edit.set_in_field(out, False))
    assert len(c.main.surface.cards.cards) == 11
    outs = [("click", b) for b in ("5", "8", "11", "14", "17", "21", "24", "27", "31")]
    # Two survivors ride the final sprint; the winner's click decides both places.
    script = [*outs, ("click", "42")]
    _play_in_app(c, script)
    assert c.main.surface.state.text() == "Provisional"
    assert c.mark_final()
    _same_as_twin(c, race_id, [*script, ("final", None)])
    assert out_name not in _names_in_csv(c, tmp_path)


def test_a_points_race_ended_and_undone_to_its_start_takes_a_new_count(make_app, tmp_path):
    """Every kind of entry a Points Race takes, then End Race, all undone;
    another race is scored in between; the count and the field change."""
    from madtracker.control.race import PENALTY

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.set_board_live(True)
    race_id = c.races[2].race_id
    c.select_race(race_id)
    out = c.live.roster.resolve("51")
    out_name = c.live.name(out)
    _play_in_app(
        c,
        [
            ("click", "7"),
            ("click", "12"),
            ("click", "4"),
            ("click", "9"),
            ("record", None),
            ("act", "33", "lap_gained"),
            ("act", "7", f"{PENALTY}5"),
            ("act", "38", "withdrawn"),
            ("act", "45", "dns"),
            ("end", None),
        ],
    )
    assert c.main.surface.state.text() == "Provisional"
    assert "Race ended" in c.main.surface.task.text()
    _undo_to_start(c)
    # Another race scored in between leaves this one at its start list.
    c.select_race(c.races[0].race_id)
    assert c.click(c.live.roster.resolve("7"))
    c.select_race(race_id)
    assert c.main.surface.state.text() == "Start list" and not c.main.undo.isEnabled()
    in_ = _rider_named(c, "Marcus", "Delgado")

    def change(edit):
        edit.number.setValue(2)
        edit.set_in_field(out, False)
        edit.set_in_field(in_, True)

    _edit_race(c, race_id, change)
    assert c.live.rules.sprint_count == 2 and len(c.live.roster.ids) == 10
    script = [
        ("click", "7"),
        ("click", "12"),
        ("click", "4"),
        ("click", "9"),
        ("record", None),
        *[("click", b) for b in ("3", "7", "12", "4", "9", "19", "22", "33", "38", "45")],
    ]
    _play_in_app(c, script)
    assert c.main.surface.state.text() == "Provisional"
    assert c.mark_final()
    _same_as_twin(c, race_id, [*script, ("final", None)])
    shape = _result_shape(c.store, race_id)
    assert shape[2] == 2 and shape[4] is None, "two sprints, not ended"
    assert all(row[7] == 0 for row in shape[6]), "no penalty from the first run"
    assert all(row[1] is None for row in shape[6]), "no status from the first run"
    csv = _names_in_csv(c, tmp_path)
    assert "Marcus Delgado" in csv and out_name not in csv


def test_a_madison_undone_to_its_start_takes_new_teams(make_app, tmp_path):
    """A Madison scored, undone to its start list, and a
    team added; here one is also removed and one made over."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.set_board_live(True)
    race_id = c.races[3].race_id
    c.select_race(race_id)
    by_bib = {e.bib: e.rider_id for e in c.store.entries(c.event.event_id)}
    _play_in_app(
        c,
        [
            ("click", "Blue"),
            ("click", "Red"),
            ("click", "Orange"),
            ("click", "Yellow"),
            ("record", None),
            ("act", "Black", "lap_gained"),
        ],
    )
    assert c.board.layout_name() == "madison"
    _undo_to_start(c)
    yellow = c.live.roster.resolve("Yellow")

    def change(edit):
        assert edit.add_team("Green", [by_bib[17], by_bib[42]]), edit.error.text()
        edit.teams_table.selectRow(3)
        assert edit.remove_team(), edit.error.text()
        assert [t[0] for t in edit.teams] == ["Blue", "Red", "Orange", "Black", "Green"]
        assert edit.edit_team(3, members=[by_bib[14], by_bib[11]]), edit.error.text()

    _edit_race(c, race_id, change)
    teams = {t.name: t for t in c.store.teams(race_id)}
    assert set(teams) == {"Blue", "Red", "Orange", "Black", "Green"}
    assert set(teams["Black"].members) == {by_bib[14], by_bib[11]}
    assert yellow not in c.live.roster.ids
    assert len(c.main.surface.cards.cards) == 5
    assert c.live.undo_text() == "Nothing to Undo"
    script = [
        ("click", "Green"),
        ("click", "Blue"),
        ("click", "Red"),
        ("click", "Orange"),
        ("record", None),
        ("click", "Black"),
        ("click", "Green"),
        ("click", "Blue"),
        ("click", "Red"),
        ("record", None),
        ("act", "Black", "lap_gained"),
        ("click", "Blue"),
        ("click", "Black"),
        ("click", "Green"),
        ("click", "Red"),
        ("record", None),
        ("click", "Black"),
        ("click", "Green"),
        ("click", "Blue"),
        ("click", "Red"),
        ("click", "Orange"),
    ]
    _play_in_app(c, script)
    assert c.main.surface.state.text() == "Provisional"
    assert c.mark_final()
    _same_as_twin(c, race_id, [*script, ("final", None)])
    shape = _result_shape(c.store, race_id)
    assert shape[6][0][3] == "Black"
    assert "Dana Brooks" in _names_in_csv(c, tmp_path)


def test_a_program_row_lights_under_the_pointer(make_app, tmp_path, quiet):
    """The races light under the pointer as every other control does:
    the list tracks the mouse and the delegate tints
    the hovered row, the selected row keeping its own fill."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    c = make_app(demo=True, data_dir=tmp_path / "data")
    lst = c.main.program.list
    assert lst.hasMouseTracking()
    delegate = lst.itemDelegate()

    def pixel(state, row=1):
        pix = QPixmap(300, 60)
        pix.fill(Qt.GlobalColor.white)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 300, 60)
        option.state = state
        p = QPainter(pix)
        delegate.paint(p, option, lst.model().index(row, 0))
        p.end()
        return pix.toImage().pixelColor(290, 3).name()

    assert pixel(QStyle.StateFlag.State_MouseOver) == style.ACCENT_TINT
    assert pixel(QStyle.StateFlag.State_MouseOver, row=2) == style.ACCENT_TINT
    assert pixel(QStyle.StateFlag.State_Enabled) == "#f5f6f8", "the odd row's own shading"
    assert pixel(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver) == style.NEXT_BLUE.name()  # fmt: skip


def test_a_right_click_on_a_race_row_selects_nothing_and_opens_nothing(make_app, tmp_path, quiet):
    """No right-click menus, and the right button never switches the race."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    lst = c.main.program.list
    c.main.show()
    QApplication.processEvents()
    assert lst.currentRow() == 0
    where = lst.visualItemRect(lst.item(2)).center()
    QTest.mouseClick(lst.viewport(), Qt.MouseButton.RightButton, pos=where)
    from PySide6.QtGui import QContextMenuEvent

    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, where, lst.viewport().mapToGlobal(where)
    )
    QApplication.sendEvent(lst.viewport(), event)
    QApplication.processEvents()
    assert lst.currentRow() == 0 and c.live.race_id == c.races[0].race_id
    assert "menu" not in quiet


def _quit(c, monkeypatch) -> None:
    """File > Quit as far as the program goes, without ending the test session's Qt."""
    monkeypatch.setattr(c, "app", type("NoQuit", (), {"quit": lambda self: None})())
    c.quit()
    c.close()


def test_the_extra_folder_gets_the_end_of_night_copies_only(make_app, tmp_path, quiet, monkeypatch):
    """Every result backs up beside the file; the chosen folder, never pruned, gets one on Quit and on Backup now."""
    stick = tmp_path / "stick"
    stick.mkdir()
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.store.set_setting(venue.BACKUP_KEY, str(stick))
    _finish_first_race(c)
    automatic = venue.automatic_backup_dir(c.data_dir)
    assert len(list(automatic.glob("*.sqlite"))) == 1
    assert list(stick.glob("*.sqlite")) == []
    assert c.backup_now(stick / "tonight.sqlite") is not None
    assert len(list(stick.glob("*.sqlite"))) == 1
    _quit(c, monkeypatch)
    assert len(list(stick.glob("*.sqlite"))) == 2
    assert len(list(automatic.glob("*.sqlite"))) == 3


@pytest.mark.parametrize(
    ("remembered", "default_exists", "said"),
    [
        ("default", False, "Data file not found, so a new one was created:\n{r}"),
        ("elsewhere", False, "Data file not found:\n{r}\n\nA new one was created:\n{d}"),
        ("elsewhere", True, "Data file not found:\n{r}\n\nOpened instead:\n{d}"),
    ],
)
def test_a_missing_remembered_file_says_what_was_opened_or_made(
    make_app, tmp_path, monkeypatch, remembered, default_exists, said
):
    from PySide6.QtCore import QSettings

    from madtracker import app as app_mod
    from madtracker.store import paths

    default = tmp_path / "home" / "madtracker.sqlite"
    default.parent.mkdir()
    if default_exists:
        Store.open(default).close()
    monkeypatch.setattr(paths, "default_database_path", lambda: default)
    missing = default if remembered == "default" else tmp_path / "usb" / "old.sqlite"
    QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat).setValue(
        app_mod.DATA_FILE_KEY, str(missing)
    )
    c = make_app()
    assert c.data_path == default and c.store is not None
    assert c._notice == said.format(r=missing, d=default)


def test_a_small_field_shows_every_card_without_a_scroll_bar(make_app, tmp_path):
    """An elimination of five after two finished races shows every card with
    no scroll bar: the grid holds its rows' height."""
    from madtracker.control import rulesets

    c = make_app(data_dir=tmp_path / "data")
    s = c.store
    mid = s.add_event("Friday Night 1", "2026-10-16").event_id
    ids = []
    for bib, last in enumerate(["Abernethy", "Achterberg", "Ekwueme", "Fairbairn", "Gallardo"], 1):
        rider = s.add_rider("Rider", last)
        s.add_entry(mid, rider.rider_id, bib)
        ids.append(rider.rider_id)

    def race(name, fmt, field):
        rules = rulesets.rules_for(s, rulesets.default_ruleset_name(s), fmt)
        r = s.add_race(mid, name, fmt, rules=rules.to_dict())
        for rider_id in field:
            s.add_race_entry(r.race_id, rider_id)
        return r

    done = [race("A Final", "placings", ids[:2]), race("B Scratch", "placings", ids[2:])]
    elimination = race("Elimination", "elimination", ids)
    c.open_event(mid)
    c.main.resize(1920, 1032)
    c.main.show()
    for r in done:
        c.select_race(r.race_id)
        for rider_id in [e.rider_id for e in s.race_entries(r.race_id)]:
            c.click(rider_id)
        c.mark_final()
    c.select_race(elimination.race_id)
    QApplication.processEvents()
    grid = c.main.surface.cards
    assert len(grid.cards) == 5
    assert grid.height() >= grid.needed_height()
    assert not grid.verticalScrollBar().isVisible()


def _slots(grid) -> dict[int, tuple[int, tuple]]:
    """Each entrant's card widget and its cell in the grid."""
    return {
        w.card.entrant_id: (id(w), grid.grid.getItemPosition(grid.grid.indexOf(w)))
        for w in grid.cards
    }


@pytest.mark.parametrize(
    ("row", "steps"),
    [
        # A chase: two from the front, one from the back, a status, and Undo of each.
        (0, [("click", "7"), ("click", "12"), ("act", "51", "place_last"), ("act", "9", "dnf")]),
        # An elimination: three out, a status, then the moves of an out.
        (1, [("click", "42"), ("click", "17"), ("act", "8", "dnf"), ("act", "42", "move_up")]),
        # A points race: a sprint, a withdrawal, a lap, a badge in the next sprint.
        (
            2,
            [
                ("click", "12"),
                ("click", "7"),
                ("record",),
                ("act", "38", "withdrawn"),
                ("act", "4", "lap_gained"),
                ("click", "4"),
            ],
        ),
    ],
)
def test_every_card_keeps_its_widget_and_its_slot_until_the_result_completes(
    make_app, tmp_path, row, steps
):
    """A click, a status, or an Undo turns a card done or live where it stands:
    no widget moves to another cell and none is made again, so no card
    slides under the scorer's finger."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.resize(1366, 740)
    c.main.show()
    c.select_race(c.races[row].race_id)
    QApplication.processEvents()
    grid = c.main.surface.cards
    at_start = _slots(grid)
    assert len(at_start) == len(c.live.roster.ids)

    def same(where):
        QApplication.sendPostedEvents()
        QApplication.processEvents()
        assert _slots(grid) == at_start, where

    for step in steps:
        if step[0] == "click":
            assert c.click(c.live.roster.resolve(step[1])), c.main.surface.problem.text()
        elif step[0] == "act":
            assert c.rider_action(c.live.roster.resolve(step[1]), step[2]), (
                c.main.surface.problem.text()
            )
        else:
            assert c.record_sprint(), c.main.surface.problem.text()
        same(step)
        # A click on each done card is refused and moves nothing either.
        for w in [w for w in grid.cards if w.card.done]:
            assert not c.click(w.card.entrant_id)
            same(("done click", step))
    while c.main.undo.isEnabled():
        assert c.undo()
        same("undo")
    assert not any(w.card.done for w in grid.cards)


def test_a_click_on_a_done_card_changes_nothing(make_app, tmp_path):
    """The mouse on a done card: no signal reaches the controller, the red
    line stays empty, nothing is recorded or staged, and the card neither
    lights nor shows the hand."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.resize(1600, 900)
    c.main.show()
    c.select_race(c.races[0].race_id)
    eid = c.live.roster.resolve("7")
    grid = c.main.surface.cards
    live = grid.card_for(eid)
    assert live.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert c.click(eid)
    QApplication.processEvents()
    card = grid.card_for(eid)
    assert card is live and card.card.done and card.badge_text() == "1"
    assert card.cursor().shape() == Qt.CursorShape.ArrowCursor
    log = [r.action_id for r in c.live.rows()]
    staged = c.live.staged()
    heard: list[int] = []
    card.pressed_entrant.connect(heard.append)
    grid.pressed_entrant.connect(heard.append)
    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=QPoint(style.MD, card.height() // 2))
    QApplication.processEvents()
    assert heard == []
    assert c.main.surface.problem.text() == ""
    assert [r.action_id for r in c.live.rows()] == log
    assert c.live.staged() == staged
    assert grid.card_for(eid) is card and card.card.done and card.badge_text() == "1"
    assert not card.property("lit") and not card.isDown()
    assert c.undo()
    assert not card.card.done and card.toolTip() == ""
    assert card.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_a_done_cards_menu_is_its_rows_and_each_pick_goes_where_the_rows_does(
    make_app, tmp_path, quiet, monkeypatch
):
    """The ⋯ on a done card and on its result row are two doors to one menu:
    a move lands in the result as the row's does, and Disqualify asks the
    same question first."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QContextMenuEvent

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.resize(1600, 900)
    c.main.show()
    c.select_race(c.races[1].race_id)
    first, second = (c.live.roster.resolve(b) for b in ("42", "17"))
    assert c.click(first) and c.click(second)
    QApplication.processEvents()
    grid = c.main.surface.cards
    table = c.main.surface.table

    def row_menu(eid):
        return [label for _, label in table.screen.rows[table.row_of(eid)].actions]

    card = grid.card_for(first)
    assert card.card.done and card.badge_text() == "12"
    assert [label for _, label in card.menu_actions] == row_menu(first)
    assert card.dots.isVisible() and not card.lap_up.isVisible()

    def pick(label):
        def run(menu, where):
            items = [a for a in menu.actions() if a.menu() is None]
            action = next(a for a in items if a.text() == label)
            action.trigger()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QApplication.processEvents()

        return run

    # The strip, and a right-click (as a long press on the touchscreen is).
    monkeypatch.setattr(widgets, "run_menu", pick("Move Up"))
    card.dots.click()
    assert c.live.standings().by_entrant(first).rank == 11
    assert (card.badge_text(), grid.card_for(second).badge_text()) == ("11", "12")
    monkeypatch.setattr(widgets, "run_menu", pick("Move Down"))
    centre = card.rect().center()
    QApplication.sendEvent(
        card, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, centre, card.mapToGlobal(centre))
    )
    assert (card.badge_text(), grid.card_for(second).badge_text()) == ("12", "11")
    quiet.clear()
    monkeypatch.setattr(widgets, "run_menu", pick("Disqualify"))
    card.open_actions()
    assert quiet == ["ask:Disqualify"]
    assert c.live.standings().by_entrant(first).status == "DQ"
    assert grid.card_for(first) is card and card.badge_text() == "DQ"
    assert card.toolTip() == "Disqualified"


# Invented riders for the large fields, a few as long as the cards' sample name.
BIG_FIELD = (
    "Wren Talbot,Iker Solano,Mina Varga,Otto Brennan,Zara Quell,Teo Marchetti,"
    "Callum Ashworth,Ingrid Halvorsen,Mateo Villanueva,Priscilla Oduya,Dorian Kettleby,"
    "Freya Lindgren,Hollis Abernant,Juniper Castell,Kasimir Novotny,Leocadia Brandt,"
    "Marisol Quintero,Nikolai Ferrante,Odessa Whitlock,Quentin Oyelaran,Rafaela Montiel,"
    "Soren Blackwood,Tamsin Okonkwo,Ulrich Pemberton,Valentina Rusev,Wilhelmina Ochoa,"
    "Xavier Delacroix,Yusuf Harrowgate,Briony Castellan,Anselm Whitcombe"
).split(",")


@pytest.mark.parametrize(("size", "wide"), [((1366, 740), False), ((1920, 1080), True)])
def test_a_field_of_8_to_30_keeps_every_name_whole_and_scrolls_only_past_its_room(
    make_app, tmp_path, size, wide
):
    """An elimination with half out and a chase with four placed, at the laptop
    stacked and at 1920 side by side: no name is cut on a live or a done
    card, the result keeps its rows, and the grid scrolls only when its rows
    are taller than the room it has."""
    from madtracker.control import rulesets
    from madtracker.ui.surface import RIDER_RESULT_ROWS

    c = make_app(data_dir=tmp_path / "data")
    s = c.store
    event_id = s.add_event("Friday Night 1", "2026-10-16").event_id
    ids = []
    for bib, name in enumerate(BIG_FIELD, 1):
        rider = s.add_rider(*name.split(" ", 1))
        s.add_entry(event_id, rider.rider_id, bib)
        ids.append(rider.rider_id)
    races = []
    for n in (8, 14, 20, 30):
        for fmt, clicks in (("elimination", n // 2), ("placings", 4)):
            # A status too where the field has a 16-character name to mark:
            # the widest chip beside the longest name.
            rules = rulesets.rules_for(s, rulesets.default_ruleset_name(s), fmt)
            race = s.add_race(event_id, f"{fmt} {n}", fmt, rules=rules.to_dict())
            for rider_id in ids[:n]:
                s.add_race_entry(race.race_id, rider_id)
            status = None if n < 14 else ("dnf" if fmt == "elimination" else "withdrawn")
            races.append((race.race_id, n, clicks, status))
    c.open_event(event_id)
    c.main.resize(*size)
    c.main.show()
    surface = c.main.surface
    grid = surface.cards
    for race_id, n, clicks, status in races:
        c.select_race(race_id)
        # Every other rider, so done cards sit among the live ones.
        for rider_id in ids[1:n:2][:clicks]:
            assert c.click(rider_id), surface.problem.text()
        if status is not None:
            assert c.live.entry(ids[8]).names == ["Mateo Villanueva"]
            assert c.rider_action(ids[8], status), surface.problem.text()
            clicks += 1
        for _ in range(3):
            QApplication.processEvents()
        where = (size, c.live.race.name)
        assert surface.wide == wide, where
        assert len(grid.cards) == n and sum(w.card.done for w in grid.cards) == clicks, where
        for w in grid.cards:
            assert w.shown_name() == w.card.entry.names[0], (where, w.card.entry.names[0])
        table = surface.table
        assert table.isVisible(), where
        if not wide:
            assert table.height() >= surface._table_need(RIDER_RESULT_ROWS), where
        scrolls = grid.verticalScrollBar().isVisible()
        assert scrolls == (grid.needed_height() > grid.viewport().height()), where


def test_open_event_deletes_an_unraced_event_and_leaves_it_if_it_was_open(
    make_app, tmp_path, quiet, monkeypatch
):
    from PySide6.QtWidgets import QDialog

    from madtracker.control.copying import copy_program
    from madtracker.ui import setup as su

    c = make_app(demo=True, data_dir=tmp_path / "data")
    demo = c.event.event_id
    # The demo's night before stays too (it has a final Madison).
    kept = [m.event_id for m in c.store.events()]
    race = c.races[0]
    rider = c.store.race_entries(race.race_id)[0].rider_id
    c.store.append_action(race.race_id, "status", {"entrant_id": rider, "status": "DNS"}, 1)
    spare = c.store.add_event("Friday Night 2", "2026-12-04").event_id
    copy_program(c.store, demo, spare)
    c.open_event(spare)

    def run(dialog):
        dialog.select_event(demo)
        assert not dialog.delete.isEnabled() and dialog.delete_why.text() == "Has raced"
        dialog.select_event(spare)
        assert dialog.delete.isEnabled() and dialog.delete_why.text() == ""
        assert dialog.delete_selected()
        assert dialog.table.rowCount() == len(kept)
        return int(QDialog.DialogCode.Rejected)

    asked = []
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or True)
    monkeypatch.setattr(su.OpenEventDialog, "exec", run)
    c.pick_event()
    assert asked == ["Delete Friday Night 2? 13 races go with it. The riders themselves stay."]
    assert [m.event_id for m in c.store.events()] == kept
    assert c.event.event_id == demo, "the open event is gone, so the newest left opens"


def _file_groups(menu, dropped=()) -> list[list[str]]:
    """The File menu's items between dividers, less any the platform moves away."""
    groups: list[list[str]] = [[]]
    for action in menu.actions():
        if action.isSeparator():
            groups.append([])
        elif action not in dropped:
            groups[-1].append(action.text().replace("&", ""))
    return groups


@pytest.mark.parametrize("mac", [False, True])
def test_backup_now_stands_alone_between_dividers(qapp, monkeypatch, mac):
    """Backup Now is a group of its own, and no divider doubles where Settings leaves on a Mac."""
    from madtracker.ui import window

    monkeypatch.setattr(window, "settings_in_file_menu", lambda: not mac)
    w = window.MainWindow()
    dropped = (w.settings_action,) if mac else ()
    settings = [] if mac else [["Settings..."]]
    assert _file_groups(w.file_menu, dropped) == [
        ["New Event...", "Open Event...", "Edit Riders..."],
        [
            "Export Program PDF...",
            "Export Results PDF...",
            "Export USAC CSV...",
            "Multi-Race Standings...",
        ],
        ["Backup Now..."],
        *settings,
        ["New Data File...", "Open Data File..."],
        ["Quit"],
    ]
    w.deleteLater()


def test_backup_now_asks_where_starting_in_the_backup_folder(
    make_app, tmp_path, quiet, monkeypatch
):
    """Backup now asks where the copy goes."""
    from PySide6.QtWidgets import QFileDialog

    from madtracker.control.backups import backup_name

    stick = tmp_path / "stick"
    stick.mkdir()
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.store.set_setting(venue.BACKUP_KEY, str(stick))
    offered = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: offered.append(a[2]) or ("", "")
    )
    assert c.backup_now() is None, "Cancel writes nothing"
    start = Path(offered[0])
    assert start.parent == stick and start.name.startswith("madtracker-")
    assert len(start.name) == len(backup_name())
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(start), ""))
    assert c.backup_now() == start and start.is_file()
    assert c.main.backup_action.text().replace("&", "") == "Backup Now..."
    # The open file itself is refused: on Linux and macOS the rename would
    # replace the live file and lose everything entered after it.
    riders = len(c.store.riders())
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(c.data_path), ""))
    assert c.backup_now() is None
    assert quiet[-1] == f"warn:{c.data_path.name} is the open data file. Choose another name."
    assert len(c.store.riders()) == riders


@pytest.mark.parametrize("export", ["export_program", "export_pdf", "export_csv"])
@pytest.mark.parametrize("beside", ["", "-wal", "-shm"])
def test_an_export_never_writes_over_the_open_file_or_its_wal(
    make_app, tmp_path, monkeypatch, quiet, export, beside
):
    """The save box takes any name typed: a sheet written over the open
    file, or its -wal or -shm, would wreck everything scored into it.
    Backup Now refuses the same names."""
    from PySide6.QtWidgets import QDialog, QFileDialog

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.store.connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
    target = Path(f"{c.data_path}{beside}")
    if not target.exists():
        target.write_bytes(b"")
    held = target.read_bytes()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(QDialog, "exec", lambda self: int(QDialog.DialogCode.Accepted))
    assert getattr(c, export)() is None
    what = "is the open data file" if not beside else "belongs to the open data file"
    assert quiet[-1] == f"warn:{target.name} {what}. Choose another name."
    assert target.read_bytes() == held
    assert c.backup_now() is None and target.read_bytes() == held
    assert c.store.riders(), "the file still reads"


def test_an_empty_file_offers_the_first_nights_steps_and_checks_them_off(
    make_app, tmp_path, monkeypatch
):
    """The empty window offers the first night's steps, not a lone Edit
    event button with the steps in the File menu."""
    from madtracker.control import venue
    from madtracker.ui import settings as settings_ui
    from madtracker.ui.setup import RidersDialog

    c = make_app(data_dir=tmp_path / "fresh")
    win = c.main
    assert c.event is None and win.showing() == "empty"
    assert win.welcome.isVisibleTo(win.empty)
    assert win.welcome_settings.icon().isNull() and win.welcome_riders.icon().isNull()
    assert not win.program.mode.isEnabled() and win.program.mode.toolTip()
    exports = (win.export_program_action, win.export_pdf_action, win.export_csv_action)
    assert not any(a.isEnabled() for a in exports), "nothing to export without an event"
    from madtracker.control import race as rc

    assert win.undo.text() == rc.NOTHING_TO_UNDO_LABEL and not win.undo.isEnabled()

    def named(store, data_dir, parent):
        store.set_setting(venue.NAME_KEY, "Test Track")
        return True

    monkeypatch.setattr(settings_ui, "open_settings", named)
    win.welcome_settings.click()
    assert not win.welcome_settings.icon().isNull() and win.welcome_riders.icon().isNull()
    monkeypatch.setattr(RidersDialog, "exec", lambda d: c.store.add_rider("Ann", "Alpha") and 0)
    win.welcome_riders.click()
    assert not win.welcome_riders.icon().isNull()
    # The app's own slot opens a modal New event dialog.
    win.new_event_requested.disconnect()
    seen = []
    win.new_event_requested.connect(lambda: seen.append("new"))
    win.welcome_event.click()
    assert seen == ["new"]


def test_mark_final_and_reopen_leave_the_result_table_where_it_was(make_app, tmp_path):
    c = make_app(demo=True, data_dir=tmp_path / "data")
    _shown(c)
    _finish_first_race(c)
    surface = c.main.surface
    QApplication.processEvents()
    provisional = surface.table.geometry()
    assert c.mark_final()
    QApplication.processEvents()
    assert surface.visible_buttons() == ["Reopen"]
    assert surface.table.geometry() == provisional
    assert surface.reopen_button.height() == surface.final_button.height()


def test_the_title_names_the_app_and_the_event_but_not_the_version(make_app, tmp_path):
    import madtracker
    from madtracker.dates import show_date
    from madtracker.ui.window import window_title

    c = make_app(demo=True, data_dir=tmp_path / "data")

    when = show_date(c.event.event_date)
    assert c.main.windowTitle() == window_title("Demo Race Night", c.event.event_date)
    assert when in c.main.windowTitle() and madtracker.__version__ not in c.main.windowTitle()


def test_about_opens_in_the_middle_of_the_window(make_app, tmp_path):
    """About sets its height as it shows; it must then sit centered, not low."""
    from madtracker.ui.about import AboutDialog

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.resize(780, 760)
    c.main.move(0, 0)
    c.main.show()
    QApplication.processEvents()
    d = AboutDialog(c.main)
    d.show()
    QApplication.processEvents()
    assert abs(d.frameGeometry().center().y() - c.main.frameGeometry().center().y()) <= 2
    d.close()


def test_open_data_folder_opens_the_open_files_folder(make_app, tmp_path, quiet, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    browsed = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: browsed.append(url) or True))  # fmt: skip
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.data_folder_action.trigger()
    # As paths: Qt gives a Windows folder back with forward slashes.
    assert [Path(url.toLocalFile()) for url in browsed] == [c.data_path.parent]
    assert not quiet
    # A folder the system cannot open says so.
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: False))
    c.main.data_folder_action.trigger()
    assert quiet == [f"warn:The data folder could not be opened:\n{c.data_path.parent}"]


def test_a_click_redraws_in_place_and_shows_what_the_file_holds(make_app, tmp_path):
    """Every click redraws the window; widgets made and styled anew per click
    are what cost a Windows laptop most. The cards and the program rows
    that did not change are kept, and the window still reads as a redraw
    from the file would."""
    from logbook import event_log

    c = make_app(demo=True, data_dir=tmp_path / "data")
    _shown(c)
    race = next(r for r in c.races if r.format == "points")
    c.select_race(race.race_id)
    program = c.main.program.list
    cards = list(c.main.surface.cards.cards)
    lines = event_log(c.store, c.event.event_id)

    assert c.click(cards[0].card.entrant_id)
    assert c.main.surface.cards.cards == cards, "the same card widgets, in place"
    assert cards[0].badge_text() == "1"
    # The first click tags the race Racing, so the program rebuilt once;
    # the clicks after it leave the rows as they are.
    rows = [program.item(i) for i in range(program.count())]
    assert c.click(cards[2].card.entrant_id)
    assert [program.item(i) for i in range(program.count())] == rows
    # A lap is an entry: one line more in the file's log, the others kept.
    assert c.rider_action(cards[1].card.entrant_id, "lap_gained")
    assert c.main.surface.cards.cards == cards
    assert cards[1].chip_text() and not cards[0].chip_text()
    after = event_log(c.store, c.event.event_id)
    assert after[: len(lines)] == lines and len(after) == len(lines) + 1
    assert c.main.undo.text() == c.live.screen().undo_text
    assert c.undo()
    assert not cards[1].chip_text()
    assert event_log(c.store, c.event.event_id)[-2].voided, "the entry Undo took back is struck"
    assert c.main.undo.text() == c.live.screen().undo_text


def test_f1_opens_the_help_for_the_screen_in_view(make_app, tmp_path):
    from madtracker.ui import help

    c = make_app(demo=True, data_dir=tmp_path / "data")
    win = c.main
    for key, section in help.HELP_HERE.values():
        if section is not None:
            path = help.help_dir() / dict((k, n) for k, _t, n in help.PAGES)[key]
            assert section in help.headings(path), (key, section)
    win.help_here.trigger()
    assert (win.help_window.current_key(), win.help_window.current_section()) == (
        "start",
        "Scoring a race",
    )
    c.open_setup()
    win.help_here.trigger()
    assert win.help_window.current_section() == "The event"


def test_a_result_rows_long_moves_fold_into_one_submenu_before_disqualify(
    make_app, tmp_path, monkeypatch
):
    """A 10-rider chase would put nine "Move to" items in a row's menu; they
    sit in one Move to Place submenu, with Disqualify still last."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    _shown(c)
    for eid in list(c.live.roster.ids):
        assert c.click(eid)
    assert c.live.state == "provisional"
    menus = []
    monkeypatch.setattr(widgets, "run_menu", lambda menu, where: menus.append(menu))
    table = c.main.surface.table
    assert table.open_row_menu(0)
    (menu,) = menus
    assert [a.text() for a in menu.actions()] == [
        "Move Down",
        "Tie with the Rider Below",
        "Move to Place",
        "Disqualify",
    ]
    sub = menu.actions()[2].menu()
    places = [a.text() for a in sub.actions()]
    assert places[0] == "2nd" and len(places) == len(c.live.roster.ids) - 1
    # Picking the last place from the submenu moves the winner to the bottom.
    winner = table.screen.rows[0].entrant_id
    sub.actions()[-1].trigger()
    QApplication.processEvents()
    assert c.main.surface.table.screen.rows[-1].entrant_id == winner
    assert c.live.undo_text() == f"Undo: {c.live.label(winner)} moved to 10th"


def test_a_points_penalty_asks_the_points_in_its_dialog_then_records(
    make_app, tmp_path, quiet, monkeypatch
):
    """The card's or the row's Points Penalty... opens the one dialog; Record
    sends the keyed action, Cancel sends nothing (design sections 7 and 8)."""
    from PySide6.QtWidgets import QDialog, QPushButton

    from madtracker.ui import penalty as pen

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    assert c.live.kind == "points"
    eid = c.live.roster.ids[0]
    opened: list[str] = []

    def run(self):
        opened.append(f"{self.windowTitle()} {self.current}")
        self.spin.setValue(7)
        return int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(pen.PointsPenaltyDialog, "exec", run)
    assert c.rider_action(eid, "points_penalty")
    assert opened == ["Points Penalty 0"]
    assert c.live.standings().by_entrant(eid).adjust_points == -7
    # Opened again from the row, the dialog shows the penalty standing
    # and the number typed replaces it.
    monkeypatch.setattr(pen.PointsPenaltyDialog, "exec", lambda self: (opened.append(f"{self.windowTitle()} {self.current}"), self.spin.setValue(3), int(QDialog.DialogCode.Accepted))[-1])  # fmt: skip
    assert c.row_action(eid, "points_penalty")
    assert opened[-1] == "Points Penalty 7"
    assert c.live.standings().by_entrant(eid).adjust_points == -3
    monkeypatch.setattr(pen.PointsPenaltyDialog, "exec", run)
    assert c.rider_action(eid, "points_penalty")
    assert c.live.standings().by_entrant(eid).adjust_points == -7
    assert c.main.undo.text() == f"Undo: {c.live.label(eid)} penalty set to 7"
    assert c.main.surface.problem.text() == ""
    table = c.main.surface.table
    headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
    assert headers.index("Penalty") == headers.index("Total") - 1 == headers.index("Laps") + 1
    row = table.row_of(eid)
    assert table.item(row, headers.index("Penalty")).text() == "\u22127"
    monkeypatch.setattr(pen.PointsPenaltyDialog, "exec", lambda self: int(QDialog.DialogCode.Rejected))  # fmt: skip
    assert not c.rider_action(eid, "points_penalty")
    assert c.live.standings().by_entrant(eid).adjust_points == -7
    # Lap Not Counted records at once, like a lap, with nothing asked.
    assert c.rider_action(eid, "lap_gained") and c.rider_action(eid, "lap_not_counted")
    assert not quiet[-1:] or not quiet[-1].startswith("ask:")
    assert c.live.standings().by_entrant(eid).laps_gained == 0
    # The dialog itself: the rider named, one spin box from 0 showing the
    # penalty standing, Record grayed until the number changes.
    d = pen.PointsPenaltyDialog("#12 Maya Petrakis")
    assert d.windowTitle() == "Points Penalty" and d.points() == 0
    buttons = {b.text(): b for b in d.findChildren(QPushButton)}
    assert not buttons["Record"].isEnabled()
    d.spin.setValue(150)
    assert d.points() == 99 and buttons["Record"].isEnabled()
    # Record is the default: a typed number and Enter record.
    assert buttons["Record"].isDefault() and not buttons["Cancel"].isDefault()
    assert buttons["Record"].objectName() == "primary"
    d.deleteLater()
    d = pen.PointsPenaltyDialog("#12 Maya Petrakis", 5)
    assert d.points() == 5 and d.spin.minimum() == 0
    buttons = {b.text(): b for b in d.findChildren(QPushButton)}
    assert not buttons["Record"].isEnabled()
    d.accept()
    assert d.result() != int(QDialog.DialogCode.Accepted), (
        "Enter on the same number records nothing"
    )
    d.spin.setValue(0)
    assert buttons["Record"].isEnabled()
    d.deleteLater()


def test_the_card_or_row_stays_lit_while_its_menu_is_open_and_a_right_click_outside_moves_it(
    make_app, tmp_path, quiet, monkeypatch
):
    """The menu says whose it is by lighting the card or row it came from
    until it closes, and a right-click on another rider while a menu is
    open closes it and opens that rider's, where Qt alone would keep the
    click. The row's ⋯ is a finger wide and the row's full
    height, as the card's lap buttons are."""
    from PySide6.QtCore import QEvent, QPointF, QTimer
    from PySide6.QtGui import QMouseEvent

    from madtracker.ui import review, widgets

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    c.main.show()
    QApplication.processEvents()
    table = c.main.surface.table
    cards = c.main.surface.cards.cards
    seen: list = []

    def probe(menu, where):
        seen.append((cards[0].property("lit"), table.item(0, 0).background().color().name()))

    monkeypatch.setattr(widgets, "run_menu", probe)
    assert not cards[0].property("lit")
    cards[0].open_actions()
    assert seen == [(True, table.item(0, 0).background().color().name())]
    assert not cards[0].property("lit"), "the card's look comes back when the menu closes"
    before = table.item(0, 0).background()
    assert table.open_row_menu(0)
    assert seen[-1] == (False, style.ACCENT_TINT_STRONG)
    assert table.item(0, 0).background() == before, "the row's own shading comes back"
    dots = table.cellWidget(0, table.columnCount() - 1)
    assert not dots.property("lit")
    # The row's ⋯: a finger wide, the row's full height, the card's glyph.
    assert table.columnWidth(table.columnCount() - 1) == review.DOTS_COL_W == 56
    assert dots.height() == table.rowHeight(0) == review.ROW_H
    assert dots.iconSize().width() == widgets.DOTS_PX == 28
    from madtracker.ui import cards as card_mod

    assert card_mod.NAME_PT == card_mod.NAME_PT_BASE
    assert cards[0].dots.iconSize().width() == widgets.DOTS_PX, "the card's glyph is the row's"
    # The real menu (exec_menu, under the quiet fixture's stub): a
    # right-press outside it, over the second card, closes it and the
    # second card's menu opens in its place (posted, so the first caller
    # has returned); a Close there ends the test's menus.
    calls: list = []
    target = cards[1].mapToGlobal(cards[1].rect().center())

    def press_outside(menu):
        # The press as the menu receives it, sent straight to it: QTest's
        # press would leave the right button down for every later test.
        local = QPointF(menu.mapFromGlobal(target))
        event = QMouseEvent(QEvent.Type.MouseButtonPress, local, QPointF(target), Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)  # fmt: skip
        QApplication.sendEvent(menu, event)

    def run(menu, where):
        calls.append(len(calls))
        if len(calls) == 1:
            QTimer.singleShot(0, lambda: press_outside(menu))
        else:
            seen.append(("second", cards[1].property("lit"), cards[0].property("lit")))
            QTimer.singleShot(0, menu.close)
        widgets.exec_menu(menu, where)

    monkeypatch.setattr(widgets, "run_menu", run)
    # The offscreen platform cannot say which window is under a point.
    monkeypatch.setattr(widgets, "widget_at", lambda at: cards[1] if at == target else None)
    far = c.main.mapToGlobal(c.main.rect().bottomRight())
    cards[0].open_actions(far)
    for _ in range(20):
        QApplication.processEvents()
        if len(calls) == 2:
            break
    assert len(calls) == 2, "the right-click outside opened the other card's menu"
    assert seen[-1] == ("second", True, False)
    for _ in range(5):
        QApplication.processEvents()
    assert not cards[1].property("lit")


# The real boxes, taken before the quiet fixture stands in for them.
REAL_BOXES = {name: getattr(icons, name) for name in ("ask", "choose", "inform", "warn")}


def test_every_closed_dialog_and_menu_is_let_go(make_app, tmp_path, quiet, monkeypatch):
    """A dialog or ⋯ menu the scorer closes is deleted, not kept under the
    main window for the rest of the night: each one is opened through the
    app's own path and closed, and once deferred deletes are delivered
    nothing is left but the help window, which is kept to be reused."""
    from PySide6.QtCore import QCoreApplication, QEvent, QTimer
    from PySide6.QtWidgets import QDialog, QMenu
    from shiboken6 import isValid

    from madtracker.ui.about import AboutDialog
    from madtracker.ui.settings import SettingsDialog

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    assert c.live.kind == "points"
    for eid in c.live.roster.ids[: c.live.scoring_places(1)]:
        assert c.click(eid)
    assert c.record_sprint()
    c.main.show()
    QApplication.processEvents()
    entrant = c.live.roster.ids[0]
    for name, real in REAL_BOXES.items():
        monkeypatch.setattr(icons, name, real)
    monkeypatch.setattr(widgets, "run_menu", widgets.exec_menu)

    # A dialog with a dialog of its own opens it once, from its own loop.
    nested = {SettingsDialog: "open_rulesets", AboutDialog: "show_licenses"}
    opened: list[str] = []

    def closer():
        modal = QApplication.activeModalWidget()
        if modal is not None:
            opened.append(type(modal).__name__)
            slot = nested.pop(type(modal), None)
            if slot is not None:
                QTimer.singleShot(0, modal, getattr(modal, slot))
            else:
                modal.reject()
        popup = QApplication.activePopupWidget()
        if popup is not None:
            opened.append("menu")
            popup.close()

    timer = QTimer(c.main)
    timer.timeout.connect(closer)
    timer.start(5)

    def alive() -> list[str]:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        seen = {
            id(w): w
            for w in [*c.main.findChildren(QDialog), *c.main.findChildren(QMenu)]
            + QApplication.topLevelWidgets()
            if isValid(w)
        }
        return [
            type(w).__name__
            for w in seen.values()
            if (isinstance(w, QDialog) and w is not c.main.help_window)
            or (isinstance(w, QMenu) and w.objectName() == "touchMenu")
        ]

    screen = c.main.setup
    race_id = c.races[0].race_id
    paths = {
        "settings and rulesets": c.edit_settings,
        "edit riders": c.manage_riders,
        "about and licenses": c.main.show_about,
        "open event": c.pick_event,
        "new event": c.new_event,
        "new data file": lambda: c.new_data_file(tmp_path / "other.sqlite"),
        "export results pdf": c.export_pdf,
        "points penalty": lambda: c.rider_action(entrant, "points_penalty"),
        "shorten race": lambda: c.race_action("shorten_race"),
        "multi-race standings": c.open_standings,
        "ask": lambda: icons.ask(c.main, "Ask", "Go on?"),
        "choose": lambda: icons.choose(c.main, "Choose", "Which?", ["One", "Two"], "Two"),
        "warn": lambda: icons.warn(c.main, "Warn", "Careful."),
        "inform": lambda: icons.inform(c.main, "Inform", "Done."),
        "card menu": lambda: c.main.surface.cards.cards[0].open_actions(),
        "row menu": lambda: c.main.surface.table.open_row_menu(0),
        "task line menu": c.main.surface.open_race_actions,
        "setup groups": lambda: (c.open_setup(), screen.manage_groups()),
        "setup choose riders": screen.choose_riders,
        "setup add race": screen.add_race,
        "setup edit race": lambda: screen.edit_race(race_id),
        "setup duplicate race": lambda: screen.duplicate_race(race_id),
    }
    left = {}
    for name, path in paths.items():
        before = len(opened)
        path()
        assert len(opened) > before, f"{name} opened nothing"
        if still := alive():
            left[name] = still
    timer.stop()
    assert not nested, "every nested dialog was opened"
    assert left == {}


def test_end_race_results_stand_asks_first_and_ends_the_race_on_the_sprints_ridden(
    make_app, tmp_path, quiet, monkeypatch
):
    """The task line's ⋯ is there from a Points Race's first screen, so the
    line never changes height; its items are grayed, each with why, until a
    sprint is recorded. End Race asks first, Cancel the default; Yes
    completes the race on the sprints ridden and Undo reopens it."""
    from madtracker.ui import icons, widgets

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    assert c.live.kind == "points"
    s = c.main.surface
    assert s.task_dots.isVisibleTo(s)
    assert s.screen.race_actions == (), "nothing stands before a sprint"
    assert s.screen.race_menu == (
        ("end_race", "End Race Now, Result As-Is...", "Record a sprint first; nothing stands yet."),
        ("shorten_race", "Shorten Race...", "Record a sprint first."),
    )
    menus = []
    monkeypatch.setattr(
        widgets,
        "run_menu",
        lambda menu, where: menus.append(
            [
                (a.text(), a.isEnabled(), "" if a.isEnabled() else a.toolTip())
                for a in menu.actions()
            ]
        ),
    )
    s.task_dots.click()
    assert menus == [
        [
            ("End Race Now, Result As-Is...", False, "Record a sprint first; nothing stands yet."),
            ("Shorten Race...", False, "Record a sprint first."),
        ]
    ]
    assert not c.race_action("end_race"), "a grayed item picked anyway is refused"
    assert s.problem.text() == "Record a sprint first; nothing stands yet."
    ids = c.live.roster.ids
    for eid in ids[: c.live.scoring_places(1)]:
        assert c.click(eid)
    assert c.record_sprint()
    assert s.task_dots.isVisibleTo(s)
    assert s.screen.race_actions == (
        ("end_race", "End Race Now, Result As-Is..."),
        ("shorten_race", "Shorten Race..."),
    )
    s.task_dots.click()
    assert menus[-1] == [
        ("End Race Now, Result As-Is...", True, ""),
        ("Shorten Race...", True, ""),
    ]
    monkeypatch.setattr(icons, "ask", lambda *a, **k: quiet.append(("ask", a[1], a[2], k)) or False)
    quiet.clear()
    assert not c.race_action("end_race")
    assert quiet == [
        (
            "ask",
            "End Race",
            "End the race now? Results will be recorded as-is.",
            {"verb": "End Race"},
        )
    ]
    assert not c.live.standings().is_complete
    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    assert c.race_action("end_race")
    assert c.live.standings().is_complete and c.live.state == "provisional"
    assert s.screen.review and s.task_dots.isVisibleTo(s)
    assert s.screen.race_actions == () and all(
        why == "The race is already complete." for _k, _l, why in s.screen.race_menu
    )
    assert s.visible_buttons() == ["Mark Final"]
    assert s.table.screen.sprint_columns == (1,)
    assert c.main.undo.text() == "Undo: race ended after 1 sprint"
    assert c.undo()
    assert not c.live.standings().is_complete and s.task_dots.isVisibleTo(s)
    assert s.problem.text() == ""


def test_shorten_race_asks_for_the_count_and_records_on_enter(make_app, tmp_path, quiet):
    """USAC 1G4(b): the task line's Shorten Race... opens a box with the
    count from the next sprint to one below the count in force. Cancel is
    the default and records nothing; Enter in the number records, and the
    task line turns to the final sprint."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest

    from madtracker.ui.shorten import ShortenRaceDialog

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    assert c.live.kind == "points" and c.live.sprint_count == 3
    s = c.main.surface
    ids = c.live.roster.ids
    for eid in ids[: c.live.scoring_places(1)]:
        assert c.click(eid)
    assert c.record_sprint()
    seen = []

    def answer(how):
        def run():
            box = QApplication.activeModalWidget()
            assert isinstance(box, ShortenRaceDialog)
            seen.append(
                (
                    box.windowTitle(),
                    box.spin.minimum(),
                    box.spin.maximum(),
                    box.spin.value(),
                    box.cancel.isDefault(),
                    box.shorten.isDefault(),
                    box.shorten.text(),
                )
            )
            how(box)

        QTimer.singleShot(0, c.main, run)

    answer(lambda box: box.cancel.click())
    assert not c.race_action("shorten_race")
    assert seen == [("Shorten Race", 2, 2, 2, True, False, "Shorten")]
    assert c.live.sprint_count == 3 and s.task.text().startswith("Sprint 2")
    answer(lambda box: QTest.keyClick(box.spin, Qt.Key.Key_Return))
    assert c.race_action("shorten_race")
    assert c.live.sprint_count == 2
    assert c.live.task().kind == "final_sprint"
    assert s.task.text() == "Final sprint: click every rider in order."
    assert c.main.undo.text() == "Undo: race shortened to 2 sprints"
    assert s.screen.race_actions == (("end_race", "End Race Now, Result As-Is..."),)
    assert s.problem.text() == ""
    assert c.undo()
    assert c.live.sprint_count == 3


def test_record_sprint_asks_when_fewer_than_the_scoring_places_are_clicked(
    make_app, tmp_path, quiet, monkeypatch
):
    """Record Sprint with fewer riders placed than the sprint awards asks
    first, Cancel the default; No records nothing, Yes records the short
    sprint as called."""
    from madtracker.ui import icons

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    assert c.live.kind == "points"
    ids = c.live.roster.ids
    places = c.live.scoring_places(1)
    assert places >= 2
    assert c.click(ids[0])
    monkeypatch.setattr(icons, "ask", lambda *a, **k: quiet.append("ask:" + a[1]) or False)
    quiet.clear()
    assert not c.record_sprint()
    assert quiet == ["ask:Record Sprint"] and not c.live.recorded_sprints()
    monkeypatch.setattr(icons, "ask", lambda *a, **k: quiet.append("body:" + a[2]) or True)
    quiet.clear()
    assert c.record_sprint()
    assert quiet == [f"body:Only 1 of {places} places are clicked. Record Sprint 1 anyway?"]
    assert sorted(c.live.recorded_sprints()) == [1]
    # The scoring places filled: no question.
    quiet.clear()
    for eid in ids[:places]:
        assert c.click(eid)
    assert c.record_sprint()
    assert quiet == [] and sorted(c.live.recorded_sprints()) == [1, 2]


def test_a_row_offers_the_riders_actions_while_the_race_runs_and_a_right_click_opens_the_menu(
    make_app, tmp_path, quiet
):
    """The scorer who sees the wrong figure in the table acts there: while
    a points race runs each row's ⋯ offers what the card's does, less the
    staged moves, through the same questions and dialog. A right-click on
    a card or a row opens the same menu, a second way and never the only
    one; a right-click on a row without a menu opens
    nothing."""
    from PySide6.QtGui import QContextMenuEvent

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    assert c.live.kind == "points"
    table = c.main.surface.table
    cards = c.main.surface.cards.cards
    eid = cards[0].card.entrant_id
    row = next(r for r in table.screen.rows if r.entrant_id == eid)
    card_keys = [k for k, _ in cards[0].card.actions]
    assert [k for k, _ in row.actions] == card_keys == [
        "dns", "dnf", "withdrawn", "lap_gained", "lap_lost", "points_penalty", "dq"
    ]  # fmt: skip
    # A badged card keeps its moves; the row never has them.
    assert c.click(eid) and c.click(cards[1].card.entrant_id)
    row = next(r for r in table.screen.rows if r.entrant_id == eid)
    assert [k for k, _ in row.actions] == ["dnf", "lap_gained", "lap_lost", "points_penalty", "dq"]
    assert [k for k, _ in cards[0].card.actions][0] == "move_down"
    # The row's Did Not Finish asks, as the card's does (quiet answers Yes).
    quiet.clear()
    assert c.row_action(eid, "dnf")
    assert quiet == ["ask:Did Not Finish"]
    assert c.live.standings().by_entrant(eid).status == "DNF"
    # Out of the race, the row still offers Disqualify; disqualified, nothing.
    assert [k for k, _ in c.live.review_actions(eid)] == ["dq"]
    assert c.row_action(eid, "dq")
    assert c.live.standings().by_entrant(eid).status == "DQ"
    # Right-click: the card's menu, the row's menu, nothing on a row without one.
    c.main.show()
    QApplication.processEvents()
    quiet.clear()
    w = next(w for w in c.main.surface.cards.cards if not w.card.done)
    QApplication.sendEvent(w, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, w.rect().center(), w.mapToGlobal(w.rect().center())))  # fmt: skip
    assert quiet == ["menu"]
    quiet.clear()
    i = next(n for n, r in enumerate(table.screen.rows) if r.actions)
    # A mouse right-click reaches a scroll area through its viewport (the
    # area itself ignores one), so the test sends it the same way.
    where = table.visualRect(table.model().index(i, 0)).center()
    QApplication.sendEvent(table.viewport(), QContextMenuEvent(QContextMenuEvent.Reason.Mouse, where, table.viewport().mapToGlobal(where)))  # fmt: skip
    assert quiet == ["menu"]
    quiet.clear()
    j = next(n for n, r in enumerate(table.screen.rows) if not r.actions)
    where = table.visualRect(table.model().index(j, 0)).center()
    QApplication.sendEvent(table.viewport(), QContextMenuEvent(QContextMenuEvent.Reason.Mouse, where, table.viewport().mapToGlobal(where)))  # fmt: skip
    assert quiet == []


def test_a_running_eliminations_row_tie_goes_through_the_review(make_app, tmp_path):
    """The row's Tie with the Rider Above on an out while the Elimination
    runs is the bell's tie, not the staged tie (a chase's)."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[1].race_id)
    assert c.live.kind == "elimination"
    bibs = ["42", "17", "31"]
    ids = [c.live.roster.resolve(b) for b in bibs]
    for eid in ids:
        assert c.click(eid)
    assert "tie_above" in [k for k, _ in c.live.review_actions(ids[1])]
    assert c.row_action(ids[1], "tie_above"), c.main.surface.problem.text()
    rows = {r.entrant_id: r.place_text for r in c.live.screen().rows}
    assert rows[ids[1]] == rows[ids[2]]
    assert c.live.undo_text() == f"Undo: {c.live.label(ids[1])} tied with {c.live.label(ids[2])}"


def test_the_scoreboard_menu_lists_each_display_with_what_the_board_is_there(make_app, tmp_path):
    """One list, no submenu: Automatic, each display
    marked Full Screen or Windowed, then None for off; a divider; Logo, Live."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.main.set_screens(
        [
            ("eDP-1", "Display 1, 1366x768 (Primary) (Windowed)"),
            ("HDMI-1", "Sony TV, 1920x1080 (Full Screen)"),
        ],
        "HDMI-1",
    )
    assert c.main.display_labels() == [
        "Automatic",
        "Display 1, 1366x768 (Primary) (Windowed)",
        "Sony TV, 1920x1080 (Full Screen)",
        "None",
    ]
    assert [a.isChecked() for a in c.main.display_group.actions()] == [False, False, True, False]
    menu = [a.text() for a in c.main.board_menu.actions() if not a.isSeparator()]
    assert menu[-2:] == ["&Logo", "Li&ve"]
    c.main.set_board_shown(False)
    assert c.main.none_action.isChecked()
    c.main.set_board_shown(True)
    assert c.main.display_group.actions()[2].isChecked()


def test_the_program_tags_a_race_being_scored_racing(make_app, tmp_path):
    """The race that asks before you switch away is the one tagged Racing:
    from the first staged click until its result."""
    c = make_app(demo=True, data_dir=tmp_path / "data")
    _shown(c)
    chase = c.live.race_id
    rows = {r.race_id: r.status for r in c.main.program._rows}
    assert rows[chase] == ""
    assert c.click(c.live.roster.ids[0])
    rows = {r.race_id: r.status for r in c.main.program._rows}
    assert rows[chase] == "Racing", "a staged click, no entry yet"
    for eid in list(c.live.roster.ids)[1:]:
        assert c.click(eid)
    rows = {r.race_id: r.status for r in c.main.program._rows}
    assert rows[chase] == "Provisional"
    assert c.mark_final()
    rows = {r.race_id: r.status for r in c.main.program._rows}
    assert rows[chase] == "Final"


def test_a_file_that_needs_updating_but_cannot_be_written_is_not_called_damaged(
    make_app, tmp_path, quiet, monkeypatch
):
    """A read-only version-1 file gets no damaged-file notice."""
    from madtracker.store import NeedsUpdateError, Store

    def refuse(path, *a, **k):
        raise NeedsUpdateError("The data file is from an earlier version and is read-only.")

    data = tmp_path / "data"
    data.mkdir()
    (data / "madtracker.sqlite").write_bytes(b"SQLite format 3\0")
    monkeypatch.setattr(Store, "open", staticmethod(refuse))
    c = make_app(data_dir=data)
    assert c.store is None and not c.damaged
    assert "needs updating" in c._notice and "damaged" not in c._notice
    assert "copy it to a folder you can write to" in c._notice


@pytest.mark.parametrize("size", [(1366, 768), (1920, 1080)])
def test_a_rows_dots_fill_their_column_cell(make_app, tmp_path, size):
    """The ⋯ strip covers its whole column cell, so its tint and glyph sit on the column.

    The table's item padding would narrow the cell widget by 16 px, leaving
    an untinted band and a glyph left of the column's center.
    """
    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    c.main.resize(*size)
    c.main.show()
    QApplication.processEvents()
    table = c.main.surface.table
    col = table.columnCount() - 1
    dots = table.cellWidget(0, col)
    assert dots is not None
    cell = table.visualRect(table.model().index(0, col))
    assert dots.geometry() == cell
    assert dots.width() == table.columnWidth(col)


def test_a_menu_action_that_removes_its_card_or_rebuilds_its_row_raises_nothing(
    make_app, tmp_path, quiet, monkeypatch
):
    """Did Not Finish from a card's ⋯ menu takes the card out of the grid
    before the menu's loop returns; the card's look must not be put back
    on a widget that is gone. A row's menu action rebuilds the table the
    same way, and the shading it puts back belongs to the row it lit."""
    from PySide6.QtCore import QEvent
    from shiboken6 import isValid

    from madtracker.ui import widgets

    c = make_app(demo=True, data_dir=tmp_path / "data")
    c.select_race(c.races[2].race_id)
    c.main.show()
    QApplication.processEvents()
    surface = c.main.surface
    card = surface.cards.cards[0]
    gone = card.card.entrant_id

    def pick(label):
        def run(menu, where):
            action = next(a for a in menu.actions() if a.text() == label)
            action.trigger()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QApplication.processEvents()

        return run

    monkeypatch.setattr(widgets, "run_menu", pick("Did Not Finish"))
    card.open_actions()
    assert not isValid(card) or not card.property("lit")
    assert next(k for k in surface.cards.cards if k.card.entrant_id == gone).card.done
    assert c.live.standings().by_entrant(gone).status == "DNF"

    table = surface.table
    assert table.rowCount() > 0
    monkeypatch.setattr(widgets, "run_menu", pick("Disqualify"))
    assert table.open_row_menu(0)
    QApplication.processEvents()
    for i in range(table.rowCount()):
        dots = table.cellWidget(i, table.columnCount() - 1)
        assert dots is None or not dots.property("lit")


def test_a_record_refills_the_standings_rows_in_place(make_app, tmp_path, quiet, monkeypatch):
    """A record, a lap, or an Undo changes what the rows say, not which
    columns there are: the table keeps every row's items and ⋯ button
    rather than making them again, and a row lit for its menu comes back
    with the shading the menu's own action gave it, not the light."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QToolButton

    from madtracker.ui import style, widgets
    from madtracker.ui.review import STATUS_INK

    c = make_app(demo=True, data_dir=tmp_path / "data")
    for race in c.races:
        if race.format == "points":
            c.select_race(race.race_id)
            if c.live.state != "final":
                break
    assert c.live.format_key == "points" and c.live.state != "final"
    c.main.show()
    QApplication.processEvents()
    table = c.main.surface.table
    last = table.columnCount() - 1
    ids = list(c.live.roster.ids)

    def dots():
        return [table.cellWidget(i, last) for i in range(table.rowCount())]

    def items():
        return [table.item(i, 0) for i in range(table.rowCount())]

    before_dots, before_items = dots(), items()
    assert before_dots and all(w is not None for w in before_dots)
    assert c.click(ids[0]) and c.click(ids[1])
    assert c.record_sprint()
    col = table.sprint_column(1)
    assert any(table.item(i, col).text() for i in range(table.rowCount()))
    assert dots() == before_dots and items() == before_items
    assert c.undo()
    assert not any(table.item(i, col).text() for i in range(table.rowCount()))
    assert dots() == before_dots and items() == before_items

    def pick(label):
        def run(menu, where):
            action = next(a for a in menu.actions() if a.text() == label)
            action.trigger()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QApplication.processEvents()

        return run

    monkeypatch.setattr(widgets, "run_menu", pick("Did Not Finish"))
    assert table.open_row_menu(table.row_of(ids[2]))
    QApplication.processEvents()
    assert c.live.standings().by_entrant(ids[2]).status == "DNF"
    out = table.row_of(ids[2])
    assert table.item(out, 0).foreground().color().name() == QColor(STATUS_INK).name()
    light = QColor(style.ACCENT_TINT_STRONG).name()
    for i in range(table.rowCount()):
        assert table.item(i, 0).background().color().name() != light
        w = table.cellWidget(i, last)
        assert w is None or not w.property("lit")
    # A reopened sprint takes every row's ⋯ away: hidden at once, not on
    # the event loop's next pass, so a grab between shows none.
    assert c.record_sprint()
    assert c.reopen_sprint(1), c.main.surface.problem.text()
    QApplication.processEvents()
    assert not any(table.cellWidget(i, last) for i in range(table.rowCount()))
    assert not [b for b in table.viewport().findChildren(QToolButton) if b.isVisible()]


def test_a_sprint_column_is_never_narrower_than_its_widest_value(make_app, tmp_path, quiet):
    """The sprint columns are held to a narrow floor so a long race's all
    show, but never below a value's width in the cells' own font: a value
    that does not fit is not drawn at all. The double-points final puts a
    10 in the last column."""
    from PySide6.QtGui import QFont, QFontMetrics

    from madtracker.ui import style

    c = make_app(demo=True, data_dir=tmp_path / "data")
    for race in c.races:
        if race.format == "points":
            c.select_race(race.race_id)
            if c.live.state != "final":
                break
    table = c.main.surface.table
    ids = list(c.live.roster.ids)
    while not c.live.standings().is_complete:
        for eid in ids:
            if c.live.standings().is_complete:
                break
            c.click(eid)
        if not c.live.standings().is_complete:
            assert c.record_sprint(), c.main.surface.problem.text()
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    heavy = QFont(table.horizontalHeader().font())
    heavy.setWeight(QFont.Weight.DemiBold)
    head = QFontMetrics(heavy)
    margin = table.style().pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, table) + 1
    values = {}
    for n, col in table._sprint_columns.items():
        texts = []
        for r in range(table.rowCount()):
            item = table.item(r, col)
            index = table.model().index(r, col)
            opt = QStyleOptionViewItem()
            table.itemDelegateForIndex(index).initStyleOption(opt, index)
            opt.rect = table.visualRect(index)
            # The room the delegate draws the text in: the cell less the
            # style sheet's padding, less the delegate's own margin.
            room = table.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, table)
            room = room.width() - 2 * margin
            assert QFontMetrics(item.font()).horizontalAdvance(item.text()) <= room, (
                n,
                item.text(),
            )
            texts.append(item.text())
        values[n] = texts
        header = table.horizontalHeaderItem(col).text()
        assert table.columnWidth(col) >= head.horizontalAdvance(header) + 2 * style.SM
    assert any("10" in texts for texts in values.values()), values


def test_a_team_row_keeps_both_riders_on_their_own_lines(make_app, tmp_path, quiet):
    """A rider's name wider than the Riders column is elided on its line
    rather than wrapped onto the second rider's; the cell is drawn by the
    riders' delegate in a team race and by the stock one otherwise."""
    from PySide6.QtGui import QFontMetrics

    from madtracker.ui.review import elided_lines

    c = make_app(demo=True, data_dir=tmp_path / "data")
    table = c.main.surface.table
    c.select_race(next(r.race_id for r in c.races if r.format == "madison"))
    assert table.itemDelegateForColumn(table._name_col) is table._lines_delegate
    c.select_race(next(r.race_id for r in c.races if r.format == "points"))
    assert table.itemDelegateForColumn(table._name_col) is None

    metrics = QFontMetrics(table.font())
    long = "Maximilian-Alexander Featherstonehaugh-Worthington III"
    wide = metrics.horizontalAdvance(long) + 20
    assert elided_lines(f"{long}\nA B", metrics, wide) == [long, "A B"]
    narrow = metrics.horizontalAdvance("Maximilian-Alexander") + 10
    lines = elided_lines(f"{long}\u2028A B", metrics, narrow)
    assert len(lines) == 2 and lines[1] == "A B"
    assert lines[0].endswith("…") and metrics.horizontalAdvance(lines[0]) <= narrow


def test_the_platform_keys_undo_close_the_help_and_open_it(make_app, tmp_path, quiet):
    """Command-Z or Ctrl+Z is the Undo button, Command-W or Ctrl+W closes
    the help window, the platform's help key opens the help beside F1, and
    Settings takes the Mac's Command-comma."""
    from PySide6.QtGui import QKeySequence

    c = make_app(demo=True, data_dir=tmp_path / "data")
    win = c.main
    # A shortcut fires only in a shown, active window.
    win.show()
    win.activateWindow()
    QTest.qWait(10)
    race = next(r for r in c.races if r.format == "points" and r.state != "final")
    c.select_race(race.race_id)
    assert c.click(list(c.live.roster.ids)[0])
    before = c.live.undo_text()
    undo = QKeySequence(QKeySequence.StandardKey.Undo)[0]
    QTest.keyClick(win, undo.key(), undo.keyboardModifiers())
    assert c.live.undo_text() != before
    # With nothing to undo the key does nothing.
    while win.undo.isEnabled():
        c.undo()
    QTest.keyClick(win, undo.key(), undo.keyboardModifiers())
    assert not win.undo.isEnabled()
    win.open_help()
    help_window = win.help_window
    assert help_window.isVisible()
    help_window.activateWindow()
    QTest.qWait(10)
    close = QKeySequence(QKeySequence.StandardKey.Close)[0]
    QTest.keyClick(help_window, close.key(), close.keyboardModifiers())
    assert not help_window.isVisible()
    keys = [k.toString() for k in win.help_here.shortcuts()]
    assert QKeySequence(Qt.Key.Key_F1).toString() in keys
    assert QKeySequence(QKeySequence.StandardKey.HelpContents).toString() in keys
    assert win.settings_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Preferences)
