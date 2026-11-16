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


# The Madison table's rotation ------------------------------------------------


def test_rotation_shows_names_then_color_then_names():
    from madtracker.board import rotation
    from madtracker.board.rotation import RowLook

    assert rotation.look(0, 0, 5) == RowLook(0, 1, 0)
    mid = rotation.NAMES_MS + rotation.change_ms(5)
    assert rotation.look(mid + 10, 0, 5) == RowLook(1, 0, 1)
    assert rotation.look(mid + 10, 4, 5) == RowLook(1, 0, 1)
    assert rotation.look(rotation.cycle_ms(5) + 10, 0, 5) == RowLook(0, 1, 0)
    assert rotation.cycle_ms(5) == 10000 + 4000 + 2 * (4 * 80 + 750)


def test_rows_start_their_change_eighty_ms_apart():
    from madtracker.board import rotation

    t0 = rotation.NAMES_MS + 100
    assert rotation.look(t0, 0, 5).sweep > rotation.look(t0, 1, 5).sweep > 0
    assert rotation.look(t0 - 100 + 80, 1, 5) == rotation.look(t0 - 100, 0, 5)
    assert rotation.look(rotation.NAMES_MS + 79, 1, 5) == rotation.RowLook(0, 1, 0)


def test_a_rows_names_fade_before_its_color_word_rises():
    from madtracker.board import rotation

    at = rotation.NAMES_MS
    early = rotation.look(at + rotation.NAMES_FADE_MS, 0, 5)
    assert early.names == 0 and early.label == 0 and 0 < early.sweep < 1
    late = rotation.look(at + rotation.LABEL_AT_MS + rotation.LABEL_MS / 2, 0, 5)
    assert 0 < late.label < 1
    assert rotation.look(at + rotation.SWEEP_MS, 0, 5).sweep == 1


def test_the_change_back_is_the_change_to_color_run_backward():
    from madtracker.board import rotation

    change = rotation.change_ms(5)
    back = rotation.NAMES_MS + change + rotation.COLOR_MS
    for s in (0, 100, 333, 700, change - 1):
        for row in range(5):
            assert rotation.look(back + s, row, 5) == rotation.look(
                rotation.NAMES_MS + change - s, row, 5
            )


def test_the_rotation_says_when_it_moves_and_how_long_until_it_next_does():
    from madtracker.board import rotation

    change = rotation.change_ms(5)
    assert not rotation.moving(0, 5)
    assert rotation.until_change(0, 5) == rotation.NAMES_MS
    assert rotation.moving(rotation.NAMES_MS + 1, 5)
    assert rotation.until_change(rotation.NAMES_MS + 1, 5) == 0
    color = rotation.NAMES_MS + change + 1000
    assert not rotation.moving(color, 5)
    assert rotation.until_change(color, 5) == rotation.COLOR_MS - 1000
    assert rotation.moving(rotation.cycle_ms(5) - 1, 5)


def test_the_page_turns_after_each_names_and_color_cycle():
    from madtracker.board import rotation

    cycle = rotation.cycle_ms(6)
    assert [rotation.page_at(t, 6, 2) for t in (0, cycle - 1, cycle, 2 * cycle + 5)] == [0, 0, 1, 0]
    assert rotation.page_at(5 * cycle, 6, 1) == 0
