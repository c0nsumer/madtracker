"""The board's texture: one shape tiled in a staggered grid.

The scoreboard fades and solid fills carry a faint repeat of a shape (a
bundled pattern, or the venue's own SVG), sized, turned, spaced, and toned
by the venue's adjustments. The cell is an alpha mask, so any color tints
it, and it is cut to tile seamlessly so a brush anchored at one point shows
the same pattern under every row.
"""

import functools
from dataclasses import dataclass
from importlib.resources import files
from xml.etree import ElementTree as _writer  # writes only; parsing is defusedxml's

from defusedxml import ElementTree
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QTransform
from PySide6.QtSvg import QSvgRenderer

# The shape's height in board units; its width follows its aspect.
TILE_H = 32
# The grid's pitch as a multiple of the shape's width and height. Every
# second row shifts half a pitch, so shapes interlock as bricks do.
PITCH_X = 1.35
PITCH_Y = 0.92
# The texture's strength on a fade, as a share of the fade's own alpha.
FADE_SHARE = 1 / 3
# A solid color's texture: a veil of this alpha, in the color darkened by
# SOLID_DARKER (the QColor.darker factor).
SOLID_ALPHA = 0.12
SOLID_DARKER = 115
# A venue file larger than this is refused: a logo is a few kilobytes.
MAX_SVG_BYTES = 256 * 1024

# The bundled patterns, in the order the picker offers them: key and label.
PATTERNS: tuple[tuple[str, str], ...] = (
    ("bolts", "Lightning Bolts"),
    ("slant", "Slant Strokes"),
    ("chevrons", "Chevrons"),
    ("dots", "Dots"),
    ("none", "None"),
)
DEFAULT_PATTERN = "bolts"
_BUNDLED = ("bolts", "slant", "chevrons", "dots")
# A bundled pattern's shape height as a share of TILE_H: dots are a fine
# grain and chevrons small Vs, so neither is as tall as a row's text.
# A venue's own shape is drawn at 1.0.
BASE_SCALE = {"bolts": 1.0, "slant": 1.0, "chevrons": 0.75, "dots": 0.28}

_SVG_NS = "http://www.w3.org/2000/svg"
_SHAPES = ("path", "polygon", "rect", "circle", "ellipse")

_writer.register_namespace("", _SVG_NS)
_writer.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


# Elements that draw. first_shape_svg keeps only the tagged one among them,
# so the document renders as the shape alone, transforms and all.
_DRAWS = (*_SHAPES, "line", "polyline", "text", "image", "use", "g", "switch")


# Containers whose shapes are never drawn where they stand: they are clips,
# masks, definitions, or styling, so a shape inside is not the logo.
_NOT_DRAWN = ("defs", "clipPath", "mask", "symbol", "pattern", "marker", "style")
# A shape wider or taller than this many times its other side cannot tile
# in a cell of a usable size, and would not read as a texture.
MAX_ASPECT = 8
# The backstop on a cell's side in pixels.
MAX_CELL_PX = 8192


def _declared(el, name: str) -> str | None:
    """A presentation value from the element's inline style or attribute."""
    for part in (el.get("style") or "").split(";"):
        key, _, value = part.partition(":")
        if key.strip() == name and value.strip():
            return value.strip()
    value = el.get(name)
    return value.strip() if value else None


def first_shape_svg(data: bytes) -> bytes | None:
    """The SVG reduced to its first filled shape, tagged ``id="tile"``, or None.

    Hostile input is refused: an oversize file, malformed XML, an entity
    bomb or external entity (defusedxml raises), or no filled shape. The
    shape keeps its ancestors' transforms; everything else that draws is
    dropped, so the renderer's measure of the document is the shape's.
    """
    if len(data) > MAX_SVG_BYTES:
        return None
    try:
        root = ElementTree.fromstring(data)
    except Exception:
        return None
    if _local(root.tag) != "svg":
        return None
    chain: list = []

    def find(el, inherited: str | None) -> bool:
        for child in el:
            tag = _local(child.tag)
            if tag in _NOT_DRAWN or _declared(child, "display") == "none":
                continue
            fill = _declared(child, "fill") or inherited
            if tag in _SHAPES and fill != "none":
                chain.append((el, child))
                return True
            if find(child, fill):
                chain.append((el, child))
                return True
        return False

    if not find(root, _declared(root, "fill")):
        return None
    tile = chain[0][1]
    keep = {id(el) for pair in chain for el in pair}
    keep.add(id(tile))
    for parent, _ in chain:
        for child in list(parent):
            if id(child) not in keep and _local(child.tag) in _DRAWS:
                parent.remove(child)
    tile.set("id", "tile")
    out = _writer.tostring(root, encoding="utf-8")
    return out if _measure(out) is not None else None


