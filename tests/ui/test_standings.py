"""File > Multi-Race Standings: the dialog over the demo's two-night Team Omnium."""

import pytest
from apps import dispose_app
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog

from madtracker.control import multi_race, rulesets
from madtracker.control.demo import (
    DEMO_FOUR_RACE_STANDINGS,
    DEMO_RIDER_STANDINGS,
    DEMO_STANDINGS,
)
from madtracker.control.race import LiveRace
from madtracker.dates import show_date
from madtracker.ui import icons
from madtracker.ui.rulesets import TABLE_TIP
from madtracker.ui.standings import BAD_PLACES, NO_MADISON, NO_RACE, NOTE_ROLE, StandingsDialog
from madtracker.ui.widgets import ID_ROLE, NameDialog


@pytest.fixture
def app(qapp, tmp_path):
    from madtracker.app import AppController

    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    c = AppController(qapp, demo=True, settings=settings, data_dir=tmp_path / "data")
    yield c
    dispose_app(c)


def tonights_madison(c) -> int:
    """Tonight's 4 Mile Madison, one sprint in: Blue, Red, Black, Orange (Red scores 3)."""
    (race,) = [r for r in c.store.races(c.event.event_id) if r.name == "4 Mile Madison"]
    teams = {t.name: t.team_id for t in c.store.teams(race.race_id)}
    session = LiveRace(c.store, race.race_id)
    for name in ("Blue", "Red", "Black", "Orange"):
        assert session.click(teams[name]).ok
    assert session.record_sprint().ok
    return race.race_id


def tonight() -> str:
    """The demo's race night is seeded on today's date, as 2026-Oct-18."""
    from datetime import date

    return show_date(date.today())


def last_night() -> str:
    from datetime import date, timedelta

    return show_date(date.today() - timedelta(days=1))


def short(shown: str) -> str:
    """The race column's date, "Oct-18", from a shown date."""
    return shown[5:]


@pytest.fixture
def dialog(app):
    d = StandingsDialog(app.store, app.main, export=lambda standings_id: None)
    yield d
    d.deleteLater()


def headers(table) -> list[str]:
    return table.headers()


def column(table, word: str) -> list[str]:
    return table.column(word)


def item_texts(check_list) -> list[str]:
    return [check_list.item(i).text() for i in range(check_list.count())]


def tick(check_list, text: str) -> None:
    """A click on the row, as the scorer ticks it."""
    (i,) = [i for i in range(check_list.count()) if check_list.item(i).text() == text]
    check_list.itemClicked.emit(check_list.item(i))


def test_the_file_menu_opens_the_dialog(app, monkeypatch):
    opened = []
    monkeypatch.setattr(QDialog, "exec", lambda self: opened.append(self) or 0)
    app.main.standings_action.trigger()
    (d,) = opened
    assert isinstance(d, StandingsDialog) and d.windowTitle() == "Multi-Race Standings"
    assert d.names() == [DEMO_STANDINGS, DEMO_FOUR_RACE_STANDINGS, DEMO_RIDER_STANDINGS]


def test_the_demo_standings_shows_three_madisons_and_the_four_teams_that_rode_them(app):
    tonights_madison(app)
    d = StandingsDialog(app.store, app.main)
    assert d.name.text() == DEMO_STANDINGS and d.kind.currentText() == "Team Omnium by Points"
    assert item_texts(d.events) == [
        f"Demo Race Night ({tonight()})",
        f"Demo Opening Night ({last_night()})",
    ]
    (table,) = d.standings_views
    assert headers(table) == [
        "Place",
        "Team",
        "Riders",
        f"{short(last_night())}\n8 Mile Madison",
        f"{short(last_night())}\n4 Mile Madison",
        f"{short(tonight())}\n4 Mile Madison",
        "Total",
    ]
    # Green rode only last night and Black only tonight: both left out.
    # Last night's 8 Mile Madison (ended after two sprints) and 4 Mile
    # Madison, then tonight's first sprint: Blue 18 + 10 + 5 = 33, Orange
    # 1 + 17 + 1 = 19, Red 6 + 5 + 3 = 14, Yellow 1 + 9 = 10.
    assert column(table, "Team") == ["Blue", "Orange", "Red", "Yellow"]
    totals = dict(zip(column(table, "Team"), column(table, "Total"), strict=True))
    assert totals["Red"] == "14", "Red's 11 last night and 3 tonight"
    assert "\n" in column(table, "Riders")[0], "a pair is listed one rider per line"
    # The Standings box is read, not picked from.
    for part in table.parts:
        assert part.selectionMode() == part.SelectionMode.NoSelection
        assert part.focusPolicy() == Qt.FocusPolicy.NoFocus and part.alternatingRowColors()
    assert d.state.text() == "" and d.state.styleSheet() == "", (
        "no tag until the standings are final"
    )
    assert d.detail.text().endswith("3 of 4 Madisons raced over 2 events")
    assert d.export_button.isEnabled()
    d.deleteLater()


def test_the_races_list_tonights_madisons_under_their_night(dialog):
    texts = item_texts(dialog.races)
    assert texts == [
        f"Demo Race Night ({tonight()})",
        "8 Mile Madison (Group A)",
        "4 Mile Madison (Group A)",
        f"Demo Opening Night ({last_night()})",
        "8 Mile Madison (Group A)",
        "4 Mile Madison (Group A)",
    ]
    heading = dialog.races.item(0)
    assert not heading.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert all(dialog.race_ticks().values())


