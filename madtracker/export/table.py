"""The table both landscape sheets print: the results sheet's races and the standings' groups.

A row is a place, then a team's swatch and name with its riders beside
or under it, or a rider's bib and name, then the sheet's own figures, with the total
at the right. The first three rows are larger, then the rest of the
ranked rows, then the status rows a little apart in a smaller face. A
table that fits a page is never split; one that does not is split with
its heading and header row repeated, never leaving a page with fewer
than ``MIN_ROWS`` of it. A table may print its rows in more than one
column, down each column and then across, each column under its own
header row.

What the two sheets share lives here, each value once: the tiers, the
gaps between columns, the place, swatch, bib, penalty, and total
columns, a name's lines, the rider lines' leading, the header's face,
and the fit-or-split rule. What only one sheet has (the sprint columns
and race heading; the race columns, dates, and bands) stays with that
sheet, and so does the header row's height, since the standings' header
carries each race's date and name.

``export.pdf`` imports this module and this module imports it, so neither
reads the other's names while it is being imported, only when called.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

from madtracker.export import pdf as P

Col = tuple[float, float]


@dataclass(frozen=True)
class Tier:
    """One row size: the point size, the height of one text line, and padding."""

    size: float
    line: float
    pad: float
    place_style: str
    name_style: str
    # The riders under a team's name, in a smaller face so the team reads
    # first: the team is the row and its riders are the detail, as on the
    # board's team block.
    rider_pt: float

    def height(self, lines: int) -> float:
        return lines * self.line + self.pad


# A row's line is LEADING mm per point of its size, 1.13 em: a little
# under Inter's own line box (1.21 em), so a page holds more rows, and
# still clear between the two lines of a wrapped name.
LEADING = 0.40

# The first three, the rest of the ranked rows, then the status rows.
TOP = Tier(22, 22 * LEADING, 2.2, "K", "B", 11)
REST = Tier(16, 16 * LEADING, 1.6, "B", "", 9)
STATUS = Tier(11, 11 * LEADING, 1.2, "B", "", 8)

# The air between two columns.
GAP = 3.0
# The place column holds "DNF" at the podium size.
PLACE_W = 17.0
# A rider's bib is a little more than a column gap from the name, so the
# two read as two fields.
BIB_GAP = 4.0
# The penalty column holds "−40" under its header.
PENALTY_W = 16.0
# The air a figure has beside its column's edge.
FIGURE_AIR = 1.0
# A name wraps rather than being cut, up to this many lines: cut, "Green
# Machine" reads "Green…", and two long names print the same. Only a
# name still too long on its last line is cut.
NAME_LINES = 3
# A team's color: a bar SWATCH_BAR wide in a column SWATCH_W wide, inset
# SWATCH_INSET from the top and foot of the row's text.
SWATCH_W = 7.0
SWATCH_BAR = 5.0
SWATCH_INSET = 1.2
# The Bib column's width when every bib fits it: three digits on a
# podium row, shrunk as ``_fit`` shrinks them.
BIB_W = 14.0
# The widest figure a column must hold when the table has none wider:
# two digits. A column is sized to the table's own widest figure, so a
# table of small figures keeps its name column.
WIDEST = "00"
# A rider's line under a team's name: the rider face's line, opened up a
# little so two riders read as two lines.
RIDER_LEADING = 1.15
# The least a name shrinks to, as a share of its size, before it wraps
# or is cut: much smaller reads as a different kind of row.
NAME_SHRINK = 0.85
# A team's riders stand beside its name, one per line, one GAP after the
# table's widest team name, as the board's sprint card sets them: the
# block is as tall as the taller of the two, not the name's line plus
# a line per rider. A table where any rider's name would wrap there
# puts every team's riders under its name instead, since a wrapped rider
# beside a name reads as a third rider.
HEADER_PT = 8.0
# The air between a heading and its header row, and under the header's rule.
HEAD_TO_TABLE = 1.0
HEADER_TO_ROWS = 0.5
# The first status row sits this far apart from the ranked rows, unless
# it starts a column, where the gap would only misalign it.
STATUS_GAP = 1.5
# A table starts on a new page rather than leave fewer rows than this
# under its heading at the foot of a page.
MIN_ROWS = 4


@dataclass(frozen=True)
class Lines:
    """A cell's text as wrapped lines, and the size they print at."""

    lines: tuple[str, ...]
    size: float


