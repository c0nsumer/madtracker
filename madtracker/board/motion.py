"""Motion for the scoreboard: a clock, easing curves and a repaint ticker.

Animation reads time from a ``Clock`` the canvas holds, so a test
drives it with a ``ManualClock`` and a headless canvas has none, which
leaves every page drawn at rest and the mockup renders deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QElapsedTimer, QObject, QTimer
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QWidget

# About 60 frames a second; the timer only runs while something moves.
FRAME_MS = 16


class Clock(Protocol):
    def now(self) -> float:
        """Milliseconds, monotonic."""
        ...


class SteadyClock:
    """The wall clock for a real display."""

    def __init__(self) -> None:
        self._t = QElapsedTimer()
        self._t.start()

    def now(self) -> float:
        return float(self._t.elapsed())


class ManualClock:
    """A clock that moves only when told, so a test steps motion exactly."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = float(start)

    def now(self) -> float:
        return self._now

    def advance(self, ms: float) -> None:
        self._now += ms


def phase(now: float, start: float, dur: float) -> float:
    """Progress 0..1 of a move that began at ``start`` and lasts ``dur``."""
    if dur <= 0:
        return 1.0 if now >= start else 0.0
    return min(1.0, max(0.0, (now - start) / dur))


def ease_out(x: float) -> float:
    return 1.0 - (1.0 - x) ** 3


def ease_in(x: float) -> float:
    return x**3


def ease_back(x: float, s: float = 1.70158) -> float:
    """Overshoots 1 and settles back to it."""
    y = x - 1.0
    return 1.0 + (s + 1.0) * y**3 + s * y**2


def mix(a: QColor, b: QColor, k: float) -> QColor:
    k = min(1.0, max(0.0, k))
    return QColor(
        round(a.red() + (b.red() - a.red()) * k),
        round(a.green() + (b.green() - a.green()) * k),
        round(a.blue() + (b.blue() - a.blue()) * k),
        round(a.alpha() + (b.alpha() - a.alpha()) * k),
    )


class Ticker(QObject):
    """Repaints a widget every frame while ``busy`` says something moves."""

    def __init__(self, widget: QWidget, busy: Callable[[], bool]) -> None:
        super().__init__(widget)
        self._widget = widget
        self._busy = busy
        self._timer = QTimer(self, interval=FRAME_MS)
        self._timer.timeout.connect(self._tick)

    def poke(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self) -> None:
        # The last update runs after busy turns false, so the final frame
        # is the resting one.
        self._widget.update()
        if not self._busy():
            self._timer.stop()


def default_clock() -> Clock | None:
    """No clock when headless, so tests and mockups see pages at rest."""
    if QGuiApplication.platformName() == "offscreen":
        return None
    return SteadyClock()
