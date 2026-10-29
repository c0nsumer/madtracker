"""The ruleset editor's tabs and words, and the word's path from the ruleset to every screen."""

import json

import pytest
from PySide6.QtWidgets import QDialog

from madtracker.control import board_feed, rulesets
from madtracker.control.race import LiveRace
from madtracker.export.summary import build_summary
from madtracker.store import Store
from madtracker.ui import setup as su
from madtracker.ui.rulesets import FIELD_LABELS, RulesetEditor, RulesetsDialog
from madtracker.ui.surface import Surface
from madtracker.ui.widgets import PLACEHOLDER_ROLE, PlaceholderDelegate

DEVIL = "Last rider over the line every 2 laps is out"


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "rules.sqlite")
    yield s
    s.close()


@pytest.fixture
def house(store):
    """A stored copy of the rulebook that calls the elimination the Devil."""
    doc = rulesets.apply_values(
        rulesets.builtin_ruleset(),
        lap_points=10,
        format_names={"elimination": "Devil"},
        format_descriptions={"elimination": DEVIL},
    )
    doc["name"] = "House"
    return rulesets.save_ruleset(store, doc)


def test_the_editor_has_a_tab_per_family_with_its_values_and_its_formats(qtbot, store, house):
    ed = RulesetEditor(store, house.doc, house.ruleset_id)
    qtbot.addWidget(ed)
    assert [ed.tabs.tabText(i) for i in range(ed.tabs.count())] == [
        "Scratch Race and Others",
        "Points Race",
        "Madison",
        "Tempo Race",
        "Elimination",
        "Win-and-Out (Club)",
    ]
    assert set(FIELD_LABELS) == set(rulesets.PAGE_KEYS)
    # Each value's widget sits on its family's tab, laps included: a lap is
    # priced per sprint format. A one-format tab names it in two fields; the
    # finals tab, with six formats, in a table.
    for i, family in enumerate(rulesets.FAMILY_LABELS):
        page = ed.tabs.widget(i)
        for key in rulesets.FAMILY_KEYS[family]:
            assert ed.fields[key].parent() is page, (family, key)
        formats = rulesets.family_formats(family)
        table = page.findChild(su.QTableWidget, f"words_{family}")
        if len(formats) == 1:
            assert table is None
            assert page.findChild(su.QLabel, "hint").text() == rulesets.family_source_line(family)
            name = ed.words[(formats[0].key, "format_names")]
            assert name.parent() is page and name.placeholderText() == formats[0].label
        else:
            assert [table.item(r, 0).text() for r in range(table.rowCount())] == [
                f.source_text for f in formats
            ]
            assert page.findChild(su.QLabel, "hint") is None
            # An empty Shown as cell shows the rulebook's name in gray.
            assert [table.item(r, 1).data(PLACEHOLDER_ROLE) for r in range(table.rowCount())] == [
                f.label for f in formats
            ]
            assert isinstance(table.itemDelegate(), PlaceholderDelegate)
    assert ed.fields["points_lap_gained"].value() == 10
    assert ed.fields["madison_lap_lost"].value() == 10
    # A table field is a comma list, as the Multi-Race Standings field is.
    assert ed.fields["points_table"].text() == "5, 3, 2, 1"
    assert ed.fields["madison_table"].placeholderText() == "5, 3, 2, 1"
    tip = ed.fields["points_table"].toolTip()
    assert tip.startswith("Points per place, first place first, like 10, 7, 5, 3, 2, 1")
    # Only a tab whose values are the rulebook's can fill from it; the
    # win-and-out's are a club's, and its tooltips say so.
    buttons = {
        family: ed.tabs.widget(i).findChild(su.QPushButton, f"reset_{family}")
        for i, family in enumerate(rulesets.FAMILY_LABELS)
    }
    assert buttons["win_and_out"] is None
    assert all(b is not None for f, b in buttons.items() if f != "win_and_out")
    assert buttons["elimination"].text() == "Fill USAC 2025 Values"
    assert ed.fields["places"].toolTip() == "Club: 3"
    assert ed.fields["survivors"].toolTip() == "USAC 2025: 2"
    assert ed.words[("elimination", "format_names")].text() == "Devil"
    assert ed.words[("elimination", "format_descriptions")].text() == DEVIL
    assert ed.words[("chase", "format_names")].text() == ""


