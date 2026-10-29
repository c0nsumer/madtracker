"""The scoring window's place: maximized the first time, afterwards where it was last quit (design section 5)."""

import pytest
from apps import dispose_app
from PySide6.QtCore import QRect, QSettings
from PySide6.QtWidgets import QApplication

from madtracker.app import WINDOW_KEY
from madtracker.ui.window import MainWindow, place_window


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def make_app(qapp, tmp_path, settings):
    from madtracker.app import AppController

    made = []

    def build():
        c = AppController(
            qapp, demo=True, settings=settings, data_dir=tmp_path / f"data{len(made)}"
        )
        made.append(c)
        return c

    yield build
    # A shown window has a zero-time bar fit queued; it runs before the
    # window goes, not after.
    QApplication.processEvents()
    for c in made:
        dispose_app(c)


def _quit_by_window_button(c, monkeypatch) -> None:
    """The close button's path (closeEvent -> request_quit -> quit_requested), without ending Qt."""
    monkeypatch.setattr(c, "app", type("NoQuit", (), {"quit": lambda self: None})())
    monkeypatch.setattr(c.main, "confirm_quit", lambda: True)
    c.main.request_quit()


def test_the_first_start_opens_maximized_and_a_quit_keeps_the_place(
    make_app, settings, monkeypatch
):
    assert settings.value(WINDOW_KEY, None) is None
    c = make_app()
    c.start()
    QApplication.processEvents()
    assert c.main.isMaximized()
    _quit_by_window_button(c, monkeypatch)
    assert settings.value(WINDOW_KEY, None) is not None


def test_a_later_start_opens_where_the_window_was_last_quit(make_app, settings, monkeypatch):
    c = make_app()
    c.start()
    QApplication.processEvents()
    c.main.showNormal()
    c.main.setGeometry(40, 50, 600, 400)
    QApplication.processEvents()
    # The window's minimum size may widen what was asked for, and the
    # offscreen screen (800x800) is smaller than that minimum, so Qt's
    # restore nudges the window back onto it: the size is what holds.
    kept = c.main.geometry()
    monkeypatch.setattr(c, "app", type("NoQuit", (), {"quit": lambda self: None})())
    c.quit()  # File > Quit
    QApplication.processEvents()
    dispose_app(c)

    again = make_app()
    again.start()
    QApplication.processEvents()
    assert not again.main.isMaximized()
    assert again.main.geometry().size() == kept.size()


def test_a_place_on_no_screen_falls_back_to_maximized(qapp):
    """A display unplugged since the last quit: the saved place is on none of the screens left."""
    old = MainWindow()
    old.setGeometry(40, 50, 600, 400)
    saved = old.saveGeometry()
    old.deleteLater()

    w = MainWindow()
    place_window(w, saved, screens=[QRect(5000, 5000, 1366, 768)])
    w.show()
    QApplication.processEvents()
    assert w.isMaximized()
    w.hide()
    w.deleteLater()


def test_an_unreadable_place_falls_back_to_maximized(qapp):
    w = MainWindow()
    place_window(w, b"not a geometry")
    w.show()
    QApplication.processEvents()
    assert w.isMaximized()
    w.hide()
    w.deleteLater()
