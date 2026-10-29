"""Colors, type and drawing primitives shared by the scoreboard layouts.

Every size is a multiple of ``u``, one 1080th of the board's height, so a
layout drawn for a 1080p TV is the same picture on a 4K one. Fonts are set
by pixel size from ``u`` for the same reason: point sizes would scale with
the screen's DPI setting instead of with the space actually available.
"""

from collections.abc import Iterable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

from madtracker.ui.look import available_families

# White and amber on near-black: the highest contrast pair that still
# reads as calm on a big TV, per the stack evaluation's rendering rules.
BG = QColor("#0b0d11")
BAR = QColor("#12151b")
ROW = QColor("#151920")
CARD = QColor("#181c24")
RULE = QColor("#262c36")
TEXT = QColor("#f4f6f9")
MUTED = QColor("#8f9aab")
# A zero in a sprint column: quieter than a score, but 3:1 on the rows
# (WCAG's floor for large type), so a far seat still sees it was scored.
DIM = QColor("#646d7e")
PLATE = QColor("#f7f7f2")
PLATE_TEXT = QColor("#0b0d11")
# A team's total sits on a plate edged in the gray a Black block's ring
# shows (TEAM_RING over Black), one edge for every outline on the board.
FIGURE_PLATE_EDGE = QColor("#686a6c")
# A plate for a rider already out: present but plainly not in the race,
# its digits still 6:1 against the plate.
PLATE_OUT = QColor("#262c36")
PLATE_OUT_TEXT = QColor("#b4bdcb")
# The venue's accent (design section 11): the one color for emphasis.
DEFAULT_ACCENT = "#ffc83d"
ACCENT = QColor(DEFAULT_ACCENT)
# The ink on a chip filled with the accent.
ACCENT_INK = QColor(PLATE_TEXT)
# A near-white accent would fill a chip the color of a bib plate, so "Group B"
# would read as a bib; such an accent draws its chips hollow.
ACCENT_HOLLOW = False

# What happened, in colors of their own; set_accent keeps them apart from
# an accent of the same hue.
_OUT, _GAIN, _LOSS = "#ff5a5f", "#6fd590", "#ff7f7f"
OUT = QColor(_OUT)
OUT_SOFT = QColor(255, 90, 95, 40)
GAIN = QColor(_GAIN)
LOSS = QColor(_LOSS)

# WCAG's ratio for text: an accent darker than this against the board's
# background is lightened until it reads, keeping its hue.
ACCENT_CONTRAST = 4.5


def luminance(c: QColor) -> float:
    """Relative luminance (WCAG 2), 0 for black to 1 for white."""

    def lin(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c.redF()) + 0.7152 * lin(c.greenF()) + 0.0722 * lin(c.blueF())


def contrast(a: QColor, b: QColor) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable(c: QColor, on: QColor) -> QColor:
    """``c`` lightened in steps until its contrast with ``on`` is ACCENT_CONTRAST."""
    out = QColor(c)
    h, sat, light, _a = out.getHslF()
    while contrast(out, on) < ACCENT_CONTRAST and light < 1.0:
        light = min(1.0, light + 0.03)
        out = QColor.fromHslF(max(h, 0.0), sat, light)
    return out


def _near(a: QColor, b: QColor, degrees: float = 25) -> bool:
    """Whether two saturated colors share a hue closely enough to be confused."""
    if a.hslSaturationF() < 0.35 or a.hslHueF() < 0:
        return False
    d = abs(a.hslHueF() - b.hslHueF()) * 360
    return min(d, 360 - d) <= degrees


