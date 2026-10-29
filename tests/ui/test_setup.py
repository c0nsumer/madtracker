"""Edit event (design section 6) and the rules for riders (section 12), against a real store.

Dialogs are driven through their methods, never through a modal exec,
so the tests run headless and fast.
"""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from madtracker.control.race import LiveRace
from madtracker.control.roster import TEAM_NAME_MAX
from madtracker.store import Store
from madtracker.ui import icons, style
from madtracker.ui import setup as su

CSV = (
    "Last Name,First Name,USAC License,Category,Bib\n"
    "Quill,Ada,100001,Group A,\n"
    "Lin,Bo,100002,Group B,\n"
)


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "setup.sqlite")
    yield s
    s.close()


@pytest.fixture
def event(store):
    event = store.add_event("Test Night", "2026-10-10")
    ids = {}
    for bib, (first, last, group) in {
        3: ("Marcus", "Delgado", "Group A"),
        5: ("Priya", "Okafor", "Group A"),
        7: ("Maya", "Petrakis", "Group B"),
        12: ("Tess", "Gallagher", "Group B"),
    }.items():
        rider = store.add_rider(first, last)
        store.add_entry(event.event_id, rider.rider_id, bib, local_group=group)
        ids[bib] = rider.rider_id
    return event.event_id, ids


@pytest.fixture
def riders(qtbot, store, event):
    """The Riders window with tonight's event as the one an import offers."""
    d = su.RidersDialog(store, None, import_event=event[0])
    qtbot.addWidget(d)
    return d


@pytest.fixture
def screen(qtbot, store, event):
    w = su.SetupScreen()
    qtbot.addWidget(w)
    w.load(store, event[0])
    return w


def roster_rows(screen):
    """Each roster row as (bib, "First Last", group, license, age)."""
    t = screen.roster
    rows = [[t.item(r, c).text() for c in range(t.columnCount())] for r in range(t.rowCount())]
    return [(r[su.BIB], f"{r[su.FIRST]} {r[su.LAST]}", *r[su.GROUP :]) for r in rows]


def dialog_name(d, row):
    """The rider's whole name in a RidersDialog row, from its two columns."""
    return f"{d.table.item(row, d.first_col).text()} {d.table.item(row, d.last_col).text()}"


def dialog_names(d):
    return [dialog_name(d, r) for r in range(d.table.rowCount())]


# ----- the event ---------------------------------------------------------------


def test_event_name_date_and_series_save_as_they_are_edited(screen, store, event):
    screen.name.setText("Friday Night 4")
    screen.name.editingFinished.emit()
    screen.series.setCurrentText("Winter Series")
    screen.series.lineEdit().editingFinished.emit()
    night = store.event(event[0])
    assert (night.name, night.series) == ("Friday Night 4", "Winter Series")
    screen.name.setText("")
    screen.name.editingFinished.emit()
    assert "needs a name" in screen.event_status.text()
    assert store.event(event[0]).name == "Friday Night 4"
    # The refused name goes back to the file's, and a saved one shows tidied.
    assert screen.name.text() == "Friday Night 4"
    screen.name.setText("  Friday   Night 5 ")
    screen.name.editingFinished.emit()
    assert store.event(event[0]).name == "Friday Night 5" and screen.name.text() == "Friday Night 5"
    # Enter in Series saves the text and adds nothing to the list.
    before = screen.series.count()
    screen.series.setCurrentText("Spring Series")
    screen.series.lineEdit().returnPressed.emit()
    screen.series.lineEdit().editingFinished.emit()
    assert store.event(event[0]).series == "Spring Series" and screen.series.count() == before


def test_renaming_onto_another_event_is_refused_on_the_event_line(screen, store, event):
    store.add_event("Friday Night 5", "2026-10-10")
    screen.name.setText("friday night 5")
    screen.name.editingFinished.emit()
    assert "An event named Friday Night 5 on 2026-Oct-10 already exists." in (
        screen.event_status.text()
    )
    assert store.event(event[0]).name == "Test Night"


# ----- the roster --------------------------------------------------------------


def test_roster_lists_bib_name_group_license_and_age(screen, store, event):
    headers = [screen.roster.horizontalHeaderItem(c).text() for c in range(6)]
    assert headers == ["Bib", "First", "Last", "Group", "USAC License", "Age"]
    assert [r[:4] for r in roster_rows(screen)] == [
        ("3", "Marcus Delgado", "Group A", ""),
        ("5", "Priya Okafor", "Group A", ""),
        ("7", "Maya Petrakis", "Group B", ""),
        ("12", "Tess Gallagher", "Group B", ""),
    ]
    store.update_rider(event[1][3], birth_year=2008)
    screen.refresh()
    assert roster_rows(screen)[0][4] == "18", "the racing age: year end minus birth year"


def test_a_bib_is_shared_on_the_roster_and_refused_only_in_a_race_field(screen, store, event):
    """Riders who never share a race may wear one number (design section 6)."""
    event_id, ids = event
    item = screen.roster.item(0, su.BIB)
    item.setText("7")
    assert store.entry(event_id, ids[3]).bib == 7 and screen.roster_status.text() == ""
    screen.refresh()
    rows = {r[1]: r[0] for r in roster_rows(screen)}
    assert rows["Marcus Delgado"] == rows["Maya Petrakis"] == "7"
    row = screen.row_of(ids[3])
    assert screen.roster.item(row, su.BIB).toolTip() == "Bib 7 is also worn by Maya Petrakis"
    race = store.add_race(event_id, "Chase", "chase")
    store.add_race_entry(race.race_id, ids[5])
    store.add_race_entry(race.race_id, ids[12])
    screen.roster.item(screen.row_of(ids[5]), su.BIB).setText("12")
    assert screen.roster_status.text() == "Bib 12 is worn by Tess Gallagher in Chase."
    assert store.entry(event_id, ids[5]).bib == 5
    assert screen.roster.item(screen.row_of(ids[5]), su.BIB).text() == "5"


def test_an_empty_bib_is_tinted_and_counted_until_typed(screen, store, event):
    event_id, ids = event
    assert screen.roster_count.text() == "4 riders"
    late = store.add_rider("Cy", "Dorn")
    store.add_entry(event_id, late.rider_id, None, local_group="Group A")
    screen.refresh()
    assert screen.roster_count.text() == "5 riders, 1 without a bib"
    row = screen.row_of(late.rider_id)
    assert row == 4, "a rider without a bib lists last"
    item = screen.roster.item(row, su.BIB)
    assert item.text() == "" and item.background().color() == su.style.DANGER_TINT
    item.setText("31")
    assert store.entry(event_id, late.rider_id).bib == 31
    screen._resort(late.rider_id)
    assert screen.roster_count.text() == "5 riders"
    item = screen.roster.item(screen.row_of(late.rider_id), su.BIB)
    assert item.background().color() == su.style.INPUT_GRAY
    # Emptying the cell takes the bib off again, except for a scored race's rider.
    item.setText("")
    assert store.entry(event_id, late.rider_id).bib is None
    race = store.add_race(event_id, "Chase", "chase")
    store.add_race_entry(race.race_id, ids[3])
    store.add_race_entry(race.race_id, ids[5])
    live = LiveRace(store, race.race_id)
    assert live.click(ids[3]).ok and live.click(ids[5]).ok
    screen.refresh()
    screen.roster.item(screen.row_of(ids[3]), su.BIB).setText("")
    assert screen.roster_status.text() == "Marcus Delgado is in Chase, which has been scored."
    assert store.entry(event_id, ids[3]).bib == 3


def test_group_edits_take_the_event_spelling(screen, store, event):
    screen.roster.item(3, su.GROUP).setText("group a")
    assert store.entry(event[0], event[1][12]).local_group == "Group A"


def _late_riders(screen, store, event_id):
    """Two riders entered without bibs, as an import leaves them, on a shown screen."""
    from PySide6.QtWidgets import QApplication

    ann = store.add_rider("Ann", "Alpha")
    ben = store.add_rider("Ben", "Beta")
    for rider in (ann, ben):
        store.add_entry(event_id, rider.rider_id, None, local_group="Group A")
    screen.refresh()
    screen.show()
    QApplication.processEvents()
    return ann.rider_id, ben.rider_id


def _roster_editor(screen, combo=False):
    """The one open editor: a Bib's line edit, or a Group's combo."""
    from PySide6.QtWidgets import QComboBox, QLineEdit

    viewport = screen.roster.viewport()
    if combo:
        found = [e for e in viewport.findChildren(QComboBox) if e.isVisible()]
    else:
        found = [
            e
            for e in viewport.findChildren(QLineEdit)
            if e.isVisible() and not isinstance(e.parentWidget(), QComboBox)
        ]
    assert len(found) == 1, found
    return found[0]


def test_enter_in_a_roster_bib_opens_the_next_rider_without_one(screen, store, event):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit

    event_id, ids = event
    ann, ben = _late_riders(screen, store, event_id)
    assert screen.edit_rider_cell(ann, su.BIB)
    QTest.keyClicks(_roster_editor(screen), "1")
    QTest.keyClick(_roster_editor(screen), Qt.Key.Key_Return)
    QApplication.processEvents()
    assert store.entry(event_id, ann).bib == 1
    # The re-sort put Ann first; the open cell followed Ben, not the row.
    assert screen.row_of(ann) == 0
    assert screen.roster.currentRow() == screen.row_of(ben)
    assert screen.roster.currentColumn() == su.BIB
    QTest.keyClicks(_roster_editor(screen), "22")
    QTest.keyClick(_roster_editor(screen), Qt.Key.Key_Return)
    QApplication.processEvents()
    assert store.entry(event_id, ben).bib == 22
    # Nobody is left without a bib, so typing stops.
    visible = [e for e in screen.roster.viewport().findChildren(QLineEdit) if e.isVisible()]
    assert visible == []


def test_tab_in_a_roster_bib_opens_the_group_as_a_list_of_the_events_groups(screen, store, event):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox

    event_id, ids = event
    ann, ben = _late_riders(screen, store, event_id)
    assert screen.edit_rider_cell(ann, su.BIB)
    QTest.keyClick(_roster_editor(screen), Qt.Key.Key_Tab)
    QApplication.processEvents()
    combo = _roster_editor(screen, combo=True)
    # Picked, never typed: a slip in a cell would make a group of one.
    assert not combo.isEditable()
    texts = [combo.itemText(i) for i in range(combo.count())]
    assert texts == ["No Group", "Group A", "Group B"]
    assert combo.currentText() == "Group A"
    assert screen.roster.currentRow() == screen.row_of(ann)
    combo.setCurrentIndex(combo.findText("Group B"))
    QTest.keyClick(combo, Qt.Key.Key_Tab)
    QApplication.processEvents()
    assert store.entry(event_id, ann).local_group == "Group B"
    # Tab from the Group goes on to the next rider's Bib, Shift+Tab back again.
    assert (screen.roster.currentRow(), screen.roster.currentColumn()) == (
        screen.row_of(ben),
        su.BIB,
    )
    QTest.keyClick(_roster_editor(screen), Qt.Key.Key_Backtab)
    QApplication.processEvents()
    assert (screen.roster.currentRow(), screen.roster.currentColumn()) == (
        screen.row_of(ann),
        su.GROUP,
    )
    assert isinstance(_roster_editor(screen, combo=True), QComboBox)


def test_a_refused_roster_bib_keeps_the_scorer_on_its_cell(screen, store, event):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    event_id, ids = event
    ann, ben = _late_riders(screen, store, event_id)
    race = store.add_race(event_id, "Chase", "chase")
    store.add_race_entry(race.race_id, ids[3])
    store.add_race_entry(race.race_id, ann)
    assert screen.edit_rider_cell(ann, su.BIB)
    QTest.keyClicks(_roster_editor(screen), "3")
    QTest.keyClick(_roster_editor(screen), Qt.Key.Key_Return)
    QApplication.processEvents()
    assert store.entry(event_id, ann).bib is None
    assert screen.roster_status.isVisible() and screen.roster_status.text()
    assert (screen.roster.currentRow(), screen.roster.currentColumn()) == (
        screen.row_of(ann),
        su.BIB,
    )
    assert _roster_editor(screen).text() == ""


def _click_header(table, col):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    header = table.horizontalHeader()
    x = header.sectionViewportPosition(col) + header.sectionSize(col) // 2
    QTest.mouseClick(
        header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, header.height() // 2)
    )


def test_a_header_click_sorts_the_roster_and_the_sort_survives_bib_edits(screen, store, event):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    event_id, ids = event
    header = screen.roster.horizontalHeader()
    assert (header.sortIndicatorSection(), header.sortIndicatorOrder()) == (
        su.BIB,
        Qt.SortOrder.AscendingOrder,
    )
    screen.show()
    QApplication.processEvents()
    screen.roster.selectRow(screen.row_of(ids[7]))
    _click_header(screen.roster, su.LAST)
    by_last_name = ["Marcus Delgado", "Tess Gallagher", "Priya Okafor", "Maya Petrakis"]
    assert [r[1] for r in roster_rows(screen)] == by_last_name
    assert (header.sortIndicatorSection(), header.sortIndicatorOrder()) == (
        su.LAST,
        Qt.SortOrder.AscendingOrder,
    )
    assert su.selected_id(screen.roster) == ids[7], "the selection follows the rider"
    screen.roster.item(screen.row_of(ids[5]), su.BIB).setText("1")
    QApplication.processEvents()
    assert store.entry(event_id, ids[5]).bib == 1
    assert [r[1] for r in roster_rows(screen)] == by_last_name
    assert screen.roster.item(screen.row_of(ids[5]), su.BIB).text() == "1"
    _click_header(screen.roster, su.LAST)
    assert [r[1] for r in roster_rows(screen)] == by_last_name[::-1]
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    _click_header(screen.roster, su.FIRST)
    by_first_name = ["Marcus Delgado", "Maya Petrakis", "Priya Okafor", "Tess Gallagher"]
    assert [r[1] for r in roster_rows(screen)] == by_first_name


def test_enter_in_a_roster_bib_follows_the_shown_order(screen, store, event):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    event_id, ids = event
    ann, ben = _late_riders(screen, store, event_id)
    zed = store.add_rider("Cy", "Zed").rider_id
    store.add_entry(event_id, zed, None, local_group="Group A")
    screen.refresh()
    # Name descending: Zed first, then Beta, then Alpha. In bib order the
    # next rider without a bib after Zed would wrap round to Alpha.
    screen.roster_sort.clicked(su.LAST)
    screen.roster_sort.clicked(su.LAST)
    assert screen.row_of(zed) < screen.row_of(ben) < screen.row_of(ann)
    assert screen.edit_rider_cell(zed, su.BIB)
    QTest.keyClicks(_roster_editor(screen), "9")
    QTest.keyClick(_roster_editor(screen), Qt.Key.Key_Return)
    QApplication.processEvents()
    assert store.entry(event_id, zed).bib == 9
    assert screen.row_of(zed) == 0, "still sorted by name"
    assert (screen.roster.currentRow(), screen.roster.currentColumn()) == (
        screen.row_of(ben),
        su.BIB,
    )


def test_the_roster_by_bib_descending_lists_empty_bibs_last(screen, store, event):
    event_id, ids = event
    late = store.add_rider("Cy", "Dorn")
    store.add_entry(event_id, late.rider_id, None)
    store.update_rider(ids[3], birth_year=2000)
    screen.refresh()
    screen.roster_sort.clicked(su.BIB)
    assert [r[0] for r in roster_rows(screen)] == ["12", "7", "5", "3", ""]
    assert screen.roster.item(4, su.BIB).background().color() == su.style.DANGER_TINT
    # Age is a number too, and a blank one lists last both ways.
    screen.roster_sort.clicked(su.AGE)
    assert roster_rows(screen)[0][1] == "Marcus Delgado"
    screen.roster_sort.clicked(su.AGE)
    assert roster_rows(screen)[0][1] == "Marcus Delgado"
    assert screen.roster_count.text() == "5 riders, 1 without a bib, 1 without a group"


def test_the_rider_list_keeps_its_sort_through_the_search(qtbot, store, event):
    from PySide6.QtCore import Qt

    event_id, ids = event
    store.update_rider(ids[3], birth_year=2000)
    store.update_rider(ids[7], birth_year=1990)
    d = su.RidersDialog(store, event_id)
    qtbot.addWidget(d)
    born = d.first_col + 3

    def names():
        return dialog_names(d)

    headers = [d.table.horizontalHeaderItem(c).text() for c in range(1, 5)]
    assert headers == ["First", "Last", "USAC License", "Birth Year"]
    assert names()[0] == "Marcus Delgado", "last name ascending, as the search returns them"
    assert d.table.horizontalHeader().sortIndicatorSection() == d.last_col
    d.show()
    _click_header(d.table, born)
    header = d.table.horizontalHeader()
    assert (header.sortIndicatorSection(), header.sortIndicatorOrder()) == (
        born,
        Qt.SortOrder.AscendingOrder,
    )
    assert names()[:2] == ["Maya Petrakis", "Marcus Delgado"], "unknown birth years last"
    d.search.setText("m")
    assert names() == ["Maya Petrakis", "Marcus Delgado"]
    # The tick column is a control, not a sort.
    d.sort.clicked(0)
    assert header.sortIndicatorSection() == born


def _cells(d):
    """Every cell of a riders table as what it shows and how it acts."""
    t = d.table
    return [
        [
            (
                t.item(r, c).text(),
                t.item(r, c).data(su.ID_ROLE),
                t.item(r, c).checkState() if d.roster_mode and c == 0 else None,
                t.item(r, c).flags(),
                t.item(r, c).background().color().name(),
            )
            for c in range(t.columnCount())
        ]
        for r in range(t.rowCount())
    ]


@pytest.mark.parametrize("roster", [True, False])
def test_the_riders_table_reads_as_new_after_its_rows_are_reused(qtbot, store, event, roster):
    """A filter keystroke gives kept rows new text; every cell must match a dialog opened fresh."""
    event_id, ids = event
    for first, last in (("Ada", "Quill"), ("Bo", "Lin"), ("Mira", "Dahl")):
        store.add_rider(first, last)
    store.update_rider(ids[7], usac_license="200007", birth_year=1999)
    d = su.RidersDialog(store, event_id if roster else None)
    qtbot.addWidget(d)
    if roster:
        # A tick made here: a reused row's box must follow its rider, not the row.
        assert d.set_on_roster(store.search_riders("Quill")[0].rider_id, True)
    for text in ("m", "", "d", "ma", "q", "", "zz", ""):
        d.search.setText(text)
        fresh = su.RidersDialog(store, event_id if roster else None)
        qtbot.addWidget(fresh)
        fresh.search.blockSignals(True)
        fresh.search.setText(text)
        fresh.search.blockSignals(False)
        # Every cell made new: an empty table has no row to keep.
        fresh.table.setRowCount(0)
        fresh.refresh()
        assert _cells(d) == _cells(fresh), text
        assert d.shown_ids() == fresh.shown_ids()
        if roster:
            assert d.roster_count.text() == fresh.roster_count.text()
        sel = d.table.selectionModel().selectedRows()
        assert [i.row() for i in sel] == [
            i.row() for i in fresh.table.selectionModel().selectedRows()
        ]
    # Enter ticks the top match of a narrowed list.
    if roster:
        d.search.setText("Dah")
        assert d.choose()
        assert store.search_riders("Dahl")[0].rider_id in {
            e.rider_id for e in store.entries(event_id)
        }


