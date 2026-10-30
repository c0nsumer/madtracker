"""Platform-independent look: one bundled font, a fixed light palette, Fusion.

Two things vary by machine and must not: which fonts are installed,
and whether the operating system is in dark mode. Qt's own default
picks up both. So the program bundles Inter (SIL Open Font License,
``madtracker/assets/fonts/``) and registers it before any
widget is built, asks for the Fusion style with an explicit light
palette, which ignores the OS theme, and sizes every control from that
font. The window sets Regular with SemiBold for emphasis and Bold for
headings and primary buttons; the scoreboard paints its own dark theme
in Bold, with Black for its largest elements.

``madtracker.assets.fonts`` owns the registration; the same small step
lives here as the fallback.
"""

import sys
from functools import partial
from importlib.resources import files

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QLabel,
    QProxyStyle,
    QScrollBar,
    QStyle,
    QStyleFactory,
)

# The bundled family, by preference; whatever the folder registers wins.
PREFERRED = ("Inter",)

_registered: list[str] | None = None
_families: list[str] | None = None


def register_fonts() -> list[str]:
    """Load the bundled fonts into Qt once; returns the family names registered."""
    global _registered
    if _registered is not None:
        return list(_registered)
    found: list[str] = []
    try:
        from madtracker.assets import fonts

        found = list(fonts.register_with_qt())
    except (ImportError, OSError):
        found = []
    if found:
        _registered = found
        return list(found)
    folder = files("madtracker.assets").joinpath("fonts")
    try:
        names = sorted(p.name for p in folder.iterdir() if p.name.endswith((".ttf", ".otf")))
    except (OSError, AttributeError):
        names = []
    for name in names:
        try:
            data = folder.joinpath(name).read_bytes()
        except OSError:
            continue
        index = QFontDatabase.addApplicationFontFromData(data)
        if index >= 0:
            for family in QFontDatabase.applicationFontFamilies(index):
                if family not in found:
                    found.append(family)
    _registered = found
    return list(found)


def available_families() -> list[str]:
    """The bundled family first, then the system font as the one fallback.

    Resolved once, after the application exists (the font database needs
    one). No per-machine search: the bundled font is the look.
    """
    global _families
    if _families is None:
        registered = register_fonts()
        picked = [f for f in PREFERRED if f in registered] or registered[:1]
        system = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
        # Only a family the database lists by name: on macOS the system
        # font is the hidden ".AppleSystemUIFont", which Qt resolves itself
        # but would otherwise reach through an alias search. Glyphs the
        # bundled face lacks still fall back through Qt's own list.
        if system and system not in picked and system in QFontDatabase.families():
            picked.append(system)
        _families = picked or [QFont().defaultFamily()]
    return list(_families)


# The check boxes and radio buttons, drawn here rather than by Fusion.
# Fusion draws an indicator 13 px square with an outline derived from
# the window color, a faint gray on this light palette that a scorer
# reading a laptop at arm's length cannot see as a box at all. These are
# larger, outlined in the window's dim ink and filled with the accent
# when on, in every widget that shows one: a QCheckBox, a list item, a
# table cell. One drawing, so a tick looks the same everywhere.
INDICATOR_PX = 20
_CHECK_BORDER = QColor("#6b7484")
_CHECK_ON = QColor("#1f5fd1")
_CHECK_HOVER = QColor("#1f5fd1")
_CHECK_OFF_FILL = QColor("#ffffff")
_CHECK_DISABLED_BORDER = QColor("#c3c9d2")
_CHECK_DISABLED_FILL = QColor("#f3f4f6")
_CHECK_DISABLED_ON = QColor("#9aa1ad")
_CHECK_GLYPH = QColor("#ffffff")


