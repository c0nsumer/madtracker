"""A Madison team's row: its color as a swatch and a fade, its riders named side by side.

The riders' names lead and the team's color only identifies (design
section 10): a solid swatch at the row's left edge says which jerseys,
and the fade carries the color under the first rider without putting
type on a colored ground. On the standings table the row's left end,
the swatch, and the color's edges lean at the board's slant
(``theme.SLANT``), the score chip's angle. Every size is in design units,
multiplied by the page's ``u``.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPolygonF,
)

from madtracker.board import theme as t

LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

# The solid swatch of the team color at the row's left edge.
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


def band_shape(row: QRectF, u: float, slant: float = 0.0) -> QPainterPath:
    """A team row's outline: its left end cut at ``slant``, its right end rounded.

    The cut's foot is at the row's left edge, so the row never leans
    left over the place beside it. With no slant both ends are rounded.
    """
    r = ROW_RADIUS * u
    shape = QPainterPath()
    if not slant:
        shape.addRoundedRect(row, r, r)
        return shape
    # The rounded corners on the left fall outside the cut, so only the
    # right end keeps them.
    shape.addRoundedRect(row.adjusted(-r, 0, 0, 0), r, r)
    cut = QPainterPath()
    left = row.left() + run(row, slant) / 2
    cut.addPolygon(between(row, left, row.right() + r + run(row, slant), slant))
    cut.closeSubpath()
    return shape.intersected(cut)


def slant_shift(rh: float, surname_px: float, u: float) -> float:
    """How far right of the square swatch's layout the surnames stand beside a slanted one.

    A tall row's swatch leans far enough right at the top of the
    surnames' capitals to crowd them; the surnames move only as far as
    keeps SLANT_AIR there, so a short row's names stay where they are.
    Measured at ``surname_px``, the largest the surnames may be set.
    """
    fm = QFontMetricsF(t.font(surname_px, t.HEAVY))
    # A line set centered on the row puts its capitals' top this far above the middle.
    caps = fm.capHeight() - (fm.ascent() - fm.descent()) / 2
    lean = t.SLANT * (rh / 2 + caps)
    return max(0.0, lean - (ROW_PAD - SLANT_AIR) * u)


def swatch_shape(row: QRectF, u: float, slant: float = 0.0) -> QPainterPath:
    """The swatch: SWATCH_W wide along the row's left end, leaning with it."""
    return fill_shape(row, u, slant=slant)


def _lead(row: QRectF, u: float, sweep: float, zone_right: float | None, slant: float) -> float:
    """Where the solid color ends across the row's middle: past the swatch by ``sweep``.

    At a full sweep the end's top corner is at ``zone_right``, so the
    color leans no further right than the zone.
    """
    half = run(row, slant) / 2
    swatch_right = row.left() + half + SWATCH_W * u
    sweep = min(1.0, max(0.0, sweep))
    end = (row.right() if zone_right is None else zone_right) - half
    return swatch_right + (end - swatch_right) * sweep


def fill_shape(
    row: QRectF,
    u: float,
    sweep: float = 0.0,
    zone_right: float | None = None,
    slant: float = 0.0,
) -> QPainterPath:
    """The solid color: the swatch, swept ``sweep`` of the way to ``zone_right``.

    Both its ends lean at ``slant``, so the color opens and closes along
    the row's cut.
    """
    left = row.left() + run(row, slant) / 2
    lead = _lead(row, u, sweep, zone_right, slant)
    return _part(band_shape(row, u, slant), row, left, lead, slant)


def _part(
    shape: QPainterPath, row: QRectF, left: float, right: float, slant: float
) -> QPainterPath:
    # The row's own outline cut between two slanted edges, so the swatch
    # and the sweep keep the row's ends, antialiased.
    box = QPainterPath()
    box.addPolygon(between(row, left, right, slant))
    box.closeSubpath()
    return shape.intersected(box)


def _across(row: QRectF, x: float, length: float, slant: float) -> QLinearGradient:
    """A gradient ``length`` long along the row from ``x`` at its middle, its lines at ``slant``.

    The gradient runs square to the slanted edges, so each of its colors
    lies along a line parallel to them, and ``length`` is measured along
    the row.
    """
    y = row.center().y()
    k = length / (1 + slant * slant)
    return QLinearGradient(x, y, x + k, y + k * slant)


def paint_band(
    p: QPainter,
    row: QRectF,
    color: str | None,
    u: float,
    sweep: float = 0.0,
    zone_right: float | None = None,
    slant: float = 0.0,
) -> None:
    """A team's row: the band, the solid swatch, and the fade under the first rider.

    ``sweep`` fills the color solid from the swatch toward ``zone_right``
    (the row's right end when None), 0 none and 1 all of it; while it is
    partway the fill leads with a soft light edge. ``slant`` cuts the
    row's left end, the swatch, the fade's start, the fill's end, and its
    light edge at one angle, and the fill's end leans no further right
    than ``zone_right``. A dark color has no ring; the riders' names carry
    a dark team (design section 10).
    """
    shape = band_shape(row, u, slant)
    sweep = min(1.0, max(0.0, sweep))
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(t.ROW)
    p.drawPath(shape)
    if color:
        c = QColor(color)
        left = row.left() + run(row, slant) / 2
        fade = _across(row, left, row.width() * FADE_END_AT, slant)
        fade.setColorAt(0, _tinted(c, FADE_EDGE))
        fade.setColorAt(FADE_MID_AT / FADE_END_AT, _tinted(c, FADE_MID))
        fade.setColorAt(1, _tinted(c, 0.0))
        p.setBrush(QBrush(fade))
        p.drawPath(shape)

        # As ``fill_shape`` draws it, from the outline already made.
        lead = _lead(row, u, sweep, zone_right, slant)
        p.setBrush(c)
        p.drawPath(_part(shape, row, left, lead, slant))
        if 0 < sweep < 1:
            swatch_right = left + SWATCH_W * u
            edge = SWEEP_EDGE * u
            light = _across(row, lead - edge, edge, slant)
            light.setColorAt(0, QColor(255, 255, 255, 0))
            light.setColorAt(1, QColor(255, 255, 255, SWEEP_EDGE_ALPHA))
            p.setBrush(QBrush(light))
            p.drawPath(_part(shape, row, max(swatch_right, lead - edge), lead, slant))
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
    Bibs Only such a rider is named, never shown an empty plate.
    """
    x0 = row.left() + (SWATCH_W + ROW_PAD) * u
    half = (row.right() - ROW_PAD * u - x0) / 2
    floor = t.MIN_PX * u
    for k, name in enumerate(names[:2]):
        bib = bibs[k] if k < len(bibs) else ""
        x = x0 + k * half
        room = half - RIDER_GAP * u
        if rider_label == "bibs" and bib:
            ph = min(row.height() * BIBS_ONLY_PLATE_SHARE, BIBS_ONLY_PLATE_MOST * u)
            plate = QRectF(x, row.center().y() - ph / 2, t.plate_width(ph), ph)
            t.plate(p, plate, bib)
            continue
        if rider_label != "names":
            ph = min(row.height() * PLATE_SHARE, PLATE_MOST * u)
            pw = t.plate_width(ph)
            if bib:
                t.plate(p, QRectF(x, row.center().y() - ph / 2, pw, ph), bib)
            x += pw + PLATE_GAP * u
            room -= pw + PLATE_GAP * u
        paint_stacked(p, QRectF(x, row.top(), room, row.height()), name, first_px, last_px, floor)