class _FullDisk:
    """The live connection with COMMIT failing as SQLite does when the disk fills."""

    def __init__(self, real):
        self.real = real

    def execute(self, sql, *args):
        import sqlite3

        if sql.strip().upper().startswith("COMMIT"):
            raise sqlite3.OperationalError("database or disk is full")
        return self.real.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self.real, name)


def test_a_roster_bib_the_disk_refuses_reverts_and_says_so(screen, store, event, monkeypatch):
    event_id, ids = event
    monkeypatch.setattr(store, "_conn", _FullDisk(store._conn))
    screen.roster.item(screen.row_of(ids[3]), su.BIB).setText("77")
    monkeypatch.undo()
    assert store.entry(event_id, ids[3]).bib == 3
    assert screen.roster.item(screen.row_of(ids[3]), su.BIB).text() == "3"
    assert "database or disk is full" in screen.roster_status.text()
    # The file takes the next write once the disk has room again.
    screen.roster.item(screen.row_of(ids[3]), su.BIB).setText("77")
    assert store.entry(event_id, ids[3]).bib == 77


@pytest.mark.parametrize(
    ("typed", "said"),
    [
        ("abc", "A bib is a number from 1 to 9999."),
        ("0", "A bib is a number from 1 to 9999."),
        ("10000", "A bib is a number from 1 to 9999."),
        ("9" * 25, "A bib is a number from 1 to 9999."),
        ("\u00b2", "A bib is a number from 1 to 9999."),
    ],
)
def test_a_roster_bib_that_is_not_a_bib_is_refused_and_reverts(screen, store, event, typed, said):
    event_id, ids = event
    screen.roster.item(screen.row_of(ids[5]), su.BIB).setText(typed)
    assert screen.roster_status.text() == said
    assert store.entry(event_id, ids[5]).bib == 5
    assert screen.roster.item(screen.row_of(ids[5]), su.BIB).text() == "5"


def test_a_group_typed_in_the_roster_refreshes_the_count(screen, store, event):
    """The no-group count follows a group typed for a rider at once, with no reload."""
    event_id, ids = event
    late = store.add_rider("Cy", "Dorn")
    store.add_entry(event_id, late.rider_id, 9)
    screen.refresh()
    assert screen.roster_count.text() == "5 riders, 1 without a group"
    screen.roster.item(screen.row_of(late.rider_id), su.GROUP).setText("Group A")
    assert store.entry(event_id, late.rider_id).local_group == "Group A"
    assert screen.roster_count.text() == "5 riders"
    screen.roster.item(screen.row_of(late.rider_id), su.GROUP).setText("")
    assert screen.roster_count.text() == "5 riders, 1 without a group"


def test_a_roster_refusal_never_stands_under_the_next_edit(screen, store, event):
    event_id, ids = event
    screen.roster.item(screen.row_of(ids[5]), su.BIB).setText("abc")
    assert screen.roster_status.text()
    # A Group edit that saves fine clears the Bib's refusal too.
    screen.roster.item(screen.row_of(ids[7]), su.GROUP).setText("Group A")
    assert screen.roster_status.text() == ""
    assert store.entry(event_id, ids[7]).local_group == "Group A"


def _ticked(d, rider_id) -> bool:
    return d._box(rider_id).checkState() == Qt.CheckState.Checked


def test_choose_riders_ticks_riders_onto_the_roster_and_only_picks(
    qtbot, store, event, monkeypatch
):
    """A roster is a choice from the Riders window: a tick per name, nothing else."""
    event_id, ids = event
    newcomer = store.add_rider("Cy", "Dorn")
    regular = store.add_rider("Di", "Ash")
    vale = store.add_rider("Ed", "Vale").rider_id
    earlier = store.add_event("Earlier Night", "2026-10-03")
    store.add_entry(earlier.event_id, regular.rider_id, 40, local_group="Group A")
    d = su.RidersDialog(store, event_id)
    qtbot.addWidget(d)
    assert d.windowTitle() == "Choose Riders: Test Night"
    assert d.focusWidget() is d.search, "on the roster the name is typed first"
    shown = [b.text() for b in d.findChildren(QPushButton)]
    assert shown == ["Select All", "Select None", "Close"], (
        "made and kept in File > Edit riders only, and nothing beside Close to read as OK"
    )
    assert d.table.horizontalHeaderItem(0).text() == "" and d.first_col == 1
    assert _ticked(d, ids[3]) and not _ticked(d, newcomer.rider_id)
    assert d.roster_count.text() == "4 of 7 riders on the roster"
    # A rider never on a roster: on it with no bib and no group.
    assert d.set_on_roster(newcomer.rider_id, True)
    entry = store.entry(event_id, newcomer.rider_id)
    assert (entry.bib, entry.local_group or "") == (None, "")
    assert _ticked(d, newcomer.rider_id)
    assert d.status.text() == "" and d.status.isHidden(), "the tick is the confirmation"
    assert d.roster_count.text() == "5 of 7 riders on the roster"
    # A regular takes the group from their most recent event, never the bib.
    assert d.set_on_roster(regular.rider_id, True)
    entry = store.entry(event_id, regular.rider_id)
    assert (entry.bib, entry.local_group) == (None, "Group A")
    assert d.added == [newcomer.rider_id, regular.rider_id]
    # A click anywhere on the row is the tick, and an untick is the way off.
    row = next(
        r for r in range(d.table.rowCount()) if d.table.item(r, 0).data(su.ID_ROLE) == ids[3]
    )
    d.table.cellClicked.emit(row, d.last_col)
    assert not _ticked(d, ids[3]) and store._entry_or_none(event_id, ids[3]) is None
    assert d.status.text() == ""
    assert d.removed == [ids[3]]
    d.table.cellClicked.emit(row, 0)
    assert _ticked(d, ids[3]) and store.entry(event_id, ids[3]).bib is None
    assert d.removed == [] and ids[3] not in d.added, "back on is no change at all"
    # Ticking a rider already on the roster adds nobody twice.
    assert not d.set_on_roster(ids[5], True)
    assert d.status.text() == "Priya Okafor is already on the roster."
    assert _ticked(d, ids[5])
    # Select all ticks every rider the filter shows; Select none takes
    # them off, asking once, and one in a scored race stays.
    d.search.setText("Vale")
    assert d.tick_all(True) == 1 and _ticked(d, vale)
    d.search.clear()
    assert d.roster_count.text() == "7 of 7 riders on the roster"
    race = store.add_race(event_id, "Scratch", "scratch")
    store.add_race_entry(race.race_id, ids[5])
    store.append_action(race.race_id, "status", {"entrant_id": ids[5], "status": "DNS"}, 1)
    chase = store.add_race(event_id, "Chase", "chase")
    store.add_race_entry(chase.race_id, ids[7])
    asked = []
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or True)
    assert d.tick_all(False) == 6
    assert asked == [
        "Take 6 riders off the roster? 1 is in races not yet run and come out of them."
    ]
    assert [e.rider_id for e in store.entries(event_id)] == [ids[5]]
    assert d.status.text().startswith("1 rider stay on the roster. Priya Okafor is in Scratch")


def test_add_rider_untick_follows_the_roster_rules_and_puts_the_box_back(
    qtbot, store, event, monkeypatch
):
    event_id, ids = event
    asked = []
    answer = [False]
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append((a[2], k)) or answer[0])
    chase = store.add_race(event_id, "Chase", "chase")
    store.add_race_entry(chase.race_id, ids[3])
    scored = store.add_race(event_id, "Scratch", "scratch")
    store.add_race_entry(scored.race_id, ids[5])
    store.append_action(scored.race_id, "status", {"entrant_id": ids[5], "status": "DNS"}, 1)
    d = su.RidersDialog(store, event_id)
    qtbot.addWidget(d)
    # In a scored race: refused, the reason on the status line, the box back.
    assert not d.set_on_roster(ids[5], False)
    assert "Scratch, which has been scored" in d.status.text()
    assert _ticked(d, ids[5]) and store.entry(event_id, ids[5]).bib == 5
    assert asked == []
    # In an unscored field: asked first, Cancel keeps them.
    assert not d.set_on_roster(ids[3], False)
    assert asked == [("Remove Marcus Delgado from this event? They are in: Chase.", {"verb": "Remove"})]  # fmt: skip
    assert _ticked(d, ids[3]) and store.entry(event_id, ids[3]).bib == 3
    answer[0] = True
    assert d.set_on_roster(ids[3], False)
    assert not _ticked(d, ids[3]) and store._entry_or_none(event_id, ids[3]) is None
    assert d.status.text() == ""
    # A rider added and then unticked is not counted as added.
    late = store.add_rider("Ann", "Alpha")
    d.refresh()
    assert d.set_on_roster(late.rider_id, True) and d.added == [late.rider_id]
    assert d.set_on_roster(late.rider_id, False) and d.added == []