def quiet_wrap(
    pdf: P._Doc, text: str, width: float, style: str, size: float, min_size: float, max_lines: int
) -> Lines:
    """``_wrap_lines`` with nothing reported; the caller reports the whole text."""
    kept = len(pdf.unprintable)
    lines, pt = P._wrap_lines(pdf, text, width, style, size, min_size, max_lines)
    del pdf.unprintable[kept:]
    return Lines(tuple(lines), pt)


def wrapped(
    pdf: P._Doc, text: str, width: float, style: str, size: float, min_size: float, max_lines: int
) -> Lines:
    """``text`` wrapped to ``width``, reported whole when the font lacks a letter of it."""
    out = quiet_wrap(pdf, text, width, style, size, min_size, max_lines)
    pdf.txt(text)
    return out


def put_lines(
    pdf: P._Doc, x: float, y: float, w: float, line_h: float, cell: Lines, align: str, style: str
) -> None:
    for k, line in enumerate(cell.lines):
        # A word too long for a line on its own is cut on its line, so it
        # never runs into the next column.
        fitted = pdf.quiet_fit(line, w, style, cell.size)
        pdf.set_xy(x, y + k * line_h)
        pdf.cell(w, line_h, fitted, align=align)


def figure_w(pdf: P._Doc, text: str, size: float, style: str = "") -> float:
    """The width of a cell that holds ``text`` at ``size``."""
    pdf.use(style, size)
    return pdf.get_string_width(pdf.txt(text)) + 2 * pdf.c_margin


def widest(figures: Iterable[str]) -> str:
    """The widest of ``figures`` by characters; at least WIDEST."""
    return max([WIDEST, *figures], key=len)


def total_width(pdf: P._Doc, totals: Iterable[str]) -> float:
    """The Total column's width: the table's widest total, bold at the podium size, and
    never narrower than its header, so a table of small totals keeps its name column."""
    return max(
        figure_w(pdf, widest(totals), TOP.size, "B") + FIGURE_AIR,
        figure_w(pdf, "Total", HEADER_PT, "B"),
    )


def bib_width(pdf: P._Doc, bibs: Iterable[str], size: float) -> float:
    """The Bib column's width: BIB_W, or wider when a bib printed at ``size`` would be cut.

    A bib prints at its row's size and shrinks to fit, down to 70%; a
    bib still too wide there (the roster takes four digits) widens the
    column for its table rather than print cut, as a figure column is
    sized to its table's own widest figure.
    """
    least = size - 0.5 * int((size - size * 0.7) / 0.5)
    return max([BIB_W, *(figure_w(pdf, bib, least) for bib in set(bibs))])


def rider_line(size: float) -> float:
    """The height of a rider's line under a team's name, at ``size`` points."""
    return P._line_h(size) * RIDER_LEADING


@dataclass(frozen=True)
class Lead:
    """The columns a row starts with, before the sheet's figures.

    ``team`` is the team's name line, None on a table of riders; ``bib``
    is None on a table that prints no bibs; ``name`` holds the riders'
    names, under the team's name or as the row's own. ``span`` is the
    table column the row's rule runs across, None for the page's width.
    ``beside`` puts a team's riders right of its name, both centered on
    the block, rather than under it.
    """

    place: Col
    swatch: float | None
    team: Col | None
    bib: Col | None
    name: Col
    span: Col | None = None
    beside: bool = False


def lead_columns(
    pdf: P._Doc,
    place_w: float,
    *,
    swatch: bool,
    bibs: Sequence[str] | None,
    bib_pt: float,
    bib_gap: float,
    left: float | None = None,
) -> tuple[Col, float | None, Col | None, float]:
    """The place column, the swatch's x, the bib column, and where the name starts.

    ``left`` is the table column's left edge, the page margin by default.
    """
    x = P.MARGIN if left is None else left
    place = (x, place_w)
    x += place_w + GAP
    swatch_x = None
    if swatch:
        swatch_x = x
        x += SWATCH_W
    bib = None
    if bibs is not None:
        bib = (x, bib_width(pdf, bibs, bib_pt))
        x += bib[1] + bib_gap
    return place, swatch_x, bib, x