def test_unticking_an_event_drops_its_column_and_changes_the_total(app, dialog):
    tonights_madison(app)
    dialog.refresh()
    assert len(headers(dialog.standings_views[0])) == 7
    tick(dialog.events, f"Demo Race Night ({tonight()})")
    standings = app.store.get_standings(dialog.shown_id)
    assert len(standings.event_ids) == 1, "the tick is saved at once"
    (table,) = dialog.standings_views
    assert f"{short(tonight())}\n4 Mile Madison" not in headers(table)
    # Last night alone: Green rode every Madison that counts now.
    # Blue 18 + 10, Orange 1 + 17, Red 6 + 5, Yellow 1 + 9, Green 4 + 2.
    assert column(table, "Team") == ["Blue", "Orange", "Red", "Yellow", "Green"]
    assert column(table, "Total")[0] == "28"
    assert item_texts(dialog.races) == [
        f"Demo Opening Night ({last_night()})",
        "8 Mile Madison (Group A)",
        "4 Mile Madison (Group A)",
    ]
    tick(dialog.events, f"Demo Opening Night ({last_night()})")
    assert not dialog.races.isVisibleTo(dialog) and dialog.no_races.isVisibleTo(dialog)
    assert dialog.no_races.text() == NO_MADISON
    assert dialog.row_count() == 0 and not dialog.export_button.isEnabled()


def test_unticking_a_race_drops_its_column(app, dialog):
    race_id = tonights_madison(app)
    dialog.refresh()
    i = [dialog.races.item(i).data(Qt.ItemDataRole.UserRole) for i in range(dialog.races.count())]
    dialog.races.itemClicked.emit(dialog.races.item(i.index(race_id)))
    assert app.store.get_standings(dialog.shown_id).excluded_race_ids == [race_id]
    assert headers(dialog.standings_views[0])[3:-1] == [
        f"{short(last_night())}\n8 Mile Madison",
        f"{short(last_night())}\n4 Mile Madison",
    ]
    # The night unticked and ticked again keeps the race left out.
    tick(dialog.events, f"Demo Race Night ({tonight()})")
    tick(dialog.events, f"Demo Race Night ({tonight()})")
    assert app.store.get_standings(dialog.shown_id).excluded_race_ids == [race_id]


def test_add_refuses_a_blank_name_and_says_the_stores_refusal_of_a_taken_one(app, dialog):
    assert dialog.add("  ") is None
    assert dialog.status.text() == "The standings needs a name."
    assert dialog.add(DEMO_STANDINGS.upper()) is None
    assert dialog.status.text() == f"A standings named {DEMO_STANDINGS} already exists."
    made = dialog.add("Oktoberfest 2 Day Omnium")
    assert made is not None and dialog.status.text() == ""
    assert dialog.selected_id() == made and dialog.name.text() == "Oktoberfest 2 Day Omnium"
    assert dialog.ticked_events() == [] and dialog.no_races.isVisibleTo(dialog)
    assert dialog.state.text() == ""


def test_add_asks_for_the_name_and_refuses_in_the_dialog(dialog, monkeypatch):
    """The name dialog keeps a refused name in its field; the next try is one correction."""
    asked = []

    def run(self):
        asked.append((self.windowTitle(), self.text()))
        self.field.setText(DEMO_STANDINGS.lower())
        assert not self.submit(), "a taken name is refused in place"
        assert self.error.text() == f"A standings named {DEMO_STANDINGS} already exists."
        assert self.text() == DEMO_STANDINGS.lower()
        self.field.setText("  ")
        assert not self.submit() and self.error.text() == "The standings needs a name."
        self.field.setText(
            "Rumble 2026-27" if self.windowTitle() == "Add Standings" else "Rumble 2"
        )
        assert self.submit()
        return self.result()

    monkeypatch.setattr(NameDialog, "exec", run)
    dialog.add_button.click()
    assert asked == [("Add Standings", "")] and "Rumble 2026-27" in dialog.names()
    assert dialog.status.text() == ""
    dialog.duplicate_button.click()
    assert asked[-1] == ("Duplicate Standings", "Rumble 2026-27 copy")
    assert "Rumble 2" in dialog.names() and dialog.name.text() == "Rumble 2"


def test_the_place_points_field_carries_the_rulesets_tip(dialog):
    assert dialog.place_points.toolTip() == TABLE_TIP


def test_duplicate_copies_the_events_and_left_out_races(app, dialog):
    source = app.store.get_standings(dialog.selected_id())
    made = dialog.duplicate("Copy")
    copy = app.store.get_standings(made)
    assert copy.event_ids == source.event_ids and copy.kind == source.kind
    assert dialog.duplicate("copy") is None and "already exists" in dialog.status.text()


def test_the_kind_is_a_choice_saved_at_once_with_the_new_kinds_defaults(app, dialog):
    kind = dialog.kind
    assert [kind.itemText(i) for i in range(kind.count())] == [
        "Team Omnium by Points",
        "Team Omnium by Place",
        "Omnium by Place",
        "Four-Race Omnium",
    ]
    sid = dialog.shown_id
    app.store.update_standings(sid, rules={"absent_points": -5})
    dialog.refresh()
    assert dialog.table.detail == "Each team's Madison totals are summed."
    kind.setCurrentIndex(1)
    stored = app.store.get_standings(sid)
    assert stored.kind == multi_race.PLACES and stored.rules == {}, (
        "a kind starts from its defaults"
    )
    assert dialog.table.detail.startswith(
        "Each team scores points for its place in each Madison, 7-5-3-2-1,"
    )
    kind.setCurrentIndex(0)
    assert app.store.get_standings(sid).kind == multi_race.TOTALS


def test_the_place_points_row_shows_only_for_the_place_kinds(dialog):
    form, field = dialog.form, dialog.place_points
    assert not form.isRowVisible(field)
    dialog.set_kind(multi_race.PLACES)
    assert form.isRowVisible(field) and field.text() == "7, 5, 3, 2, 1"
    dialog.set_kind(multi_race.TOTALS)
    assert not form.isRowVisible(field)
    dialog.set_kind(multi_race.OMNIUM)
    assert form.isRowVisible(field) and field.text() == "7, 5, 3, 2, 1"
    # The Four-Race Omnium's table is the rulebook's: nothing to set.
    dialog.set_kind(multi_race.FOUR_RACE)
    assert not form.isRowVisible(field)