def test_the_editor_caps_what_a_field_takes_where_the_race_dialog_does(qtbot, store, house):
    """Places share the race dialog's ceiling; Shown as takes a name's length, Description more."""
    from PySide6.QtWidgets import QStyleOptionViewItem

    ed = RulesetEditor(store, house.doc, house.ruleset_id)
    qtbot.addWidget(ed)
    places = ed.fields["places"]
    assert (places.minimum(), places.maximum()) == (1, rulesets.MAX_COUNT) == (1, su.MAX_COUNT)
    assert ed.words[("elimination", "format_names")].maxLength() == 60
    assert ed.words[("elimination", "format_descriptions")].maxLength() == 600
    table = ed.findChild(su.QTableWidget, "words_placings")
    delegate = table.itemDelegate()
    editors = {
        col: delegate.createEditor(table, QStyleOptionViewItem(), table.model().index(0, col))
        for col in (1, 2)
    }
    assert (editors[1].maxLength(), editors[2].maxLength()) == (60, 600)


def test_the_editor_saves_the_words_and_reset_keeps_them(qtbot, store, house):
    ed = RulesetEditor(store, house.doc, house.ruleset_id)
    qtbot.addWidget(ed)
    ed.fields["survivors"].setValue(3)
    # A table typed with spaces or a sheet's hyphens saves all the same;
    # a value past the Multi-Race Standings field's cap is refused here too.
    ed.fields["madison_table"].setText("7 5-3-2-1")
    assert ed.fields["madison_table"].maxLength() == rulesets.TABLE_TEXT_MAX
    ed.fields["points_table"].setText("1000, 7")
    assert not ed.save()
    assert (
        ed.error.text()
        == "Sprint points are whole numbers from 0 to 999, such as 10, 7, 5, 3, 2, 1."
    )
    assert ed.fields["points_table"].text() == "1000, 7", "the text stays to be fixed"
    ed.fields["points_table"].setText("10, 7")
    ed.words[("elimination", "format_names")].setText("  ")
    ed.words[("madison", "format_names")].setText("Mad")
    ed.words[("madison", "format_descriptions")].setText("Two riders, hand slings")
    doc = ed.build_doc()
    assert doc["format_names"] == {"madison": "Mad"}, "a blanked word is gone"
    assert doc["madison_table"] == [7, 5, 3, 2, 1]
    assert doc["format_descriptions"] == {
        "elimination": DEVIL,
        "madison": "Two riders, hand slings",
    }
    # Reset puts the rulebook's values back on one tab and leaves every word.
    ed.reset_tab("elimination")
    assert ed.fields["survivors"].value() == 2
    assert ed.fields["points_lap_gained"].value() == 10
    assert ed.words[("madison", "format_names")].text() == "Mad"
    assert ed.save()
    saved = store.ruleset(house.ruleset_id).doc
    assert saved["format_names"] == {"madison": "Mad"} and saved["survivors"] == 2
    assert rulesets.rules_for(store, "House", "madison").lap_gained_points == 10


def test_duplicate_asks_for_a_name_and_refuses_a_taken_one_in_the_dialog(
    qtbot, store, house, monkeypatch
):
    """The name dialog keeps the refused name in its field and stays open."""
    from PySide6.QtWidgets import QDialog

    from madtracker.ui.widgets import NameDialog

    seen = []

    def run(self):
        seen.append((self.windowTitle(), self.text(), self.buttons["primary"].text()))
        self.field.setText("house")
        assert not self.submit() and self.error.text() == "A ruleset named House already exists."
        assert self.text() == "house" and self.result() != QDialog.DialogCode.Accepted
        self.field.setText(" ")
        assert not self.submit() and self.error.text() == "The ruleset needs a name."
        self.field.setText("Winter House")
        assert self.submit()
        return self.result()

    monkeypatch.setattr(NameDialog, "exec", run)
    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    d.refresh("House")
    assert d.new_from() == "Winter House"
    assert seen == [("Duplicate Ruleset", "House copy", "Duplicate")]
    assert d.status.text() == "" and store.ruleset_by_name("Winter House") is not None
    # A name handed in (the fuzzer's path) is refused on the status line instead.
    assert d.new_from("winter house") is None
    assert d.status.text() == "A ruleset named Winter House already exists."


def test_the_rulesets_dialog_opens_the_tabbed_editor(qtbot, store, house):
    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    d.refresh("House")
    ed = d.editor_for_selected()
    assert ed is not None and ed.tabs.count() == 6
    assert ed.windowTitle() == "Edit Ruleset"