def _measure(svg: bytes) -> tuple[QSvgRenderer, QRectF] | None:
    """The renderer and the shape's box, or None when it cannot tile."""
    renderer = QSvgRenderer(QByteArray(svg))
    ink = _ink_bounds(renderer) if renderer.isValid() else None
    if ink is None:
        return None
    ratio = ink.width() / ink.height()
    if ratio > MAX_ASPECT or ratio < 1 / MAX_ASPECT:
        return None
    return renderer, ink


def _ink_bounds(renderer: QSvgRenderer) -> QRectF | None:
    """The rectangle, in the document's units, that the drawing covers.

    QSvgRenderer.boundsOnElement ignores the transforms of the element's
    parent groups, so the shape is measured from a render instead.
    """
    view = renderer.viewBoxF()
    if view.width() <= 0 or view.height() <= 0:
        return None
    scale = 1024 / max(view.width(), view.height())
    w, h = max(1, round(view.width() * scale)), max(1, round(view.height() * scale))
    image = QImage(w, h, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    renderer.render(p, QRectF(0, 0, w, h))
    p.end()
    alpha = bytes(image.constBits())[3::4]
    rows = [y for y in range(h) if any(alpha[y * w : (y + 1) * w])]
    if not rows:
        return None
    cols = [x for x in range(w) if any(alpha[x::w])]
    left, right, top, bottom = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
    return QRectF(
        view.x() + left / scale,
        view.y() + top / scale,
        (right - left) / scale,
        (bottom - top) / scale,
    )


@functools.cache
def pattern_svg(key: str) -> bytes | None:
    """A bundled pattern's SVG reduced to its shape, or None for any other key."""
    if key not in _BUNDLED:
        return None
    raw = (files("madtracker.assets") / "textures" / f"{key}.svg").read_bytes()
    return first_shape_svg(raw)


# Each adjustment's range, low and high.
SIZE = (50, 200)
ROTATION = (-45, 45)
SPACING = (60, 200)
OPACITY = (0, 200)
TONE = (-100, 100)


def _within(value: int, bounds: tuple[int, int]) -> int:
    return min(bounds[1], max(bounds[0], int(value)))


@dataclass(frozen=True)
class Adjust:
    """The venue's taste for the texture: percents, and rotation in degrees."""

    size: int = 100
    rotation: int = 0
    spacing: int = 100
    opacity: int = 100
    tone: int = 0

    def clamped(self) -> "Adjust":
        return Adjust(
            _within(self.size, SIZE),
            _within(self.rotation, ROTATION),
            _within(self.spacing, SPACING),
            _within(self.opacity, OPACITY),
            _within(self.tone, TONE),
        )


def _mixed(color: QColor, tone: int) -> QColor:
    """``color`` mixed toward black (tone below 0) or white (above), keeping its alpha."""
    if tone == 0:
        return QColor(color)
    target = 0 if tone < 0 else 255
    share = abs(tone) / 100
    out = QColor(
        round(color.red() + (target - color.red()) * share),
        round(color.green() + (target - color.green()) * share),
        round(color.blue() + (target - color.blue()) * share),
    )
    out.setAlpha(color.alpha())
    return out


class Texture:
    """A shape and its staggered cell, cached per scale.

    ``builtin`` marks a bundled pattern. A shape that cannot tile falls
    back to the bolts, so a texture always draws something.
    """

    def __init__(
        self, svg: bytes, adjust: Adjust | None = None, *, builtin: bool = False, scale: float = 1.0
    ):
        self.adjust = (adjust or Adjust()).clamped()
        measured = _measure(svg)
        if measured is None:
            fallback = pattern_svg(DEFAULT_PATTERN)
            measured = _measure(fallback) if fallback is not None else None
            builtin = True
        assert measured is not None
        renderer, ink = measured
        # The view box is the shape's own box, so the render below fills
        # the bounds it is given.
        renderer.setViewBox(ink)
        self._renderer = renderer
        self._aspect = ink.width() / ink.height()
        self._builtin = builtin
        self._scale = scale
        self._cells: dict[tuple[float, float], QImage] = {}
        self._brushes: dict[tuple[float, float, int], QBrush] = {}

    @property
    def builtin(self) -> bool:
        return self._builtin

    @property
    def rotated(self) -> bool:
        return self.adjust.rotation != 0

    @property
    def fade_share(self) -> float:
        return FADE_SHARE * self.adjust.opacity / 100

    @property
    def solid_alpha(self) -> float:
        return SOLID_ALPHA * self.adjust.opacity / 100

    def fade_color(self, base: QColor) -> QColor:
        return _mixed(base, self.adjust.tone)

    def solid_color(self, base: QColor) -> QColor:
        return _mixed(base.darker(SOLID_DARKER), self.adjust.tone)

    def _draw_shape(self, p: QPainter, x: float, y: float, w: float, h: float) -> None:
        self._renderer.render(p, QRectF(x, y, w, h))

    def cell(self, u: float, dpr: float) -> QImage:
        key = (u, dpr)
        if key in self._cells:
            return self._cells[key]
        h = TILE_H * self._scale * self.adjust.size / 100 * u * dpr
        w = h * self._aspect
        spread = self.adjust.spacing / 100
        width = min(MAX_CELL_PX, max(1, round(PITCH_X * spread * w)))
        height = min(MAX_CELL_PX, max(1, round(2 * PITCH_Y * spread * h)))
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("white"))
        for ox, oy in ((0.0, 0.0), (width / 2, height / 2)):
            for dx in (-width, 0, width):
                for dy in (-height, 0, height):
                    self._draw_shape(p, ox + dx, oy + dy, w, h)
        # The shape's own colors are dropped; only its alpha is the mask.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(image.rect(), QColor("white"))
        p.end()
        image.setDevicePixelRatio(dpr)
        self._cells[key] = image
        return image

    def brush(self, u: float, dpr: float, color: QColor, origin: QPointF) -> QBrush:
        key = (u, dpr, color.rgba())
        tinted_brush = self._brushes.get(key)
        if tinted_brush is None:
            # A copy of the mask, pixel for pixel: drawing the mask onto a
            # fresh image would scale it by its pixel ratio.
            tinted = self.cell(u, dpr).copy()
            p = QPainter(tinted)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            p.fillRect(tinted.rect(), color)
            p.end()
            tinted.setDevicePixelRatio(dpr)
            tinted_brush = QBrush(tinted)
            self._brushes[key] = tinted_brush
        brush = QBrush(tinted_brush)
        # The turn is about the row's origin, so the pattern stays fixed to
        # the row however the adjustment leans it.
        turn = QTransform.fromTranslate(origin.x(), origin.y())
        if self.adjust.rotation:
            turn.rotate(self.adjust.rotation)
        brush.setTransform(turn)
        return brush


def make_texture(pattern: str, venue_svg: bytes | None, adjust: Adjust) -> Texture | None:
    """The texture for a stored choice, or None when nothing is to be drawn.

    ``none`` and zero opacity draw nothing. ``venue`` is the venue's own
    shape, the bolts without one; a key that is not offered gives the bolts.
    """
    adjust = adjust.clamped()
    if pattern == "none" or adjust.opacity == 0:
        return None
    if pattern == "venue" and venue_svg:
        return Texture(venue_svg, adjust)
    svg = pattern_svg(pattern) or pattern_svg(DEFAULT_PATTERN)
    assert svg is not None
    key = pattern if pattern in BASE_SCALE else DEFAULT_PATTERN
    return Texture(svg, adjust, builtin=True, scale=BASE_SCALE[key])