def text_w(pdf: P._Doc, text: str, size: float, style: str) -> float:
    """The width of a cell that holds ``text`` on one line, nothing reported."""
    pdf.use(style, size)
    return pdf.get_string_width(pdf.quiet(text)) + 2 * pdf.c_margin


def team_name_width(
    pdf: P._Doc, room: float, names: Iterable[tuple[str, float]], riders_want: float
) -> float:
    """The team name's column in a block ``room`` wide, its riders beside it.

    ``names`` is each team's name with the size its row prints it at, and
    ``riders_want`` what the widest rider line needs. The name column is
    the table's widest name, so the riders line up one GAP after it; when
    the two do not fit side by side, the riders keep their width and the
    name wraps, down to half the block, and past that both wrap.
    """
    want = max((text_w(pdf, text, size, "B") for text, size in names), default=0.0)
    if want + GAP + riders_want <= room:
        return want
    return min(want, max(room / 2, room - GAP - riders_want))


def riders_fit(pdf: P._Doc, width: float, riders: Iterable[tuple[str, float]]) -> bool:
    """Whether every (name, size) fits one line of ``width``, shrunk no further than NAME_SHRINK."""
    return all(text_w(pdf, text, size * NAME_SHRINK, "") <= width + 1e-6 for text, size in riders)


@dataclass(frozen=True)
class RowText:
    """One row's wrapped team and rider names, and the height of the text block.

    Each rider is a bib (blank when the sheet prints none) and the name's
    lines; ``rider_line`` is one rider line's height and ``bib_pt`` the
    bib's size.
    """

    team: Lines
    riders: tuple[tuple[str, Lines], ...]
    rider_line: float
    rider_style: str
    bib_pt: float
    height: float
    # The row tier's line, which the team's name prints on, and whether
    # the riders stand beside the name.
    tier_line: float = 0.0
    beside: bool = False

    @property
    def team_h(self) -> float:
        return len(self.team.lines) * self.tier_line

    @property
    def riders_h(self) -> float:
        return sum(max(1, len(n.lines)) for _, n in self.riders) * self.rider_line


def row_text(
    tier: Tier,
    team: Lines,
    riders: tuple[tuple[str, Lines], ...],
    rider_line: float,
    rider_style: str,
    bib_pt: float,
    *,
    beside: bool = False,
) -> RowText:
    """The row's text and its height: the team's lines, then a line or more per rider;
    ``beside``, the taller of the team's lines and its riders' lines."""
    text = RowText(team, riders, rider_line, rider_style, bib_pt, 0.0, tier.line, beside)
    if beside and team.lines:
        height = max(text.team_h, text.riders_h)
    else:
        height = text.team_h + text.riders_h
    return replace(text, height=max(tier.line, height))


def ordered[Row](rows: Iterable[Row], placed: Callable[[Row], bool]) -> list[tuple[Row, Tier]]:
    """Ranked rows in order, the first three larger, then the status rows in the order given."""
    rows = list(rows)
    ranked = [r for r in rows if placed(r)]
    others = [r for r in rows if not placed(r)]
    out = [(r, TOP if i < 3 else REST) for i, r in enumerate(ranked)]
    return out + [(r, STATUS) for r in others]


def table_head(heading_h: float, header_h: float) -> float:
    """What a page must hold above the rows: the heading, the header row, and the air between."""
    return heading_h + HEAD_TO_TABLE + header_h + HEADER_TO_ROWS


def _note_after_name(
    pdf: P._Doc, note: str, name: str, col: Col, y: float, tier: Tier, style: str
) -> None:
    """A placed rider's status, muted, after the name: "3  Avery Quinn  Did not finish".

    The number is the fact the sheet exists for, so the note gives way
    to it: it takes what the name leaves and is left off a line with no
    room (the data file's log still has it).
    """
    fitted = pdf.quiet_fit(name, col[1], style, tier.size)
    used = pdf.get_string_width(fitted) + 2 * pdf.c_margin + 2.0
    room = col[1] - used
    if room < 18:
        return
    pdf.set_text_color(*P.MUTED)
    P._text(pdf, col[0] + used, y, room, tier.line, note, "L", "", tier.size * 0.72, 6)
    pdf.set_text_color(*P.INK)