def set_accent(hex_color: str | None) -> None:
    """Take the venue's accent; an unreadable value keeps the default.

    A dark accent (navy, maroon, forest green) is lightened until it reads
    on the board's near-black, or every emphasis on it would vanish. The out,
    gain and loss colors give way to white when the accent shares their
    hue, so the accent's "1st" is never mistaken for a FINAL stamp or the
    eliminated rider's red.
    """
    global ACCENT, ACCENT_INK, ACCENT_HOLLOW, OUT, GAIN, LOSS
    color = QColor(hex_color) if hex_color else QColor(DEFAULT_ACCENT)
    if not color.isValid():
        color = QColor(DEFAULT_ACCENT)
    ACCENT = readable(color, BG)
    ACCENT_INK = QColor(PLATE_TEXT) if luminance(ACCENT) > 0.3 else QColor(TEXT)
    ACCENT_HOLLOW = ACCENT.hslSaturationF() < 0.25 and ACCENT.lightnessF() > 0.75
    OUT = QColor(TEXT) if _near(ACCENT, QColor(_OUT)) else QColor(_OUT)
    LOSS = QColor(TEXT) if _near(ACCENT, QColor(_LOSS)) else QColor(_LOSS)
    GAIN = QColor(TEXT) if _near(ACCENT, QColor(_GAIN)) else QColor(_GAIN)


# Families come from madtracker.ui.look, resolved against the fonts this
# machine has, so no window ever asks Qt for an absent family.


def font(
    px: float,
    weight: QFont.Weight = QFont.Weight.Normal,
    spacing: float = 0.0,
    tabular: bool = False,
) -> QFont:
    """The board's face at ``px`` pixels.

    ``tabular`` is for figures that stand in a column (totals, sprint
    points, laps, places, bib plates): each digit the same width, so a
    total changing from 19 to 21 does not make the column shimmer. Names,
    titles, labels and chips keep proportional figures, because Inter's
    tabular set also widens the hyphen to a digit's width and
    "Vanderbilt-Rochester" would draw as "Vanderbilt - Rochester".
    """
    f = QFont()
    f.setFamilies(available_families())
    f.setPixelSize(max(1, round(px)))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    if tabular:
        try:
            f.setFeature(QFont.Tag("tnum"), 1)
        except AttributeError:
            pass
    return f


BOLD = QFont.Weight.Bold
HEAVY = QFont.Weight.Black
SEMI = QFont.Weight.DemiBold


# The smallest a list of names may be set, as a fraction of its design
# size. Below this a name reads worse than an initial would, so the list
# stops shrinking and the long names give up their first name instead.
NAME_FLOOR = 0.72


def text(
    p: QPainter,
    rect: QRectF,
    s: str,
    f: QFont,
    color: QColor,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    shrink: bool = False,
) -> float:
    """Draw one line and return the width it used.

    ``shrink`` lets a lone line, such as a race title, give up a little
    size before it is elided. Lists never use it: a row shrunk on its own
    would sit beside rows at another size, so a list picks one size for
    every row with ``fit_scale`` and passes in strings that already fit.
    """
    fm = QFontMetricsF(f)
    width = fm.horizontalAdvance(s)
    if shrink and width > rect.width() > 0:
        f = scaled(f, max(NAME_FLOOR, rect.width() / width))
        fm = QFontMetricsF(f)
    p.setFont(f)
    p.setPen(color)
    shown = fm.elidedText(s, Qt.TextElideMode.ElideRight, rect.width())
    p.drawText(rect, int(align), shown)
    return fm.horizontalAdvance(shown)


# Baseline to baseline for the lines of one stacked name, in ems. The line
# box (1.21 em in Inter) would set the two lines of one name as far apart as
# two different names. In Inter Bold and Black an acute, grave, circumflex,
# diaeresis or caron on a capital rises to 0.95 em and a descender drops to
# 0.22 em, so 1.18 em is the tightest leading that keeps the two apart. Only
# the ring on Å (1.00 em) can touch a descender above it.
STACK_LEADING = 1.18


def stacked_lines(rect: QRectF, f: QFont, n: int) -> list[QRectF]:
    """Line rects for ``n`` lines set as one block, the block's capitals centered on ``rect``.

    Centering is by the capitals, not the line boxes: a line box carries
    the font's accent room above and its descender room below, so
    centering boxes leaves the visible letters off center. Each rect is
    exactly one line box tall, so ``text`` with a vertically centered
    alignment puts the baseline where the block wants it.
    """
    fm = QFontMetricsF(f)
    cap = fm.capHeight()
    gap = STACK_LEADING * f.pixelSize()
    first = rect.center().y() - (cap + (n - 1) * gap) / 2 + cap
    return [
        QRectF(rect.x(), first + i * gap - fm.ascent(), rect.width(), fm.height()) for i in range(n)
    ]