def test_place_points_parse_and_save_and_junk_is_refused_on_the_red_line(app, dialog):
    tonights_madison(app)
    dialog.refresh()
    sid = dialog.shown_id
    dialog.set_kind(multi_race.PLACES)
    (table,) = dialog.standings_views
    # Blue leads on 7-5-3-2-1: 1st, 2nd, and 1st tonight, 7 + 5 + 7.
    assert column(table, "Team")[0] == "Blue" and column(table, "Total")[0] == "19"
    dialog.place_points.setText("5,4 3  2, 1")
    dialog.place_points.editingFinished.emit()
    assert app.store.get_standings(sid).rules == {"points_by_place": [5, 4, 3, 2, 1]}
    assert dialog.place_points.text() == "5, 4, 3, 2, 1" and dialog.status.text() == ""
    (table,) = dialog.standings_views
    # The same places on the new table: 5 + 4 + 5.
    assert column(table, "Total")[0] == "14", "the Standings box follows the table"
    # The sheet's own form parses too, and shows as the field's.
    dialog.place_points.setText("5-4-3-2-1")
    dialog.place_points.editingFinished.emit()
    assert dialog.place_points.text() == "5, 4, 3, 2, 1" and dialog.status.text() == ""
    for junk in ("", "7, five", "7, -1", "1000"):
        dialog.place_points.setText(junk)
        dialog.place_points.editingFinished.emit()
        assert dialog.status.text() == BAD_PLACES, junk
        assert dialog.place_points.text() == "5, 4, 3, 2, 1"
    assert app.store.get_standings(sid).rules == {"points_by_place": [5, 4, 3, 2, 1]}


def test_the_longest_place_points_table_shows_uncut(app, dialog):
    """Fifty places at 999 written out run past the plain text cap: a cut field would
    save a shorter table than the one typed."""
    dialog.refresh()
    sid = dialog.shown_id
    dialog.set_kind(multi_race.PLACES)
    full = rulesets.table_text([rulesets.TABLE_MAX] * rulesets.MAX_COUNT)
    dialog.place_points.setText(full)
    dialog.place_points.editingFinished.emit()
    assert dialog.status.text() == ""
    assert dialog.place_points.text() == full
    stored = app.store.get_standings(sid).rules["points_by_place"]
    assert stored == [rulesets.TABLE_MAX] * rulesets.MAX_COUNT


def test_close_with_refused_place_points_says_why_once_then_closes(dialog):
    dialog.show()
    dialog.set_kind(multi_race.PLACES)
    dialog.place_points.setText("lots")
    dialog.close_button.click()
    assert dialog.isVisible() and dialog.status.text() == BAD_PLACES
    dialog.close_button.click()
    assert not dialog.isVisible()


def test_duplicate_keeps_the_kind_and_its_place_points(app, dialog):
    dialog.set_kind(multi_race.PLACES)
    dialog.place_points.setText("10 6 3")
    dialog.place_points.editingFinished.emit()
    made = dialog.duplicate("Copy")
    copy = app.store.get_standings(made)
    assert copy.kind == multi_race.PLACES and copy.rules == {"points_by_place": [10, 6, 3]}
    assert dialog.kind.currentText() == "Team Omnium by Place"
    assert dialog.place_points.text() == "10, 6, 3"


def test_a_refused_rename_puts_the_old_name_back(app, dialog, qapp):
    dialog.add("Other")
    dialog.select(DEMO_STANDINGS)
    dialog.name.setText("other")
    assert not dialog.save_name()
    assert dialog.name.text() == DEMO_STANDINGS and "already exists" in dialog.status.text()
    dialog.name.setText("Weekend")
    dialog.name.editingFinished.emit()
    qapp.processEvents()
    others = [DEMO_FOUR_RACE_STANDINGS, DEMO_RIDER_STANDINGS]
    assert dialog.names() == [*others, "Other", "Weekend"] and dialog.name.text() == "Weekend"


def test_delete_asks_then_deletes(app, dialog, monkeypatch):
    for s in app.store.list_standings():
        if s.name != DEMO_STANDINGS:
            app.store.remove_standings(s.standings_id)
    dialog.refresh()
    asked = []
    monkeypatch.setattr(icons, "ask", lambda *a, **k: asked.append(a[1]) or False)
    assert dialog.delete_button.objectName() == "danger", "red as Delete is everywhere"
    dialog.delete_button.click()
    assert asked == ["Delete Standings"] and dialog.names() == [DEMO_STANDINGS]
    monkeypatch.setattr(icons, "ask", lambda *a, **k: True)
    dialog.delete_button.click()
    assert dialog.names() == [] and app.store.list_standings() == []
    assert not dialog.delete_button.isEnabled() and not dialog.duplicate_button.isEnabled()
    assert not dialog.page.isEnabled() and not dialog.export_button.isEnabled()


def test_export_pdf_hands_the_standings_to_the_export(app):
    sent = []
    d = StandingsDialog(app.store, app.main, export=sent.append)
    d.export_button.click()
    assert sent == [d.selected_id()]
    d.deleteLater()


def test_the_apps_export_names_the_file_and_writes_it(app, monkeypatch, tmp_path):
    import sys
    import types

    from madtracker.app import AppController

    written = []
    module = types.ModuleType("madtracker.export.standings_pdf")
    module.suggested_standings_name = lambda table: f"x - {table.name} - Standings.pdf"
    module.write_standings_pdf = lambda store, sid, path, **k: written.append((sid, path))
    monkeypatch.setitem(sys.modules, "madtracker.export.standings_pdf", module)
    offered = []
    monkeypatch.setattr(
        AppController, "_export_path", lambda self, title, name, f: offered.append(name) or None
    )
    (standings,) = [s for s in app.store.list_standings() if s.name == DEMO_STANDINGS]
    assert app.export_standings(standings.standings_id) is None
    assert offered == [f"x - {DEMO_STANDINGS} - Standings.pdf"]
    out = app.export_standings(standings.standings_id, tmp_path / "s.pdf")
    assert out == tmp_path / "s.pdf" and written == [(standings.standings_id, out)]


def test_f1_opens_the_multi_race_standings_page(dialog):
    dialog.help_action.trigger()
    w = dialog.help_window
    assert (w.current_key(), w.current_section()) == ("multi_race", None)


def test_the_dialog_fits_a_1366_by_768_screen(dialog):
    from madtracker.ui.widgets import screen_room

    room = screen_room(dialog)
    assert dialog.width() <= room.width() and dialog.height() <= room.height()


