"""Small shared widgets (madtracker.ui.widgets) on their own."""


def test_the_date_field_takes_a_typed_month_number_as_well_as_the_word(qtbot):
    """The month shows as a word but takes numbers as well."""
    from PySide6.QtCore import QDate
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDateEdit

    from madtracker.ui.widgets import date_edit

    edit = date_edit(QDate(2026, 5, 31))
    qtbot.addWidget(edit)
    edit.show()
    edit.setFocus()

    def typed(keys: str) -> str:
        edit.setCurrentSection(QDateEdit.Section.MonthSection)
        QTest.keyClicks(edit, keys)
        return edit.date().toString("yyyy-MM-dd")

    assert typed("9") == "2026-09-30", "a short month takes its last day"
    assert typed("12") == "2026-12-30"
    assert typed("1") == "2026-01-30", "a lone 1 is January until a second digit"
    assert typed("0") == "2026-10-30"
    assert typed("07") == "2026-07-30"
    assert edit.text() == "2026-Jul-30"


def test_the_settings_window_is_named_as_each_platform_names_the_menu_item(monkeypatch):
    """Qt puts the item in the macOS application menu as
    Preferences..., so the window says Preferences there; Settings elsewhere."""
    from madtracker.ui import widgets

    monkeypatch.setattr(widgets.sys, "platform", "darwin")
    assert widgets.settings_word() == "Preferences"
    for platform in ("win32", "linux"):
        monkeypatch.setattr(widgets.sys, "platform", platform)
        assert widgets.settings_word() == "Settings"


def test_undo_button_sets_the_verb_apart_and_cuts_the_name_first(qtbot):
    """ "Undo #51 Hana Yoon 10th" in one bold run would read as one word, and
    three weights as pieces: the label is a sentence, "Undo:" bold and the
    rest plain, and a narrow
    button cuts the rider's name before the end of the sentence."""
    from PySide6.QtGui import QFontMetrics

    from madtracker.ui.widgets import UndoButton

    b = UndoButton("Undo")
    qtbot.addWidget(b)
    b.set_label("Undo: #51 Hana Yoon placed 10th", "#51 Hana Yoon")
    assert b.runs() == [("Undo:", True), ("#51 Hana Yoon", False), ("placed 10th", False)]
    b.set_label("Undo: #19 Omar Rahimi gained a lap", "#19 Omar Rahimi")
    assert b.runs() == [("Undo:", True), ("#19 Omar Rahimi", False), ("gained a lap", False)]
    b.set_label("Undo: Blue placed 2nd", "Blue")
    assert b.runs() == [("Undo:", True), ("Blue", False), ("placed 2nd", False)]
    b.set_label("Undo: Sprint 3 recorded")
    assert b.runs() == [("Undo:", True), ("Sprint 3 recorded", False)]
    b.set_label("Nothing to Undo")
    assert b.runs() == [("Nothing to Undo", True)]
    b.set_label("Reopen First to Undo")
    assert b.runs() == [("Reopen First to Undo", True)]
    # A label naming someone the text does not hold names nobody.
    b.set_label("Undo: Sprint 3 recorded", "#51 Hana Yoon")
    assert b.who() == ""

    b.set_label("Undo: #51 Hana Yoon placed 10th", "#51 Hana Yoon")
    b.resize(600, 48)
    b.show()
    assert not b.is_cut()
    assert b.shown_runs() == ["Undo:", "#51 Hana Yoon", "placed 10th"]
    # The runs sit as the one sentence would: each gap is a plain space.
    bold, plain = b._fonts()
    whole = QFontMetrics(bold).horizontalAdvance("Undo:") + QFontMetrics(plain).horizontalAdvance(
        " #51 Hana Yoon placed 10th"
    )
    runs = b._fitted(600)
    laid = sum(w for _, _, w in runs) + b._gap() * (len(runs) - 1)
    # Each run's advance rounds to a pixel on its own, so a join may add one.
    assert whole <= laid <= whole + len(runs) - 1
    b.resize(170, 48)
    assert b.is_cut()
    shown = b.shown_runs()
    assert shown[0] == "Undo:" and shown[2] == "placed 10th"
    assert shown[1] != "#51 Hana Yoon" and shown[1].endswith("…")