def text_width(s: str, f: QFont) -> float:
    return QFontMetricsF(f).horizontalAdvance(s)


def scaled(f: QFont, scale: float) -> QFont:
    """``f`` at ``scale`` times its pixel size, rounded down so it never overshoots."""
    out = QFont(f)
    out.setPixelSize(max(1, int(f.pixelSize() * scale)))
    return out


def fit_scale(needs: Iterable[tuple[str, float, QFont]], floor: float = NAME_FLOOR) -> float:
    """The one scale at which every ``(string, width, font)`` fits, but not below ``floor``."""
    scale = 1.0
    for s, width, f in needs:
        w = text_width(s, f)
        if w > width > 0:
            scale = min(scale, width / w)
    return max(floor, scale)


def initialed(first_last: str) -> str | None:
    """Shorten "Maximiliana Vanderbilt-Rochester" to "M. Vanderbilt-Rochester".

    The first word is taken as the first name, so a multi-word last name
    ("van der Berg") survives whole. None for a one-word name.
    """
    first, sep, rest = first_last.strip().partition(" ")
    if not sep or not first or not rest.strip():
        return None
    return f"{first[0]}. {rest.strip()}"


def fit_name(first_last: str, width: float, f: QFont) -> str:
    """The longest form of a name that fits ``width``: whole, initial and last, then elided.

    The first name goes before the last because the last name is what the
    announcer says and what the stands match against the program.
    """
    fm = QFontMetricsF(f)
    if fm.horizontalAdvance(first_last) <= width:
        return first_last
    short = initialed(first_last) or first_last
    if fm.horizontalAdvance(short) <= width:
        return short
    return fm.elidedText(short, Qt.TextElideMode.ElideRight, width)


def elide(s: str, width: float, f: QFont) -> str:
    """``s`` cut with an ellipsis to fit ``width`` at ``f``, never shrunk."""
    return QFontMetricsF(f).elidedText(s, Qt.TextElideMode.ElideRight, width)


def plate(p: QPainter, rect: QRectF, bib: str, out: bool = False) -> None:
    """A bib as a white number plate, the shape riders and fans already know.

    ``out`` is a rider no longer racing: a dark plate with light digits.
    A white plate at half opacity would put gray digits on gray, which
    read from nowhere in the stands.
    """
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(PLATE_OUT if out else PLATE)
    r = rect.height() * 0.16
    p.drawRoundedRect(rect, r, r)
    # A margin inside the plate, so a three-digit bib gives way a little
    # rather than running into the plate's edges.
    pad = rect.height() * 0.08
    text(
        p,
        rect.adjusted(pad, 0, -pad, 0),
        bib,
        font(rect.height() * 0.68, HEAVY, tabular=True),
        PLATE_OUT_TEXT if out else PLATE_TEXT,
        Qt.AlignmentFlag.AlignCenter,
        shrink=True,
    )


def plate_width(height: float) -> float:
    # Wide enough for a three-digit bib at the plate's own type size.
    return height * 1.45


# WCAG's ratio for large type (bold at 14 pt and up): every team name is.
LARGE_CONTRAST = 3.0


def team_ink(color: QColor) -> QColor:
    """The ink a team's name needs on its own color: near-black or white.

    The ink that reaches WCAG's 4.5:1 wins (no color allows both), so
    White, Yellow, Orange and Green get dark ink and Black, Purple and
    Brown white. A mid-tone such as Blue or Red reaches only 4 to 4.5:1
    with either; it gets white, which passes WCAG's 3:1 for type this
    large and is how a jersey's lettering usually reads.
    """
    dark, light = QColor(PLATE_TEXT), QColor(TEXT)
    if contrast(color, light) >= ACCENT_CONTRAST:
        return light
    if contrast(color, dark) >= ACCENT_CONTRAST:
        return dark
    return light if contrast(color, light) >= LARGE_CONTRAST else dark


# Under this contrast with the board's background a team block gets a
# light ring, or Black (and navy, maroon) would vanish into the board.
TEAM_RING_CONTRAST = 2.0
TEAM_RING = QColor(255, 255, 255, 90)
# The air either side of a team name in its block, in ems of its type.
TEAM_PAD = 0.5


