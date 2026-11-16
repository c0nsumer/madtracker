"""A Madison team's row: its color as a swatch and a fade, its riders named side by side.

The riders' names lead and the team's color only identifies (design
section 10): a solid swatch at the row's left edge says which jerseys,
and the fade carries the color under the first rider without putting
type on a colored ground. The row's left end is square; the swatch's
right edge, the fade's start, and the color view's moving edge lean at
the board's slant (``theme.SLANT``), the score chip's angle, on the
start list and the standings table alike. The venue's texture lies
faint on the fade and tone on tone on the solid color, fixed to the
row's top left (design section 10). A rider's row is the same row with a
bar for the swatch, in the accent for the leader and neutral for the
rest (``rider_bar``). Every size is in design units, multiplied by the
page's ``u``.
"""

import math
import weakref

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPolygonF,
)

from madtracker.board import texture as tx
from madtracker.board import theme as t

LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

# The solid swatch of the team color at the row's left edge, this wide at
# its foot; its slanted right edge widens it toward the row's top.
SWATCH_W = 26
# The fade's opacity at the row's left edge and at FADE_MID_AT of its
# width; by FADE_END_AT the row is bare, so the second rider sits on the
# plain row and the color reads as the team's, not as a highlight.
FADE_EDGE = 0.42
FADE_MID = 0.22
FADE_MID_AT = 0.25
FADE_END_AT = 0.60
ROW_RADIUS = 14
# Between two team rows.
ROW_GAP = 14
# The start list's surname and first name as shares of the row's height.
# A surname past 96 px and a first name past 52 px only crowd a lone
# team's row; the first name is never set under the board's floor.
START_SURNAME_SHARE = 0.50
START_SURNAME_MOST = 96
START_FIRST_SHARE = 0.27
START_FIRST_MOST = 52
# The first name a step quieter than the surname, which is what the
# announcer says and the stands match to the program.
FIRST_NAME_ALPHA = 200
# A sweep of the color across the row leads with a soft light edge this
# wide, rising to this alpha, so the eye follows it to where it stops.
SWEEP_EDGE = 60
SWEEP_EDGE_ALPHA = 90
# Air inside the row: after the swatch, and before the row's right end.
ROW_PAD = 40
# Between the first rider's half and the second's.
RIDER_GAP = 40
# The least air between a slanted swatch and the top of the surnames'
# capitals, where the swatch leans nearest them.
SLANT_AIR = 20
# A rider's bib plate beside the stacked name, as a share of the row's
# height up to PLATE_MOST, with PLATE_GAP before the name.
PLATE_SHARE = 0.56
PLATE_MOST = 100
PLATE_GAP = 28
# With Bibs Only the plates stand alone, so they take the room the names
# leave, up to the plate grid's own largest.
BIBS_ONLY_PLATE_SHARE = 0.70
BIBS_ONLY_PLATE_MOST = 170
# Between the first name's baseline and the surname's capitals, in ems of
# the first name: clear of the first name's descenders, close enough that
# the two lines read as one rider.
STACK_GAP = 0.30
# A rider row's bar: riders have no team colors, so the bar says rank. Every
# rider's but the leader's is this neutral light gray (the board's muted
# text), at the strength a team color's fade has.
RIDER_BAR = "#8f9aab"
# The fade's textured layers a texture keeps: every team of a page in
# both the start list's and the table's row size, with room for a resize.
FADE_LAYERS_KEPT = 48

# Each texture's fade layers, keyed by row size, color, scale and slant;
# a venue's new texture starts with none.
_fade_layers: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def split_name(full: str) -> tuple[str, str]:
    """A name as first word and the rest, so a multi-word surname stays whole.

    A rider with one name has it as the surname: it is the name the stands
    match, so it takes the surname's size.
    """
    first, sep, rest = full.strip().partition(" ")
    rest = rest.strip()
    if not sep or not rest:
        return "", first
    return first, rest