def test_a_click_on_the_box_or_the_name_is_one_tick_and_a_double_click_no_more(qtbot, store, event):
    """Through Qt's own mouse logic: the row is the control, as in CheckList."""
    from PySide6.QtTest import QTest

    event_id, ids = event
    ann = store.add_rider("Ann", "Alpha")
    d = su.RidersDialog(store, event_id)
    qtbot.addWidget(d)
    d.show()
    row = next(r for r in range(d.table.rowCount()) if d.table.item(r, 0).data(su.ID_ROLE) == ann.rider_id)  # fmt: skip
    box = d.table.visualItemRect(d.table.item(row, 0)).center()
    name = d.table.visualItemRect(d.table.item(row, d.last_col)).center()
    QTest.mouseClick(d.table.viewport(), Qt.MouseButton.LeftButton, pos=box)
    assert _ticked(d, ann.rider_id) and store.entry(event_id, ann.rider_id).bib is None
    QTest.mouseClick(d.table.viewport(), Qt.MouseButton.LeftButton, pos=name)
    assert not _ticked(d, ann.rider_id) and store._entry_or_none(event_id, ann.rider_id) is None
    # Through the window, so the second press goes through Qt's own
    # double-click logic (a DblClick sent straight to the viewport skips
    # the press that a view toggles on, and proves nothing).
    spot = d.table.viewport().mapTo(d, name)
    QTest.mouseDClick(d.windowHandle(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, spot)  # fmt: skip
    QApplication.processEvents()
    assert _ticked(d, ann.rider_id) and store.entry(event_id, ann.rider_id).bib is None
    assert su.selected_id(d.table) is None, "a roster row is ticked, never selected"


def test_choose_riders_stays_open_for_the_next_name(qtbot, screen, store, event, monkeypatch):
    """A roster typed by hand is one name after another in one open dialog."""
    event_id, ids = event
    ann = store.add_rider("Ann", "Alpha")
    bea = store.add_rider("Bea", "Bravo")
    seen: list[su.RidersDialog] = []

    def run(d):
        seen.append(d)
        for rider in (ann, bea):
            d.search.setText(rider.last_name)
            assert d.table.rowCount() == 1
            d.search.returnPressed.emit()
            # Back to the search box, empty, for the next name.
            assert d.search.text() == "" and d.focusWidget() is d.search
            assert _ticked(d, rider.rider_id)
        assert d.status.text() == ""
        # Enter on a name already on the roster adds nobody twice.
        d.search.setText("Alpha")
        d.search.returnPressed.emit()
        assert d.status.text() == "Ann Alpha is already on the roster."
        d.search.setText("Nobody")
        d.search.returnPressed.emit()
        assert d.status.text() == "No rider matches."
        # Two clicks are one tick, not a tick and an untick.
        d.search.clear()
        row = next(
            r
            for r in range(d.table.rowCount())
            if d.table.item(r, 0).data(su.ID_ROLE) == ann.rider_id
        )
        d.table.activated.emit(d.table.model().index(row, 1))
        assert _ticked(d, ann.rider_id)
        assert d.set_on_roster(ids[12], False)
        return int(QDialog.DialogCode.Rejected)

    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    monkeypatch.setattr(su.RidersDialog, "exec", run)
    screen.choose_riders()
    assert seen[0].added == [ann.rider_id, bea.rider_id]
    assert store.entry(event_id, bea.rider_id).bib is None
    assert screen.roster_status.text() == "" and not screen.roster_status.isVisibleTo(screen)
    assert su.selected_id(screen.roster) == bea.rider_id


def test_import_preview_shows_the_plan_then_applies_the_ticked_rows(
    screen, store, event, tmp_path, riders
):
    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    assert preview is not None
    assert [preview.table.item(r, su.ACTION).text() for r in range(2)] == ["New", "New"]
    assert preview.table.item(1, su.P_GROUP).text() == "Group B"
    preview.set_checked(1, False)
    preview.table.item(0, su.P_BIB).setText("21")
    assert preview.apply()
    riders.import_done(preview)
    screen.refresh()
    names = [r[1] for r in roster_rows(screen)]
    assert "Ada Quill" in names and "Bo Lin" not in names
    assert store.entry(event[0], store.find_rider_by_license("100001").rider_id).bib == 21
    bad = tmp_path / "bad.csv"
    bad.write_text("nothing here\n", encoding="utf-8")
    assert riders.preview_for(bad) is None
    assert "Could not read bad.csv" in riders.status.text()
    assert riders.preview_for(path) is not None
    assert riders.status.text() == "", "a file that reads clears the last complaint"


def test_a_preview_deleted_before_its_fit_runs_is_left_alone(store, event):
    """The deferred fit is bound to the dialog, so it never runs on a
    deleted table when the dialog goes first."""
    import shiboken6

    from madtracker.importers.bikereg import parse, plan_import

    preview = su.ImportPreview(store, event[0], plan_import(store, event[0], parse(CSV)))
    preview._fit_details_later()
    shiboken6.delete(preview)
    QApplication.processEvents()


def test_a_preview_deleted_before_its_first_bib_opens_is_left_alone(store, event):
    """Opening the first empty bib waits a turn bound to the dialog, so a
    dialog deleted first never runs it."""
    import shiboken6

    from madtracker.importers.bikereg import parse, plan_import

    preview = su.ImportPreview(store, event[0], plan_import(store, event[0], parse(CSV)))
    preview.show()
    shiboken6.delete(preview)
    QApplication.processEvents()


def test_a_roster_deleted_before_its_resort_or_next_cell_is_left_alone(store, event):
    """The re-sort after a bib edit and the move to the next cell wait a
    turn bound to the screen, so a screen deleted first never runs them."""
    import shiboken6

    event_id, ids = event
    screen = su.SetupScreen()
    screen.load(store, event_id)
    row = screen.row_of(ids[3])
    screen.roster.item(row, su.BIB).setText("33")
    screen.roster_typed(row, su.BIB, Qt.Key.Key_Tab)
    shiboken6.delete(screen)
    QApplication.processEvents()
    assert store.entry(event_id, ids[3]).bib == 33


def test_import_preview_names_the_roster_and_can_keep_the_riders_only(
    store, event, tmp_path, riders
):
    """The import is in the Riders window; the roster it fills is a choice, "No Event" included."""
    event_id, ids = event
    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    assert preview.event.currentData() == event_id
    assert preview.event.itemText(preview.event.count() - 1) == "No Event"
    assert not preview.table.isColumnHidden(su.P_BIB)
    assert preview.set_event(None)
    assert preview.event.currentText() == "No Event"
    assert preview.table.isColumnHidden(su.P_BIB) and preview.table.isColumnHidden(su.P_GROUP)
    assert "already on this roster" not in preview.intro.text()
    assert preview.apply()
    assert len(store.entries(event_id)) == len(ids), "nobody new on the roster"
    assert store.find_rider_by_license("100001") is not None
    preview.close()


def test_import_preview_imports_without_bibs_and_tints_them_to_fill(
    screen, store, event, tmp_path, riders
):
    """The export has no bibs, the program never invents one, and the
    numbers often come after registration closes."""
    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    t = preview.table
    assert [t.item(r, su.P_BIB).text() for r in range(2)] == ["", ""]
    assert all(t.item(r, su.P_BIB).background().color() == su.style.DANGER_TINT for r in range(2))
    assert preview.apply_button.isEnabled() and preview.apply_button.toolTip() == ""
    t.item(0, su.P_BIB).setText("021")
    assert t.item(0, su.P_BIB).text() == "21", "the cell reads back as the roster's would"
    assert t.item(0, su.P_BIB).background().color() == su.style.INPUT_GRAY
    # Only a cell that is not a number stops Import, in the roster's words.
    t.item(1, su.P_BIB).setText("x")
    assert not preview.apply_button.isEnabled()
    assert preview.apply_button.toolTip() == "Bo Lin: a bib is a number from 1 to 9999."
    assert t.item(1, su.P_BIB).text() == "x", "a refused cell keeps the text to fix"
    # A number someone wears, or one typed twice, is said, never refused.
    t.item(1, su.P_BIB).setText("7")
    assert preview.apply_button.isEnabled()
    assert t.item(1, su.DETAILS).text() == "bib 7 is also worn by Maya Petrakis"
    t.item(1, su.P_BIB).setText("21")
    assert t.item(1, su.DETAILS).text() == "bib 21 is also typed for Ada Quill"
    t.item(1, su.P_BIB).setText("")
    assert t.item(1, su.DETAILS).text() == ""
    assert preview.apply()
    riders.import_done(preview)
    screen.refresh()
    assert riders.status.text() == "", "a clean import shows in the table, not the line"
    assert screen.roster_count.text() == "6 riders, 1 without a bib"
    assert store.entry(event[0], store.find_rider_by_license("100002").rider_id).bib is None


def test_import_preview_enter_in_a_bib_moves_down_and_never_imports(
    qtbot, screen, tmp_path, riders
):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit

    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    qtbot.addWidget(preview)
    preview.show()
    QApplication.processEvents()
    assert not preview.apply_button.isDefault() and not preview.apply_button.autoDefault()

    def editor():
        found = [e for e in preview.table.viewport().findChildren(QLineEdit) if e.isVisible()]
        assert len(found) == 1
        return found[0]

    # The first bib wanted is open on show, so typing starts at once.
    QTest.keyClicks(editor(), "21")
    QTest.keyClick(editor(), Qt.Key.Key_Return)
    assert preview.table.item(0, su.P_BIB).text() == "21"
    assert preview.table.currentRow() == 1
    QTest.keyClicks(editor(), "22")
    QTest.keyClick(editor(), Qt.Key.Key_Return)
    assert preview.table.item(1, su.P_BIB).text() == "22"
    assert preview.result is None and preview.isVisible(), "Enter never imports"
    assert preview.apply_button.isEnabled()
    preview.done(QDialog.DialogCode.Rejected)  # past the discard question


def test_import_preview_tab_crosses_the_row_and_enter_goes_down(qtbot, screen, tmp_path, riders):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit

    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    qtbot.addWidget(preview)
    preview.show()
    QApplication.processEvents()
    t = preview.table

    def editor():
        found = [e for e in t.viewport().findChildren(QLineEdit) if e.isVisible()]
        assert len(found) == 1
        return found[0]

    def at():
        return (t.currentRow(), t.currentColumn())

    assert at() == (0, su.P_BIB)
    QTest.keyClicks(editor(), "21")
    QTest.keyClick(editor(), Qt.Key.Key_Tab)
    assert at() == (0, su.P_GROUP) and t.item(0, su.P_BIB).text() == "21"
    QTest.keyClick(editor(), Qt.Key.Key_Tab)
    assert at() == (1, su.P_BIB)
    QTest.keyClick(editor(), Qt.Key.Key_Backtab)
    assert at() == (0, su.P_GROUP)
    QTest.keyClick(editor(), Qt.Key.Key_Return)
    assert at() == (1, su.P_GROUP), "Enter goes down the column"
    QTest.keyClick(editor(), Qt.Key.Key_Backtab)
    assert at() == (1, su.P_BIB)
    assert preview.result is None and preview.isVisible()
    preview.done(QDialog.DialogCode.Rejected)  # past the discard question


def test_import_preview_details_wrap_instead_of_eliding(
    qtbot, screen, store, event, tmp_path, riders
):
    """Details is what the import will change: all of it is readable."""
    from PySide6.QtWidgets import QApplication

    store.update_rider(event[1][3], usac_license="100009", birth_year=1998)
    path = tmp_path / "entries.csv"
    path.write_text(
        "Last Name,First Name,USAC License,UCI Code,Age on 12/31/2026,Category,Bib\n"
        "Delgado,Marco,100009,10099988877,34,Group A,\n"
        "Lin,Bo,100002,,,Group B,\n",
        encoding="utf-8",
    )
    preview = riders.preview_for(path)
    qtbot.addWidget(preview)
    preview.resize(800, 500)
    preview.show()
    for _ in range(3):
        QApplication.processEvents()
    t = preview.table
    long, short = t.item(0, su.DETAILS), t.item(1, su.DETAILS)
    assert "registered as Marco" in long.text() and "birth year" in long.text()
    assert long.toolTip() == long.text()
    assert short.toolTip() == short.text()
    one_line = t.rowHeight(1)
    lines = t.fontMetrics().lineSpacing()
    assert t.rowHeight(0) >= one_line + lines, "the long Details wraps onto more lines"
    # A changed Details text (a bib someone wears) carries its new tooltip.
    t.item(1, su.P_BIB).setText("3")
    assert short.text() == "bib 3 is also worn by Marcus Delgado" == short.toolTip()
    preview.done(QDialog.DialogCode.Rejected)  # past the discard question


DUPLICATES_CSV = (
    "Last Name,First Name,USAC License,Category,Bib\n"
    "Delgádo,Márcus,100003,Group A,\n"
    "Gallagher,Tess,12345,Group B,\n"
    "Lin,Bo,100002,Group B,22\n"
)


def test_import_preview_selects_all_new_or_none_and_leaves_a_conflict_off(
    store, event, tmp_path, riders
):
    """The whole file at once, as Choose riders offers. A
    row whose license is someone else's is the scorer's call, one at a time."""
    event_id, ids = event
    store.update_rider(ids[5], usac_license="12345")
    store.add_rider("Bo", "Lin", usac_license="100002")
    path = tmp_path / "entries.csv"
    path.write_text(
        "Last Name,First Name,USAC License,Category,Bib\n"
        "Zulu,Zed,100009,Group A,\n"
        "Gallagher,Tess,12345,Group B,\n"
        "Lin,Bo,100002,Group B,22\n",
        encoding="utf-8",
    )
    preview = riders.preview_for(path)
    assert [b.text() for b in (preview.select_all, preview.select_new, preview.select_none)] == [
        "Select All",
        "Select New",
        "Select None",
    ]
    assert [p.action for p in preview.plans] == ["new", "match", "match"]
    assert preview.plans[1].conflict and not preview.plans[2].conflict
    preview.select_none.click()
    assert preview.ticked() == []
    preview.select_all.click()
    assert preview.ticked() == [0, 2], "the conflict stays off"
    preview.select_new.click()
    assert preview.ticked() == [0]
    preview.close()


def test_enter_on_an_import_preview_row_leaves_the_ticks_alone(qtbot, tmp_path, riders):
    """A table passes Enter up to the dialog: no Select button may take it."""
    from PySide6.QtTest import QTest

    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    preview.show()
    preview.select_none.click()
    assert preview.ticked() == []
    preview.table.setFocus()
    preview.table.setCurrentCell(1, 1)
    QTest.keyClick(preview.table, Qt.Key.Key_Return)
    assert preview.ticked() == []
    assert not any(
        b.autoDefault() for b in (preview.select_all, preview.select_new, preview.select_none)
    )
    preview.close()


def test_import_reviews_each_ticked_rider_whose_values_differ_before_writing(
    store, event, tmp_path, riders, monkeypatch
):
    """A rider on file the file disagrees with is settled
    in the merge's table, one window each, counted in the title; a Cancel
    writes nothing and keeps the picks."""
    meet_id, ids = event
    store.update_rider(ids[3], usac_license="500003", birth_year=1990)
    store.update_rider(ids[5], usac_license="500005", birth_year=1990)
    store.update_rider(ids[7], usac_license="500007")
    path = tmp_path / "entries.csv"
    # Marc for Marcus is only another form of his name (no question);
    # Jaya for Priya is another initial, believed on the birth year.
    path.write_text(
        "Last Name,First Name,USAC License,Age on 12/31/2026,Category,Bib\n"
        "Delgado,Marc,500003,30,Group A,3\n"
        "Okafor,Jaya,500005,36,Group A,5\n"
        "Petrakis,Maya,500007,,Group B,7\n",
        encoding="utf-8",
    )
    preview = riders.preview_for(path)
    t = preview.table
    assert [t.item(r, su.ACTION).text() for r in range(3)] == ["Review", "Review", "On file"]
    assert t.item(0, su.DETAILS).text() == "birth year: 1990 or 1996; registered as Marc"
    assert preview.intro.text() == "3 registrations: 1 on file, 2 to review."
    seen = []

    def first_only(dialog):
        seen.append((dialog.windowTitle(), dialog.primary.text(), dialog.primary.isEnabled()))
        shown = [(line.label, line.texts) for line in dialog.values.lines]
        if len(seen) == 1:
            # The license agrees and the UCI ID is blank on both: shown, not asked.
            assert shown == [
                ("First name", ("Marcus",)),
                ("Last name", ("Delgado",)),
                ("USAC License", ("500003",)),
                ("UCI ID", ()),
                ("Birth year", ("1990 (on file)", "1996 (BikeReg)")),
            ]
        else:
            assert shown[0] == ("First name", ("Priya (on file)", "Jaya (BikeReg)"))
        if len(seen) == 2:
            return int(QDialog.DialogCode.Rejected)
        assert not dialog.primary.isEnabled() and dialog.left.text() == "1 to choose"
        dialog.values.choose("Birth year", "1996 (BikeReg)")
        assert dialog.primary.isEnabled() and dialog.left.text() == ""
        dialog.accept()
        return int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(su.ReconcileDialog, "exec", first_only)
    assert not preview.apply(), "a Cancel in the second review writes nothing"
    assert seen == [
        ("Update Marcus Delgado from the File (1 of 2)", "Next", False),
        ("Update Priya Okafor from the File (2 of 2)", "Import", False),
    ]
    assert store.rider(ids[3]).birth_year == 1990 and preview.result is None
    # Going on again starts the first review where the scorer left it.
    seen.clear()

    def keep_all(dialog):
        seen.append(dialog.values.chosen())
        if not dialog.values.chosen():
            dialog.values.choose("First name", "Priya (on file)")
        dialog.accept()
        return int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(su.ReconcileDialog, "exec", keep_all)
    preview.set_checked(2, False)
    assert preview.apply()
    assert seen == [{4: 1}, {}]
    marcus = store.rider(ids[3])
    assert (marcus.first_name, marcus.birth_year) == ("Marcus", 1996)
    assert store.rider(ids[5]).first_name == "Priya"


def test_an_unticked_rider_on_file_is_never_reviewed(store, event, tmp_path, riders, monkeypatch):
    meet_id, ids = event
    store.update_rider(ids[3], usac_license="500003")
    path = tmp_path / "entries.csv"
    path.write_text(
        "Last Name,First Name,USAC License,Category,Bib\nDelgado,Marc,500003,Group A,3\n",
        encoding="utf-8",
    )
    preview = riders.preview_for(path)
    preview.set_checked(0, False)
    monkeypatch.setattr(su.ReconcileDialog, "exec", lambda d: pytest.fail("reviewed"))
    assert preview.apply()
    assert store.rider(ids[3]).first_name == "Marcus"


def test_import_preview_offers_possible_matches_and_flags_a_conflict(
    screen, store, event, tmp_path, riders, monkeypatch
):
    event_id, ids = event
    store.update_rider(ids[5], usac_license="12345")
    path = tmp_path / "entries.csv"
    path.write_text(DUPLICATES_CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    t = preview.table
    assert preview.intro.text() == ("3 registrations: 1 new, 2 conflicts.")
    # A near-duplicate is a choice that starts at New rider: nothing merges silently.
    combo = preview.action_choice(0)
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Conflict",
        "Same as Marcus Delgado",
    ]
    # The likely match is on tonight's roster: a conflict, said where the status goes.
    assert combo.currentText() == "Conflict"
    # The likely match is on tonight's roster, so the row also starts unticked.
    assert t.item(0, su.DETAILS).text() == (
        "possible match already on this roster with bib 3; may be Marcus Delgado"
    )
    assert preview.action_choice(2) is None
    # A license on file for someone else unticks the row and says whose it is.
    assert preview.chosen() == [2]
    assert (
        t.item(1, su.DETAILS)
        .text()
        .startswith("USAC License 12345 is on file for Priya Okafor; matched by name")
    )
    conflict = preview.action_choice(1)
    assert conflict.currentText() == "Conflict: Same as Tess Gallagher"
    assert "Same as Priya Okafor (USAC License 12345)" in [
        conflict.itemText(i) for i in range(conflict.count())
    ]

    combo.setCurrentIndex(1)
    assert preview.intro.text() == "3 registrations: 1 new, 1 to review, 1 conflict.", (
        "a choice recounts"
    )
    # The accents differ from the rider on file: settled in the review.
    assert t.item(0, su.ACTION).text() == "Review"
    assert combo.currentText() == "Review: Same as Marcus Delgado"
    assert combo.itemText(0) == "New"
    assert t.item(0, su.DETAILS).text().startswith("matched by your choice; ")
    assert t.item(0, su.P_BIB).text() == "3", "the chosen rider's bib tonight"
    assert preview.chosen() == [0, 2]
    preview.set_checked(1, True)
    seen = []

    def settle(dialog):
        seen.append(dialog.windowTitle())
        dialog.values.choose("First name", "Márcus (BikeReg)")
        dialog.values.choose("Last name", "Delgado (on file)")
        return dialog.accept() or int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(su.ReconcileDialog, "exec", settle)
    assert preview.apply()
    assert seen == ["Update Marcus Delgado from the File (1 of 1)"]
    assert store.rider(ids[3]).last_name == "Delgado"
    assert store.rider(ids[3]).usac_license == "100003"
    assert store.rider(ids[3]).first_name == "Márcus"
    assert store.rider(ids[12]).usac_license is None, "the conflicting license stays put"
    assert store.rider(ids[5]).usac_license == "12345"
    assert preview.result.created and len(preview.result.created) == 1


def test_import_preview_unticked_row_is_read_only_and_keeps_what_was_typed(
    screen, store, event, tmp_path, riders
):
    """Import drops an unticked row, so nothing can be typed into one unseen."""
    from PySide6.QtCore import Qt

    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    assert preview.intro.text() == ("2 registrations: 2 new.")
    t = preview.table
    t.item(1, su.P_BIB).setText("x")
    assert not preview.apply_button.isEnabled()
    preview.set_checked(1, False)
    assert preview.apply_button.isEnabled(), "a row left out cannot stop Import"
    preview.set_checked(1, True)
    t.item(1, su.P_BIB).setText("22")
    t.item(1, su.P_GROUP).setText("Group C")
    preview.set_checked(1, False)
    for col in (su.P_BIB, su.P_GROUP):
        cell = t.item(1, col)
        assert not cell.flags() & Qt.ItemFlag.ItemIsEditable
        assert cell.background().color() == su.style.COMPUTED_WHITE
    assert (t.item(1, su.P_BIB).text(), t.item(1, su.P_GROUP).text()) == ("22", "Group C")
    assert not preview.edit_cell(1, su.P_BIB), "Enter skips the unticked row"
    preview.set_checked(1, True)
    for col in (su.P_BIB, su.P_GROUP):
        cell = t.item(1, col)
        assert cell.flags() & Qt.ItemFlag.ItemIsEditable
        assert cell.background().color() == su.style.INPUT_GRAY
    assert preview.apply()
    bo = store.find_rider_by_license("100002").rider_id
    assert (store.entry(event[0], bo).bib, store.entry(event[0], bo).local_group) == (
        22,
        "Group C",
    )


def test_import_preview_types_bibs_for_riders_already_on_the_roster(
    screen, store, event, tmp_path, riders
):
    """Re-importing the same file is how the bibs that came later get typed."""
    from PySide6.QtCore import Qt

    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    first = riders.preview_for(path)
    assert first.apply()
    riders.import_done(first)
    screen.refresh()
    preview = riders.preview_for(path)
    t = preview.table
    assert preview.intro.text() == ("2 registrations: 2 on file.")
    assert preview.ticked() == [] and preview.chosen() == [], "nothing to change yet"
    assert t.item(0, su.ACTION).text() == "On file"
    assert t.item(0, su.DETAILS).text() == "already on this roster"
    for col in (su.P_BIB, su.P_GROUP):
        assert t.item(0, col).flags() & Qt.ItemFlag.ItemIsEditable
    assert t.item(0, su.P_BIB).background().color() == su.style.DANGER_TINT
    assert preview.edit_cell(0, su.P_BIB), "Enter reaches an unticked roster row"
    t.item(0, su.P_BIB).setText("21")
    assert preview.chosen() == [0] and preview.ticked() == []
    assert preview.apply()
    ada = store.find_rider_by_license("100001").rider_id
    bo = store.find_rider_by_license("100002").rider_id
    assert store.entry(event[0], ada).bib == 21
    assert store.entry(event[0], bo).bib is None


def test_import_preview_escape_asks_before_losing_typed_bibs(
    qtbot, screen, tmp_path, monkeypatch, riders
):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    asked = []
    answer = [False]
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append((a[2], k)) or answer[0])
    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")

    untouched = riders.preview_for(path)
    qtbot.addWidget(untouched)
    untouched.reject()
    assert asked == [] and untouched.result is None, "nothing typed asks nothing"

    preview = riders.preview_for(path)
    qtbot.addWidget(preview)
    preview.show()
    preview.table.item(0, su.P_BIB).setText("21")
    preview.table.setFocus()
    QTest.keyClick(preview.table, Qt.Key.Key_Escape)
    assert asked == [("Discard the bibs you typed?", {"verb": "Discard"})]
    assert preview.isVisible(), "Cancel on the question keeps the bibs"
    cancel = next(b for b in preview.findChildren(QPushButton) if b.text() == "Cancel")
    answer[0] = True
    cancel.click()
    assert len(asked) == 2 and not preview.isVisible()


# ----- the venue's riders ---------------------------------------------------


def test_merge_with_asks_who_then_settles_each_value(qtbot, store, event):
    """JOSM's way: what the
    records agree on is kept, what differs is chosen, nothing is chosen for
    the scorer, and there is no "which record stays"."""
    event_id, ids = event
    spare = store.add_rider("Marcus J.", "Delgado", usac_license="512345", birth_year=1990)
    store.add_entry(event_id, spare.rider_id, 30, local_group="Group A")
    d = su.RidersDialog(store, None)
    qtbot.addWidget(d)
    d.select_rider(spare.rider_id)
    assert d.merge.text() == "Merge With..." and d.merge.isEnabled()
    m = d.merge_dialog()
    qtbot.addWidget(m)
    assert m.windowTitle() == "Merge Riders"
    assert m.stack.currentIndex() == su.PICK
    row = [m.table.item(0, c).text() for c in range(5)]
    assert row == ["Marcus", "Delgado", "", "", "Same name"], "the likely match first"
    assert not m.table.selectionModel().hasSelection(), "nothing picked on open"
    assert not m.next_button.isEnabled() and not m.go_next()
    m.select_rider(ids[3])
    assert m.next_button.isEnabled() and m.go_next()
    assert m.stack.currentIndex() == su.KEEP_PAGE
    assert m.heading.text() == "Merge Marcus J. Delgado and Marcus Delgado"
    shown = [
        (
            m.values_table.item(r, 0).text(),
            m.values_table.cellWidget(r, 1) is not None,
            m.values_table.item(r, 1).text(),
        )
        for r in range(m.values_table.rowCount())
    ]
    assert shown == [
        ("First name", True, ""),
        ("Last name", False, "Delgado"),
        ("USAC License", False, "512345"),
        ("UCI ID", False, ""),
        ("Birth year", False, "1990"),
        ("Bib, Test Night", True, ""),
        ("Events", False, "Test Night"),
    ]
    first = m.values_table.cellWidget(0, 1)
    assert first.currentIndex() == -1 and first.placeholderText() == "Choose..."
    assert m.values_table.item(0, 0).background().color() == style.DANGER_TINT
    assert m.left.text() == "2 to choose" and not m.merge_button.isEnabled()
    m.choose("First name", "Marcus")
    assert m.values_table.item(0, 0).background().color() != style.DANGER_TINT
    assert m.left.text() == "1 to choose" and not m.merge()
    m.go_back()
    assert m.stack.currentIndex() == su.PICK
    assert su.selected_id(m.table) == ids[3], "Back keeps the pick"
    m.go_next()
    assert m.chosen() == {0: 1}, "and the values chosen"
    m.choose("Bib, Test Night", "3")
    assert m.left.text() == "" and m.merge_button.isEnabled()
    assert m.merge()
    d.merge_done(m)
    # Neither had raced, so the record started from is the row kept, with
    # the values the page showed.
    kept = store.rider(m.kept)
    assert m.kept == spare.rider_id
    assert (kept.first_name, kept.usac_license, kept.birth_year) == ("Marcus", "512345", 1990)
    assert store.entry(event_id, kept.rider_id).bib == 3
    assert store.search_riders("Marcus J") == []

    # A record that has raced is the row kept, whichever was started from.
    race = store.add_race(event_id, "Chase", "placings")
    store.add_race_entry(race.race_id, kept.rider_id)
    store.append_action(race.race_id, "status", {"entrant_id": kept.rider_id, "status": "DNS"}, 1)
    other = store.add_rider("Mark", "Delgado")
    m = su.MergeDialog(store, other.rider_id, d)
    qtbot.addWidget(m)
    m.select_rider(kept.rider_id)
    m.go_next()
    m.choose("First name", "Mark")
    assert m.merge()
    assert m.kept == kept.rider_id and store.rider(kept.rider_id).first_name == "Mark"
    # From a raced record, the other raced records are off on page 1, so two
    # raced records are never picked and then refused.
    twin = store.add_rider("Marcus", "Delgado-Twin")
    store.add_entry(event_id, twin.rider_id, 33)
    store.add_race_entry(race.race_id, twin.rider_id)
    m2 = su.MergeDialog(store, twin.rider_id, d)
    qtbot.addWidget(m2)
    rows = {m2.table.item(r, 0).data(su.ID_ROLE): r for r in range(m2.table.rowCount())}
    assert m2.table.item(rows[kept.rider_id], su.M_MATCH).text() == "Has raced"
    m2.select_rider(kept.rider_id)
    assert su.selected_id(m2.table) is None and not m2.next_button.isEnabled()


