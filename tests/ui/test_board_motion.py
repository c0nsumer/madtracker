"""The board's motion layer: a clock that is off when headless, easing, a ticker."""

import pytest
from PySide6.QtWidgets import QWidget

from madtracker.board import motion
from madtracker.board.window import BoardCanvas


def test_phase_clamps_and_eases_end_where_they_start():
    assert motion.phase(50, 100, 200) == 0.0
    assert motion.phase(200, 100, 200) == 0.5
    assert motion.phase(400, 100, 200) == 1.0
    assert motion.phase(99, 100, 0) == 0.0
    assert motion.phase(100, 100, 0) == 1.0
    for ease in (motion.ease_out, motion.ease_in, motion.ease_back):
        assert ease(0.0) == pytest.approx(0.0) and ease(1.0) == pytest.approx(1.0)
    assert max(motion.ease_back(i / 100) for i in range(101)) > 1.0


def test_manual_clock_moves_only_when_told():
    c = motion.ManualClock(10)
    assert c.now() == 10
    c.advance(5)
    assert c.now() == 15


def test_a_headless_canvas_has_no_clock_and_a_set_clock_reaches_every_page(qtbot):
    canvas = BoardCanvas()
    qtbot.addWidget(canvas)
    assert canvas.clock is None
    clock = motion.ManualClock()
    canvas.set_clock(clock)
    assert canvas.clock is clock
    assert all(page.clock is clock for page in canvas.pages.values())


def test_the_ticker_repaints_while_busy_and_stops_after(qtbot):
    class Counted(QWidget):
        updates = 0

        def update(self):
            self.updates += 1

    widget = Counted()
    qtbot.addWidget(widget)
    state = {"ticks": 0}

    def busy():
        state["ticks"] += 1
        return state["ticks"] <= 3

    ticker = motion.Ticker(widget, busy)
    ticker.poke()
    ticker.poke()  # a second poke while running changes nothing
    qtbot.waitUntil(lambda: state["ticks"] >= 4, timeout=1000)
    qtbot.wait(5 * motion.FRAME_MS)
    assert widget.updates == 4  # three busy ticks, then one last
    assert state["ticks"] == 4  # the timer stopped
    ticker.poke()
    qtbot.waitUntil(lambda: state["ticks"] >= 5, timeout=1000)
    assert widget.updates == 5
