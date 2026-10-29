"""The app's own wordmark, drawn as vectors: the bike glyph and the app name.

The board shows it when the venue has set no logo of its own. A PNG
stretched across 70% of a 4K TV, and again by a 150% Windows display
scale, goes soft; the glyph drawn from its SVG and the name filled as a
text outline stay sharp at any size and any device pixel ratio.
tools/make_logo.py draws the bundled PNG (which the PDF and the Settings
preview use) through ``paint`` too, so the three never disagree.
"""

from importlib.resources import files

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath

from madtracker import APP_NAME

# Proportions of the original placeholder PNG, in units of the glyph's
# ink height (168 px of its 215): the gap from glyph to text, the height
# of the text's ink (ascender top to baseline; the name has no
# descenders) and where that ink ends below the glyph's top.
GAP = 39 / 168
TEXT_H = 100 / 168
TEXT_BOTTOM = 139 / 168
# The PNG's canvas, 1200 by 215, and the share of its height the ink
# fills. The top bar sizes its box and the mark in it as for the PNG,
# so the mark and the race title sit where the PNG put them.
CANVAS_ASPECT = 1200 / 215
CANVAS_INK = 168 / 215
# The bike's ink inside its 24-unit viewBox, read from the path data:
# the wheels touch both sides and the bottom, the head stops at 1.2.
GLYPH_INK = QRectF(0, 1.2, 24, 20.8)
GLYPH_W = GLYPH_INK.width() / GLYPH_INK.height()
COLOR = "#ffffff"
# The text outline is built once at this size and scaled by the painter;
# the outline is exact at any scale, unlike a hinted font size.
_REF_PX = 1000

_renderer = None
_text: QPainterPath | None = None


def _glyph():
    global _renderer
    if _renderer is None:
        from PySide6.QtSvg import QSvgRenderer

        svg = files("madtracker.assets").joinpath("icons", "bike.svg").read_text(encoding="utf-8")
        svg = svg.replace("<path ", f'<path fill="{COLOR}" ', 1)
        _renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    return _renderer


def _text_path() -> QPainterPath:
    global _text
    if _text is None:
        from madtracker.ui.look import available_families

        font = QFont()
        font.setFamilies(available_families())
        font.setPixelSize(_REF_PX)
        font.setWeight(QFont.Weight.Black)
        path = QPainterPath()
        path.addText(0, 0, font, APP_NAME)
        _text = path
    return _text


def _text_w() -> float:
    """The text's ink width, in glyph ink heights."""
    bounds = _text_path().boundingRect()
    return bounds.width() * TEXT_H / bounds.height()


def aspect() -> float:
    """Width over height of the drawn ink, for sizing the box it goes in."""
    return GLYPH_W + GAP + _text_w()


def paint(
    p: QPainter,
    rect: QRectF,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
) -> QRectF:
    """Draw the wordmark as large as fits ``rect``; returns the rectangle the ink fills."""
    ratio = aspect()
    g = min(rect.height(), rect.width() / ratio)
    w = g * ratio
    if align & Qt.AlignmentFlag.AlignHCenter:
        x = rect.center().x() - w / 2
    elif align & Qt.AlignmentFlag.AlignRight:
        x = rect.right() - w
    else:
        x = rect.left()
    y = rect.center().y() - g / 2

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = g / GLYPH_INK.height()
    try:
        glyph = _glyph()
    except OSError:
        # A build that left the SVG out still shows the name; a blank
        # board would hide the fault behind a worse one.
        glyph = None
    if glyph is not None:
        glyph.render(p, QRectF(x - GLYPH_INK.x() * s, y - GLYPH_INK.y() * s, 24 * s, 24 * s))

    path = _text_path()
    bounds = path.boundingRect()
    k = TEXT_H * g / bounds.height()
    p.translate(
        x + (GLYPH_W + GAP) * g - bounds.left() * k, y + TEXT_BOTTOM * g - bounds.bottom() * k
    )
    p.scale(k, k)
    p.fillPath(path, QColor(COLOR))
    p.restore()
    return QRectF(x, y, w, g)