def test_a_value_neither_record_has_is_typed_on_the_merge(qtbot, store):
    """A merge tidies the record in one pass."""
    ann = store.add_rider("Ann", "Alpha").rider_id
    anne = store.add_rider("Ann", "Alpha").rider_id
    store.add_rider("Bo", "Beta", usac_license="200", uci_id="10012345678")
    m = su.MergeDialog(store, ann)
    qtbot.addWidget(m)
    m.select_rider(anne)
    m.go_next()
    editable = [
        m.values_table.item(r, 0).text()
        for r in range(m.values_table.rowCount())
        if m.values_table.item(r, 1).flags() & Qt.ItemFlag.ItemIsEditable
    ]
    assert editable == ["USAC License", "UCI ID", "Birth year"]
    assert m.merge_button.isEnabled(), "nothing to choose, and nothing has to be typed"
    m.type_value("Birth year", "19")
    assert not m.merge_button.isEnabled()
    assert m.error.text().startswith("The birth year is a four-digit year")
    m.type_value("Birth year", "1990")
    m.type_value("USAC License", "200")
    assert m.error.text() == "USAC License 200 is on file for Bo Beta."
    m.type_value("USAC License", "pending")
    assert m.error.text() == "A USAC License is a number; leave it blank if the rider has none."
    m.type_value("USAC License", "300")
    m.type_value("UCI ID", "10012345678")
    assert m.error.text() == "UCI ID 10012345678 is on file for Bo Beta."
    m.type_value("UCI ID", "10087654321")
    assert m.error.text() == "" and m.merge()
    kept = store.rider(m.kept)
    assert (kept.usac_license, kept.uci_id, kept.birth_year) == ("300", "10087654321", 1990)


def test_enter_in_the_merge_filter_picks_the_top_rider_and_goes_on(qtbot, store, event):
    """One page per Enter: the key that picks never also presses Merge."""
    from PySide6.QtTest import QTest

    event_id, ids = event
    spare = store.add_rider("Priya", "Okafor-Spare")
    m = su.MergeDialog(store, spare.rider_id)
    qtbot.addWidget(m)
    m.show()
    m.search.setText("Okafor")
    QTest.keyClick(m.search, Qt.Key.Key_Return)
    assert su.selected_id(m.table) == ids[5]
    assert m.stack.currentIndex() == su.KEEP_PAGE and not m.result()


def test_riders_dialog_rules(qtbot, store, event, monkeypatch):
    event_id, ids = event
    d = su.RidersDialog(store, None)
    qtbot.addWidget(d)

    def names():
        return dialog_names(d)

    assert names() == ["Marcus Delgado", "Tess Gallagher", "Priya Okafor", "Maya Petrakis"]
    d.table.selectRow(0)
    # A rider who has raced is not deleted, and the button says why under it.
    race = store.add_race(event_id, "Chase", "placings")
    store.add_race_entry(race.race_id, ids[3])
    store.append_action(race.race_id, "status", {"entrant_id": ids[3], "status": "DNS"}, 1)
    d.refresh()
    d.select_rider(ids[3])
    assert not d.delete.isEnabled() and d.delete_why.text() == "Has raced"
    assert not d.delete_selected(confirm=False)
    assert d.status.text() == "Marcus Delgado has raced, so they can't be deleted."
    # One only on the roster can go; the question names the roster.
    asked = []
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or True)
    d.select_rider(ids[12])
    assert d.delete.isEnabled() and d.delete_why.text() == ""
    assert d.delete_selected()
    assert asked == [
        "Delete Tess Gallagher from the venue's riders? They come off the roster of Test Night."
    ]
    # A rider in no event can go, and nothing is said under the button.
    store.add_rider("Zed", "Zulu")
    d.search.setText("Zulu")
    assert d.table.rowCount() == 1
    assert d.delete.isEnabled() and d.delete_why.text() == ""
    assert d.delete_selected(confirm=False)
    assert store.search_riders("Zulu") == []


def test_riders_dialog_with_no_event_keeps_the_list_and_offers_no_roster(
    qtbot, store, event, monkeypatch
):
    """File > Edit riders: the same list and rules, with nothing about an event."""
    event_id, ids = event
    d = su.RidersDialog(store, None)
    qtbot.addWidget(d)
    assert d.windowTitle() == "Edit Riders"
    assert d.search.placeholderText() == "Filter by name"
    shown = [b.text() for b in d.findChildren(QPushButton)]
    assert shown == [
        "New Rider...",
        "Import from BikeReg...",
        "Edit...",
        "Merge With...",
        "Delete",
        "Close",
    ]
    assert d.table.columnCount() == 4, "no tick, no note: the list is the list"
    d.select_rider(ids[3])
    assert d.delete.isEnabled(), "on a roster but never raced"

    # A new rider stays in the list, selected, rather than closing it.
    def fill(form):
        form.first.setText("Zed")
        form.last.setText("Zulu")
        return int(QDialog.DialogCode.Accepted if form.save() else QDialog.DialogCode.Rejected)

    monkeypatch.setattr(su.RiderForm, "exec", fill)
    d.new_rider()
    assert d._selected().last_name == "Zulu"
    assert d.delete_selected(confirm=False)
    assert store.search_riders("Zulu") == []


def test_riders_dialog_columns_fit_each_mode(qtbot, store, event):
    """Manage: the list. Roster: a tick first."""
    event_id, ids = event

    def headers(d):
        return [d.table.horizontalHeaderItem(c).text() for c in range(d.table.columnCount())]

    d = su.RidersDialog(store, None)
    qtbot.addWidget(d)
    assert headers(d) == ["First", "Last", "USAC License", "Birth Year"]
    d = su.RidersDialog(store, event_id)
    qtbot.addWidget(d)
    assert headers(d) == ["", "First", "Last", "USAC License", "Birth Year"]


def test_a_double_click_edits_in_the_riders_list(qtbot, store, event, monkeypatch):
    event_id, ids = event
    opened = []
    monkeypatch.setattr(
        su.RiderForm,
        "exec",
        lambda f: opened.append(f.rider_id) or int(QDialog.DialogCode.Rejected),
    )
    d = su.RidersDialog(store, None)
    qtbot.addWidget(d)
    d.select_rider(ids[5])
    d.table.activated.emit(d.table.model().index(d.table.currentRow(), 1))
    assert opened == [ids[5]]


def test_enter_on_a_riders_row_edits_it_as_a_double_click_does(qtbot, store, event, monkeypatch):
    from PySide6.QtTest import QTest

    event_id, ids = event
    opened = []
    monkeypatch.setattr(
        su.RiderForm,
        "exec",
        lambda f: opened.append(f.rider_id) or int(QDialog.DialogCode.Rejected),
    )
    d = su.RidersDialog(store, None)
    qtbot.addWidget(d)
    d.show()
    d.select_rider(ids[5])
    d.table.setFocus()
    QTest.keyClick(d.table, Qt.Key.Key_Return)
    assert opened == [ids[5]], "Enter edits the row, never New Rider..."
    assert not any(b.autoDefault() for b in (d.new, d.import_button, d.edit, d.merge, d.delete))


def test_demo_has_one_rider_on_no_roster_for_delete_to_work_on(qtbot, tmp_path):
    from madtracker.control.demo import SPARE_RIDER, seed_demo

    with Store.open(tmp_path / "demo.sqlite") as store:
        event_id = seed_demo(store)
        spare = next(r for r in store.riders() if f"{r.first_name} {r.last_name}" == SPARE_RIDER)
        assert spare.rider_id not in {e.rider_id for e in store.entries(event_id)}
        d = su.RidersDialog(store, None)
        qtbot.addWidget(d)
        d.select_rider(spare.rider_id)
        assert d.delete.isEnabled() and d.delete_why.text() == ""
        d.close()


def test_the_rider_form_refuses_a_uci_id_another_rider_holds(qtbot, store, event):
    _event_id, ids = event
    store.update_rider(ids[7], uci_id="10012345678")
    form = su.RiderForm(store, ids[5])
    qtbot.addWidget(form)
    form.uci_id.setText("10012345678")
    assert not form.save()
    assert form.error.text() == "UCI ID 10012345678 already belongs to Maya Petrakis."
    own = su.RiderForm(store, ids[7])
    qtbot.addWidget(own)
    assert own.save(), "a rider keeps their own"


def test_rider_form_holds_only_what_stays_true_and_edits_apply_everywhere(qtbot, store, event):
    event_id, ids = event
    form = su.RiderForm(store, ids[7])
    qtbot.addWidget(form)
    assert not hasattr(form, "group")
    form.first.setText("Maia")
    form.license.setText("INTL-CAN")
    assert not form.save()
    assert form.error.text() == "A USAC License is a number; leave it blank if the rider has none."
    form.license.setText("0123456")
    import datetime

    said = f"The birth year is a four-digit year from 1900 to {datetime.date.today().year}."
    form.birth_year.setText("abc")
    assert not form.save() and form.error.text() == said
    # A year outside the range is a real year, so the message says the range.
    form.birth_year.setText("1875")
    assert not form.save() and form.error.text() == said
    form.birth_year.setText("1990")
    assert form.save()
    r = store.rider(ids[7])
    assert (r.first_name, r.usac_license, r.birth_year) == ("Maia", "123456", 1990)
    assert store.race_entries  # the name is the person's: the roster shows it at once
    assert store.entry(event_id, ids[7]).local_group == "Group B"


# ----- the program -------------------------------------------------------------


def test_add_race_asks_the_design_questions_and_the_group_fills_the_field(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    assert [d.format.itemText(i) for i in range(d.format.count())] == [
        "USA Cycling Rulebook 8•25",
        "Elimination (USAC 2E)",
        "Handicap (USAC 2D)",
        "Keirin Final (USAC 2H)",
        "Madison (USAC 2N)",
        "Points Race (USAC 2M)",
        "Scratch Race (USAC 2C)",
        "Sprint Final (USAC 2F)",
        "Tempo Race (USAC 2P)",
        "Club Formats",
        "Chariot (Club)",
        "Unknown Distance (Club)",
        "Win-and-Out (Club)",
    ]
    # The headers are drawn, never chosen; a new race starts on the scratch race.
    assert d.format_key() == "chase"
    for header in (0, 9):
        assert not d.format.model().item(header).isEnabled()
        d.format.setCurrentIndex(header)
        assert d.format_key() is not None
    d.format.setCurrentIndex(d.format.findData("points"))
    assert d.number_label.text() == "Sprints"
    d.number.setValue(3)
    d.choose_group("Group B")
    assert set(d.field_ids()) == {ids[7], ids[12]}
    d.set_in_field(ids[3], True)
    assert d.save()
    race = store.race(d.race_id)
    assert (race.name, race.format, race.group_label) == (
        "Group B Points Race",
        "points",
        "Group B",
    )
    assert race.rules["sprint_count"] == 3 and race.rules_preset == "rulebook"
    assert {e.rider_id for e in store.race_entries(race.race_id)} == {ids[7], ids[12], ids[3]}
    screen.refresh()
    # The Group A rider ticked into this Group B race is counted.
    assert screen.program.item(0, 4).text() == "3 sprints"
    assert screen.program.item(0, 5).text() == "3 riders, 1 from Group A"


def test_win_and_out_takes_places_from_the_ruleset(screen, store, event):
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("win_and_out"))
    assert d.number_label.text() == "Places" and d.number.value() == 3
    d.number.setValue(5)
    d.choose_group("Group A")
    assert d.save()
    assert store.race(d.race_id).rules["places"] == 5


def test_race_field_refuses_a_ticked_bib_clash_and_lists_one_a_group_brings(screen, store, event):
    """A bib is unique within a race's field, not within the event."""
    event_id, ids = event
    store.change_bib(event_id, ids[7], 3)
    late = store.add_rider("Cy", "Dorn")
    store.add_entry(event_id, late.rider_id, None, local_group="Group A")
    d = screen.race_dialog(None)
    d.choose_group("Group B")
    assert d.error.text() == ""
    d.set_in_field(ids[3], True)
    assert d.error.text() == "Bib 3 is worn by Maya Petrakis in this race."
    assert ids[3] not in d.field_ids()
    # A group fills the field anyway and says what to fix.
    store.set_entry_group(event_id, ids[7], "Group A")
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    assert set(d.field_ids()) == {ids[3], ids[5], ids[7], late.rider_id}
    assert d.error.text() == "Bib 3 is worn by Marcus Delgado and Maya Petrakis in this race."
    assert d.field_count.text() == "4 riders in the field, 1 without a bib"
    assert d.save(), "saved; the race waits for the fix before it can be scored"


def test_madison_asks_for_teams_of_two(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("madison"))
    d.number.setValue(2)
    # A team race's field is its teams: the Field list gives way to them.
    assert d.teams_box.isVisibleTo(d) and not d.field_box.isVisibleTo(d)
    assert not d.save() and d.error.text() == "Add the teams."
    assert not d.add_team("Blue", [ids[3]]) and "has 2 riders" in d.error.text()
    assert d.add_team("Blue", [ids[3], ids[5]])
    assert not d.add_team("Blue", [ids[7], ids[12]]) and "already a Blue team" in d.error.text()
    assert d.add_team("Red", [ids[7], ids[12]])
    assert d.save()
    teams = store.teams(d.race_id)
    assert [(t.name, t.members) for t in teams] == [("Blue", (ids[3], ids[5])), ("Red", (ids[7], ids[12]))]  # fmt: skip
    assert sorted(e.rider_id for e in store.race_entries(d.race_id)) == sorted(ids[n] for n in (3, 5, 7, 12))  # fmt: skip
    # The team dialog itself accepts two or more riders, and exactly the format's count when fixed.
    td = su.TeamDialog([(ids[3], "3 Marcus"), (ids[5], "5 Priya"), (ids[7], "7 Maya")], set(), None)
    td.check(ids[3])
    assert not td.accept_team() and "at least two" in td.error.text()
    td.check(ids[5])
    td.check(ids[7])
    assert td.accept_team() and td.members() == [ids[3], ids[5], ids[7]]


def test_a_scored_race_keeps_its_format_and_field(screen, store, event):
    event_id, ids = event
    race = store.add_race(event_id, "Chase", "chase")
    store.add_race_entry(race.race_id, ids[3])
    store.add_race_entry(race.race_id, ids[5])
    # A staged click is not an entry; a recorded one (a DNF) is.
    assert LiveRace(store, race.race_id).act(ids[3], "dnf").ok
    d = screen.race_dialog(race.race_id)
    assert not d.format.isEnabled() and not d.field.isEnabled()
    assert d.locked_note.isVisibleTo(d) and d.locked_note.text() == "Scored races keep their rules."
    d.name.setText("2 Mile Chase")
    assert d.save()
    assert store.race(race.race_id).name == "2 Mile Chase"
    assert {e.rider_id for e in store.race_entries(race.race_id)} == {ids[3], ids[5]}
    screen.refresh()
    assert not screen.remove_race(race.race_id, confirm=False)
    assert "has been scored" in screen.program_status.text()


def test_program_moves_and_removes(screen, store, event):
    event_id, _ = event
    a = store.add_race(event_id, "A", "chase")
    b = store.add_race(event_id, "B", "chase")
    screen.refresh()
    assert screen.move_race(1, a.race_id)
    assert [r.name for r in store.races(event_id)] == ["B", "A"]
    assert not screen.move_race(1, a.race_id)
    assert screen.program_status.text() == "It is already last."
    assert not screen.move_race(-1, b.race_id)
    assert screen.program_status.text() == "It is already first."
    assert screen.remove_race(b.race_id, confirm=False)
    assert [r.name for r in store.races(event_id)] == ["A"]
    screen.program.clearSelection()
    assert not screen.remove_race(None) and "Select a race" in screen.program_status.text()


def test_set_up_event_buttons_are_off_with_the_reason_until_they_mean_something(
    screen, store, event
):
    event_id, ids = event
    store.add_race(event_id, "A", "chase")
    b = store.add_race(event_id, "B", "chase")
    store.add_race_entry(b.race_id, ids[3])
    store.add_race_entry(b.race_id, ids[5])
    screen.refresh()
    program = (screen.edit_race_button, screen.remove_race_button)
    program += (screen.up_button, screen.down_button)
    assert screen.add_race_button.isEnabled()
    for button in program:
        assert not button.isEnabled() and button.toolTip() == "Select a race first"

    screen.program.selectRow(0)
    assert screen.edit_race_button.isEnabled() and screen.remove_race_button.isEnabled()
    assert not screen.up_button.isEnabled()
    assert screen.up_button.toolTip() == "It is already first."
    assert screen.down_button.isEnabled() and screen.down_button.toolTip() == "Move down"
    screen.program.selectRow(1)
    assert screen.up_button.isEnabled()
    assert not screen.down_button.isEnabled()
    assert screen.down_button.toolTip() == "It is already last."
    # Moving follows the race, and the buttons follow the move.
    assert screen.move_race(-1, b.race_id)
    assert not screen.up_button.isEnabled() and screen.down_button.isEnabled()

    assert LiveRace(store, b.race_id).act(ids[3], "dnf").ok
    screen.refresh()
    screen.program.selectRow(0)
    assert not screen.remove_race_button.isEnabled()
    assert screen.remove_race_button.toolTip() == "B has been scored and cannot be removed."
    assert screen.edit_race_button.isEnabled()