def test_the_list_tags_are_title_style(qtbot, store, house):
    # App-defined list items take title style.
    rulesets.set_default_ruleset(store, "House")
    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    d.refresh()
    texts = [d.list.item(i).text() for i in range(d.list.count())]
    assert texts == [f"{rulesets.BUILTIN_LABEL}  (Built-In)", "House  (Default)"]
    # Under the buttons it is a status line, in sentence style.
    d.list.setCurrentRow(0)
    assert d.locked_why.text() == "Built-in"
    assert d.delete_button.objectName() == "danger", "red as Delete is everywhere"


def test_the_word_reaches_the_name_the_program_the_surface_the_board_and_the_sheet(
    qtbot, store, house
):
    event = store.add_event("Test Night", "2026-10-10")
    ids = []
    for bib, (first, last) in enumerate([("Ann", "Alpha"), ("Ben", "Bravo"), ("Cy", "Charlie")], 1):
        rider = store.add_rider(first, last)
        store.add_entry(event.event_id, rider.rider_id, bib, local_group="Group A")
        ids.append(rider.rider_id)
    screen = su.SetupScreen()
    qtbot.addWidget(screen)
    screen.load(store, event.event_id)
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("elimination"))
    d.choose_group("Group A")
    # The rulebook names it as the book does; the house ruleset as the venue does.
    d.ruleset.setCurrentIndex(d.ruleset.findData("rulebook"))
    assert d.name.placeholderText() == "Group A Elimination"
    d.ruleset.setCurrentIndex(d.ruleset.findData("House"))
    assert d.name.placeholderText() == "Group A Devil"
    assert d.save()
    race = store.race(d.race_id)
    assert race.name == "Group A Devil"
    assert race.rules["format_name"] == "Devil" and race.rules["format_description"] == DEVIL
    assert race.rules["survivors"] == 2, "the words sit beside the rules, not in their way"
    screen.refresh()
    assert screen.program.item(0, 1).text() == "Devil"

    live = LiveRace(store, race.race_id)
    shown = live.screen()
    assert (shown.detail, shown.description) == ("Devil", DEVIL)
    surface = Surface()
    qtbot.addWidget(surface)
    surface.show_screen(shown)
    # Unnamed, so the venue's word is the title, with the group beside it
    # and no format line repeating it, on the surface and the board alike.
    assert surface.title.text() == "Devil"
    assert surface.detail.text() == "Group A"
    assert surface.description.text() == DEVIL and not surface.description.isHidden()
    _, payload = board_feed.board_for(live.view())
    assert (payload.header.title, payload.header.detail) == ("Devil", "")
    assert build_summary(store, race).format_label == "Devil"

    # A race made from the rulebook says nothing extra and shows no description line.
    d = screen.race_dialog(None)
    d.format.setCurrentIndex(d.format.findData("elimination"))
    d.choose_group("Group A")
    d.ruleset.setCurrentIndex(d.ruleset.findData("rulebook"))
    assert d.save()
    plain = store.race(d.race_id)
    assert "format_name" not in plain.rules
    surface.show_screen(LiveRace(store, plain.race_id).screen())
    assert (surface.title.text(), surface.detail.text()) == ("Elimination", "Group A")
    assert surface.description.isHidden()
    assert d.result() != QDialog.DialogCode.Rejected


def test_the_editor_holds_a_table_of_as_many_places_as_a_race_may_ask_for(qtbot, store, house):
    """Fifty values at the most a place awards fit the field; a fifty-first is refused."""
    from madtracker.ui.rulesets import LONG_TABLE, parse_table

    ed = RulesetEditor(store, house.doc, house.ruleset_id)
    qtbot.addWidget(ed)
    longest = rulesets.table_text([rulesets.TABLE_MAX] * rulesets.MAX_COUNT)
    ed.fields["points_table"].setText(longest)
    assert ed.fields["points_table"].text() == longest
    assert ed.save()
    assert store.ruleset_by_name("House").doc["points_table"] == [999] * 50
    with pytest.raises(ValueError, match=f"^{LONG_TABLE}$"):
        parse_table(",".join(["1"] * 51))