class CheckStyle(QProxyStyle):
    """Fusion with legible check and radio indicators (see INDICATOR_PX)."""

    CHECKS = (
        QStyle.PrimitiveElement.PE_IndicatorCheckBox,
        QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
    )
    RADIOS = (QStyle.PrimitiveElement.PE_IndicatorRadioButton,)
    SIZES = (
        QStyle.PixelMetric.PM_IndicatorWidth,
        QStyle.PixelMetric.PM_IndicatorHeight,
        QStyle.PixelMetric.PM_ExclusiveIndicatorWidth,
        QStyle.PixelMetric.PM_ExclusiveIndicatorHeight,
    )

    def __init__(self) -> None:
        super().__init__(QStyleFactory.create("Fusion"))
        # Named as the base style is, so a check for Fusion still passes.
        self.setObjectName("fusion")

    def pixelMetric(self, metric, option=None, widget=None) -> int:
        if metric in self.SIZES:
            return INDICATOR_PX
        return super().pixelMetric(metric, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None) -> None:
        if element in self.CHECKS:
            self._draw_check(option, painter)
        elif element in self.RADIOS:
            self._draw_radio(option, painter)
        else:
            super().drawPrimitive(element, option, painter, widget)

    @staticmethod
    def _colors(option) -> tuple[QColor, QColor, QColor]:
        """Border, fill and glyph for the indicator's state."""
        state = option.state
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        on = bool(state & (QStyle.StateFlag.State_On | QStyle.StateFlag.State_NoChange))
        if not enabled:
            fill = _CHECK_DISABLED_ON if on else _CHECK_DISABLED_FILL
            return _CHECK_DISABLED_BORDER, fill, _CHECK_GLYPH
        if on:
            return _CHECK_ON, _CHECK_ON, _CHECK_GLYPH
        hover = bool(state & QStyle.StateFlag.State_MouseOver)
        return (_CHECK_HOVER if hover else _CHECK_BORDER), _CHECK_OFF_FILL, _CHECK_GLYPH

    @staticmethod
    def _square(option) -> QRectF:
        r = option.rect
        side = min(r.width(), r.height(), INDICATOR_PX)
        return QRectF(
            r.x() + (r.width() - side) / 2, r.y() + (r.height() - side) / 2, side, side
        ).adjusted(1, 1, -1, -1)

    def _draw_check(self, option, painter: QPainter) -> None:
        border, fill, glyph = self._colors(option)
        box = self._square(option)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(border, 1.5))
        painter.setBrush(fill)
        painter.drawRoundedRect(box, 3, 3)
        s = box.width()
        pen = QPen(glyph, max(2.0, s * 0.13))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if option.state & QStyle.StateFlag.State_NoChange:
            painter.drawLine(
                QPointF(box.x() + s * 0.25, box.center().y()),
                QPointF(box.x() + s * 0.75, box.center().y()),
            )
        elif option.state & QStyle.StateFlag.State_On:
            painter.drawPolyline(
                [
                    QPointF(box.x() + s * 0.24, box.y() + s * 0.53),
                    QPointF(box.x() + s * 0.43, box.y() + s * 0.72),
                    QPointF(box.x() + s * 0.77, box.y() + s * 0.31),
                ]
            )
        painter.restore()

    def _draw_radio(self, option, painter: QPainter) -> None:
        border, fill, glyph = self._colors(option)
        box = self._square(option)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(border, 1.5))
        painter.setBrush(fill)
        painter.drawEllipse(box)
        if option.state & QStyle.StateFlag.State_On:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glyph)
            dot = box.width() * 0.36
            painter.drawEllipse(box.center(), dot / 2, dot / 2)
        painter.restore()


# One text size for every scorer; the operator window's sizes are
# chosen once, for older volunteers reading a laptop at arm's length.
# Sizes are in points, which Windows and Linux draw at 96 to the inch and
# macOS at 72, so macOS scales them up by 96/72 and the window has the
# same proportions in pixels on every platform. The scale is read from
# the screen rather than assumed from the OS: Qt's offscreen platform,
# which the suite runs on, draws at 96 everywhere, and the OS alone
# would scale a Mac's test run twice.
TEXT_SCALE = 96 / 72 if sys.platform == "darwin" else 1.0
_text_scale: float | None = None


def text_scale() -> float:
    """96 over the screen's logical dpi on macOS, 1.0 elsewhere; fixed once read."""
    global _text_scale
    if _text_scale is None:
        if sys.platform != "darwin":
            _text_scale = 1.0
        else:
            screen = QGuiApplication.primaryScreen() if QGuiApplication.instance() else None
            if screen is None:
                return TEXT_SCALE
            _text_scale = 96 / (screen.logicalDotsPerInch() or 72)
    return _text_scale


# The operator window's body text, and the application font: tables,
# menus, lists and buttons are this size, and nothing in the window is
# smaller. Cards, titles and the task line are larger on purpose.
APP_PT = 12.0

# The dialogs' type: 11 pt, a step under the window's 12, since the
# scorers are older and 10 pt reads small beside the window.
DIALOG_BASE_PT = 11.0


def dialog_point_size(base_pt: float = DIALOG_BASE_PT) -> float:
    return round(base_pt * text_scale(), 1)


def dialog_font_rule(base_pt: float = DIALOG_BASE_PT) -> str:
    """A style sheet rule that sets every widget in a dialog to the scaled size.

    A widget with a style sheet resolves its children's fonts from the
    application font, not from its own ``setFont``; a rule on ``QWidget``
    reaches every child.
    """
    return f"QWidget {{ font-size: {dialog_point_size(base_pt)}pt; }}\n"