def test_new_event_dialog_can_start_from_an_earlier_program(qtbot, store, event):
    event_id, _ = event
    store.add_race(event_id, "Chase", "chase", group_label="Group A")
    d = su.NewEventDialog(store)
    qtbot.addWidget(d)
    assert [d.start_from.itemText(i) for i in range(d.start_from.count())] == [
        "An Empty Program",
        "Test Night (2026-Oct-10)",
    ]
    assert not d.create() and "needs a name" in d.error.text()
    d.name.setText("Next Night")
    d.start_from.setCurrentIndex(1)
    assert d.create()
    races = store.races(d.event_id)
    assert [(r.name, r.group_label) for r in races] == [("Chase", "Group A")]
    assert store.race_entries(races[0].race_id) == [] and store.entries(d.event_id) == []


def test_new_event_dialog_offers_the_roster_only_with_an_earlier_program(qtbot, store, event):
    event_id, ids = event
    race = store.add_race(event_id, "Chase", "chase", group_label="Group A")
    store.add_race_entry(race.race_id, ids[7])
    d = su.NewEventDialog(store)
    qtbot.addWidget(d)
    assert not d.copy_roster.isEnabled() and not d.copy_roster.isChecked()
    d.start_from.setCurrentIndex(1)
    assert d.copy_roster.isEnabled()
    d.copy_roster.setChecked(True)
    d.start_from.setCurrentIndex(0)
    assert not d.copy_roster.isEnabled() and not d.copy_roster.isChecked()
    d.start_from.setCurrentIndex(1)
    d.copy_roster.setChecked(True)
    d.name.setText("Day Two")
    assert d.create()
    assert len(store.entries(d.event_id)) == len(store.entries(event_id))
    assert [e.rider_id for e in store.race_entries(store.races(d.event_id)[0].race_id)] == [ids[7]]


# ----- the race dialog: locks, names, USAC fields, teams ----------------------


def test_a_scored_race_keeps_its_rules_and_only_the_name_changes(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("points"))
    d.number.setValue(4)
    d.choose_group("Group A")
    assert d.save()
    race_id = d.race_id
    assert LiveRace(store, race_id).act(ids[3], "dnf").ok
    d = screen.race_dialog(race_id)
    for w in (d.format, d.group, d.ruleset, d.number, d.field, d.teams_box):
        assert not w.isEnabled()
    assert d.locked_note.isVisibleTo(d)
    # The team buttons say why they are off: the race, not a missing selection.
    for b in (d.edit_team_button, d.remove_team_button):
        assert b.toolTip() == "Scored races keep their rules."
    # Even a value forced into a locked control is not written.
    d.number.setValue(9)
    d.group.setCurrentText("Group B")
    d.name.setText("Renamed")
    assert d.save()
    race = store.race(race_id)
    assert race.name == "Renamed"
    assert race.rules["sprint_count"] == 4 and race.group_label == "Group A"
    # An unscored race shows no lock.
    other = screen.race_dialog(None)
    assert not other.locked_note.isVisibleTo(other) and other.number.isEnabled()


def _undo_to_start(live):
    guard = 0
    while live.can_undo() and guard < 100:
        assert live.undo().ok
        guard += 1
    assert live.rows() == [] and live.state == "setup" and live.staged() == []


def test_a_race_undone_to_its_start_opens_unlocked_and_takes_new_rules(screen, store, event):
    """Undo back to the start list leaves no entry standing (design section
    6): the dialog opens like one for a race never scored, and every rule
    changes. Remove stays refused, since the log keeps the undone rows."""
    event_id, ids = event
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("points"))
    d.number.setValue(4)
    d.choose_group("Group A")
    assert d.save()
    race_id = d.race_id
    live = LiveRace(store, race_id)
    assert live.click(ids[3]).ok and live.record_sprint().ok
    assert live.act(ids[5], "dnf").ok
    d = screen.race_dialog(race_id)
    assert d.scored and not d.format.isEnabled()
    _undo_to_start(live)
    d = screen.race_dialog(race_id)
    assert not d.scored
    assert all(w.isEnabled() for w in d.locked_widgets())
    assert not d.locked_note.isVisibleTo(d)
    for b in (d.edit_team_button, d.remove_team_button):
        assert b.toolTip() != "Scored races keep their rules."
    d.number.setValue(6)
    d.choose_group("Group B")
    d.format.setCurrentIndex(d.format.findData("tempo"))
    assert d.save()
    race = store.race(race_id)
    assert race.format == "tempo" and race.rules["sprint_count"] == 6
    assert race.group_label == "Group B"
    assert {e.rider_id for e in store.race_entries(race_id)} == {ids[7], ids[12]}
    screen.refresh()
    assert not screen.remove_race(race_id, confirm=False)
    assert screen.program_status.text() == f"{race.name} has had entries and cannot be removed."
    # Scored again under the new rules, nothing of the first run shows.
    live = LiveRace(store, race_id)
    assert live.roster.ids == [ids[7], ids[12]] and live.format_key == "tempo"
    assert live.click(ids[7]).ok and live.record_sprint().ok
    assert {r.entrant_id for r in live.standings().rows} == {ids[7], ids[12]}
    assert live.standings().by_entrant(ids[7]).total_points == 1
    d = screen.race_dialog(race_id)
    assert d.scored


def test_a_live_entry_before_the_start_keeps_the_dialog_locked(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    assert d.save()
    live = LiveRace(store, d.race_id)
    assert live.act(ids[3], "dns").ok and live.state == "setup"
    d = screen.race_dialog(live.race_id)
    assert d.scored and d.locked_note.isVisibleTo(d)
    assert live.undo().ok
    d = screen.race_dialog(live.race_id)
    assert not d.scored and d.field.isEnabled()


def test_a_madison_undone_to_its_start_takes_new_teams(screen, store, event):
    """A sprint scored, every entry undone, and the teams made over: a team
    whose riders changed is a new team with a new id, so the staged
    clicks and Undo start over, and the race scores with the new teams."""
    event_id, ids = event
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("madison"))
    d.number.setValue(2)
    d.choose_group("Group A")
    assert d.add_team("Red", [ids[3], ids[5]]) and d.add_team("Blue", [ids[7], ids[12]])
    mad = screen.add_race(_saving(d))
    red, blue = store.teams(mad)
    live = LiveRace(store, mad)
    assert live.click(red.team_id).ok and live.click(blue.team_id).ok
    assert live.record_sprint().ok
    assert live.act(blue.team_id, "lap_gained").ok
    d = screen.race_dialog(mad)
    assert d.scored and not d.teams_box.isEnabled()
    _undo_to_start(live)
    d = screen.race_dialog(mad)
    assert not d.scored and d.teams_box.isEnabled()
    # Red keeps its riders and takes a name; Blue is remade with another pair.
    assert d.edit_team(0, name="Red Rockets")
    assert d.edit_team(1, members=[ids[7], ids[3]])
    assert d.edit_team(0, members=[ids[5], ids[12]])
    assert d.save()
    teams = {t.name: t for t in store.teams(mad)}
    assert set(teams) == {"Red Rockets", "Blue"}
    assert set(teams["Red Rockets"].members) == {ids[5], ids[12]}
    assert set(teams["Blue"].members) == {ids[7], ids[3]}
    # The file hands the taken-out team's id to the next team added, so
    # the dead rows name the new Blue: nothing of them reaches the result.
    assert teams["Blue"].team_id == blue.team_id
    assert store.get_setting(f"race/{mad}/staged") is None
    live = LiveRace(store, mad)
    assert live.undo_text() == "Nothing to Undo"
    assert set(live.roster.ids) == {t.team_id for t in teams.values()}
    new_blue = teams["Blue"].team_id
    assert live.click(new_blue).ok and live.record_sprint().ok
    assert live.standings().by_entrant(new_blue).total_points == 5
    assert {r.entrant_id for r in live.standings().rows} == set(live.roster.ids)


def test_a_rider_leaves_the_roster_once_their_race_is_undone_to_its_start(screen, store, event):
    """Choose Riders' untick follows the same rule as the race dialog."""
    from madtracker.ui.setup.riders import remove_from_roster, rider_refusal

    event_id, ids = event
    race = store.add_race(event_id, "Chase", "chase")
    store.add_race_entry(race.race_id, ids[3])
    store.add_race_entry(race.race_id, ids[5])
    live = LiveRace(store, race.race_id)
    assert live.act(ids[3], "dnf").ok
    assert "has been scored" in rider_refusal(store, event_id, ids[3])[0]
    assert live.undo().ok
    assert rider_refusal(store, event_id, ids[3]) == ("", [store.race(race.race_id)])
    removed, _ = remove_from_roster(screen, store, event_id, ids[3], confirm=False)
    assert removed
    assert [e.rider_id for e in store.race_entries(race.race_id)] == [ids[5]]


def test_editing_a_race_with_its_default_name_shows_the_default_in_gray(screen, store, event):
    """A default name opens blank with the default as placeholder, and follows a new group."""
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("chase"))
    d.choose_group("Group A")
    assert d.save()
    race_id = d.race_id
    assert store.race(race_id).name == "Group A Scratch Race"
    d = screen.race_dialog(race_id)
    assert d.name.text() == "" and d.name.placeholderText() == "Group A Scratch Race"
    d.choose_group("Group B")
    assert d.save()
    assert store.race(race_id).name == "Group B Scratch Race"
    # A typed name opens as typed.
    store.update_race(race_id, name="Group B Final")
    d = screen.race_dialog(race_id)
    assert d.name.text() == "Group B Final"


