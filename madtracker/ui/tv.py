"""The TV preview under the program: what the stands see, and a click on it changes what they see.

The preview is a second ``BoardCanvas`` fed every call the TV's window
gets, so the scorer always sees what the stands see (design principle
6). It is also the one control over the TV: a click on the logo puts
the race up, a click on the race puts the logo back. It needs no label,
since the picture is the state; under the pointer the picture dims under
"Switch to Live" or "Switch to Logo". While the board is off the picture is
grayed under "Off" and a click does nothing: picking a display in the
Scoreboard menu is the one way back. The Scoreboard menu's Logo and
Live are the same choice, kept in step.
"""

from functools import partial

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsColorizeEffect,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from madtracker.board.window import BoardCanvas
from madtracker.ui import style
from madtracker.ui.icons import mdi_pixmap

# Why a click does nothing: the TV shows nothing, or there is no race yet.
HIDDEN_TIP = "The scoreboard is off. Pick a display in the Scoreboard menu."
NO_RACE = "No race to show yet"
# What a click does, in the Scoreboard menu's words, over the picture
# while the pointer is on it: the picture alone does not say which way
# a click switches.
TO_LIVE = "Switch to Live"
TO_LOGO = "Switch to Logo"


class BoardPreview(QWidget):
    """The scoreboard, small, kept at 16:9 by following its width."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("boardPreview")
        self.canvas = BoardCanvas(parent=self)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # The narrowest program column (window.PROGRAM_NARROW_W, 240) less
        # the pane's 10 px margins and 1 px border each side: at 240 itself
        # the preview would overflow the pane and lose its right edge.
        self.setMinimumWidth(218)
        self.setFixedHeight(180)
        # Over the picture while the TV shows nothing: the picture goes gray
        # and faded, so what will come back is still there to see, under a
        # monitor-off glyph and "Off" in the window's gray ink. A red
        # "Hidden" would read as an error for what is usually a choice;
        # "Off" is the menu's None in a word.
        self.grayed = QGraphicsColorizeEffect(self.canvas)
        self.grayed.setColor(QColor("#808080"))
        self.grayed.setStrength(1.0)
        self.grayed.setEnabled(False)
        self.canvas.setGraphicsEffect(self.grayed)
        self.veil = OffVeil(self)
        self.veil.setVisible(False)
        self.hover = HoverVeil(self)
        self.hover.setVisible(False)

        # The canvas never sees the mouse: the pane under it is the control.
        self.canvas.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_hidden(self, hidden: bool) -> None:
        self.grayed.setEnabled(hidden)
        self.veil.setVisible(hidden)
        self.veil.raise_()

    def set_hover(self, text: str) -> None:
        """Dim the picture under ``text``; "" takes it away."""
        self.hover.set_text(text)
        self.hover.setVisible(bool(text))
        self.hover.raise_()

    def resizeEvent(self, event) -> None:
        height = round(self.width() * 9 / 16)
        if self.minimumHeight() != height:
            self.setFixedHeight(height)
        self.canvas.setGeometry(self.rect())
        self.veil.setGeometry(self.rect())
        self.hover.setGeometry(self.rect())
        super().resizeEvent(event)


OFF_TEXT = "Off"
# The wash over the grayed picture: light enough that the glyph and the
# word in the window's gray ink read on it.
OFF_WASH = QColor(255, 255, 255, 200)
# The wash under the pointer: dark, so the picture stays in color and
# still reads through it, with the glyph and the words in white on it.
HOVER_WASH = QColor(17, 21, 27, 150)
HOVER_INK = "#ffffff"


def paint_badge(widget: QWidget, wash: QColor, glyph_name: str, ink: str, text: str) -> None:
    """A wash over ``widget`` with a glyph over a word, both centered: the veils' one look."""
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(widget.rect(), wash)
    h = widget.height()
    glyph = max(16, round(h * 0.34))
    font = style.ui_font(10, bold=True)
    font.setPixelSize(max(12, round(h * 0.16)))
    metrics = QFontMetrics(font)
    gap = max(2, round(h * 0.03))
    total = glyph + gap + metrics.height()
    top = (h - total) // 2
    pix = mdi_pixmap(glyph_name, glyph, ink, widget.devicePixelRatioF())
    painter.drawPixmap((widget.width() - glyph) // 2, top, pix)
    painter.setFont(font)
    painter.setPen(QColor(ink))
    painter.drawText(
        QRect(0, top + glyph + gap, widget.width(), metrics.height()),
        int(Qt.AlignmentFlag.AlignCenter),
        text,
    )
    painter.end()


class OffVeil(QWidget):
    """The preview's "off" state: a light wash, the monitor-off glyph, and "Off"."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("boardOff")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def text(self) -> str:
        return OFF_TEXT

    def paintEvent(self, event) -> None:
        paint_badge(self, OFF_WASH, "monitor-off", style.DIM, OFF_TEXT)


class HoverVeil(QWidget):
    """What a click does, over the picture while the pointer is on it.

    The pane's hover tint and hand say the picture is a control; this
    says which way it switches, as the Scoreboard menu's words, on a
    dark wash so the picture itself stays in color under it.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("boardHover")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text = ""

    def text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self.update()

    def paintEvent(self, event) -> None:
        paint_badge(self, HOVER_WASH, "monitor", HOVER_INK, self._text)


class TvPane(QFrame):
    """The preview in its own white pane, as tall as the picture; the pane is the button.

    No focus: a click would keep it, and
    Space or Enter would switch the TV again. The outline on hover and
    the hand say it is a control; a click flashes it as a button does.
    """

    live_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("boardPane")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview = BoardPreview()
        self.canvas = self.preview.canvas
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(self.preview)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._live = False
        self._hidden = False
        self._ready = True
        self._pressed = False
        self._over = False

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.set_hover(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.set_hover(False)

    def set_hover(self, over: bool) -> None:
        """The pointer is over the pane, or has left it; the overlay follows."""
        self._over = over
        self._show_hover()

    def hover_text(self) -> str:
        """What the overlay says now: "" when it is not shown."""
        if not self._over or self._hidden or not self._ready:
            return ""
        return TO_LOGO if self._live else TO_LIVE

    def _show_hover(self) -> None:
        self.preview.set_hover(self.hover_text())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        pressed, self._pressed = self._pressed, False
        event.accept()
        if pressed and self.rect().contains(event.position().toPoint()):
            self.click()

    def click(self) -> None:
        """Switch the page, when the TV shows one and there is a race to show."""
        if self._hidden or not self._ready:
            return
        self.set_live(not self._live)
        self._set_flash(True)
        # The pane is no button, so look.ClickFlash never sees it: the
        # same flash for the same time, cleared by a single shot bound to
        # the pane, so a pane gone first is never touched (a free-floating
        # single shot can fire on a deleted pane).
        QTimer.singleShot(style.FLASH_MS, self, partial(self._set_flash, False))
        self.live_toggled.emit(self._live)

    def _set_flash(self, on: bool) -> None:
        self.setProperty("flash", on)
        # Qt re-reads property selectors only on a fresh polish.
        self.style().unpolish(self)
        self.style().polish(self)

    def set_board_hidden(self, hidden: bool) -> None:
        """The TV shows nothing: the picture is veiled, and the menu brings it back."""
        if hidden == self._hidden:
            return
        self._hidden = hidden
        self.preview.set_hidden(hidden)
        self.set_ready(self._ready)

    def set_live(self, live: bool) -> None:
        self._live = live
        self._show_hover()

    def is_live(self) -> bool:
        return self._live

    def set_ready(self, ready: bool) -> None:
        """Live only when there is a race to show and the TV shows something."""
        self._ready = ready
        active = ready and not self._hidden
        self.setCursor(Qt.CursorShape.PointingHandCursor if active else Qt.CursorShape.ArrowCursor)
        self.setProperty("active", active)
        # Said only when it explains why a click does nothing; what a
        # click does is the overlay's.
        self.setToolTip(HIDDEN_TIP if self._hidden else "" if ready else NO_RACE)
        self._show_hover()
        # Qt re-reads property selectors only on a fresh polish.
        self.style().unpolish(self)
        self.style().polish(self)