def light_palette() -> QPalette:
    """A fixed light palette so the operator window reads the same in any OS theme."""
    p = QPalette()
    ink = QColor("#11151b")
    dim = QColor("#8a919c")
    # Read, not only seen: a placeholder that is the value a blank field
    # takes, and a locked field's value. The hint gray reaches 4.5:1 on a
    # field's gray and is still lighter than typed text.
    shown = QColor("#5b6472")
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        p.setColor(group, QPalette.ColorRole.Window, QColor("#f3f4f6"))
        p.setColor(group, QPalette.ColorRole.WindowText, ink)
        p.setColor(group, QPalette.ColorRole.Base, QColor("#ffffff"))
        p.setColor(group, QPalette.ColorRole.AlternateBase, QColor("#f5f6f8"))
        p.setColor(group, QPalette.ColorRole.Text, ink)
        p.setColor(group, QPalette.ColorRole.PlaceholderText, shown)
        p.setColor(group, QPalette.ColorRole.Button, QColor("#e9ebef"))
        p.setColor(group, QPalette.ColorRole.ButtonText, ink)
        p.setColor(group, QPalette.ColorRole.Highlight, QColor("#cfe0ff"))
        p.setColor(group, QPalette.ColorRole.HighlightedText, ink)
        # The style sheet's dark tip (style.py), for a tip shown where no
        # sheet reaches.
        p.setColor(group, QPalette.ColorRole.ToolTipBase, QColor("#2b313a"))
        p.setColor(group, QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
        p.setColor(group, QPalette.ColorRole.Link, QColor("#1f5fd1"))
    disabled = QPalette.ColorGroup.Disabled
    p.setColor(disabled, QPalette.ColorRole.WindowText, dim)
    p.setColor(disabled, QPalette.ColorRole.Text, shown)
    p.setColor(disabled, QPalette.ColorRole.ButtonText, shown)
    p.setColor(disabled, QPalette.ColorRole.PlaceholderText, shown)
    p.setColor(disabled, QPalette.ColorRole.Base, QColor("#f3f4f6"))
    p.setColor(disabled, QPalette.ColorRole.Button, QColor("#f3f4f6"))
    return p


class ClickFlash(QObject):
    """Every button darkens for a moment after a click, so a touch is seen to land.

    On the scorer's touchscreen a finger is up again before Qt's pressed
    look can be seen, so a click would leave no trace. The
    release that will click (the button is still down, so the pointer is
    on it) sets the ``flash`` property the sheet styles (style.py), and a
    single shot bound to the button clears it, so a button that goes
    away first is never touched. One filter on the application, since
    every button, dialog or card, should answer the same way; it also
    drops the context menu of every scrollbar.
    """

    def eventFilter(self, obj, event) -> bool:
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and isinstance(obj, QAbstractButton)
            and obj.isDown()
            and obj.isEnabled()
        ):
            flash(obj)
        if event.type() == QEvent.Type.ContextMenu and isinstance(obj, QScrollBar):
            # Qt's stock "Scroll here" menu on a right-click or a long
            # press on any scrollbar: a card and a result row have a menu
            # and nothing else does, and the stock one is unstyled.
            return True
        return False


class PlainLabels(QObject):
    """Every label shows its text as typed, never as markup.

    A QLabel left to Qt's automatic format draws a string that looks like
    HTML as HTML, so a team named "<b>Bold</b> & Co" would lose its tags
    and turn bold. Names are stored as typed and styled here, so every
    label, message box text and tooltip still on the automatic format is
    plain before it is first drawn; a label set to rich text on purpose
    keeps it.
    """

    def eventFilter(self, obj, event) -> bool:
        if (
            event.type() == QEvent.Type.Polish
            and isinstance(obj, QLabel)
            and obj.textFormat() == Qt.TextFormat.AutoText
        ):
            obj.setTextFormat(Qt.TextFormat.PlainText)
        return False


def flash(button: QAbstractButton) -> None:
    """Give ``button`` the flash look for style.FLASH_MS.

    The single shot is bound to the button as its context: once the
    button is gone the call never comes. A timer owned by the button,
    with a slot that deletes the timer, can crash in the event flush
    after the button goes.
    """
    from madtracker.ui.style import FLASH_MS

    set_flash(button, True)
    QTimer.singleShot(FLASH_MS, button, partial(set_flash, button, False))


def set_flash(button: QAbstractButton, on: bool) -> None:
    button.setProperty("flash", on)
    # Qt re-reads property selectors only on a fresh polish of that widget.
    button.style().unpolish(button)
    button.style().polish(button)


_click_flash: ClickFlash | None = None
_plain_labels: PlainLabels | None = None


def apply_look(app) -> None:
    """Fusion plus the light palette plus the bundled font, app-wide.

    Fusion is the one Qt style that draws from the palette alone, so the
    OS dark mode cannot leak through; the platform styles consult the
    system appearance for some controls regardless of the palette.
    """
    register_fonts()
    # Switching style re-polishes every live widget; on Windows that never
    # returns once many exist, so the style is set only when it changes.
    if not isinstance(app.style(), CheckStyle):
        app.setStyle(CheckStyle())
    # The palette is the app's own, so a change of the system's appearance
    # leaves the window light; the platform's parts around it (the title
    # bar, the native file dialogs) keep the system's appearance, as every
    # other window on a dark desktop does.
    app.setPalette(light_palette())
    global _click_flash, _plain_labels
    if _click_flash is None:
        _click_flash = ClickFlash(app)
        app.installEventFilter(_click_flash)
    if _plain_labels is None:
        _plain_labels = PlainLabels(app)
        app.installEventFilter(_plain_labels)
    base = QFont()
    base.setFamilies(available_families())
    base.setPointSizeF(APP_PT * text_scale())
    app.setFont(base)