def test_a_race_says_whom_it_is_for_even_once_scored(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    assert [d.gender.itemText(i) for i in range(d.gender.count())] == ["Men", "Women", "Mixed"]
    assert d.gender.currentText() == "Mixed"
    d.choose_group("Group A")
    assert d.save()
    race_id = d.race_id
    assert store.race(race_id).usac_gender == "Mixed"
    d = screen.race_dialog(race_id)
    d.gender.setCurrentText("Women")
    assert d.save()
    assert store.race(race_id).usac_gender == "Women"
    assert screen.race_dialog(race_id).gender.currentText() == "Women"
    # It changes nothing in the result, so a scored race can still change it.
    assert LiveRace(store, race_id).act(ids[3], "dnf").ok
    d = screen.race_dialog(race_id)
    assert d.gender.isEnabled() and d.locked_note.isVisibleTo(d)
    d.gender.setCurrentText("Men")
    assert d.save()
    assert store.race(race_id).usac_gender == "Men"


def test_the_usac_fields_default_from_the_group_and_its_last_race(screen, store, event):
    d = screen.race_dialog(None)
    labels = {label.buddy(): label.text() for label in d.usac_box.findChildren(QLabel)}
    assert [d.race_box.title(), d.usac_box.title()] == ["Race", "USAC CSV Details"]
    assert [labels[w] for w in (d.gender, d.category, d.usac_class, d.age_group)] == [
        "Gender",
        "Category",
        "Class",
        "Age group",
    ]
    assert all(w.toolTip() for w in (d.category, d.usac_class, d.age_group))
    d.choose_group("Group A")
    assert d.category.placeholderText() == "Group A"
    assert (d.usac_class.text(), d.age_group.text()) == ("", "")
    assert d.save()
    first = store.race(d.race_id)
    # A blank Category saves as the group; the group is no longer the class.
    assert (first.usac_category, first.usac_class, first.usac_age_group) == ("Group A", None, None)

    d = screen.race_dialog(first.race_id)
    d.category.setText(" Cat 3/4 ")
    d.usac_class.setText("Junior")
    d.age_group.setText("9-14")
    assert d.save()
    # The next race of the group starts from what that one used; another group does not.
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    assert (d.category.text(), d.usac_class.text(), d.age_group.text()) == ("", "Junior", "9-14")
    d.choose_group("Group B")
    assert (d.usac_class.text(), d.age_group.text()) == ("", "")
    # A value the scorer typed stays put when the group changes.
    d.usac_class.setText("Master")
    d.usac_class.setModified(True)
    d.choose_group("Group A")
    assert (d.usac_class.text(), d.age_group.text()) == ("Master", "9-14")
    race = store.race(first.race_id)
    assert (race.usac_category, race.usac_class, race.usac_age_group) == (
        "Cat 3/4",
        "Junior",
        "9-14",
    )


def test_the_usac_fields_offer_usacs_words_then_the_files(screen, store, event):
    """A value typed once is picked, spelled the same, every week after."""
    from madtracker.export.usac_csv import CATEGORIES, CLASSES

    d = screen.race_dialog(None)
    items = lambda box: [box.itemText(i) for i in range(box.count()) if box.itemText(i)]  # noqa: E731
    assert items(d.category) == list(CATEGORIES)
    assert items(d.usac_class) == list(CLASSES)
    assert items(d.age_group) == []
    d.choose_group("Group A")
    d.category.setText("Cat 1/2/3")
    d.usac_class.setText("junior")
    d.age_group.setText("9-14")
    assert d.save()
    d = screen.race_dialog(None)
    # Typed values follow USAC's after a separator; one already offered is not repeated.
    assert items(d.category) == [*CATEGORIES, "Cat 1/2/3"]
    assert items(d.usac_class) == list(CLASSES)
    assert items(d.age_group) == ["9-14"]
    # A blank Category saved as the group is the venue's word, never offered.
    assert "Group A" not in items(d.category)
    # Picked from the list, a value is the scorer's own: a group's suggestion keeps off it.
    d.usac_class.setCurrentIndex(CLASSES.index("Master"))
    d.usac_class.activated.emit(CLASSES.index("Master"))
    d.choose_group("Group A")
    assert d.usac_class.text() == "Master"


def test_edit_race_names_another_race_usac_would_see_as_this_one(screen, store, event):
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    assert not d.look_alike.isVisibleTo(d)
    assert d.save()
    first = store.race(d.race_id)
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    assert d.look_alike.isVisibleTo(d)
    assert d.look_alike.text() == f"Same USAC details as {first.name}."
    # A note, not a refusal; a Class sets them apart.
    d.usac_class.setText("Junior")
    assert not d.look_alike.isVisibleTo(d)
    d.usac_class.setText("")
    assert d.save()


def test_a_scored_race_still_changes_its_usac_fields(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    assert d.save()
    race_id = d.race_id
    assert LiveRace(store, race_id).act(ids[3], "dnf").ok
    d = screen.race_dialog(race_id)
    assert d.scored and d.locked_note.isVisibleTo(d)
    assert all(w.isEnabled() for w in (d.category, d.usac_class, d.age_group))
    d.category.setText("Open")
    d.usac_class.setText("Senior")
    d.age_group.setText("35+")
    assert d.save()
    race = store.race(race_id)
    assert (race.usac_category, race.usac_class, race.usac_age_group) == ("Open", "Senior", "35+")
    # Cleared, the category falls back to the group as it does on a new race.
    d = screen.race_dialog(race_id)
    d.category.setText("")
    d.age_group.setText("")
    assert d.save()
    race = store.race(race_id)
    assert (race.usac_category, race.usac_age_group) == ("Group A", None)


def test_the_group_fills_the_field_only_when_picked_from_the_list(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    assert set(d.field_ids()) == {ids[3], ids[5]}
    d.set_in_field(ids[7], True)
    # Typing, or a text change from code, leaves the hand-made field alone.
    d.group.setCurrentText("Group B")
    d.group.lineEdit().setText("Group")
    assert set(d.field_ids()) == {ids[3], ids[5], ids[7]}
    # A pick from the list is what refills it.
    d.group.activated.emit(d.group.findText("Group B"))
    assert set(d.field_ids()) == {ids[7], ids[12]}


def _madison(screen, ids):
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("madison"))
    d.number.setValue(2)
    d.choose_group("Group A")
    return d


def test_madison_teams_are_checked_before_anything_is_written(screen, store, event):
    event_id, ids = event
    blue = ("Blue", "Blue", su.PALETTE["Blue"])
    red = ("Red", "Red", su.PALETTE["Red"])
    wolves = ("Wolves", "Green", su.PALETTE["Green"])
    cases = [
        ([(*blue, [ids[3]]), (*red, [ids[7], ids[12]])], "Team Blue has one rider."),
        ([(*blue, [ids[3], ids[5]]), (*blue, [ids[7], ids[12]])], "There are two Blue teams."),
        (
            [(*blue, [ids[3], ids[5]]), (*red, [ids[5], ids[7]])],
            "Priya Okafor is on team Blue and team Red.",
        ),
        (
            [(*wolves, [ids[3], ids[5]]), ("wolves", "Red", su.PALETTE["Red"], [ids[7], ids[12]])],
            "There are two teams named wolves.",
        ),
        (
            [
                (*wolves, [ids[3], ids[5]]),
                ("Bears", "Green", su.PALETTE["Green"], [ids[7], ids[12]]),
            ],
            "There are two Green teams.",
        ),
    ]
    for teams, message in cases:
        d = _madison(screen, ids)
        d.teams = [(n, c, h, list(m)) for n, c, h, m in teams]
        assert not d.save()
        assert d.error.text() == message
        assert store.races(event_id) == []


def test_a_failing_save_leaves_no_race(screen, store, event, monkeypatch):
    from madtracker.store import StoreError

    event_id, ids = event
    d = _madison(screen, ids)
    assert d.add_team("Blue", [ids[3], ids[5]]) and d.add_team("Red", [ids[7], ids[12]])

    def fail(*_a, **_k):
        raise StoreError("the disk is full")

    monkeypatch.setattr(store, "add_team_member", fail)
    assert not d.save()
    assert "disk is full" in d.error.text()
    assert store.races(event_id) == [] and d.race_id is None


def test_a_team_may_have_a_name_and_a_blank_name_is_its_color(screen, store, event):
    event_id, ids = event
    d = _madison(screen, ids)
    assert d.add_team("Blue", [ids[3], ids[5]], name="Wolves")
    assert d.add_team("Red", [ids[7], ids[12]], name="  ")
    assert d.teams == [
        ("Wolves", "Blue", su.PALETTE["Blue"], [ids[3], ids[5]]),
        ("Red", "Red", su.PALETTE["Red"], [ids[7], ids[12]]),
    ]
    table = d.teams_table
    # The swatch shows the color, so the name stands alone.
    assert [table.item(0, c).text() for c in range(2)] == ["Wolves", "Marcus Delgado, Priya Okafor"]  # fmt: skip
    assert [table.item(1, c).text() for c in range(2)] == ["Red", "Maya Petrakis, Tess Gallagher"]  # fmt: skip
    assert d.save()
    assert [(t.name, t.color, t.color_hex, t.members) for t in store.teams(d.race_id)] == [
        ("Wolves", "Blue", su.PALETTE["Blue"], (ids[3], ids[5])),
        ("Red", "Red", su.PALETTE["Red"], (ids[7], ids[12])),
    ]
    # Opened again, the dialog reads them back as they were saved; an edit
    # replaces the stored team and leaves the other alone.
    again = screen.race_dialog(d.race_id)
    assert again.teams == d.teams
    red_id = store.teams(d.race_id)[1].team_id
    assert again.edit_team(0, name="Hawks") and again.save()
    assert [(t.name, t.color, t.members) for t in store.teams(d.race_id)] == [
        ("Hawks", "Blue", (ids[3], ids[5])),
        ("Red", "Red", (ids[7], ids[12])),
    ]
    assert store.teams(d.race_id)[1].team_id == red_id
    # The dialog: a blank name reads as the picked color, and follows it.
    td = su.TeamDialog([(ids[3], "3 Marcus"), (ids[5], "5 Priya")], set(), 2)
    assert td.windowTitle() == "Add Team" and td.name.placeholderText() == "Blue"
    td.color.setCurrentText("Green")
    assert td.name.placeholderText() == "Green" and td.team_name() == "Green"
    td.name.setText(" Wolves ")
    assert td.team_name() == "Wolves"
    assert td.name.maxLength() == TEAM_NAME_MAX
    # Only a team saved under its color's own spelling comes back blank.
    riders = [(ids[3], "3 Marcus"), (ids[5], "5 Priya")]
    for name, shown in (("Red", ""), ("RED", "RED")):
        td = su.TeamDialog(riders, set(), 2, team=(name, "Red", [ids[3], ids[5]]))
        assert td.name.text() == shown and td.team_name() == name


def test_a_team_name_is_refused_when_taken_or_when_it_reads_as_a_bib(screen, store, event):
    event_id, ids = event
    d = _madison(screen, ids)
    assert d.add_team("Blue", [ids[3], ids[5]], name="Wolves")
    assert not d.add_team("Red", [ids[7], ids[12]], name="wolves")
    assert d.error.text() == "There is already a team named wolves."
    assert not d.add_team("Red", [ids[7], ids[12]], name="12")
    assert "would read as a bib" in d.error.text()
    assert not d.add_team("Blue", [ids[7], ids[12]], name="Bears")
    assert d.error.text() == "There is already a Blue team."
    assert len(d.teams) == 1
    # The dialog refuses the same on its own line, and stays open.
    td = su.TeamDialog(
        [(ids[7], "7 Maya"), (ids[12], "12 Tess")], {"blue"}, 2, used_names={"wolves"}
    )
    td.check(ids[7])
    td.check(ids[12])
    td.name.setText("Wolves")
    assert not td.accept_team() and td.error.text() == "There is already a team named Wolves."
    td.name.setText("7")
    assert not td.accept_team() and "would read as a bib" in td.error.text()
    td.name.setText("")
    td.color.setCurrentText("Blue")
    assert not td.accept_team() and td.error.text() == "There is already a Blue team."
    td.color.setCurrentText("Red")
    assert td.accept_team()


def test_edit_team_changes_a_team_in_place(screen, store, event, monkeypatch):
    event_id, ids = event
    # A fifth rider in the field, on no team, for the edit dialog's list below.
    late = store.add_rider("Cy", "Dorn")
    store.add_entry(event_id, late.rider_id, 20, local_group="Group A")
    d = _madison(screen, ids)
    assert not d.edit_team_button.isEnabled() and not d.remove_team_button.isEnabled()
    assert d.edit_team_button.toolTip() == "Select a team first"
    assert d.remove_team_button.toolTip() == "Select a team first"
    assert d.add_team("Blue", [ids[3], ids[5]]) and d.add_team("Red", [ids[7], ids[12]])
    assert not d.edit_team() and d.error.text() == "Select a team first."
    d.teams_table.selectRow(0)
    assert d.edit_team_button.isEnabled() and d.edit_team_button.toolTip() == ""
    # A team named by its color follows a color change; a swap of riders is one edit of each.
    assert d.edit_team(color="Green", members=[ids[3], ids[7]])
    assert d.teams[0] == ("Green", "Green", su.PALETTE["Green"], [ids[3], ids[7]])
    assert d.teams_table.currentRow() == 0, "the edited team stays selected"
    assert not d.edit_team(1, color="Green") and d.error.text() == "There is already a Green team."
    assert d.edit_team(1, name="Wolves", members=[ids[5], ids[12]])
    assert d.teams[1] == ("Wolves", "Red", su.PALETTE["Red"], [ids[5], ids[12]])
    assert d.edit_team(1, color="Yellow")
    assert d.teams[1][:2] == ("Wolves", "Yellow"), "a given name stays when the color changes"
    # The dialog opens on the team as it is: its own riders ticked and listed
    # along with those on no team, the name blank when it is the color.
    opened = []

    def fake_exec(dialog):
        opened.append(dialog)
        dialog.check(ids[3], False)
        accepted = dialog.accept_team()
        return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(su.TeamDialog, "exec", fake_exec)
    d.teams_table.selectRow(0)
    assert not d.edit_team(), "the dialog refuses one rider and stays open"
    td = opened[0]
    assert td.windowTitle() == "Edit Team" and td.name.text() == ""
    assert td.color.currentText() == "Green"
    assert td.findChild(QPushButton, "primary").text() == "Save Team"
    assert td.error.text() == "A team here has 2 riders; 1 ticked."
    listed = {td.list.item(i).data(su.ID_ROLE) for i in range(td.list.count())}
    assert listed == {ids[3], ids[7], late.rider_id}
    assert d.teams[0][3] == [ids[3], ids[7]], "a refused edit changes nothing"

    def fake_exec_ok(dialog):
        dialog.check(ids[3], False)
        dialog.check(late.rider_id)
        dialog.name.setText("Hawks")
        return QDialog.DialogCode.Accepted if dialog.accept_team() else QDialog.DialogCode.Rejected

    monkeypatch.setattr(su.TeamDialog, "exec", fake_exec_ok)
    assert d.edit_team()
    assert d.teams[0][:3] == ("Hawks", "Green", su.PALETTE["Green"])
    assert sorted(d.teams[0][3]) == sorted([ids[7], late.rider_id])


def test_a_double_click_on_a_team_opens_its_edit(screen, store, event, monkeypatch):
    event_id, ids = event
    d = _madison(screen, ids)
    assert d.add_team("Blue", [ids[3], ids[5]]) and d.add_team("Red", [ids[7], ids[12]])
    opened = []

    def fake_exec(dialog):
        opened.append(dialog.windowTitle())
        dialog.color.setCurrentText("Orange")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(su.TeamDialog, "exec", fake_exec)
    d.teams_table.selectRow(1)
    d.teams_table.cellDoubleClicked.emit(1, 2)
    assert opened == ["Edit Team"]
    assert d.teams[1] == ("Orange", "Orange", su.PALETTE["Orange"], [ids[7], ids[12]])


def test_an_untick_refuses_a_team_member_and_asks_for_a_field_rider(
    qtbot, store, event, monkeypatch
):
    event_id, ids = event
    d = su.RidersDialog(store, event_id)
    qtbot.addWidget(d)
    asked = []
    answer = [False]
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or answer[0])
    madison = store.add_race(event_id, "Madison", "madison")
    for rid in (ids[3], ids[5]):
        store.add_race_entry(madison.race_id, rid)
    team = store.add_team(madison.race_id, "Blue", color="Blue")
    store.add_team_member(team.team_id, ids[3])
    store.add_team_member(team.team_id, ids[5])
    chase = store.add_race(event_id, "Chase", "chase")
    store.add_race_entry(chase.race_id, ids[7])
    points = store.add_race(event_id, "Points", "points")
    store.add_race_entry(points.race_id, ids[7])
    # On a team: refused, nothing asked, nothing removed.
    assert not d.set_on_roster(ids[3], False)
    assert d.status.text() == "Marcus Delgado is on team Blue in Madison. Edit that race first."  # fmt: skip
    assert asked == [] and store.entry(event_id, ids[3]).bib == 3
    # In fields only: asked, with the races; Cancel keeps the rider.
    assert not d.set_on_roster(ids[7], False)
    assert asked == ["Remove Maya Petrakis from this event? They are in: Chase, Points."]
    assert store.entry(event_id, ids[7]).bib == 7
    answer[0] = True
    assert d.set_on_roster(ids[7], False)
    assert [e.rider_id for e in store.entries(event_id)] == [ids[3], ids[5], ids[12]]
    # In no race: removed without a question.
    asked.clear()
    assert d.set_on_roster(ids[12], False)
    assert asked == []


def test_the_program_shows_at_least_six_rows(qtbot, store, event):
    event_id, _ = event
    w = su.SetupScreen()
    qtbot.addWidget(w)
    w.resize(1100, 1100)
    w.load(store, event_id)
    w.show()
    qtbot.waitExposed(w)
    rows_shown = (w.program.viewport().height()) // w.program.verticalHeader().defaultSectionSize()
    assert rows_shown >= su.PROGRAM_MIN_ROWS
    for i in range(10):
        store.add_race(event_id, f"Race {i}", "chase")
    w.refresh()
    assert w.program.height() >= w.program_height(su.PROGRAM_MIN_ROWS)
    # A long program gives way to the roster at half the screen.
    assert w.program.height() <= max(w.program_height(su.PROGRAM_MIN_ROWS), w.height() // 2)
    assert w.program.height() < w.program_height(16)


def test_a_click_anywhere_on_a_field_row_ticks_the_rider_once(qtbot, screen, store, event):
    """The box is a small target; the row is the control, and a click is one toggle."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    event_id, ids = event
    d = screen.race_dialog(None)
    qtbot.addWidget(d)
    d.show()
    QApplication.processEvents()
    item = next(
        d.field.item(i)
        for i in range(d.field.count())
        if d.field.item(i).data(su.ID_ROLE) == ids[7]
    )
    rect = d.field.visualItemRect(item)
    # On the name, well right of the box.
    QTest.mouseClick(d.field.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert d.field_ids() == [ids[7]]
    # On the box itself: still one toggle, not Qt's and ours.
    on_box = QPoint(rect.left() + 10, rect.center().y())
    QTest.mouseClick(d.field.viewport(), Qt.MouseButton.LeftButton, pos=on_box)
    assert d.field_ids() == []
    # A team's riders are picked the same way.
    team = su.TeamDialog([(ids[3], "3 Marcus"), (ids[5], "5 Priya")], set(), 2)
    qtbot.addWidget(team)
    team.show()
    QApplication.processEvents()
    QTest.mouseClick(
        team.list.viewport(),
        Qt.MouseButton.LeftButton,
        pos=team.list.visualItemRect(team.list.item(0)).center(),
    )
    assert team.members() == [ids[3]]


def test_the_group_box_opens_its_list_on_a_click_and_enter_never_refills(
    qtbot, screen, store, event
):
    """A click anywhere on the box opens the list; typed text is a name, not a pick."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    event_id, ids = event
    d = screen.race_dialog(None)
    qtbot.addWidget(d)
    d.show()
    QApplication.processEvents()
    c = d.group
    assert c.lineEdit().placeholderText() == "No group"
    QTest.mouseClick(c.lineEdit(), Qt.MouseButton.LeftButton, pos=QPoint(20, c.height() // 2))
    assert c.view().isVisible(), "a click on the text opens the list"
    QTest.keyClick(c.view(), Qt.Key.Key_Down)
    QTest.keyClick(c.view(), Qt.Key.Key_Return)
    assert c.currentText() == "Group B" and set(d.field_ids()) == {ids[7], ids[12]}
    # A letter typed while the list is open closes it and goes into the box.
    QTest.mouseClick(c.lineEdit(), Qt.MouseButton.LeftButton, pos=QPoint(20, c.height() // 2))
    assert c.view().isVisible()
    QTest.keyClick(c.view(), Qt.Key.Key_M)
    assert not c.view().isVisible() and c.currentText() == "m"
    # Enter on a typed group, with the list closed, saves the race as Enter
    # in Name does; the typed text is the race's group and never a list entry.
    d.set_in_field(ids[3], True)
    accepted = []
    d.accepted.connect(lambda: accepted.append(1))
    c.lineEdit().setFocus()
    c.lineEdit().selectAll()
    QTest.keyClicks(c.lineEdit(), "Juniors")
    QTest.keyClick(c.lineEdit(), Qt.Key.Key_Return)
    assert c.currentText() == "Juniors" and c.findText("Juniors") < 0
    assert accepted == [1], d.error.text()
    assert store.race(d.race_id).group_label == "Juniors"
    assert {e.rider_id for e in store.race_entries(d.race_id)} == {ids[7], ids[12], ids[3]}


def test_enter_on_a_group_row_renames_it_as_a_double_click_does(screen, store, event, monkeypatch):
    from PySide6.QtTest import QTest

    opened = []
    monkeypatch.setattr(
        su.RenameGroupDialog,
        "exec",
        lambda _d: opened.append("rename") or int(QDialog.DialogCode.Rejected),
    )
    monkeypatch.setattr(
        su.NewGroupDialog,
        "exec",
        lambda _d: opened.append("new") or int(QDialog.DialogCode.Rejected),
    )
    d = screen.groups_dialog()
    d.show()
    d.select_group("Group B")
    d.table.setFocus()
    QTest.keyClick(d.table, Qt.Key.Key_Return)
    assert opened == ["rename"], "Enter renames the row, never New Group..."
    d.table.activated.emit(d.table.model().index(d.table.currentRow(), 0))
    assert opened == ["rename", "rename"]
    assert not any(b.autoDefault() for b in (d.new, d.rename, d.delete))
    d.close()


def test_the_roster_count_says_who_has_no_group(screen, store, event):
    event_id, ids = event
    assert screen.roster_count.text() == "4 riders"
    store.set_entry_group(event_id, ids[3], None)
    screen.refresh()
    assert screen.roster_count.text() == "4 riders, 1 without a group"
    for rid in ids.values():
        store.set_entry_group(event_id, rid, None)
    screen.refresh()
    assert screen.roster_count.text() == "4 riders, no groups yet"


def test_a_click_on_a_gray_roster_cell_starts_typing(qtbot, screen, store, event):
    from PySide6.QtWidgets import QApplication, QComboBox

    screen.show()
    QApplication.processEvents()
    screen._roster_clicked(0, su.GROUP)
    editors = [w for w in screen.roster.viewport().findChildren(QComboBox) if w.isVisible()]
    assert len(editors) == 1, "the Group cell opens its list editor on one click"
    screen._roster_clicked(0, su.LAST)
    assert screen.roster.state() == screen.roster.State.EditingState, "the editor is unchanged"


def test_the_roster_keeps_no_door_to_a_riders_own_details(screen):
    """Riders are made and kept in the Riders window only; the roster is a choice from them."""
    texts = [b.text() for b in screen.roster_box.findChildren(QPushButton)]
    assert texts == ["Choose Riders...", "Edit Groups..."]
    assert not hasattr(screen, "edit_rider")


def test_groups_lists_each_group_and_renames_merges_and_deletes(screen, store, event, monkeypatch):
    """A group is one row: its riders and races; Rename follows the races until one is scored."""
    event_id, ids = event
    store.set_entry_group(event_id, ids[12], "Gruop B")
    store.set_entry_group(event_id, ids[5], "Juniors")
    chase = store.add_race(event_id, "Chase", "chase", group_label="Group A")
    d = screen.groups_dialog()
    assert d.windowTitle() == "Edit Groups: Test Night"
    # A group is made before anyone is in it, and the roster's cell offers it.
    new = su.NewGroupDialog(store, event_id, d)
    assert new.name.placeholderText() == "Group A"
    new.name.setText("  Semi  Pro ")
    assert new.submit() and new.made == "Semi Pro"
    monkeypatch.setattr(su.NewGroupDialog, "exec", lambda _d: int(QDialog.DialogCode.Accepted))
    assert d.new_group(new)
    assert d.status.text() == ""
    # A taken or blank name is refused in the dialog, which stays open with the text.
    again = su.NewGroupDialog(store, event_id, d)
    again.name.setText("semi pro")
    assert not again.submit() and again.made is None
    assert again.error.text() == "A group named Semi Pro already exists."
    assert again.name.text() == "semi pro" and again.result() != QDialog.DialogCode.Accepted
    again.name.setText("  ")
    assert not again.submit() and again.error.text() == "The group needs a name."
    assert "Semi Pro" in su.event_spellings(store, event_id)
    d.select_group("Semi Pro")
    assert d.delete.isEnabled()
    assert d.delete_selected(), "a group nobody is in goes without a question"
    assert "Semi Pro" not in su.event_spellings(store, event_id)
    rows = [
        [d.table.item(r, c).text() for c in range(d.table.columnCount())]
        for r in range(d.table.rowCount())
    ]
    assert rows == [
        ["Group A", "1", "Chase"],
        ["Group B", "1", ""],
        ["Gruop B", "1", ""],
        ["Juniors", "1", ""],
    ]
    # A group a race was made from is not deleted, and says why under Delete.
    d.select_group("Group A")
    assert d.rename.isEnabled() and d.rename_why.text() == ""
    assert not d.delete.isEnabled() and d.delete_why.text() == "Used by a race"
    # A slip is merged by renaming it to the group it meant, after a question.
    asked = []
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or True)
    d.select_group("Gruop B")
    r = d.rename_dialog()
    assert r.windowTitle() == "Rename Gruop B"
    r.group.setCurrentText("group b")
    assert r.submit() and r.made == "Group B"
    monkeypatch.setattr(su.RenameGroupDialog, "exec", lambda _d: int(QDialog.DialogCode.Accepted))
    assert d.rename_selected(r)
    assert asked == ["Merge Gruop B into Group B? Its 1 rider joins Group B."]
    assert store.entry(event_id, ids[12]).local_group == "Group B"
    assert d.status.text() == ""
    assert [d.table.item(r, 0).text() for r in range(d.table.rowCount())] == [
        "Group A",
        "Group B",
        "Juniors",
    ]
    # A rename reaches the riders and the unscored races made from the group.
    d.select_group("Group A")
    r = d.rename_dialog()
    r.group.setCurrentText("Group  Alpha")
    assert r.submit() and d.rename_selected(r)
    assert store.entry(event_id, ids[3]).local_group == "Group Alpha"
    # A declined merge keeps the dialog open and says nothing on its line.
    monkeypatch.setattr(icons, "ask", lambda *a, **k: False)
    d.select_group("Juniors")
    r = d.rename_dialog()
    r.group.setCurrentText("Group B")
    assert not r.submit() and r.made is None and r.error.text() == ""
    assert store.entry(event_id, ids[5]).local_group == "Juniors"
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[2]) or True)
    assert store.race(chase.race_id).group_label == "Group Alpha"
    # Delete leaves the riders with no group, after a question.
    asked.clear()
    d.select_group("Juniors")
    assert d.delete_selected()
    assert asked == ["Delete Juniors? Its 1 rider is left with no group."]
    assert not store.entry(event_id, ids[5]).local_group
    # Once a race has run under a group, its name is history.
    store.append_action(chase.race_id, "status", {"entrant_id": ids[3], "status": "DNS"}, 1)
    d.refresh()
    d.select_group("Group Alpha")
    assert not d.rename.isEnabled() and d.rename_why.text() == "Has raced"
    assert d.rename_dialog() is None
    monkeypatch.setattr(su.GroupsDialog, "exec", lambda _d: int(QDialog.DialogCode.Accepted))
    screen.manage_groups(d)
    assert [r[2] for r in roster_rows(screen)][0] == "Group Alpha"


def test_import_preview_details_width_does_not_follow_the_scroll_bar(
    qtbot, store, event, tmp_path, riders
):
    """The Details width decides the row heights, and so whether the scroll
    bar shows; if the bar's coming and going moved the width, the two would
    feed each other and the preview would hang on Windows. The width ignores
    the bar."""
    from PySide6.QtWidgets import QApplication

    path = tmp_path / "entries.csv"
    path.write_text(CSV, encoding="utf-8")
    preview = riders.preview_for(path)
    qtbot.addWidget(preview)
    preview.resize(900, 400)
    preview.show()
    t = preview.table
    # At 150% Windows scaling the bar's real width and its size hint
    # differ by a pixel or two; a fit that leaned on either would keep moving.
    bar = t.verticalScrollBar()
    hint = bar.sizeHint()
    bar.sizeHint = lambda: hint + QSize(2, 0)
    widths = []
    real_rows = t.rowCount()
    for rows in (real_rows, 80):
        # More rows than fit bring the bar, as long Details would.
        t.setRowCount(rows)
        for _ in range(3):
            QApplication.processEvents()
        preview._fit_details()
        widths.append((t.verticalScrollBar().isVisible(), t.columnWidth(su.DETAILS)))
    t.setRowCount(real_rows)
    assert [shown for shown, _ in widths] == [False, True]
    assert widths[0][1] == widths[1][1]


def test_the_sprint_count_starts_blank_and_takes_the_events_last_count(screen, store, event):
    """A default of one sprint saved unnoticed would make a points race its
    final sprint on the first click."""
    event_id, ids = event
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("points"))
    d.choose_group("Group A")
    assert d.number.value() == 0 and d.number.text().strip() == ""
    assert not d.save() and d.error.text() == "Set the number of sprints."
    d.number.setValue(6)
    assert d.save()
    again = screen.race_dialog(None)
    again.format.setCurrentIndex(again.format.findData("points"))
    assert again.number.value() == 6
    assert su.race_number(store.race(d.race_id)) == "6 sprints"


def test_a_race_with_a_group_may_wait_for_its_riders(screen, store, event):
    """The program can be built before the roster: the field follows the group."""
    event_id, ids = event
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("chase"))
    assert not d.save() and d.error.text() == "Pick a group or tick the riders."
    d.group.setCurrentText("Juniors")
    assert d.save() and store.race_entries(d.race_id) == []


def test_the_field_lists_the_riders_in_the_race_first(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    d.choose_group("Group B")
    ticked = [d.field.item(i).checkState() == Qt.CheckState.Checked for i in range(d.field.count())]
    assert ticked == sorted(ticked, reverse=True) and any(ticked)


def test_choose_riders_with_no_riders_says_so(qtbot, store):
    event_id = store.add_event("First Night", "2026-10-17").event_id
    d = su.RidersDialog(store, event_id)
    qtbot.addWidget(d)
    assert d.roster_count.text() == "No riders yet"
    assert d.table.rowCount() == 0


def test_a_file_imported_again_for_its_bibs_ticks_the_rows_it_changes(
    screen, store, event, tmp_path, riders
):
    """A second import is how the bibs arrive, and
    its rows read as left out, with "by license" on each."""
    first_file = tmp_path / "entries.csv"
    first_file.write_text(CSV, encoding="utf-8")
    first = riders.preview_for(first_file)
    assert first.apply()
    again = tmp_path / "entries-bibs.csv"
    with_bibs = CSV.replace("Group A,\n", "Group A,70\n").replace("Group B,\n", "Group B,71\n")
    again.write_text(with_bibs, encoding="utf-8")
    preview = riders.preview_for(again)
    t = preview.table
    assert preview.ticked() == [0, 1]
    assert t.item(0, su.ACTION).text() == "On file"
    assert t.item(0, su.DETAILS).text() == "bib: none -> 70"
    assert "license" not in t.item(1, su.DETAILS).text()


def test_every_big_dialog_fits_a_1366_by_768_screen_at_125_percent(
    qtbot, store, event, tmp_path, monkeypatch
):
    """Windows does not shrink a dialog taller than the screen, so its
    Save or Close would sit under the taskbar. A 1366 by 768 laptop at 125%
    has a 1093 by 576 work area; the room is what widgets.screen_room
    leaves of it for a client area there."""
    from madtracker.control.rulesets import builtin_ruleset
    from madtracker.ui import about, help, rulesets, settings, widgets

    room = QSize(1093 - 2 * style.MD, 576 - widgets.FRAME_ALLOWANCE - style.MD)
    monkeypatch.setattr(widgets, "screen_room", lambda _w: room)
    monkeypatch.setattr(about, "screen_room", lambda _w: room)
    event_id, _ids = event
    race = store.add_race(event_id, "Chase", "chase")
    points = store.add_race(event_id, "Points", "points")
    built = {
        "About": about.AboutDialog(),
        "Licenses": about.LicensesDialog(),
        "Help": help.HelpWindow(),
        "Settings": settings.SettingsDialog(store, tmp_path),
        "Rulesets": rulesets.RulesetsDialog(store),
        "Edit Ruleset": rulesets.RulesetEditor(store, {**builtin_ruleset(), "name": "House"}),
        "Edit Riders": su.RidersDialog(store, None),
        "Choose Riders": su.RidersDialog(store, event_id),
        "Open Event": su.OpenEventDialog(store, event_id),
        "Add Race": su.RaceDialog(store, event_id),
        "Edit Race": su.RaceDialog(store, event_id, race.race_id),
        # A sprint count is one more row, and the tallest race dialog.
        "Edit points race": su.RaceDialog(store, event_id, points.race_id),
        "Groups": su.GroupsDialog(store, event_id),
    }
    for name, d in built.items():
        qtbot.addWidget(d)
        d.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        d.show()
        QApplication.processEvents()
        assert d.width() <= room.width() and d.height() <= room.height(), (name, d.size())
        hint = d.minimumSizeHint()
        assert hint.width() <= room.width() and hint.height() <= room.height(), (name, hint)
    # Every dialog that closes with a Close button takes the platform's
    # Close key, as the help window does; the OK-and-Cancel dialogs have Escape.
    close_key = QKeySequence(QKeySequence.StandardKey.Close)
    for name in ("About", "Licenses", "Help", "Settings", "Rulesets", "Edit Riders", "Groups"):
        keys = [a.shortcut() for a in built[name].actions()]
        assert close_key in keys, name
    # Every ruleset tab's label shows, none scrolled out of sight.
    tabs = built["Edit Ruleset"].tabs
    assert tabs.tabBar().sizeHint().width() <= tabs.width()


def _preview_of(riders, tmp_path, text: str):
    path = tmp_path / "entries.csv"
    path.write_text(text, encoding="utf-8")
    return riders.preview_for(path)


def test_import_preview_names_possible_matches_and_holds_a_shared_license(
    store, event, tmp_path, riders
):
    """Details names who a row may be, a license two
    new rows share holds the later one, and a same-name pair notes each other."""
    store.add_rider("Rafa", "Quint", usac_license="710017")
    preview = _preview_of(
        riders,
        tmp_path,
        "Last Name,First Name,USAC License,Category,Bib\n"
        "Quint,Rafael,710027,Masters 40+,\n"
        "Lindqvist,Ava,710050,Juniors,\n"
        "Lindqvist,Noor,710050,Juniors,\n"
        "Okafor,Adaeze,,Group C,\n"
        "Okafor,Adaeze N.,,Group C,\n",
    )
    t = preview.table
    assert t.item(0, su.DETAILS).text() == "may be Rafa Quint (USAC License 710017)"
    assert t.item(2, su.DETAILS).text() == "the file gives USAC License 710050 to Ava Lindqvist too"
    assert t.item(3, su.DETAILS).text() == "looks like row 5, Adaeze N. Okafor"
    assert t.item(4, su.DETAILS).text() == "looks like row 4, Adaeze Okafor"
    assert preview.ticked() == [0, 1, 3, 4]
    preview.select_all.click()
    assert preview.ticked() == [0, 1, 3, 4], "the shared license stays off"
    preview.close()


def test_import_preview_holds_a_riders_later_registration_in_another_group(
    store, event, tmp_path, riders
):
    """One rider in two categories: each row says so and the later one starts
    unticked, so the scorer picks tonight's group instead of the last row winning."""
    store.add_rider("Odile", "Pelletier", usac_license="710016")
    preview = _preview_of(
        riders,
        tmp_path,
        "Last Name,First Name,USAC License,Category,Bib\n"
        "Pelletier,Odile,710016,Masters 40+,\n"
        "Pelletier,Odile,710016,Group W,\n",
    )
    t = preview.table
    assert t.item(0, su.DETAILS).text() == "also registered as Group W (row 2)"
    assert t.item(1, su.DETAILS).text() == (
        "same rider as an earlier row; also registered as Masters 40+ (row 1)"
    )
    assert preview.ticked() == [0]
    preview.select_all.click()
    assert preview.ticked() == [0]
    assert preview.apply()
    (entry,) = [e for e in store.entries(event[0]) if e.bib is None]
    assert entry.local_group == "Masters 40+"


def test_import_preview_says_the_files_bib_and_group_for_a_rostered_rider(
    store, event, tmp_path, riders
):
    """The roster's bib and group stay; Details says what the file has, so a
    re-import for a corrected category shows why nothing moved."""
    preview = _preview_of(
        riders,
        tmp_path,
        "Last Name,First Name,Category,Bib\nDelgado,Marcus,Group B,30\n",
    )
    t = preview.table
    assert (t.item(0, su.P_BIB).text(), t.item(0, su.P_GROUP).text()) == ("3", "Group A")
    assert t.item(0, su.DETAILS).text() == (
        "matched by name; already on this roster; file says bib 30 (roster has 3);"
        " file says Group B (roster has Group A)"
    )
    preview.close()


def test_import_preview_group_cell_picks_from_the_events_and_files_groups(
    qtbot, store, event, tmp_path, riders
):
    """The roster's picker in the preview: a slip can't make a group of one."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QComboBox

    preview = _preview_of(
        riders,
        tmp_path,
        "Last Name,First Name,USAC License,Category,Bib\n"
        "Quill,Ada,100001,Juniors,1\n"
        "Lin,Bo,100002,Group B,2\n",
    )
    qtbot.addWidget(preview)
    preview.show()
    QApplication.processEvents()
    t = preview.table

    def open_group(row: int) -> QComboBox:
        t.setCurrentCell(row, su.P_GROUP)
        t.editItem(t.item(row, su.P_GROUP))
        QApplication.processEvents()
        (combo,) = [c for c in t.viewport().findChildren(QComboBox) if c.isVisible()]
        return combo

    combo = open_group(0)
    assert combo.isEditable()
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "No Group",
        "Group A",
        "Group B",
        "Juniors",
    ]
    assert combo.currentText() == "Juniors"
    # Typed, a group takes the listed spelling.
    combo.lineEdit().selectAll()
    QTest.keyClicks(combo.lineEdit(), "group  a")
    QTest.keyClick(combo.lineEdit(), Qt.Key.Key_Return)
    assert t.item(0, su.P_GROUP).text() == "Group A"
    assert (t.currentRow(), t.currentColumn()) == (1, su.P_GROUP), "Enter goes down the column"
    combo = open_group(1)
    combo.setCurrentIndex(0)
    QTest.keyClick(combo.lineEdit(), Qt.Key.Key_Tab)
    assert t.item(1, su.P_GROUP).text() == "", "No group is no group"
    preview.done(QDialog.DialogCode.Rejected)


def test_import_shows_its_result_line_when_a_row_was_adjusted(store, event, tmp_path, riders):
    """An id held back is news: the scorer ticked a conflict, and the rider came in without it."""
    store.add_rider("Cora", "Abbott", usac_license="710001")
    preview = _preview_of(
        riders,
        tmp_path,
        "Last Name,First Name,USAC License,Category,Bib\nVargas,Mate,710001,Juniors,\n",
    )
    preview.set_checked(0, True)
    assert preview.apply()
    riders.import_done(preview)
    assert riders.status.isVisibleTo(riders)
    assert riders.status.text() == (
        "1 new rider, 0 riders updated, 1 on the event's roster. 1 adjusted."
        " 1 rider has no bib yet."
        " Mate Vargas added without USAC License 710001; it is on file for another rider"
    )


def test_the_review_warns_when_both_names_differ(qtbot, store, event):
    """Three differences out of three is likely another person; the window says so once."""
    from madtracker.importers.bikereg import ImportRow, choose, plan_import

    cora = store.add_rider("Cora", "Abbott", usac_license="710001")
    rows = [ImportRow(first="Mate", last="Vargas", usac_license="710001", line=2)]
    plans = choose(store, event[0], plan_import(store, event[0], rows), 0, cora.rider_id)
    dialog = su.ReconcileDialog(store, plans[0], 1, 1)
    qtbot.addWidget(dialog)
    assert dialog.warning.isVisibleTo(dialog)
    assert dialog.warning.text() == "Both names differ: this may be another rider."
    rows = [ImportRow(first="Corinne", last="Abbott", usac_license="710001", line=2)]
    (plan,) = plan_import(store, event[0], rows)
    dialog = su.ReconcileDialog(store, plan, 1, 1)
    qtbot.addWidget(dialog)
    assert not dialog.warning.isVisibleTo(dialog)


def test_import_preview_holds_a_new_row_with_a_rider_of_the_same_name_as_new_check(
    store, event, tmp_path, riders
):
    """A rider of the same name on file starts
    the row unticked as New?, counted "to check"; Select all and Select new
    leave it off. Same as or New in the Status list answers it."""
    store.add_rider("Rafa", "Quint", usac_license="710017")
    store.add_rider("Odile", "Pelletier", usac_license="710040", birth_year=1980)
    preview = _preview_of(
        riders,
        tmp_path,
        "Last Name,First Name,USAC License,Category,Bib\n"
        "Quint,Rafa,710027,Masters 40+,\n"
        "Pelletier,Odile,,Women Open,\n"
        "Quint,Rafe,,Masters 40+,\n"
        "Zulu,Zed,100009,Group A,\n",
    )
    t = preview.table
    combos = [preview.action_choice(r) for r in range(3)]
    assert [c.currentText() for c in combos] == ["New?", "New?", "New"]
    assert preview.action_choice(3) is None and t.item(3, su.ACTION).text() == "New"
    assert preview.intro.text() == "4 registrations: 2 new, 2 to check."
    assert t.item(0, su.DETAILS).text() == "may be Rafa Quint (USAC License 710017)"
    assert t.item(1, su.DETAILS).text() == "may be Odile Pelletier (USAC License 710040)"
    assert preview.ticked() == [2, 3], "a same-initial candidate stays ticked"
    preview.select_all.click()
    assert preview.ticked() == [2, 3]
    preview.select_new.click()
    assert preview.ticked() == [2, 3]
    # Same as Rafa Quint: a match, ticked.
    combos[0].setCurrentIndex(1)
    assert t.item(0, su.ACTION).text() == "Review"
    assert combos[0].currentText() == "Review: Same as Rafa Quint (USAC License 710017)"
    assert preview.ticked() == [0, 2, 3]
    # Back to New: answered, so it reads New and stays ticked.
    combos[0].setCurrentIndex(0)
    assert (t.item(0, su.ACTION).text(), combos[0].currentText()) == ("New", "New")
    assert preview.ticked() == [0, 2, 3]
    assert preview.intro.text() == "4 registrations: 3 new, 1 to check."
    # Ticking a New? row by hand imports it as a new rider.
    preview.set_checked(1, True)
    assert preview.apply()
    assert len(preview.result.created) == 4
    assert [r.usac_license for r in store.riders() if r.last_name == "Pelletier"] == [
        "710040",
        None,
    ]


def test_import_preview_notes_a_nickname_and_matches_a_blank_license_on_birth_year(
    store, event, tmp_path, riders, monkeypatch
):
    """Marc on Marcus's license is
    noted, never reviewed; Priya with no license this week is Priya on file
    when both birth years agree, and keeps her license."""
    event_id, ids = event
    store.update_rider(ids[3], usac_license="500003")
    store.update_rider(ids[5], usac_license="500005", birth_year=1990)
    preview = _preview_of(
        riders,
        tmp_path,
        "Last Name,First Name,USAC License,Age on 12/31/2026,Category,Bib\n"
        "Delgado,Marc,500003,,Group A,\n"
        "Okafor,Priya,,36,Group A,\n",
    )
    t = preview.table
    assert [t.item(r, su.ACTION).text() for r in range(2)] == ["On file", "On file"]
    assert preview.intro.text() == "2 registrations: 2 on file."
    assert t.item(0, su.DETAILS).text() == "already on this roster; registered as Marc"
    assert t.item(1, su.DETAILS).text() == "matched by name; already on this roster"
    monkeypatch.setattr(su.ReconcileDialog, "exec", lambda d: pytest.fail("reviewed"))
    preview.select_all.click()
    assert preview.apply()
    assert store.rider(ids[3]).first_name == "Marcus"
    assert store.rider(ids[5]).usac_license == "500005"
    assert preview.result.created == [] and len(store.entries(event_id)) == 4


def test_a_rider_out_of_the_races_group_is_counted_in_the_program_and_the_dialog(
    qtbot, store, event
):
    """A rider racing out of their group shows where the
    program is set up, never on the board or in the USAC CSV."""
    event_id, ids = event
    race = store.add_race(event_id, "Chase A", "placings", group_label="Group A")
    for rid in (ids[3], ids[5], ids[7]):  # two of Group A, one of Group B
        store.add_race_entry(race.race_id, rid)
    screen = su.SetupScreen()
    qtbot.addWidget(screen)
    screen.load(store, event_id)
    field = su.PROGRAM_HEADERS.index("Field")
    assert screen.program.item(0, field).text() == "3 riders, 1 from Group B"
    dialog = su.RaceDialog(store, event_id, race.race_id)
    qtbot.addWidget(dialog)
    assert dialog.field_count.text() == "3 riders in the field, 1 from Group B"


def _commits(store) -> list[str]:
    """The COMMITs the store sends from here on: each is an fsync of the WAL."""
    seen: list[str] = []
    store.connection.set_trace_callback(
        lambda sql: seen.append(sql) if sql.lstrip().upper().startswith("COMMIT") else None
    )
    return seen


def test_saving_a_race_is_one_commit_and_refills_only_the_program(
    screen, store, event, monkeypatch
):
    """A Save is one commit, not one per rider in the field (each an fsync
    on a Windows laptop), and leaves the roster, which a race never changes."""
    event_id, ids = event
    filled = []
    for name in ("_fill_roster", "_fill_program", "_fill_field"):
        cls = su.RaceDialog if name == "_fill_field" else su.SetupScreen
        real = getattr(cls, name)
        monkeypatch.setattr(
            cls,
            name,
            lambda self, *a, _n=name, _r=real, **k: (filled.append(_n), _r(self, *a, **k))[1],
        )
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("points"))
    d.number.setValue(3)
    d.choose_group("Group A")
    d.set_in_field(ids[7], True)
    filled.clear()
    commits = _commits(store)
    d.exec = lambda: (d.save(), d.result())[1]
    race_id = screen.add_race(d)
    assert len(commits) == 1
    assert {e.rider_id for e in store.race_entries(race_id)} == {ids[3], ids[5], ids[7]}
    assert filled == ["_fill_program"]
    # Edit race reads the field once, not empty and then again with its riders.
    filled.clear()
    e = screen.race_dialog(race_id)
    assert filled == ["_fill_field"]
    e.set_in_field(ids[7], False)
    e.exec = lambda: (e.save(), e.result())[1]
    monkeypatch.setattr(screen, "race_dialog", lambda _rid: e)
    filled.clear()
    assert screen.edit_race(race_id)
    assert len(commits) == 2 and filled == ["_fill_program"]


def test_select_all_on_the_import_preview_checks_the_rows_once(
    store, event, tmp_path, riders, monkeypatch
):
    """Select all is one check, touching only the cells that change: a
    check per tick, re-setting every cell and measuring every column each
    time, would take most of a minute on 60 rows."""
    path = tmp_path / "entries.csv"
    rows = "".join(f"Newcomb{i},Ann,{900000 + i},Group A,\n" for i in range(12))
    path.write_text("Last Name,First Name,USAC License,Category,Bib\n" + rows, encoding="utf-8")
    preview = riders.preview_for(path)
    checks = []
    real_check = su.ImportPreview._check
    monkeypatch.setattr(su.ImportPreview, "_check", lambda self, *a: (checks.append(1), real_check(self, *a))[1])  # fmt: skip
    flags = []
    real_flags = su.QTableWidgetItem.setFlags
    monkeypatch.setattr(su.QTableWidgetItem, "setFlags", lambda item, f: (flags.append(f), real_flags(item, f))[1])  # fmt: skip
    preview.select_none.click()
    assert checks == [1] and preview.ticked() == []
    # Every unticked row's Bib and Group become read-only: 24 cells, once each.
    assert len(flags) == 24
    checks.clear()
    flags.clear()
    preview.select_none.click()
    assert checks == [1] and flags == [], "nothing changed, nothing set"
    checks.clear()
    preview.select_all.click()
    assert checks == [1] and len(flags) == 24 and len(preview.ticked()) == 12
    preview.close()


def _saving(d):
    d.exec = lambda: (d.save(), d.result())[1]
    return d


def test_duplicate_fills_a_new_race_from_the_selected_one_and_puts_it_after(screen, store, event):
    """Another but similar race without retyping it."""
    event_id, ids = event
    d = screen.race_dialog(None)
    d.name.setText("6 Mile Points")
    d.format.setCurrentIndex(d.format.findData("points"))
    d.number.setValue(3)
    d.choose_group("Group A")
    d.set_in_field(ids[7], True)
    d.usac_class.setText("Senior")
    first = screen.add_race(_saving(d))
    last = screen.add_race(_saving(_chase_for_group_b(screen)))
    screen.program.selectRow(0)
    assert screen.duplicate_race_button.isEnabled()

    copy = screen.race_dialog(None, copy_of=first)
    assert copy.windowTitle() == "Duplicate Race" and copy.race_id is None
    # A typed name comes selected, so typing replaces it.
    assert copy.name.text() == "6 Mile Points" and copy.name.selectedText() == "6 Mile Points"
    assert (copy.format_key(), copy.number.value(), copy.group.currentText()) == (
        "points",
        3,
        "Group A",
    )
    assert set(copy.field_ids()) == {ids[3], ids[5], ids[7]}
    assert copy.usac_class.text() == "Senior"
    copy.name.setText("4 Mile Points")
    new = screen.duplicate_race(first, _saving(copy))
    assert new not in (None, first, last)
    assert [r.race_id for r in store.races(event_id)] == [first, new, last]
    race = store.race(new)
    assert (race.name, race.format, race.group_label, race.rules["sprint_count"]) == (
        "4 Mile Points",
        "points",
        "Group A",
        3,
    )
    assert {e.rider_id for e in store.race_entries(new)} == {ids[3], ids[5], ids[7]}
    assert selected_race(screen) == new
    # The original is untouched.
    assert store.race(first).name == "6 Mile Points"


def _chase_for_group_b(screen):
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("chase"))
    d.choose_group("Group B")
    return d


def selected_race(screen):
    return su.selected_id(screen.program)


def test_duplicate_copies_a_madisons_teams_and_unlocks_a_scored_race(screen, store, event):
    event_id, ids = event
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("madison"))
    d.number.setValue(2)
    d.choose_group("Group A")
    assert d.add_team("Red", [ids[3], ids[5]]) and d.add_team("Blue", [ids[7], ids[12]])
    mad = screen.add_race(_saving(d))
    team = store.teams(mad)[0]
    assert LiveRace(store, mad).act(team.team_id, "dnf").ok
    copy = screen.race_dialog(None, copy_of=mad)
    # A default name stays the default, and nothing is locked: the copy is unscored.
    assert copy.name.text() == "" and not copy.scored
    assert all(w.isEnabled() for w in copy.locked_widgets())
    assert [(t[1], t[3]) for t in copy.teams] == [
        ("Red", [ids[3], ids[5]]),
        ("Blue", [ids[7], ids[12]]),
    ]
    new = screen.duplicate_race(mad, _saving(copy))
    assert sorted(t.color for t in store.teams(new)) == ["Blue", "Red"]
    assert store.race(new).state == "setup"


def test_a_cancelled_duplicate_saves_nothing(screen, store, event):
    event_id, _ids = event
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    first = screen.add_race(_saving(d))
    copy = screen.race_dialog(None, copy_of=first)
    copy.exec = lambda: QDialog.DialogCode.Rejected
    assert screen.duplicate_race(first, copy) is None
    assert [r.race_id for r in store.races(event_id)] == [first]


def test_the_field_lists_the_race_then_its_group_then_the_rest_each_by_bib(screen, store, event):
    """The field lists in bib order; by last name the bibs starting each row read as no order."""
    _event_id, ids = event
    d = screen.race_dialog(None)
    d.choose_group("Group B")
    d.set_in_field(ids[12], False)
    d._fill_field(d.field_ids())
    order = [d.field.item(i).data(su.ID_ROLE) for i in range(d.field.count())]
    # Tess (12) left the field: the field (7), then Group B (12), then Group A by bib (3, 5).
    assert order == [ids[7], ids[12], ids[3], ids[5]]


def test_every_filter_box_follows_the_race_dialog_rule(qtbot, screen, store, event):
    """A habit learned in one filter box works in the rest."""
    _event_id, ids = event
    d = su.RidersDialog(store, None)
    qtbot.addWidget(d)
    for text in ("Maya P", "akis", "petrakis maya"):
        d.search.setText(text)
        assert d.shown_ids() == [ids[7]], text
    d.search.setText("#7")
    assert d.shown_ids() == [], "the riders list has no bibs"
    race = screen.race_dialog(None)
    assert race.field_filter.placeholderText() == "Filter by name, group, or bib"


def test_the_field_filter_hides_rows_and_keeps_their_ticks(screen, store, event):
    _event_id, ids = event
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    shown = lambda: [  # noqa: E731
        d.field.item(i).data(su.ID_ROLE)
        for i in range(d.field.count())
        if not d.field.item(i).isHidden()
    ]
    d.field_filter.setText("okafor")
    assert shown() == [ids[5]]
    d.field_filter.setText("maya p")
    assert shown() == [ids[7]]
    d.field_filter.setText("#7")
    assert shown() == [ids[7]]
    # "#1" is bib 1, which nobody wears; a bare 1 finds #12 by its digits.
    d.field_filter.setText("#1")
    assert shown() == []
    d.field_filter.setText("1")
    assert shown() == [ids[12]]
    d.field_filter.setText("group b")
    assert set(shown()) == {ids[7], ids[12]}
    # Riders filtered out stay in the field.
    assert set(d.field_ids()) == {ids[3], ids[5]}
    d.field_filter.setText("")
    assert len(shown()) == 4


def test_esc_in_a_filter_clears_it_before_it_closes_the_window(qtbot, screen, store, event):
    """Esc in a filter starts the search over before it ever closes the dialog."""
    from madtracker.ui.widgets import FilterBox

    d = screen.race_dialog(None)
    qtbot.addWidget(d)
    d.show()
    d.field_filter.setFocus()
    qtbot.keyClicks(d.field_filter, "okafor")
    qtbot.keyClick(d.field_filter, Qt.Key.Key_Escape)
    assert d.field_filter.text() == "" and d.isVisible()
    qtbot.keyClick(d.field_filter, Qt.Key.Key_Escape)
    assert not d.isVisible(), "an empty box passes Esc on to the window"
    riders = su.RidersDialog(store, event[0])
    qtbot.addWidget(riders)
    assert isinstance(riders.search, FilterBox)


def test_enter_in_the_field_filter_checks_the_top_match_and_never_saves(
    qtbot, screen, store, event
):
    """Enter works as it does in Choose riders, not as Save."""
    _event_id, ids = event
    d = screen.race_dialog(None)
    qtbot.addWidget(d)
    d.show()
    d.choose_group("Group A")
    qtbot.keyClicks(d.field_filter, "#12")
    qtbot.keyClick(d.field_filter, Qt.Key.Key_Return)
    assert d.isVisible() and d.race_id is None and store.races(event[0]) == []
    assert ids[12] in d.field_ids() and d.field_filter.text() == ""
    qtbot.keyClicks(d.field_filter, "nobody")
    qtbot.keyClick(d.field_filter, Qt.Key.Key_Return)
    assert d.error.text() == "No rider matches." and d.field_filter.text() == "nobody"


def test_a_duplicate_for_another_group_follows_it_and_keeps_its_usac_values(screen, store, event):
    d = screen.race_dialog(None)
    d.choose_group("Group A")
    d.usac_class.setText("Senior")
    d.age_group.setText("35+")
    first = screen.add_race(_saving(d))
    assert store.race(first).usac_category == "Group A"
    copy = screen.race_dialog(None, copy_of=first)
    # A Category that was only the group follows the new one.
    assert copy.category.text() == ""
    copy.choose_group("Group B")
    assert copy.category.placeholderText() == "Group B"
    # Copied values are the scorer's: the new group does not clear them.
    assert (copy.usac_class.text(), copy.age_group.text()) == ("Senior", "35+")
    new = screen.duplicate_race(first, _saving(copy))
    race = store.race(new)
    assert (race.group_label, race.usac_category, race.usac_class) == (
        "Group B",
        "Group B",
        "Senior",
    )


def test_edit_and_duplicate_keep_a_win_and_outs_places(screen, store, event):
    """Edit and Duplicate keep the stored count; the ruleset's default never replaces it."""
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("win_and_out"))
    d.choose_group("Group A")
    d.number.setValue(5)
    first = screen.add_race(_saving(d))
    assert store.race(first).rules["places"] == 5
    edit = screen.race_dialog(first)
    assert edit.number.value() == 5
    edit.name.setText("Renamed")
    assert edit.save()
    assert store.race(first).rules["places"] == 5
    assert screen.race_dialog(None, copy_of=first).number.value() == 5


def test_a_race_keeps_its_rules_when_its_ruleset_is_renamed_or_deleted(screen, store, event):
    """Edit race keeps a race's rules when no ruleset has its name, never saving the default's."""
    from madtracker.control import rulesets as rs

    doc = dict(rs.ruleset_for(store, rs.BUILTIN))
    doc["name"] = "Club X"
    doc["points_table"] = [3, 2, 1]
    row = rs.save_ruleset(store, doc)
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("points"))
    d.ruleset.setCurrentIndex(d.ruleset.findData("Club X"))
    d.number.setValue(3)
    d.choose_group("Group A")
    race_id = screen.add_race(_saving(d))
    made = store.race(race_id).rules
    assert made["intermediate_points"] == [3, 2, 1]

    # Renamed: the race follows the name, and an Edit keeps its rules.
    doc["name"] = "Club Y"
    rs.save_ruleset(store, doc, row.ruleset_id)
    assert store.race(race_id).rules_preset == "Club Y"
    edit = screen.race_dialog(race_id)
    assert edit.ruleset.currentData() == "Club Y"
    edit.name.setText("Renamed once")
    assert edit.save() and store.race(race_id).rules == made

    # Deleted: the race keeps the rules it holds and the old name, marked
    # on screen only.
    rs.delete_ruleset(store, row.ruleset_id)
    edit = screen.race_dialog(race_id)
    assert edit.ruleset.currentData() == "Club Y"
    assert edit.ruleset.currentText() == "Club Y (deleted)"
    screen.refresh()
    ruleset_col = su.PROGRAM_HEADERS.index("Ruleset")
    assert screen.program.item(0, ruleset_col).text() == "Club Y (deleted)"
    edit.name.setText("Renamed twice")
    edit.number.setValue(4)
    assert edit.save()
    kept = store.race(race_id).rules
    assert kept["intermediate_points"] == [3, 2, 1] and kept["sprint_count"] == 4
    copy = screen.race_dialog(None, copy_of=race_id)
    new = screen.duplicate_race(race_id, _saving(copy))
    assert store.race(new).rules["intermediate_points"] == [3, 2, 1]
    assert store.race(race_id).rules_preset == "Club Y"