def draw_row(
    pdf: P._Doc,
    lead: Lead,
    tier: Tier,
    y: float,
    text: RowText,
    *,
    place: str,
    color_hex: str | None = None,
    note: str = "",
    figures: Callable[[float], None] | None = None,
) -> float:
    """Draw one row at ``y`` and return its height.

    ``figures`` draws the sheet's own columns on the row's first line,
    given its top; a status row has none.
    """
    height = text.height + tier.pad
    top = y + tier.pad / 2
    status = tier is STATUS
    beside = text.beside and lead.team is not None and bool(text.team.lines)
    # Beside its riders, the team's name is centered on the block, and the
    # place and the figures keep to the name's first line.
    first = top + (text.height - text.team_h) / 2 if beside else top
    pdf.set_text_color(*(P.MUTED if status else P.INK))
    P._text(
        pdf, lead.place[0], first, lead.place[1], tier.line, place, "R", tier.place_style, tier.size
    )
    ly = first
    if lead.swatch is not None:
        pdf.set_fill_color(*P._hex_rgb(color_hex))
        pdf.set_draw_color(*P.MUTED)
        pdf.rect(
            lead.swatch,
            top + SWATCH_INSET,
            SWATCH_BAR,
            text.height - 2 * SWATCH_INSET,
            style="DF",
        )
    if lead.team is not None:
        put_lines(pdf, lead.team[0], ly, lead.team[1], tier.line, text.team, "L", "B")
        if note and len(text.team.lines) == 1:
            _note_after_name(pdf, note, text.team.lines[0], lead.team, ly, tier, "B")
        ly += len(text.team.lines) * tier.line
    if beside:
        ly = top + (text.height - text.riders_h) / 2
    for n, (bib, name) in enumerate(text.riders):
        if lead.bib is not None:
            P._text(pdf, lead.bib[0], ly, lead.bib[1], text.rider_line, bib, "R", "", text.bib_pt)
        put_lines(pdf, lead.name[0], ly, lead.name[1], text.rider_line, name, "L", text.rider_style)
        if n == 0 and note and lead.team is None and len(name.lines) == 1:
            _note_after_name(pdf, note, name.lines[0], lead.name, ly, tier, text.rider_style)
        ly += max(1, len(name.lines)) * text.rider_line
    if not status and figures is not None:
        figures(first)
    pdf.set_text_color(*P.INK)
    pdf.set_draw_color(*P.RULE)
    x, w = lead.span or (P.MARGIN, pdf.usable)
    pdf.line(x, y + height, x + w, y + height)
    return height


def draw_header_row(
    pdf: P._Doc,
    y: float,
    h: float,
    labels: Iterable[tuple[Col, str, str]],
    *,
    label_y: float,
    label_h: float,
    more: Callable[[], None] | None = None,
    span: Col | None = None,
) -> float:
    """The header row: each (column, label, align) in the header face, ``more`` for the
    sheet's own, then the rule under it across ``span`` (the page's width when None);
    returns its height ``h``."""
    pdf.set_text_color(*P.MUTED)
    for (x, w), label, align in labels:
        P._text(pdf, x, label_y, w, label_h, label, align, "B", HEADER_PT)
    if more is not None:
        more()
    pdf.set_text_color(*P.INK)
    pdf.set_draw_color(*P.MUTED)
    x, w = span or (P.MARGIN, pdf.usable)
    pdf.line(x, y + h, x + w, y + h)
    return h


def _run(heights: Sequence[float], gaps: Sequence[float], a: int, b: int) -> float:
    """The height of rows ``a`` to ``b`` as one column: the first row's gap is not drawn."""
    return sum(heights[a:b]) - (gaps[a] if b > a else 0.0)


def _fill(heights: Sequence[float], gaps: Sequence[float], start: int, room: float) -> int:
    """How many rows from ``start`` fit one column of ``room``."""
    k = 0
    while start + k < len(heights) and _run(heights, gaps, start, start + k + 1) <= room:
        k += 1
    return k


def _take(
    heights: Sequence[float], gaps: Sequence[float], start: int, room: float, columns: int
) -> int:
    """How many rows from ``start`` fit ``columns`` columns of ``room``, filled in turn."""
    k = 0
    for _ in range(columns):
        k += _fill(heights, gaps, start + k, room)
    return k