def test_a_stored_page_past_the_editor_ranges_opens_in_edit_and_the_race_dialog(qtbot, store):
    """A stored page is not checked again as it is read; the boxes hold it to their range."""
    doc = {**rulesets.builtin_ruleset(), "name": "Big", "places": 10**12, "tempo_points": 10**12}
    row = store.add_ruleset("Big", doc)
    ed = RulesetEditor(store, row.doc, row.ruleset_id)
    qtbot.addWidget(ed)
    assert ed.fields["places"].value() == rulesets.MAX_COUNT
    assert ed.fields["tempo_points"].value() == 100

    event = store.add_event("Test Night", "2026-10-22")
    d = su.RaceDialog(store, event.event_id)
    qtbot.addWidget(d)
    d.format.setCurrentIndex(d.format.findData("win_and_out"))
    d.ruleset.setCurrentIndex(d.ruleset.findData("Big"))
    assert d.number.value() == rulesets.MAX_COUNT


def test_import_cancelled_at_replace_says_nothing(qtbot, store, house, tmp_path, monkeypatch):
    import madtracker.ui.rulesets as ur

    asked = []
    monkeypatch.setattr(ur, "ask", lambda *a, **k: asked.append(a[2]) or False)
    path = rulesets.export_ruleset({**house.doc, "tempo_points": 7}, tmp_path / "house.json")
    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    assert d.import_from(path) is None
    assert asked and d.status.text() == ""
    assert store.ruleset_by_name("House").doc["tempo_points"] == house.doc["tempo_points"]


def test_import_offers_replace_for_a_name_stored_without_its_doubled_space(
    qtbot, store, tmp_path, monkeypatch
):
    import madtracker.ui.rulesets as ur

    asked = []
    monkeypatch.setattr(ur, "ask", lambda *a, **k: asked.append(a[2]) or True)
    club = rulesets.save_ruleset(store, {**rulesets.builtin_ruleset(), "name": "Club House"})
    path = rulesets.export_ruleset(
        {**club.doc, "name": "Club  House", "tempo_points": 7}, tmp_path / "club.json"
    )
    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    assert d.import_from(path) == "Club House"
    assert asked[0].startswith("A ruleset named Club House already exists. Replace")
    assert store.ruleset_by_name("Club House").doc["tempo_points"] == 7


@pytest.mark.parametrize(
    ("make", "line"),
    [
        (lambda p: None, "Could not find club rules.json."),
        (lambda p: p.mkdir(), "Could not read club rules.json: it is a folder."),
        (lambda p: p.write_text(""), "Could not read club rules.json: it is not a ruleset file."),
        (
            lambda p: p.write_text(
                json.dumps({**rulesets.builtin_ruleset(), "name": "Club", "survivors": 0})
            ),
            "Could not import club rules.json."
            " Elimination riders in the final sprint: must be a whole number from 1 to 20.",
        ),
    ],
)
def test_the_import_red_line_keeps_the_file_name_as_spelled(qtbot, store, tmp_path, make, line):
    path = tmp_path / "club rules.json"
    make(path)
    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    assert d.import_from(path) is None
    assert d.status.text() == line


def test_the_export_red_line_names_the_file_without_the_os_text(qtbot, store, house, tmp_path):
    blocker = tmp_path / "taken"
    blocker.write_text("")
    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    d.refresh(house.name)
    assert d.export_to(path=blocker / "club rules.json") is None
    assert d.status.text() == "Could not write club rules.json."


@pytest.mark.parametrize("beside", ["", "-wal"])
def test_a_ruleset_is_never_exported_over_the_open_file(qtbot, store, house, beside):
    """The save box takes any name typed: JSON written over the open file
    or its -wal would wreck everything scored into it."""
    target = store.path.with_name(store.path.name + beside)
    held = target.read_bytes() if target.exists() else None
    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    d.refresh(house.name)
    assert d.export_to(path=target) is None
    what = "is the open data file" if not beside else "belongs to the open data file"
    assert d.status.text() == f"{target.name} {what}. Choose another name."
    assert (target.read_bytes() if target.exists() else None) == held
    assert store.ruleset_by_name(house.name) is not None, "the file still reads"


def test_enter_in_the_rulesets_list_presses_no_button(store, qtbot, monkeypatch):
    """No button is the dialog's default, so Enter in the list opens no name box."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    d = RulesetsDialog(store)
    qtbot.addWidget(d)
    d.show()
    pressed = []
    monkeypatch.setattr(d, "new_from", lambda *a, **k: pressed.append("duplicate"))
    d.list.setCurrentRow(0)
    d.list.setFocus()
    qtbot.keyClick(d.list, Qt.Key.Key_Return)
    assert pressed == [] and d.isVisible()
    assert not any(b.isDefault() or b.autoDefault() for b in d.findChildren(QPushButton))