def _tinted(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlphaF(alpha)
    return out


def rider_bar(rank_or_place: int, accent: QColor) -> str:
    """A rider row's bar: the accent for the leader, as the leader's place is, else RIDER_BAR."""
    return accent.name() if rank_or_place == 1 else RIDER_BAR


def run(row: QRectF, slant: float) -> float:
    """How far a ``slant`` edge leans across ``row``'s height, its top right of its bottom."""
    return slant * row.height()


def between(row: QRectF, left: float, right: float, slant: float) -> QPolygonF:
    """The part of ``row`` between two edges leaning at ``slant``.

    Each edge is given by where it crosses the row's middle, so a run
    shared by both leaves the part's width the same at every height.
    """
    half = run(row, slant) / 2
    top, bottom = row.top(), row.bottom()
    right = max(left, right)
    return QPolygonF(
        [
            QPointF(left - half, bottom),
            QPointF(left + half, top),
            QPointF(right + half, top),
            QPointF(right - half, bottom),
        ]
    )


def upto(row: QRectF, right: float, slant: float) -> QPolygonF:
    """The part of ``row`` from its square left end to an edge leaning at ``slant``.

    The edge is given by where it crosses the row's middle.
    """
    half = run(row, slant) / 2
    left, top, bottom = row.left(), row.top(), row.bottom()
    return QPolygonF(
        [
            QPointF(left, bottom),
            QPointF(left, top),
            QPointF(max(left, right + half), top),
            QPointF(max(left, right - half), bottom),
        ]
    )


def band_shape(row: QRectF, u: float) -> QPainterPath:
    """A team row's outline: its left end square, its right end rounded.

    The swatch stands flush with the square end, so the color's left
    edge is the row's.
    """
    r = min(ROW_RADIUS * u, row.height() / 2, row.width() / 2)
    left, top, right, bottom = row.left(), row.top(), row.right(), row.bottom()
    shape = QPainterPath()
    shape.moveTo(left, top)
    shape.lineTo(right - r, top)
    shape.arcTo(QRectF(right - 2 * r, top, 2 * r, 2 * r), 90, -90)
    shape.lineTo(right, bottom - r)
    shape.arcTo(QRectF(right - 2 * r, bottom - 2 * r, 2 * r, 2 * r), 0, -90)
    shape.lineTo(left, bottom)
    shape.closeSubpath()
    return shape


def clearance(rh: float, rise: float, u: float) -> float:
    """How far right past ROW_PAD a name or plate stands to keep clear of the swatch.

    The swatch's right edge leans right as it rises, so on a tall row it
    crowds whatever starts ROW_PAD after its foot; ``rise`` is how far
    above the row's middle that thing's top stands. It moves only as far
    as keeps SLANT_AIR there, so a short row's names stay where they are.
    """
    lean = t.SLANT * (rh / 2 + rise)
    return max(0.0, lean - (ROW_PAD - SLANT_AIR) * u)


def slant_shift(rh: float, surname_px: float, u: float) -> float:
    """How far right the surnames stand to keep their capitals clear of the swatch.

    Measured at ``surname_px``, the largest the surnames may be set.
    """
    fm = QFontMetricsF(t.font(surname_px, t.HEAVY))
    # A line set centered on the row puts its capitals' top this far above the middle.
    caps = fm.capHeight() - (fm.ascent() - fm.descent()) / 2
    return clearance(rh, caps, u)


def stack_rise(first_px: float, last_px: float) -> float:
    """How far above the row's middle a stacked name's first-name capitals stand."""
    ff = t.font(first_px, t.SEMI)
    fmf = QFontMetricsF(ff)
    fml = QFontMetricsF(t.font(last_px, t.HEAVY))
    return (fmf.capHeight() + STACK_GAP * ff.pixelSize() + fml.capHeight()) / 2


def swatch_edge(row: QRectF, u: float, slant: float) -> float:
    """Where the swatch's slanted right edge crosses the row's middle.

    Its foot is SWATCH_W from the row's left edge, so the swatch is never
    narrower than that.
    """
    return row.left() + SWATCH_W * u + run(row, slant) / 2


def swatch_shape(row: QRectF, u: float, slant: float = 0.0) -> QPainterPath:
    """The swatch: flush with the row's square left end, its right edge leaning at ``slant``."""
    return fill_shape(row, u, slant=slant)


def _lead(row: QRectF, u: float, sweep: float, zone_right: float | None, slant: float) -> float:
    """Where the solid color ends across the row's middle: past the swatch by ``sweep``.

    At a full sweep the end's top corner is at ``zone_right``, so the
    color leans no further right than the zone.
    """
    swatch_right = swatch_edge(row, u, slant)
    sweep = min(1.0, max(0.0, sweep))
    end = (row.right() if zone_right is None else zone_right) - run(row, slant) / 2
    return swatch_right + (end - swatch_right) * sweep


def fill_shape(
    row: QRectF,
    u: float,
    sweep: float = 0.0,
    zone_right: float | None = None,
    slant: float = 0.0,
) -> QPainterPath:
    """The solid color: the swatch, swept ``sweep`` of the way to ``zone_right``.

    Its left end is the row's square end and its right end leans at
    ``slant``, so the color opens and closes along the swatch's edge.
    """
    lead = _lead(row, u, sweep, zone_right, slant)
    return _part(row, u, upto(row, lead, slant))


def _part(row: QRectF, u: float, part: QPolygonF) -> QPainterPath:
    # The part drawn as its own polygon, held short of the row's rounded
    # right end so it needs no cut against the outline: Qt's path
    # intersection misreads edges the two shapes share (the row's square
    # end, its top and bottom) and can return the whole row or the rest
    # of it instead of the part.
    r = min(ROW_RADIUS * u, row.height() / 2, row.width() / 2)
    left, right = row.left(), row.right() - r
    held = QPolygonF([QPointF(min(max(pt.x(), left), right), pt.y()) for pt in part])
    path = QPainterPath()
    path.addPolygon(held)
    path.closeSubpath()
    return path


def _across(row: QRectF, x: float, length: float, slant: float) -> QLinearGradient:
    """A gradient ``length`` long along the row from ``x`` at its middle, its lines at ``slant``.

    The gradient runs square to the slanted edges, so each of its colors
    lies along a line parallel to them, and ``length`` is measured along
    the row.
    """
    y = row.center().y()
    k = length / (1 + slant * slant)
    return QLinearGradient(x, y, x + k, y + k * slant)


def _fade(
    row: QRectF, color: QColor, u: float, slant: float, share: float = 1.0
) -> QLinearGradient:
    """The fade from the swatch's edge, its alphas scaled by ``share``.

    It starts at the swatch's edge and is gone FADE_END_AT of the row's
    width from its left end, measured across its middle.
    """
    start = swatch_edge(row, u, slant)
    length = max(1.0, row.width() * FADE_END_AT - (start - row.left()))
    mid = (row.width() * FADE_MID_AT - (start - row.left())) / length
    fade = _across(row, start, length, slant)
    fade.setColorAt(0, _tinted(color, FADE_EDGE * share))
    fade.setColorAt(min(max(mid, 0.0), 1.0), _tinted(color, FADE_MID * share))
    fade.setColorAt(1, _tinted(color, 0.0))
    return fade


def _build_fade_layer(
    texture: tx.Texture, w: float, h: float, color: QColor, u: float, dpr: float, slant: float
) -> QImage:
    """The texture in ``color`` over a ``w`` by ``h`` row's fade, at FADE_SHARE of its alpha.

    The layer's top left is the row's, and it reaches as far right as the
    fade does at the row's top.
    """
    row = QRectF(0, 0, w, h)
    reach = QRectF(0, 0, min(w, w * FADE_END_AT + run(row, slant) / 2), h)
    image = QImage(
        max(1, math.ceil(reach.width() * dpr)),
        max(1, math.ceil(h * dpr)),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.setDevicePixelRatio(dpr)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.fillRect(reach, texture.brush(u, dpr, color, QPointF(0, 0)))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.fillRect(reach, QBrush(_fade(row, color, u, slant, tx.FADE_SHARE)))
    p.end()
    return image


def _fade_layer(
    texture: tx.Texture, row: QRectF, color: QColor, u: float, dpr: float, slant: float
) -> QImage:
    layers = _fade_layers.setdefault(texture, {})
    key = (row.width(), row.height(), color.rgba(), u, dpr, slant)
    layer = layers.get(key)
    if layer is None:
        if len(layers) >= FADE_LAYERS_KEPT:
            del layers[next(iter(layers))]
        layer = _build_fade_layer(texture, row.width(), row.height(), color, u, dpr, slant)
        layers[key] = layer
    return layer


def paint_band(
    p: QPainter,
    row: QRectF,
    color: str | None,
    u: float,
    sweep: float = 0.0,
    zone_right: float | None = None,
    slant: float = 0.0,
    texture: tx.Texture | None = None,
    dpr: float = 1.0,
) -> None:
    """A team's row: the band, the solid swatch, and the fade under the first rider.

    ``sweep`` fills the color solid from the swatch toward ``zone_right``
    (the row's right end when None), 0 none and 1 all of it; while it is
    partway the fill leads with a soft light edge. The row's left end is
    square; ``slant`` leans the swatch's right edge, the fade's start,
    the fill's end, and its light edge at one angle, and the fill's end
    leans no further right than ``zone_right``. A dark color has no ring;
    the riders' names carry a dark team (design section 10).

    ``texture`` lies on the fade in the row's color, as strong as the
    fade times FADE_SHARE, and on the solid color one tone darker; it is
    fixed to the row's top left, so a sweep reveals it and never moves
    it. ``dpr`` is the display's pixel ratio, so it draws pixel for pixel.
    Neither the fade nor the fill reaches the figures, so neither does it.
    """
    shape = band_shape(row, u)
    sweep = min(1.0, max(0.0, sweep))
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(t.ROW)
    p.drawPath(shape)
    if color:
        c = QColor(color)
        start = swatch_edge(row, u, slant)
        p.setBrush(QBrush(_fade(row, c, u, slant)))
        p.drawPath(shape)
        if texture is not None:
            p.drawImage(row.topLeft(), _fade_layer(texture, row, c, u, dpr, slant))

        # As ``fill_shape`` draws it, from the outline already made.
        lead = _lead(row, u, sweep, zone_right, slant)
        fill = _part(row, u, upto(row, lead, slant))
        p.setBrush(c)
        p.drawPath(fill)
        if texture is not None:
            tone = c.darker(tx.SOLID_DARKER)
            tone.setAlphaF(tx.SOLID_ALPHA)
            p.setBrush(texture.brush(u, dpr, tone, row.topLeft()))
            p.drawPath(fill)
        if 0 < sweep < 1:
            edge = SWEEP_EDGE * u
            light = _across(row, lead - edge, edge, slant)
            light.setColorAt(0, QColor(255, 255, 255, 0))
            light.setColorAt(1, QColor(255, 255, 255, SWEEP_EDGE_ALPHA))
            p.setBrush(QBrush(light))
            near = max(start, lead - edge)
            p.drawPath(_part(row, u, between(row, near, lead, slant)))
    p.restore()


def paint_stacked(
    p: QPainter,
    rect: QRectF,
    full: str,
    first_px: float,
    last_px: float,
    floor_px: float = t.MIN_PX,
) -> None:
    """A rider's first name small above the surname large, centered by capitals in ``rect``.

    The surname is what the stands read, so a long one shrinks first, to
    ``floor_px``, and is cut only past that; a first name is cut and
    never shrunk, so it stays one size down the list. Both keep the
    baselines their full sizes give, so a shrunk surname sits on its
    neighbors' line. A one-word name is set alone as a surname.
    """
    first, last = split_name(full)
    ff, lf = t.font(first_px, t.SEMI), t.font(last_px, t.HEAVY)
    fmf, fml = QFontMetricsF(ff), QFontMetricsF(lf)
    if first:
        gap = STACK_GAP * ff.pixelSize()
        block = fmf.capHeight() + gap + fml.capHeight()
        first_base = rect.center().y() - block / 2 + fmf.capHeight()
        last_base = first_base + gap + fml.capHeight()
        ink = QColor(t.TEXT)
        ink.setAlpha(FIRST_NAME_ALPHA)
        line = QRectF(rect.x(), first_base - fmf.ascent(), rect.width(), fmf.height())
        t.text(p, line, t.elide(first, rect.width(), ff), ff, ink, LEFT)
    else:
        last_base = rect.center().y() + fml.capHeight() / 2
    if not last:
        return
    width = fml.horizontalAdvance(last)
    if width > rect.width() > 0:
        least = max(1, round(floor_px))
        lf = t.font(max(least, int(lf.pixelSize() * rect.width() / width)), t.HEAVY)
        fml = QFontMetricsF(lf)
    line = QRectF(rect.x(), last_base - fml.ascent(), rect.width(), fml.height())
    t.text(p, line, t.elide(last, rect.width(), lf), lf, t.TEXT, LEFT)


def paint_start_riders(
    p: QPainter,
    row: QRectF,
    bibs: list[str],
    names: list[str],
    first_px: float,
    last_px: float,
    u: float,
    rider_label: str,
) -> None:
    """A team's two riders side by side on its start list row, one half of the row each.

    Each half holds the rider's plate when the venue's rider label calls
    for one, then the stacked name. The plate's slot stays when a rider
    has no bib yet, so the names keep one column down the list; with
    Bibs Only such a rider is named, never shown an empty plate. The
    halves start clear of the swatch's slanted edge for whatever the
    label may put first in them, so every row on the page keeps one
    column.
    """
    rh = row.height()
    lone_ph = min(rh * BIBS_ONLY_PLATE_SHARE, BIBS_ONLY_PLATE_MOST * u)
    ph = min(rh * PLATE_SHARE, PLATE_MOST * u)
    pw = t.plate_width(ph)
    stacked = clearance(rh, stack_rise(first_px, last_px), u)
    if rider_label == "bibs":
        shift = max(clearance(rh, lone_ph / 2, u), stacked)
    elif rider_label == "names":
        shift = stacked
    else:
        # The stacked name stands a plate's width further right.
        shift = max(clearance(rh, ph / 2, u), stacked - pw - PLATE_GAP * u)
    x0 = row.left() + (SWATCH_W + ROW_PAD) * u + shift
    half = (row.right() - ROW_PAD * u - x0) / 2
    floor = t.MIN_PX * u
    for k, name in enumerate(names[:2]):
        bib = bibs[k] if k < len(bibs) else ""
        x = x0 + k * half
        room = half - RIDER_GAP * u
        if rider_label == "bibs" and bib:
            plate = QRectF(x, row.center().y() - lone_ph / 2, t.plate_width(lone_ph), lone_ph)
            t.plate(p, plate, bib)
            continue
        if rider_label != "names":
            if bib:
                t.plate(p, QRectF(x, row.center().y() - ph / 2, pw, ph), bib)
            x += pw + PLATE_GAP * u
            room -= pw + PLATE_GAP * u
        paint_stacked(p, QRectF(x, row.top(), room, row.height()), name, first_px, last_px, floor)