def team_block(
    p: QPainter, rect: QRectF, color: str, name: str, f: QFont, floor_px: float = 0.0
) -> None:
    """A team as one block: its color filled, its name set on it in the ink the color needs.

    The color is what a rider at speed sees first, and the name on it is
    the color's own label for a rider who cannot tell red from green.
    A long name shrinks inside its block, never
    under ``floor_px``, and is cut only past that.
    """
    fill = QColor(color)
    h = rect.height()
    if contrast(fill, BG) < TEAM_RING_CONTRAST:
        p.setPen(QPen(TEAM_RING, max(1.0, h * 0.03)))
    else:
        p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fill)
    r = h * 0.12
    p.drawRoundedRect(rect, r, r)
    if not name:
        return
    pad = f.pixelSize() * TEAM_PAD
    room = rect.width() - 2 * pad
    w = text_width(name, f)
    if w > room > 0:
        least = floor_px / f.pixelSize() if floor_px else NAME_FLOOR
        f = scaled(f, min(1.0, max(least, room / w)))
    # Centered by its capitals, as a stacked name is: centering the line
    # box would set the name low on its block.
    [line] = stacked_lines(rect, f, 1)
    text(
        p,
        QRectF(rect.x() + pad, line.y(), room, line.height()),
        name,
        f,
        team_ink(fill),
        Qt.AlignmentFlag.AlignCenter,
    )


def figure_plate(p: QPainter, rect: QRectF, block_h: float) -> None:
    """The plate a team's total sits on inside its block.

    A mid-tone block such as Blue or Red gives its own ink only 4 to
    4.5:1, so the total, the figure the riders race on, is set dark on a
    plate that reads the same on every color. The edge is the width of a
    Black block's ring, so a plate on White or Yellow still has an edge.
    """
    p.setPen(QPen(FIGURE_PLATE_EDGE, max(1.0, block_h * 0.03)))
    p.setBrush(QColor(PLATE))
    r = rect.height() * 0.14
    p.drawRoundedRect(rect, r, r)


CHIP_TYPE = 0.56


def _chip_font(h: float) -> QFont:
    return font(h * CHIP_TYPE, BOLD, spacing=h * 0.02)


def accent_chip(p: QPainter, x: float, y: float, h: float, s: str) -> float:
    """A chip in the venue's accent: filled, or hollow for a near-white accent."""
    if ACCENT_HOLLOW:
        return chip(p, x, y, h, s, BAR, ACCENT, ACCENT)
    return chip(p, x, y, h, s, ACCENT, ACCENT_INK)


def chip_width(h: float, s: str) -> float:
    return text_width(s, _chip_font(h)) + h * 0.8


def chip(
    p: QPainter,
    x: float,
    y: float,
    h: float,
    s: str,
    fill: QColor,
    ink: QColor,
    outline: QColor | None = None,
) -> float:
    """A filled label (the race group, a rider's laps) and return its width.

    With ``outline`` the chip is drawn hollow, a ring in that color
    around the fill: a stamp that is not yet settled.
    """
    f = _chip_font(h)
    w = chip_width(h, s)
    rect = QRectF(x, y, w, h)
    if outline is None:
        p.setPen(Qt.PenStyle.NoPen)
    else:
        pen_w = max(2.0, h * 0.07)
        p.setPen(QPen(outline, pen_w))
        rect = rect.adjusted(pen_w / 2, pen_w / 2, -pen_w / 2, -pen_w / 2)
    p.setBrush(fill)
    p.drawRoundedRect(rect, h * 0.2, h * 0.2)
    text(p, rect, s, f, ink, Qt.AlignmentFlag.AlignCenter, shrink=True)
    return w


# A thirtieth of the design height: the smallest type the stands can read.
MIN_PX = 36

# The board's outer margin, the same at the sides of the top bar and of
# every page. The TVs are LCD panels that show every pixel (no overscan),
# so this is a margin for the eye, not a safe area: wide enough that a row
# band does not run into the bezel, no wider.
EDGE = 40
# Between the top bar and a page's first line, and under its last.
PAGE_TOP = 24
PAGE_BOTTOM = 24


def label(u: float) -> QFont:
    """Uppercase section label type, at the board's minimum size."""
    return font(MIN_PX * u, BOLD, spacing=2.4 * u)