def pages(
    first: float,
    fresh: float,
    heights: Sequence[float],
    gaps: Sequence[float] | None = None,
    columns: int = 1,
) -> list[int]:
    """How many rows go on each page of a table that must be split.

    Each page takes what fits, then gives rows back so the next page
    starts with at least ``MIN_ROWS``; a page never ends a table on fewer.
    When too few rows remain for both pages to hold ``MIN_ROWS``, they
    split as evenly as they can: one row alone under a heading, with the
    rest overleaf, reads as a mistake. ``gaps`` is the air above each row
    within ``heights``, left out where a row starts a column.
    """
    gaps = gaps if gaps is not None else [0.0] * len(heights)
    counts: list[int] = []
    i, room = 0, first
    n = len(heights)
    while i < n:
        k = max(_take(heights, gaps, i, room, columns), 1)
        left = n - i - k
        if 0 < left < MIN_ROWS:
            back = n - i - MIN_ROWS
            k = max(1, min(k, back if back >= MIN_ROWS else -(-(n - i) // 2)))
        counts.append(k)
        i += k
        room = fresh
    return counts


def split(
    heights: Sequence[float],
    gaps: Sequence[float],
    start: int,
    count: int,
    room: float,
    columns: int,
    *,
    balance: bool,
) -> list[int]:
    """How many of ``count`` rows from ``start`` go down each column.

    Unbalanced, each column takes what fits ``room`` and the last takes
    the rest. Balanced, the columns are as even as the rows allow, with
    the left the longest: the least column height that still holds every
    row, filled in turn.
    """
    if balance and columns > 1:
        for h in sorted({_run(heights, gaps, start, start + k) for k in range(1, count + 1)}):
            if h <= room and _take(heights[: start + count], gaps, start, h, columns) == count:
                room = h
                break
    out: list[int] = []
    done = 0
    for c in range(columns):
        k = count - done
        if c < columns - 1:
            k = min(k, _fill(heights, gaps, start + done, room))
        out.append(k)
        done += k
    return out


def draw_table[Row](
    pdf: P._Doc,
    head: float,
    rows: Sequence[tuple[Row, Tier]],
    texts: Sequence[RowText],
    draw_top: Callable[[float, bool], float],
    draw: Callable[[Row, Tier, float, RowText, int], float],
    *,
    first_top: float | None = None,
    columns: int = 1,
) -> float:
    """Draw a table where it fits, splitting it over pages when it must; returns the y under it.

    ``head`` is the height of what ``draw_top(y, more)`` draws above the
    rows (``more`` on a page after the table's first); ``draw`` draws a
    row in a column and returns its height. The rows run down each of
    ``columns`` columns in turn; the last page's columns are balanced. A
    table that fits a page is never split: it moves to a fresh page. One
    too long for any page starts here only if at least MIN_ROWS of it fit
    under its heading. Nothing above it on this page means a fresh page
    would not help; on the first page, a ``y`` no lower than
    ``first_top`` counts as nothing above it too.
    """
    gaps = [
        STATUS_GAP if t is STATUS and i > 0 and rows[i - 1][1] is not STATUS else 0.0
        for i, (_, t) in enumerate(rows)
    ]
    heights = [
        gap + text.height + t.pad for gap, text, (_, t) in zip(gaps, texts, rows, strict=True)
    ]
    n = len(rows)
    fresh = pdf.bottom - pdf.later_top
    y = pdf.get_y()
    at_top = y <= pdf.body_top + 1 or (
        first_top is not None and pdf.page_no() == 1 and y <= first_top + 1
    )
    here = _take(heights, gaps, 0, pdf.bottom - y - head, columns)
    if here < n and not at_top:
        whole = _take(heights, gaps, 0, fresh - head, columns) == n
        if whole or here < min(n, MIN_ROWS):
            pdf.add_page()
            y = pdf.get_y()
    counts = pages(pdf.bottom - y - head, fresh - head, heights, gaps, columns)
    i = 0
    for page, count in enumerate(counts):
        if page:
            pdf.add_page()
            y = pdf.get_y()
        top = draw_top(y, page > 0)
        last = i + count == n
        y = top
        for column, k in enumerate(
            split(heights, gaps, i, count, pdf.bottom - top, columns, balance=last)
        ):
            cy = top
            for j in range(i, i + k):
                row, tier = rows[j]
                if j > i:
                    cy += gaps[j]
                cy += draw(row, tier, cy, texts[j], column)
            y = max(y, cy)
            i += k
    return y