# ----- fit, keys, and closing --------------------------------------------------

COLORS = ["Red", "Blue", "Green", "Yellow", "Black", "Orange"]


def weekend(store, madisons: int, team_names=COLORS, group: str = "Group A") -> int:
    """A standings over ``madisons`` scored Madisons, two a night, six teams; its id."""
    from madtracker.control import rulesets

    riders = [store.add_rider(f"Rider{i:02d}", f"Testname{i:02d}").rider_id for i in range(12)]
    made = store.add_standings("Big Omnium")
    events = []
    for night in range((madisons + 1) // 2):
        event_id = store.add_event(f"Omnium Night {night + 1}", f"2026-11-{night + 1:02d}").event_id
        events.append(event_id)
        for i, rider_id in enumerate(riders):
            store.add_entry(event_id, rider_id, 100 + i, group)
        for m in range(min(2, madisons - 2 * night)):
            rules = rulesets.rules_for(
                store, rulesets.default_ruleset_name(store), "madison", sprint_count=2
            )
            race = store.add_race(
                event_id,
                ("4 Mile Madison", "8 Mile Madison")[m],
                "madison",
                group_label=group,
                rules=rules.to_dict(),
            )
            for rider_id in riders:
                store.add_race_entry(race.race_id, rider_id)
            teams = []
            for t, name in enumerate(team_names):
                team = store.add_team(race.race_id, name, color=COLORS[t])
                store.add_team_member(team.team_id, riders[2 * t])
                store.add_team_member(team.team_id, riders[2 * t + 1])
                teams.append(team.team_id)
            session = LiveRace(store, race.race_id)
            for team_id in teams:
                assert session.click(team_id).ok
            assert session.record_sprint().ok
    store.update_standings(made.standings_id, event_ids=events)
    return made.standings_id


def shown_at(app, qapp, size: tuple[int, int], madisons: int) -> StandingsDialog:
    """The dialog at ``size`` (logical px) on the weekend's standings."""
    sid = weekend(app.store, madisons)
    d = StandingsDialog(app.store, app.main)
    d.refresh(sid)
    d.resize(*size)
    d.show()
    qapp.processEvents()
    return d


@pytest.mark.parametrize(
    "size, madisons",
    [
        ((1340, 716), 6),  # 1366 by 768 at 100 percent
        ((887, 460), 3),  # 1366 by 768 at 150 percent: 911 by 512 logical
    ],
)
def test_the_preview_shows_every_column_on_a_1366_laptop(app, qapp, size, madisons):
    d = shown_at(app, qapp, size, madisons)
    (table,) = d.standings_views
    assert d.size().toTuple() == size
    assert d.scroll.horizontalScrollBar().maximum() == 0, "the Standings box fits"
    assert table.races.horizontalScrollBar().maximum() == 0, "no race column scrolls"
    assert table.total_in_view()
    # The date is short and the race name cut to fit, never the figures.
    assert all(h.startswith("Nov-0") for h in table.shown_headers()[3:-1])
    d.close()
    d.deleteLater()


def test_past_what_fits_the_races_scroll_and_place_team_and_total_stay(app, qapp):
    d = shown_at(app, qapp, (1340, 716), 10)
    (table,) = d.standings_views
    assert table.races.horizontalScrollBar().maximum() > 0
    assert d.scroll.horizontalScrollBar().maximum() == 0
    assert table.total_in_view()
    assert table.fixed.geometry().left() <= table.BORDER
    assert table.fixed.columnWidth(0) > 0 and table.fixed.columnWidth(1) > 0
    d.close()
    d.deleteLater()


def test_the_detail_line_is_one_line(app, qapp):
    d = shown_at(app, qapp, (887, 460), 3)
    assert d.detail.text() == "3 Madisons raced over 2 events"
    assert d.detail.height() < 2 * d.detail.fontMetrics().lineSpacing()
    d.close()
    d.deleteLater()


def test_enter_in_the_name_saves_it_and_opens_nothing(app, dialog, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    asked = []
    monkeypatch.setattr(
        NameDialog,
        "exec",
        lambda self: asked.append(self.windowTitle()) or int(QDialog.DialogCode.Rejected),
    )
    dialog.show()
    assert not any(b.isDefault() or b.autoDefault() for b in dialog.findChildren(QPushButton))
    dialog.name.setFocus()
    dialog.name.setText("Weekend")
    QTest.keyClick(dialog.name, Qt.Key.Key_Return)
    assert asked == [] and dialog.isVisible()
    assert app.store.get_standings(dialog.shown_id).name == "Weekend"
    dialog.close()


def test_a_refusal_quoting_a_long_name_does_not_widen_the_dialog(dialog, qapp):
    dialog.show()
    qapp.processEvents()
    width = dialog.width()
    long_name = "W" * 200
    assert dialog.add(long_name) is not None
    assert dialog.duplicate(long_name) is None
    qapp.processEvents()
    text = dialog.status.text()
    assert "already exists" in text and "W" * 41 not in text and "..." in text
    assert dialog.status.wordWrap() and dialog.width() == width
    dialog.close()


def test_the_menu_item_is_off_with_no_usable_file(app):
    assert app.main.standings_action.isEnabled()
    app.main.set_file_usable(False)
    assert not app.main.standings_action.isEnabled()


def test_a_rename_that_resorts_the_list_keeps_the_next_click(app, dialog, qapp):
    dialog.add("Bravo")
    dialog.add("Zulu")
    demos = [DEMO_STANDINGS, DEMO_FOUR_RACE_STANDINGS, DEMO_RIDER_STANDINGS]
    assert dialog.names() == ["Bravo", *demos, "Zulu"]
    bravo_row = dialog.names().index("Bravo")
    dialog.name.setText("Aardvark")
    # Leaving the field for a click on Bravo: the rename is saved as the
    # focus goes, and the click lands on the row Bravo showed in.
    dialog.name.editingFinished.emit()
    dialog.list.setCurrentRow(bravo_row)
    qapp.processEvents()
    assert dialog.name.text() == "Bravo"
    assert dialog.names() == ["Aardvark", "Bravo", *demos]
    assert dialog.list.currentItem().text() == "Bravo"


def test_a_long_team_name_wraps_whole_over_its_row(app, qapp):
    from PySide6.QtCore import QRect

    from madtracker.ui.review import TEAM_ROW_H

    long_name = "Team Number 07 Long Name Abcde"
    names = ["Red", "Blue", long_name, "Yellow", "Black", "Orange"]
    sid = weekend(app.store, 1, team_names=names, group="")
    d = StandingsDialog(app.store, app.main)
    d.refresh(sid)
    d.show()
    qapp.processEvents()
    (table,) = d.standings_views
    row = table.column("Team").index(long_name)
    item = table.fixed.item(row, 1)
    width = table.fixed.columnWidth(1)
    from PySide6.QtGui import QFontMetrics

    needed = QFontMetrics(item.font()).boundingRect(
        QRect(0, 0, width - 2 * 8 - 18 - 12, 10_000), int(Qt.TextFlag.TextWordWrap), long_name
    )
    assert table.fixed.rowHeight(row) > TEAM_ROW_H
    assert table.fixed.rowHeight(row) >= needed.height()
    assert all(p.rowHeight(row) == table.fixed.rowHeight(row) for p in table.parts)
    # A group with no label is headed in title style, as a pane is.
    from PySide6.QtWidgets import QLabel

    assert "No Group" in [w.text() for w in d.groups.findChildren(QLabel)]
    d.close()
    d.deleteLater()


def test_every_race_unticked_says_they_were_left_out(app, dialog):
    for race_id in dialog.race_ticks():
        (i,) = [
            i
            for i in range(dialog.races.count())
            if dialog.races.item(i).data(Qt.ItemDataRole.UserRole) == race_id
        ]
        dialog.races.itemClicked.emit(dialog.races.item(i))
    assert not any(dialog.race_ticks().values())
    assert dialog.detail.text() == "every Madison left out"


def test_a_ticked_madison_not_yet_raced_says_so(dialog):
    from madtracker.ui.standings import NOT_YET_RACED, NOTE_ROLE

    notes = [dialog.races.item(i).data(NOTE_ROLE) for i in range(dialog.races.count())]
    # Tonight's two Madisons are still in setup; last night's are raced.
    assert notes == [None, NOT_YET_RACED, NOT_YET_RACED, None, None, None]
    dialog.races.itemClicked.emit(dialog.races.item(1))
    assert dialog.races.item(1).data(NOTE_ROLE) is None, "left out, not waiting"


def test_close_with_a_refused_name_says_why_once_then_closes(app, dialog):
    dialog.add("Other")
    dialog.select(DEMO_STANDINGS)
    dialog.show()
    dialog.name.setText("other")
    dialog.close_button.click()
    assert dialog.isVisible(), "the first Close shows the refusal"
    assert "already exists" in dialog.status.text() and dialog.name.text() == DEMO_STANDINGS
    dialog.close_button.click()
    assert not dialog.isVisible()


@pytest.mark.parametrize("how", ["close", "escape", "window"])
@pytest.mark.parametrize("typed", ["other", "   "])
def test_close_keeps_a_name_refusal_on_the_red_line_when_the_place_points_save(
    app, dialog, how, typed
):
    dialog.add("Other")
    dialog.select(DEMO_STANDINGS)
    dialog.show()
    dialog.set_kind(multi_race.PLACES)
    dialog.name.setText(typed)
    dialog.place_points.setText("9, 8, 7")
    shut = {
        "close": dialog.close_button.click,
        "escape": lambda: QTest.keyClick(dialog, Qt.Key.Key_Escape),
        "window": dialog.close,
    }[how]
    shut()
    assert dialog.isVisible(), "the first close shows the refusal"
    assert dialog.name.text() == DEMO_STANDINGS
    if typed == "other":
        assert "already exists" in dialog.status.text()
    else:
        assert dialog.status.text() == "The standings needs a name."
    sid = dialog.shown_id
    assert app.store.get_standings(sid).rules == {"points_by_place": [9, 8, 7]}
    shut()
    assert not dialog.isVisible()


def test_the_name_field_always_shows_the_name_as_saved(app, dialog):
    """A paste past the limit, or spaces the save squashes, never leaves the field unlike the store."""
    from madtracker.inputs import MAX_TEXT

    dialog.show()
    for typed in ("x" * 300, "x" * 300, "  Demo   Omnium  ", "  Demo   Omnium  "):
        dialog.name.setText(typed)
        dialog.name.editingFinished.emit()
        stored = app.store.get_standings(dialog.shown_id).name
        assert dialog.name.text() == stored
    assert stored == "Demo Omnium"
    assert dialog.name.maxLength() == MAX_TEXT


def test_close_after_a_refusal_on_leaving_the_field_holds_once(dialog):
    dialog.show()
    dialog.name.setText("   ")
    dialog.name.editingFinished.emit()
    assert dialog.status.text() == "The standings needs a name."
    dialog.reject()
    assert dialog.isVisible()
    dialog.reject()
    assert not dialog.isVisible()


def test_the_help_window_closes_with_the_dialog(dialog):
    dialog.show()
    dialog.help_action.trigger()
    assert dialog.help_window.isVisible()
    dialog.close_button.click()
    assert not dialog.isVisible() and not dialog.help_window.isVisible()


@pytest.mark.parametrize("which", ["standings", "rulesets"])
def test_the_dialog_is_deleted_once_closed(app, monkeypatch, which):
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QEvent

    opened = []
    monkeypatch.setattr(QDialog, "exec", lambda self: opened.append(self) or 0)
    if which == "standings":
        app.open_standings()
    else:
        from madtracker.ui.rulesets import open_rulesets

        open_rulesets(app.store, app.main)
    (d,) = opened
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(d)


# ----- the rider kinds -------------------------------------------------------------


def test_a_rider_kind_previews_bib_and_rider_columns_over_every_race_but_the_madison(dialog):
    assert dialog.set_kind(multi_race.OMNIUM)
    assert dialog.detail.text() == "11 of 22 races raced over 2 events"
    texts = item_texts(dialog.races)
    assert "8 Mile Madison (Group A)" not in texts and "2 Mile Chase (Group B)" in texts
    assert "Handicap (Group B)" in texts, "every format but the Madison"
    groups = [dialog.groups_lay.itemAt(i).widget() for i in range(dialog.groups_lay.count())]
    assert [w.text() for w in groups if w is not None and not hasattr(w, "parts")] == [
        "Group B",
        "Group A",
    ]
    b, a = dialog.standings_views
    assert headers(b)[:3] == ["Place", "Bib", "Rider"] and headers(b)[-1] == "Total"
    assert all(bib.isdigit() for bib in column(b, "Bib")), "a bib, not a swatch and a pair"
    assert b.fixed.item(0, 1).textAlignment() & Qt.AlignmentFlag.AlignRight
    assert b.fixed.item(0, 2).font().bold() and b.fixed.item(0, 1).icon().isNull()
    assert all(h == b.row_h[0] for h in b.row_h), "one line a rider"
    assert dialog.export_button.isEnabled()
    # The Place points row is the kind's, and a table typed is saved to it.
    assert dialog.form.isRowVisible(dialog.place_points)
    dialog.place_points.setText("3, 1")
    assert dialog.save_place_points()
    assert dialog.table.detail.startswith(
        "Each rider scores points for their place in each race, 3-1,"
    )
    assert len(dialog.standings_views) == 2 and "3" in column(dialog.standings_views[1], "Total")


def test_a_rider_kinds_names_never_give_way_the_races_scroll_instead(dialog):
    assert dialog.set_kind(multi_race.OMNIUM)
    table = dialog.standings_views[0]
    least = table.minimumSizeHint().width()
    names, _widths, scrolls, _total = table._widths(least)
    assert names >= table.riders_floor and scrolls
    assert not table.fixed.isColumnHidden(2)


def test_the_four_race_omnium_refuses_the_demos_program_where_the_tables_would_be(dialog):
    from PySide6.QtWidgets import QLabel

    assert dialog.set_kind(multi_race.FOUR_RACE)
    assert not dialog.form.isRowVisible(dialog.place_points)
    assert dialog.standings_views == [] and not dialog.export_button.isEnabled()
    refusal = dialog.table.refusal
    assert refusal.lead.startswith(
        "A Four-Race Omnium needs one Scratch Race, one Tempo Race, one Elimination, "
    )
    # The rule in red, then each event bold over its groups' lines in plain ink.
    (view,) = [
        dialog.groups_lay.itemAt(i).widget()
        for i in range(dialog.groups_lay.count())
        if dialog.groups_lay.itemAt(i).widget() is not None
    ]
    notes = view.findChildren(QLabel)
    want = [refusal.lead]
    for night, lines in refusal.nights:
        want += [night, *lines]
    assert [n.text() for n in notes] == want and len(refusal.nights) == 2
    assert notes[0].objectName() == "formError"
    assert [n.font().bold() for n in notes[1:3]] == [True, False]
    assert all(n.objectName() != "formError" for n in notes[1:])
    assert all(n.wordWrap() and n.textFormat() == Qt.TextFormat.PlainText for n in notes)
    assert view.toolTip() == refusal.text
    # Only the omnium's four formats are listed under Races.
    texts = item_texts(dialog.races)
    assert "2 Mile Chase (Group B)" in texts and "Elimination (Group A)" in texts
    assert "Handicap (Group B)" not in texts and "4 Mile Madison (Group A)" not in texts
    assert dialog.state.text() == ""


def test_no_race_in_the_ticked_events_reads_for_the_kind(app, dialog):
    assert dialog.set_kind(multi_race.OMNIUM)
    app.store.update_standings(dialog.shown_id, event_ids=[])
    dialog.refresh()
    assert dialog.no_races.isVisibleTo(dialog) and dialog.no_races.text() == NO_RACE
    assert dialog.set_kind(multi_race.TOTALS)
    assert dialog.no_races.text() == NO_MADISON


def test_a_four_race_status_row_previews_as_the_sheet_prints_it(app, dialog):
    """A rider out of the omnium has no figures on the sheet; the Standings box matches."""
    from madtracker.control import multi_race as S

    rows = [
        S.MultiRaceRow(1, "Ada Arden", None, [], [40, 38], 78, "", bib=1),
        S.MultiRaceRow(None, "Bram Arden", None, [], [38, 40], 78, "DNF", bib=2),
    ]
    column = S.RaceColumn(1, 1, "Friday", "2026-10-16", "Scratch", "Cat 3", "final", False, "chase")
    from madtracker.ui.standings import GroupStandings

    table = GroupStandings(S.GroupTable("Cat 3", [column, column], rows, riders=True), dialog)
    cells = table.cells()
    assert cells[:6] == ("1", "1", "Ada Arden", "40", "38", "78")
    assert cells[6:] == ("DNF", "2", "Bram Arden", "", "", "")
    table.deleteLater()


def test_a_refusal_survives_the_click_that_changed_the_selection(app, dialog):
    """Junk typed in Place points, then a click on another standings: the old
    table is back, the standings changes, and the red line still says why."""
    assert dialog.set_kind(multi_race.OMNIUM)
    other = dialog.add("Other")
    dialog.select(DEMO_STANDINGS)
    dialog.place_points.setText("junk")
    assert not dialog.save_place_points()
    assert dialog.status.text() == BAD_PLACES
    dialog.select("Other")
    assert dialog.shown_id == other and dialog.status.text() == BAD_PLACES
    # The next change clears it.
    dialog.set_kind(multi_race.OMNIUM)
    dialog.place_points.setText("9, 8")
    assert dialog.save_place_points() and dialog.status.text() == ""


def test_place_points_refuse_more_places_than_a_race_can_have(app, dialog):
    assert dialog.set_kind(multi_race.OMNIUM)
    dialog.place_points.setText(" ".join(["1"] * 51))
    assert not dialog.save_place_points() and dialog.status.text() == BAD_PLACES
    assert dialog.place_points.text() == "7, 5, 3, 2, 1"
    dialog.place_points.setText(" ".join(["1"] * 50))
    assert dialog.save_place_points()


def test_a_long_group_label_never_widens_the_preview(app, dialog, qapp):
    from madtracker.control.demo import OPENING_NIGHT
    from madtracker.ui.widgets import ElidedLabel

    (opening,) = [e for e in app.store.events() if e.name == OPENING_NIGHT]
    (race,) = [r for r in app.store.races(opening.event_id) if r.name == "2 Mile Chase"]
    app.store.update_race(race.race_id, group_label="X" * 120)
    assert dialog.set_kind(multi_race.OMNIUM)
    dialog.resize(1340, 716)
    dialog.show()
    qapp.processEvents()
    headings = [
        dialog.groups_lay.itemAt(i).widget()
        for i in range(dialog.groups_lay.count())
        if isinstance(dialog.groups_lay.itemAt(i).widget(), ElidedLabel)
    ]
    assert any(h.text() == "X" * 120 for h in headings)
    assert dialog.scroll.horizontalScrollBar().maximum() == 0
    dialog.set_kind(multi_race.FOUR_RACE)
    qapp.processEvents()
    assert dialog.scroll.horizontalScrollBar().maximum() == 0
    dialog.close()


def test_a_racing_race_says_so_in_the_list_for_a_place_kind(app, dialog):
    (race,) = [r for r in app.store.races(app.event.event_id) if r.name == "Elimination"]
    entries = app.store.race_entries(race.race_id)
    assert LiveRace(app.store, race.race_id).click(entries[0].rider_id).ok
    assert dialog.set_kind(multi_race.OMNIUM)
    (item,) = [
        dialog.races.item(i)
        for i in range(dialog.races.count())
        if dialog.races.item(i).data(ID_ROLE) == race.race_id
    ]
    assert item.data(NOTE_ROLE) == "(racing)"
    assert dialog.set_kind(multi_race.TOTALS)


def four_race_night(app) -> tuple[int, list[int]]:
    """A night of the omnium's four races for three demo riders, scored and final."""
    from madtracker.scoring import rules as R

    store = app.store
    ids = [r.rider_id for r in store.riders()[:3]]
    event = store.add_event("Omnium Night", "2026-11-05").event_id
    for i, rider_id in enumerate(ids):
        store.add_entry(event, rider_id, 70 + i)

    def race(name, format_key, rules):
        made = store.add_race(event, name, format_key, group_label="Cat 3", rules=rules.to_dict())
        for rider_id in ids:
            store.add_race_entry(made.race_id, rider_id)
        return LiveRace(store, made.race_id)

    live = race("Scratch", "chase", R.placings_rules())
    for rider_id in ids:
        assert live.click(rider_id).ok
    assert live.mark_final().ok
    live = race("Tempo", "tempo", R.tempo_rules(sprint_count=1))
    for rider_id in ids:
        assert live.click(rider_id).ok
    assert live.mark_final().ok
    live = race("Elimination", "elimination", R.elimination_rules())
    assert live.click(ids[2]).ok and live.click(ids[0]).ok
    assert live.mark_final().ok
    live = race("Points", "points", R.points_race_rules(sprint_count=1))
    for rider_id in ids:
        assert live.click(rider_id).ok
    assert live.mark_final().ok
    return event, ids


def test_the_omnium_penalty_button_is_the_four_race_kinds_and_records_a_penalty(app, dialog):
    """Hidden for the other kinds; grayed with no table; a recorded penalty comes
    off the total, shows in a Penalty column, and prints in the dialog's words."""
    from madtracker.ui.penalty import OmniumPenaltyDialog

    assert not dialog.penalty_button.isVisibleTo(dialog)
    assert dialog.set_kind(multi_race.FOUR_RACE)
    assert dialog.penalty_button.isVisibleTo(dialog) and not dialog.penalty_button.isEnabled()
    event, ids = four_race_night(app)
    sid = dialog.add("Four")
    app.store.update_standings(sid, kind=multi_race.FOUR_RACE, event_ids=[event])
    dialog.refresh(sid)
    assert dialog.penalty_button.isEnabled()
    riders = dialog.penalty_riders()
    assert [who for _id, who, _p in riders][0].startswith("#70 ")
    (table,) = dialog.standings_views
    assert "Penalty" not in headers(table)
    assert dialog.omnium_penalty(ids[0], 40)
    assert app.store.get_standings(sid).penalties == {ids[0]: 40}
    (table,) = dialog.standings_views
    assert headers(table)[-2:] == ["Penalty", "Total"]
    assert "\u221240" in column(table, "Penalty")
    assert any(p == 40 for _i, _w, p in dialog.penalty_riders())
    # The dialog: the chosen rider's number stands, Record waits for a change.
    d = OmniumPenaltyDialog(dialog.penalty_riders(), dialog)
    first_penalty = dialog.penalty_riders()[0][2]
    assert d.spin.value() == first_penalty and not d.record.isEnabled()
    d.spin.setValue(first_penalty + 20)
    assert d.record.isEnabled()
    d.accept()
    assert d.result() == QDialog.DialogCode.Accepted
    assert d.rider_id() == dialog.penalty_riders()[0][0] and d.points() == first_penalty + 20
    d.deleteLater()
    # 0 takes it off, and the column goes with it.
    assert dialog.omnium_penalty(ids[0], 0)
    assert app.store.get_standings(sid).penalties == {}
    assert "Penalty" not in headers(dialog.standings_views[0])


def test_duplicate_copies_the_omnium_penalties(app, dialog):
    event, ids = four_race_night(app)
    sid = dialog.add("Four")
    app.store.update_standings(sid, kind=multi_race.FOUR_RACE, event_ids=[event])
    dialog.refresh(sid)
    assert dialog.omnium_penalty(ids[1], 40)
    copy = dialog.duplicate("Four copy")
    assert app.store.get_standings(copy).penalties == {ids[1]: 40}


def test_the_penalty_column_and_the_dialogs_riders_are_the_ranked_rows(app, dialog):
    """A rider out of the omnium has no total to take a penalty off: their
    penalty brings no column in, and the dialog offers ranked riders only,
    once each, in bib order, a rider with no bib by name."""
    from madtracker.control import multi_race as S
    from madtracker.ui.standings import GroupStandings

    column = S.RaceColumn(1, 1, "Friday", "2026-10-16", "Scratch", "Cat 3", "final", False, "chase")
    rows = [
        S.MultiRaceRow(1, "Ada Arden", None, [], [40], 40, "", bib=9, rider_id=1),
        S.MultiRaceRow(2, "Bram Arden", None, [], [38], 38, "", bib=3, rider_id=2),
        S.MultiRaceRow(3, "Cleo Arden", None, [], [36], 36, "", bib=None, rider_id=3),
        S.MultiRaceRow(None, "Dov Arden", None, [], [34], -6, "DNF", bib=4, penalty=40, rider_id=4),
    ]
    group = S.GroupTable("Cat 3", [column], rows, riders=True)
    table = GroupStandings(group, dialog)
    assert "Penalty" not in table.headers()
    table.deleteLater()
    dialog.table = S.MultiRaceTable(
        1, "Four", S.FOUR_RACE, "Four-Race Omnium", "", "final", [group, group], [], [], []
    )
    assert dialog.penalty_riders() == [
        (2, "#3 Bram Arden", 0),
        (1, "#9 Ada Arden", 0),
        (3, "Cleo Arden", 0),
    ]


def test_a_kind_change_takes_the_omnium_penalties_off(app, dialog):
    event, ids = four_race_night(app)
    sid = dialog.add("Four")
    app.store.update_standings(sid, kind=multi_race.FOUR_RACE, event_ids=[event])
    dialog.refresh(sid)
    assert dialog.omnium_penalty(ids[0], 40)
    assert dialog.set_kind(multi_race.OMNIUM)
    assert app.store.get_standings(sid).penalties == {}
    assert dialog.set_kind(multi_race.FOUR_RACE)
    assert "Penalty" not in headers(dialog.standings_views[0])


def test_the_preview_never_scrolls_whole_with_a_penalty_column(app, qapp):
    """At 150 percent on a 1366 laptop a Penalty column takes letters off the
    names, never the Total out of view."""
    event, ids = four_race_night(app)
    made = app.store.add_standings("Four", kind=multi_race.FOUR_RACE)
    app.store.update_standings(made.standings_id, event_ids=[event])
    app.store.set_standings_penalty(made.standings_id, ids[0], 999)
    d = StandingsDialog(app.store, app.main)
    d.refresh(made.standings_id)
    for size in ((887, 460), (1340, 716)):
        d.resize(*size)
        d.show()
        qapp.processEvents()
        (table,) = d.standings_views
        assert d.scroll.horizontalScrollBar().maximum() == 0, size
        assert table.total_in_view(), size
    d.close()
    d.deleteLater()


def test_the_standings_wear_final_once_final_and_no_tag_before(app, dialog):
    event, ids = four_race_night(app)
    sid = dialog.add("Four")
    app.store.update_standings(sid, kind=multi_race.FOUR_RACE, event_ids=[event])
    dialog.refresh(sid)
    assert dialog.table.state == "final" and dialog.state.text() == "Final"
    assert "transparent" not in dialog.state.styleSheet()
    # One race reopened: no tag, not a warning.
    (race,) = [r for r in app.store.races(event) if r.name == "Points"]
    assert LiveRace(app.store, race.race_id).reopen().ok
    dialog.refresh(sid)
    assert dialog.table.state == "provisional" and dialog.state.text() == ""


def test_each_race_replays_once_while_the_dialog_is_open_and_again_on_refresh(
    app, dialog, monkeypatch
):
    from collections import Counter

    replays: Counter[int] = Counter()
    replay = LiveRace._replay
    monkeypatch.setattr(
        LiveRace,
        "_replay",
        lambda self, actions: replays.update([self.race_id]) or replay(self, actions),
    )
    dialog.refresh()
    scored = {r for r, n in replays.items() if n}
    assert scored and set(replays.values()) == {1}, "one replay per race, read by list and table"
    # Ticks, a kind change, and another selection read the same replays.
    replays.clear()
    (item,) = [
        dialog.races.item(i)
        for i in range(dialog.races.count())
        if dialog.races.item(i).data(ID_ROLE) == next(iter(dialog.race_ticks()))
    ]
    for _ in range(2):
        dialog.races.itemClicked.emit(item)
    dialog.select(DEMO_RIDER_STANDINGS)
    dialog.select(DEMO_STANDINGS)
    assert dialog.set_kind(multi_race.PLACES)
    assert set(replays) <= set(dialog.sessions) and set(replays.values()) <= {1}
    assert not replays.keys() & scored, "a race already replayed is not replayed again"
    # A race scored with the dialog open is read again by refresh().
    race_id = tonights_madison(app)
    replays.clear()
    dialog.refresh()
    assert replays[race_id] == 1


def test_a_standings_name_the_sheets_cannot_print_is_said_while_typed(dialog):
    from madtracker.ui.widgets import UNPRINTABLE_NOTE

    dialog.name.setText("Winter 王")
    assert dialog.status.text() == UNPRINTABLE_NOTE
    dialog.name.setText("Winter")
    assert dialog.status.text() == ""


def test_a_read_the_file_refuses_is_said_on_the_status_line_not_raised(app, dialog, monkeypatch):
    """A page damaged under the open file fails the next read with SQLite's
    own error; the dialog says it and takes no edits, and the slot never
    lets it out to the crash box."""
    import sqlite3

    def malformed(*a, **k):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(app.store, "get_standings", malformed)
    dialog._show_selected()
    assert dialog.status.text() == "Database disk image is malformed."
    assert not dialog.page.isEnabled() and not dialog.delete_button.isEnabled()
    monkeypatch.setattr(app.store, "list_standings", malformed)
    dialog.refresh()
    assert dialog.status.text() == "Database disk image is malformed."
    assert not dialog.page.isEnabled()