def test_the_name_dialog_refuses_in_place_and_closes_once_the_name_is_taken(qtbot):
    """A refusal lands on the dialog's own red line with the text kept; the
    primary is filled and rightmost as every dialog's, and the label is Name."""
    from PySide6.QtWidgets import QDialog, QFormLayout, QPushButton

    from madtracker.ui.widgets import NameDialog

    taken = []

    def take(name: str) -> str | None:
        if not name.strip():
            return "The thing needs a name."
        if name == "later":
            return ""
        taken.append(name)
        return None

    d = NameDialog("Add Thing", "Add", take, text="Thing copy", placeholder="Thing", parent=None)
    qtbot.addWidget(d)
    assert d.windowTitle() == "Add Thing" and d.text() == "Thing copy"
    assert d.field.placeholderText() == "Thing"
    form = d.findChild(QFormLayout)
    assert form.itemAt(0, QFormLayout.ItemRole.LabelRole).widget().text() == "Name"
    buttons = [b for b in d.findChildren(QPushButton)]
    assert [b.text() for b in buttons] == ["Cancel", "Add"]
    assert buttons[-1].isDefault() and buttons[-1].objectName() == "primary"
    d.field.setText("   ")
    assert not d.submit() and d.error.text() == "The thing needs a name."
    assert d.result() != QDialog.DialogCode.Accepted and d.text() == "   "
    d.field.setText("later")
    assert not d.submit() and d.error.text() == "", "a declined question says nothing"
    d.field.setText("Thing 2")
    assert d.submit() and taken == ["Thing 2"]
    assert d.result() == QDialog.DialogCode.Accepted


def test_enter_in_a_group_combo_presses_the_dialogs_default_button_once_the_list_is_closed(
    qtbot,
):
    """Enter leaves the box as a line edit's Enter does; Qt's own insert
    never runs, so the typed text is read on save and never listed."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout

    from madtracker.ui.widgets import GroupCombo, button_row

    d = QDialog()
    qtbot.addWidget(d)
    combo = GroupCombo()
    combo.addItems(["Group A", "Group B"])
    pressed = []
    row, buttons = button_row("Save", lambda: pressed.append(combo.currentText()), d.reject)
    lay = QVBoxLayout(d)
    lay.addWidget(combo)
    lay.addLayout(row)
    d.show()
    QApplication.processEvents()
    combo.lineEdit().setFocus()
    combo.lineEdit().selectAll()
    QTest.keyClicks(combo.lineEdit(), "Juniors")
    QTest.keyClick(combo.lineEdit(), Qt.Key.Key_Return)
    assert pressed == ["Juniors"] and combo.findText("Juniors") < 0
    # With the list open, Enter picks from it and saves nothing.
    combo.showPopup()
    assert combo.view().isVisible()
    QTest.keyClick(combo.view(), Qt.Key.Key_Down)
    QTest.keyClick(combo.view(), Qt.Key.Key_Return)
    assert not combo.view().isVisible() and pressed == ["Juniors"]
    # A disabled default button is not pressed.
    buttons["primary"].setEnabled(False)
    combo.lineEdit().setFocus()
    QTest.keyClick(combo.lineEdit(), Qt.Key.Key_Return)
    assert pressed == ["Juniors"]
    d.close()


def test_a_team_swatch_keeps_its_color_when_its_row_is_disabled(qtbot):
    """A scored race's Teams list is locked and shows a named team's name
    alone, so the chip is what says which jersey it is."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon

    from madtracker.ui.widgets import swatch_icon

    icon = swatch_icon("#e5323b")
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled):
        image = icon.pixmap(QSize(16, 16), 1.0, mode).toImage()
        assert image.pixelColor(8, 8).name() == "#e5323b", mode


def test_a_team_swatch_is_drawn_at_the_size_its_views_draw_icons(qtbot):
    """A chip rescaled to the view's icon size loses its whole-pixel outline."""
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QComboBox, QListWidget, QStyle, QTableWidget

    from madtracker.ui.widgets import swatch_icon

    sizes = swatch_icon("#e5323b").availableSizes()
    for view in (QListWidget(), QTableWidget(), QComboBox()):
        qtbot.addWidget(view)
        # An item view left unset draws at the style's small icon size.
        size = view.iconSize()
        if not size.isValid():
            side = view.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, None, view)
            size = QSize(side, side)
        assert size in sizes, type(view).__name__
