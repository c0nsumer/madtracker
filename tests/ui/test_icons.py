"""Material Design Icons in place of Qt's stock icons."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# The QMessageBox static helpers always draw Qt's stock icon, and the
# QStyle standard pixmaps are the stock icons themselves; both are
# replaced by madtracker.ui.icons. QInputDialog lays its buttons out in
# the platform's order with no filled primary and closes before a name
# can be refused; widgets.NameDialog replaces it.
FORBIDDEN = re.compile(
    r"QMessageBox\.(question|warning|information|critical)\(|StandardPixmap|QInputDialog"
)


def _ui_sources() -> list[Path]:
    return sorted((ROOT / "madtracker" / "ui").rglob("*.py")) + [ROOT / "madtracker" / "app.py"]


def test_no_stock_message_box_or_standard_pixmap_in_the_ui():
    found = []
    for path in _ui_sources():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if FORBIDDEN.search(line):
                found.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not found, (
        "use madtracker.ui.icons (ask, warn, inform, mdi) or widgets.NameDialog:\n"
        + "\n".join(found)
    )


def test_every_bundled_glyph_renders_tinted_and_cached(qapp):
    from madtracker.ui import icons

    names = sorted(p.stem for p in (ROOT / "madtracker" / "assets" / "icons" / "mdi").glob("*.svg"))
    assert {"help-circle-outline", "alert-outline", "information-outline", "undo"} <= set(names)
    for name in names:
        pix = icons.mdi_pixmap(name, 32, "#1f5fd1")
        assert not pix.isNull() and pix.width() == 32
        image = pix.toImage()
        colors = {
            image.pixelColor(x, y).name()
            for x in range(32)
            for y in range(32)
            if image.pixelColor(x, y).alpha() == 255
        }
        assert "#1f5fd1" in colors, name  # the injected fill, not the default black
        assert icons.mdi_pixmap(name, 32, "#1f5fd1") is pix
        assert not icons.mdi(name).isNull()


def test_tinted_glyphs_go_to_a_folder_of_this_users_own(qapp, tmp_path, monkeypatch):
    """The temp folder is shared between users on Linux, so the folder names the user."""
    import os
    import tempfile

    from madtracker.ui import icons

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(icons, "_icon_dir", None)
    path = icons.svg_file("check", "#1f5fd1")
    assert path.is_file() and path.parent.parent == tmp_path
    if hasattr(os, "getuid"):
        assert path.parent.name == f"madtracker-icons-{os.getuid()}"
    assert icons.svg_file("check", "#1f5fd1") == path


def test_a_taken_icon_folder_name_falls_back_to_a_private_folder(qapp, tmp_path, monkeypatch):
    """A file (or another user's folder) under the name is passed over, never an error."""
    import os
    import tempfile

    from madtracker.ui import icons

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(icons, "_icon_dir", None)
    name = f"madtracker-icons-{os.getuid()}" if hasattr(os, "getuid") else "madtracker-icons"
    (tmp_path / name).write_text("not a folder", encoding="utf-8")
    path = icons.svg_file("check", "#1f5fd1")
    assert path.is_file() and path.parent != tmp_path / name
    assert path.parent.parent == tmp_path


def test_unknown_glyph_is_an_error(qapp):
    from madtracker.ui import icons

    with pytest.raises((FileNotFoundError, OSError)):
        icons.mdi_pixmap("no-such-glyph", 24)


@pytest.mark.parametrize("kind", ["question", "warning", "information"])
def test_message_box_carries_the_mdi_glyph(qapp, kind):
    from PySide6.QtWidgets import QMessageBox

    from madtracker.ui import icons

    box = icons.message_box(None, kind, "Title", "Text")
    assert box.icon() == QMessageBox.Icon.NoIcon
    assert not box.iconPixmap().isNull()
    assert box.iconPixmap().width() == icons.BOX_ICON_SIZE


def test_quit_question_uses_the_helper(qtbot, monkeypatch):
    from madtracker.ui import window
    from madtracker.ui.window import MainWindow

    asked = []
    monkeypatch.setattr(
        window, "ask", lambda parent, title, text, verb: asked.append((text, verb)) or False
    )
    w = MainWindow()
    qtbot.addWidget(w)
    # One question, the board shown or not: the scorer knows quitting
    # closes the scoreboard.
    assert w.confirm_quit() is False
    assert asked[-1] == ("Quit MadTracker?", "Quit")
    w.set_board_shown(False)
    assert w.confirm_quit() is False
    assert asked[-1] == ("Quit MadTracker?", "Quit")


def test_buttons_carry_icons_menus_do_not_and_about_credits_mdi(qtbot):
    from madtracker.ui.about import components
    from madtracker.ui.window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    assert not w.undo.icon().isNull()
    assert not w.surface.record_button.icon().isNull()
    assert not w.program.mode.edit.icon().isNull() and not w.program.mode.score.icon().isNull()
    # No menu item anywhere carries an icon: Qt draws it in the check-mark slot.
    for m in w.menuBar().actions():
        for a in m.menu().actions():
            assert a.icon().isNull(), a.text()
    credits = {c.name: c.license for c in components()}
    assert credits["Material Design Icons by the Pictogrammers"] == "Pictogrammers Free License"
    assert credits["uharfbuzz"] == "Apache License 2.0"
    assert credits["Inter by Rasmus Andersson"] == "SIL OFL 1.1"


@pytest.mark.parametrize("press", ["verb", "Cancel"])
def test_ask_shows_cancel_then_the_verb_rightmost(qapp, monkeypatch, press):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

    from madtracker.ui import icons

    seen = []

    def run(box):
        box.show()
        QApplication.processEvents()
        buttons = [b for b in box.findChildren(QPushButton) if b.isVisible()]
        placed = sorted(buttons, key=lambda b: b.mapTo(box, QPoint(0, 0)).x())
        seen.append(([b.text() for b in placed], box.defaultButton().text()))
        target = placed[-1] if press == "verb" else placed[0]
        target.click()
        box.hide()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", run)
    answer = icons.ask(None, "Disqualify", "Disqualify Ann Alpha?", verb="Disqualify")
    # Cancel is the default, so a stray Enter never answers the question.
    assert seen == [(["Cancel", "Disqualify"], "Cancel")]
    assert answer is (press == "verb")


@pytest.mark.parametrize("press", ["first", "primary", "cancel"])
def test_choose_lays_out_cancel_then_the_verbs_with_the_primary_rightmost(qapp, monkeypatch, press):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

    from madtracker.ui import icons

    seen = []

    def run(box):
        box.show()
        QApplication.processEvents()
        buttons = [b for b in box.findChildren(QPushButton) if b.isVisible()]
        placed = sorted(buttons, key=lambda b: b.mapTo(box, QPoint(0, 0)).x())
        seen.append(([(b.text(), b.isEnabled()) for b in placed], box.defaultButton().text()))
        target = {"first": placed[1], "primary": placed[-1], "cancel": placed[0]}[press]
        target.click()
        box.hide()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", run)
    answer = icons.choose(
        None, "Demo", "Open or create?", ["Open Previous", "Create New"], "Create New"
    )
    assert seen == [([("Cancel", True), ("Open Previous", True), ("Create New", True)], "Cancel")]
    assert answer == {"first": "Open Previous", "primary": "Create New", "cancel": None}[press]
    # A grayed verb stays in its place.
    seen.clear()
    icons.choose(
        None,
        "Demo",
        "?",
        ["Open Previous", "Create New"],
        "Create New",
        disabled=("Open Previous",),
    )
    assert seen[0][0][1] == ("Open Previous", False)


def test_enter_on_a_question_cancels_it(qapp, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox

    from madtracker.ui import icons

    def run(box):
        box.show()
        QApplication.processEvents()
        QTest.keyClick(box, Qt.Key.Key_Return)
        QApplication.processEvents()
        box.hide()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", run)
    assert icons.ask(None, "Quit", "Quit?", verb="Quit") is False


def test_inform_with_copy_puts_the_text_on_the_clipboard_and_stays_open(qapp, monkeypatch):
    """Copy Details to Clipboard never closes the box: it says Copied in place, OK closes."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

    from madtracker.ui import icons

    runs = []

    def answer(box):
        box.show()
        QApplication.processEvents()
        ok = box.button(QMessageBox.StandardButton.Ok)
        copy = box.findChild(QPushButton, "copyDetails")
        if copy is None:
            runs.append(None)
            ok.click()
            box.hide()
            return 0
        # The copy button sits left of the box's own row.
        assert copy.mapTo(box, QPoint(0, 0)).x() < ok.mapTo(box, QPoint(0, 0)).x()
        before = copy.text()
        copy.click()
        copy.click()
        runs.append((before, copy.text(), box.isVisible()))
        ok.click()
        box.hide()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", answer)
    QGuiApplication.clipboard().setText("")
    icons.inform(None, "Export USAC CSV", "<p>Report</p>", copy="Report\n")
    assert QGuiApplication.clipboard().text() == "Report\n"
    assert runs == [("Copy Details to Clipboard", "Copied to Clipboard", True)]
    runs.clear()
    icons.inform(None, "Plain", "No copy here")
    assert runs == [None], "no copy button without a text to copy"


def test_inform_draws_a_report_as_html_only_when_asked(qapp, monkeypatch):
    """The export report is HTML with its names escaped; every other box shows its text as typed."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

    from madtracker.ui import icons

    formats = []

    def answer(box):
        box.show()
        QApplication.processEvents()
        label = box.findChild(QLabel, "qt_msgbox_label")
        formats.append((label.textFormat(), label.text()))
        box.hide()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", answer)
    icons.inform(None, "Export USAC CSV", "<p>Report</p>", rich=True)
    icons.inform(None, "Plain", "<p>As typed</p>")
    assert formats == [
        (Qt.TextFormat.RichText, "<p>Report</p>"),
        (Qt.TextFormat.PlainText, "<p>As typed</p>"),
    ]