UNPRINTABLE = "王小明"


def test_a_name_the_sheets_cannot_print_is_said_while_typed_and_never_refused(
    qtbot, screen, store, event, tmp_path
):
    """Every name that prints on a sheet says on its red line, while typed,
    that the sheets will show "?" for letters they lack; the line clears with
    the letters, a refusal standing there is left alone, and the name saves."""
    from madtracker.ui import settings
    from madtracker.ui.widgets import NameDialog

    event_id, ids = event
    note = su.UNPRINTABLE_NOTE
    riders = [(ids[3], "3 Marcus"), (ids[5], "5 Priya")]
    rider_form = su.RiderForm(store, None)
    race = su.RaceDialog(store, event_id)
    cases = [
        (rider_form, rider_form.first, rider_form.error),
        (rider_form, rider_form.last, rider_form.error),
        (team := su.TeamDialog(riders, set(), 2), team.name, team.error),
        (race, race.name, race.error),
        (race, race.group.lineEdit(), race.error),
        (new := su.NewEventDialog(store), new.name, new.error),
        (s := settings.SettingsDialog(store, tmp_path), s.venue_name, s.error),
        (n := NameDialog("New Group", "Add", lambda _t: None), n.field, n.error),
        (screen, screen.name, screen.event_status),
        (screen, screen.series.lineEdit(), screen.event_status),
    ]
    for owner, field, line in cases:
        if owner is not screen:
            qtbot.addWidget(owner)
        field.setText("Maya")
        assert line.text() == "", owner
        field.setText(f"Maya {UNPRINTABLE}")
        assert line.text() == note, owner
        field.setText("Maya")
        assert line.text() == "", owner
        line.setText("A refusal")
        field.setText("Mayas")
        assert line.text() == "A refusal", owner
        line.setText("")
    # The event's line is a form row shown only while it has something to say.
    screen.name.setText(UNPRINTABLE)
    assert screen.event_form.isRowVisible(screen.event_status)
    screen.name.setText("Test Night")
    assert not screen.event_form.isRowVisible(screen.event_status)
    # Said, never refused: the rider is saved under the name as typed.
    form = su.RiderForm(store, None)
    qtbot.addWidget(form)
    form.first.setText(UNPRINTABLE)
    form.last.setText("Lin")
    assert form.error.text() == note
    assert form.save()
    assert any(r.first_name == UNPRINTABLE for r in store.riders())


