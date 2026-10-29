"""Headless screenshots of the window and the scoreboard, from the app scoring the demo event.

Used by ``python -m madtracker --mockup DIR`` so the look can be
reviewed, and regressions spotted, without two monitors or a race
night. The pictures come from a temporary store seeded by
``madtracker.control.demo`` and scored through the same clicks a
scorer makes, so they show the app as it is rather than a drawing of it.
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

BOARD_SIZE = (1920, 1080)
WINDOW_SIZE = (1920, 1080)
# The smallest business laptop screen; the window must still read well there.
WINDOW_SMALL = (1366, 768)


# The demo event's program, by row.
CHASE, ELIMINATION, POINTS, MADISON, WIN_AND_OUT, MADISON_2 = range(6)


def _grab(w: QWidget, size: tuple[int, int], path: Path, over: QWidget | None = None) -> Path:
    # Shown off screen so layouts activate exactly as they would on a
    # monitor, without a window flashing up on a developer's desktop.
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(*size)
    w.show()
    # Several passes: the preview sets its 16:9 height in its own resize,
    # the column change posts a layout request, and the card grid refits
    # on the resize that follows; each is handled a pass later.
    for _ in range(4):
        QApplication.processEvents()
    picture = w.grab()
    if over is not None and over.isVisible():
        # The preview floats over the window: painted where it sits, with
        # a plain frame standing in for the system's title bar.
        from PySide6.QtGui import QColor, QPainter

        over.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        QApplication.processEvents()
        at = over.pos() - w.pos()
        p = QPainter(picture)
        p.fillRect(at.x() - 1, at.y() - 29, over.width() + 2, over.height() + 30, QColor("#dfe3e8"))
        p.setPen(QColor("#11151b"))
        p.drawText(at.x() + 10, at.y() - 9, over.windowTitle())
        p.drawPixmap(at, over.grab())
        p.end()
    if not picture.save(str(path)):
        raise OSError(f"could not write {path}")
    return path


@contextmanager
def _answering_yes():
    """The walk leaves races mid-scoring on purpose, to photograph each state.

    The app then asks (switch away from a race being scored, a rider out),
    and a modal box has nobody to click it headless, so every question is
    answered yes for the duration.
    """
    from madtracker.ui import icons

    asked, chosen = icons.ask, icons.choose
    icons.ask = lambda *a, **k: True
    icons.choose = lambda *a, **k: a[4]
    try:
        yield
    finally:
        icons.ask, icons.choose = asked, chosen


def render_mockups(out_dir: str | Path) -> list[Path]:
    """Write every screen of the design, each in a state worth looking at."""
    from PySide6.QtCore import QSettings

    from madtracker.app import AppController

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    app = QApplication.instance()

    with tempfile.TemporaryDirectory(prefix="madtracker-mockup-") as tmp, _answering_yes():
        settings = QSettings(str(Path(tmp) / "settings.ini"), QSettings.Format.IniFormat)
        c = AppController(app, demo=True, settings=settings, data_dir=Path(tmp) / "data")
        c.main.set_screens(
            [
                ("\\\\.\\DISPLAY1", "Display 1, 1366x768 (Primary) (Windowed)"),
                ("\\\\.\\DISPLAY2", "Sony TV, 1920x1080 (Full Screen)"),
            ],
            None,
        )
        board, win = c.board, c.main
        races = c.races

        def shot_board(stem: str) -> None:
            written.append(_grab(board, BOARD_SIZE, out / f"{stem}.png"))

        def shot_window(stem: str, size: tuple[int, int] = WINDOW_SIZE) -> None:
            written.append(_grab(win, size, out / f"{stem}.png"))

        def select(row: int) -> None:
            c.select_race(races[row].race_id)

        def click(*tokens: str) -> None:
            for token in tokens:
                eid = c.live.roster.resolve(token)
                if eid is None or not c.click(eid):
                    raise RuntimeError(
                        f"mockup click {token!r} refused: {win.surface.problem.text()}"
                    )

        # Every launch opens on the logo page; the scorer flips to live
        # when racing starts.
        shot_board("board_logo")
        c.open_setup()
        shot_window("window_setup")
        c.close_setup()
        c.set_board_live(True)

        select(CHASE)
        shot_board("board_start_list")
        shot_window("window_start_list")
        click("7", "12", "33")
        # A lap before the finish shows only on the card, as a chip.
        c.rider_action(c.live.roster.resolve("45"), "lap_gained")
        # The last place known early goes in from the back.
        c.rider_action(c.live.roster.resolve("51"), "place_last")
        shot_window("window_chase")
        shot_window("window_chase_1366", WINDOW_SMALL)

        select(ELIMINATION)
        click("42", "17", "31", "8")
        shot_window("window_elimination")
        shot_board("board_elimination")

        select(POINTS)
        click("12", "7", "33", "4", "22", "9")
        c.record_sprint()
        c.rider_action(c.live.roster.resolve("19"), "lap_gained")
        click("7", "12", "4")
        shot_window("window_points")
        shot_window("window_points_1366", WINDOW_SMALL)
        click("19", "9", "38")
        c.record_sprint()
        shot_board("board_sprint_result")
        c.refresh()
        shot_board("board_standings")

        select(MADISON)
        click("Blue", "Red", "Yellow", "Black")
        c.record_sprint()
        click("Red", "Orange", "Blue", "Black")
        c.record_sprint()
        click("Orange", "Blue")
        shot_window("window_madison")
        c.refresh()
        shot_board("board_madison")

        select(WIN_AND_OUT)
        click("7", "12", "33")
        shot_window("window_win_and_out")

        # The chase finished: the review, then the same list marked final.
        select(CHASE)
        click("4", "22", "9", "19", "45", "38")
        shot_window("window_review")
        shot_window("window_review_1366", WINDOW_SMALL)
        shot_board("board_result")
        c.mark_final()
        shot_window("window_final")
        c._set_board("between", _between(c))
        shot_board("board_next_race")

        board.close()
        win.close()
        c.close()
    return written


def _between(c):
    from madtracker.control import board_feed
    from madtracker.control.race import LiveRace

    nxt = LiveRace(c.store, c.races[MADISON_2].race_id).view()
    last = c.live.view()
    return board_feed.between(c.event.name, nxt, last, f"Race {MADISON_2 + 1} of {len(c.races)}")
