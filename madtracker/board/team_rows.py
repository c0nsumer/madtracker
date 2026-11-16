"""A Madison team's row: its color as a swatch and a fade, its riders named side by side.

The riders' names lead and the team's color only identifies (design
section 10): a solid swatch at the row's left edge says which jerseys,
and the fade carries the color under the first rider without putting
type on a colored ground. Every size is in design units, multiplied by
the page's ``u``.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetricsF, QLinearGradient, QPainter, QPainterPath

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


def paint_band(
    p: QPainter,
    row: QRectF,
    color: str | None,
    u: float,
    sweep: float = 0.0,
    zone_right: float | None = None,
) -> None:
    """A team's row: the band, the solid swatch, and the fade under the first rider.

    ``sweep`` fills the color solid from the swatch toward ``zone_right``
    (the row's right end when None), 0 none and 1 all of it; while it is
    partway the fill leads with a soft light edge. A dark color has no
    ring; the riders' names carry a dark team (design section 10).
    """
    r = ROW_RADIUS * u
    shape = QPainterPath()
    shape.addRoundedRect(row, r, r)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(t.ROW)
    p.drawPath(shape)
    if color:
        c = QColor(color)
        fade = QLinearGradient(row.left(), 0, row.left() + row.width() * FADE_END_AT, 0)
        fade.setColorAt(0, _tinted(c, FADE_EDGE))
        fade.setColorAt(FADE_MID_AT / FADE_END_AT, _tinted(c, FADE_MID))
        fade.setColorAt(1, _tinted(c, 0.0))
        p.setBrush(QBrush(fade))
        p.drawPath(shape)

        def part(left: float, right: float) -> QPainterPath:
            # The row's own outline cut to [left, right], so the swatch and
            # the sweep keep the row's rounded corners, antialiased.
            box = QPainterPath()
            box.addRect(QRectF(left, row.top(), max(0.0, right - left), row.height()))
            return shape.intersected(box)

        swatch_right = row.left() + SWATCH_W * u
        sweep = min(1.0, max(0.0, sweep))
        lead = swatch_right
        if sweep > 0:
            end = row.right() if zone_right is None else zone_right
            lead = swatch_right + (end - swatch_right) * sweep
        p.setBrush(c)
        p.drawPath(part(row.left(), lead))
        if 0 < sweep < 1:
            edge = SWEEP_EDGE * u
            light = QLinearGradient(lead - edge, 0, lead, 0)
            light.setColorAt(0, QColor(255, 255, 255, 0))
            light.setColorAt(1, QColor(255, 255, 255, SWEEP_EDGE_ALPHA))
            p.setBrush(QBrush(light))
            p.drawPath(part(max(swatch_right, lead - edge), lead))
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