def test_a_roster_group_the_sheets_cannot_print_is_kept_and_said(screen, store, event):
    event_id, ids = event
    row = screen.row_of(ids[3])
    screen.roster.item(row, su.GROUP).setText(f"Group {UNPRINTABLE}")
    assert store.entry(event_id, ids[3]).local_group == f"Group {UNPRINTABLE}"
    assert screen.roster_status.text() == su.UNPRINTABLE_NOTE
    screen.roster.item(row, su.GROUP).setText("Group A")
    assert screen.roster_status.text() == ""


def test_an_import_row_the_sheets_cannot_print_is_flagged_and_imported(store, event, qtbot):
    from madtracker.importers.bikereg import parse, plan_import

    csv = (
        "Last Name,First Name,USAC License,Category,Bib\n"
        f"Lin,{UNPRINTABLE},100001,Group A,\n"
        "Lin,Bo,100002,Group B,\n"
    )
    preview = su.ImportPreview(store, event[0], plan_import(store, event[0], parse(csv)))
    qtbot.addWidget(preview)
    flag = 'some letters in the name print as "?" on the PDF sheets'
    details = [preview.table.item(r, su.DETAILS).text() for r in range(2)]
    assert flag in details[0] and flag not in details[1]
    assert preview.table.item(0, su.USE).checkState() == preview.table.item(1, su.USE).checkState()


def test_a_click_on_the_series_text_opens_the_earlier_series(qtbot, store, event):
    """The Series box opens its list on a click anywhere, as every typed-into list does."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    store.add_event("Spring Opener", "2026-04-04", series="Spring Series")
    w = su.SetupScreen()
    qtbot.addWidget(w)
    w.load(store, event[0])
    w.show()
    QApplication.processEvents()
    c = w.series
    assert c.count()
    QTest.mouseClick(c.lineEdit(), Qt.MouseButton.LeftButton, pos=QPoint(20, c.height() // 2))
    assert c.view().isVisible(), "a click on the text opens the list"
    c.hidePopup()
