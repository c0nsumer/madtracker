"""The results PDF: the sheet the announcer reads from at the podium.

docs/design.md section 9: the PDF "lists each race's placings large and in
order, with the points where there are any". So each race is a heading and
a short list of big rows, not a dense table: place, bib and name, plus the
total points and net laps for a points race or madison, and net laps for
a finish-order race where any rider has one. The first three
are larger again, because those are the names read out first and read
from arm's length; riders with a status (DNF, DNS, DQ) follow in a smaller
row with the code. A points race or madison also prints each sprint's
points in a column of its own between the name and Laps, so the total's
working is on the sheet for the officials to check, as it is on the
venue's own sheet and on the scoring screen.

Letter landscape for the results and the standings (the program sheet is
portrait). Places and points are right-aligned, so their last digits
line up. Inter's default figures are proportional, so a narrow 1 would
leave a column's left edge ragged. The
sheet turns on the tabular figures feature (tnum), the same one the
scoreboard asks Qt for. fpdf2 applies OpenType features only through its
HarfBuzz text shaping, so the app ships uharfbuzz. With shaping on,
fpdf2 measures text the same way it draws it, so the fitting below still
sizes each cell to what is printed.

Output is PDF/A-2B, which forbids the PDF core fonts, so TrueType must be
embedded. The font is the bundled Inter (Regular, Bold and Black,
see ``madtracker.assets.fonts``), the same face the window and the
scoreboard use, so the sheet is identical on every machine and its
embedding rights are known. Rider names carry accents (a stroked L, an
umlaut, a cedilla), and the TrueType font renders them.

If the bundled files are missing, which is a packaging bug and not a
machine difference, the PDF is written as plain PDF with core Helvetica
instead of failing, because a results sheet that prints beats none. That
fallback is not PDF/A and Latin-1 only: characters outside Latin-1 print
as "?". ``find_font`` returns None in that case and the tests pin both
paths. Shaping is off there too: the core fonts have no OpenType tables.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from fpdf import FPDF
from fpdf.errors import FPDFException
from PIL import Image

from madtracker import APP_NAME, __version__, applog
from madtracker.assets import fonts
from madtracker.board.payloads import MINUS, lap_text
from madtracker.control import rulesets
from madtracker.control import venue as venue_settings
from madtracker.dates import show_date_time
from madtracker.export import table as T
from madtracker.export.files import write_replacing
from madtracker.export.glyphs import SILENT
from madtracker.export.glyphs import missing as _missing
from madtracker.export.summary import (
    NEUTRAL_HEX,
    RaceSummary,
    ResultRow,
    build_summary,
    format_number,
    state_line,
)
from madtracker.store import Store

BAND = (24, 24, 28)
INK = (20, 20, 20)
MUTED = (105, 105, 112)
RULE = (205, 205, 210)
ALERT = (178, 34, 34)
# Every sheet is the page a printer gives back: nothing is drawn within
# MARGIN of an edge, the band included, since an office printer leaves
# up to 6.35 mm at each edge unprinted, and a band bled to the edge
# would come back with a white border of the printer's own width.
MARGIN = 10.0
BAND_H = 22.0
# The air inside the band, between its edges and the logo and text.
BAND_PAD = 4.0
# The running header on every page after the first: the band's look at
# half its height, so a loose page still says whose results it holds.
RUN_H = 10.0
# The footer's zone above the margin: its line and a little clear air
# over the rule.
FOOTER_H = 10.0
# The air under the band before the first race, and under the running
# header before a later page's body.
BAND_GAP = 4.0
RUN_GAP = 3.0
ELLIPSIS = "…"
FAMILY = "Results"
BLACK_FAMILY = "ResultsBlack"
SECTION_GAP = 6.0
# The most of the header's width a logo takes, so the event's name has room.
LOGO_SHARE = 0.5
# The resolution the logo is embedded at, at most: a laser printer's.
LOGO_DPI = 300


# The figures beside a Total (the sprints, laps, penalty) print at one
# size of their own on every row: they are the total's working, and the
# Total alone is the row's size. A finish-order race's Laps column is the
# ranking fact and keeps the row's size. The sprint columns shrink toward
# SPRINT_MIN_PT while they do not fit beside a name column of NAME_MIN,
# and past that fold to one Sprints column with the sum.
WORKING_PT = 13.0
SPRINT_MIN_PT = 11.0
SPRINT_GAP = 1.0
NAME_MIN = 64.0
# The result table's own widths beside those it shares with the standings
# sheet (``export.table``).
LAPS_W = 16.0
HEADER_ROW_H = 4.5
# A finish-order race (no sprint figures) of at least TWO_COLUMN_MIN
# placed riders prints its rows down the left column and then the right,
# COLUMN_GUTTER apart, as the program lists riders: its few columns
# would leave most of a full-width row empty. A column too narrow for a
# name column of NAME_MIN keeps the race at the page's full width.
TWO_COLUMN_MIN = 8
# The widest gutter that still leaves a column with a Laps column its
# NAME_MIN of name, so a race with a lapped rider keeps two columns.
COLUMN_GUTTER = 7.0


# Tabular figures, so digits line up in the columns (see _Doc._figures).
TNUM = {"tnum": True}


def find_font() -> tuple[str, str, str] | None:
    """(regular, bold, black) bundled TrueType files, or None if any is missing."""
    paths = fonts.font_path(400), fonts.font_path(700), fonts.font_path(900)
    if all(p.is_file() for p in paths):
        return str(paths[0]), str(paths[1]), str(paths[2])
    return None


def _print_logo(logo: Path | bytes) -> Path | bytes | None:
    """The logo at no more than about 300 dpi of the height it prints at.

    A stored logo may be 1200 pixels high (enough for a 4K scoreboard),
    and prints BAND_H less the band's padding high here: embedded whole
    it is most of the file.
    Resampled to what a printer can show, it looks the same on paper. It
    is written as PNG with any alpha, which PDF/A-2 allows as a soft mask;
    a logo already near the print size is left alone, so it is not
    resampled for nothing. Its transparent edges are trimmed, so the
    band's air around it is the artwork's, the same on every side. One
    that Pillow cannot read is passed on as it is, for fpdf2 to report.
    """
    target = round((BAND_H - 2 * BAND_PAD) / 25.4 * LOGO_DPI)
    try:
        with Image.open(BytesIO(logo) if isinstance(logo, bytes) else logo) as im:
            im.load()
            alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
            # Premultiplied alpha, so transparent pixels' hidden color
            # does not bleed into the artwork's edges as it is resampled.
            work = im.convert("RGBa" if alpha else "RGB")
            box = im.convert("RGBA").getchannel("A").getbbox() if alpha else None
    except Image.DecompressionBombError:
        # Pillow refuses it before decoding, and so would fpdf2 inside
        # the page header, past the export's error handling. The sheet
        # prints the venue's name instead, as with no logo.
        return None
    except (OSError, ValueError):
        return logo
    trimmed = box is not None and box != (0, 0, work.width, work.height)
    if trimmed:
        work = work.crop(box)
    if work.height <= target * 1.5:
        if not trimmed:
            return logo
    else:
        size = (max(1, round(work.width * target / work.height)), target)
        work = work.resize(size, Image.Resampling.LANCZOS)
    out = BytesIO()
    work.convert("RGBA" if alpha else "RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def _hex_rgb(value: str | None) -> tuple[int, int, int]:
    text = (value or NEUTRAL_HEX).lstrip("#")
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        text = NEUTRAL_HEX.lstrip("#")
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


class _Doc(FPDF):
    def __init__(
        self,
        *,
        unicode_font: bool,
        title: str,
        subtitle: str,
        logo: Path | bytes | None,
        venue: str,
        footer_text: str,
        landscape: bool,
    ):
        super().__init__(
            orientation="L" if landscape else "P",
            unit="mm",
            format="Letter",
            enforce_compliance="PDF/A-2B" if unicode_font else None,
        )
        self.unicode_font = unicode_font
        # The code points the embedded font draws, once it is added; and
        # every text that had some it does not (see txt).
        self.glyphs: frozenset[int] | None = None
        self.unprintable: list[str] = []
        self._widths: dict[tuple, float] = {}
        # Each race's place in the program, shown before its name.
        self.race_numbers: dict[int, int] = {}
        self.band_title = title
        self.band_subtitle = subtitle
        self.logo = logo
        self.venue = venue
        self.footer_text = footer_text
        self.body_top = MARGIN
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(False)
        self.alias_nb_pages()

    def close_fonts(self) -> None:
        """Close the font files fpdf2 opened: it closes only the fonts it embeds.

        A sheet built and dropped (a measurement, a failed write) would
        otherwise leave the files open until the next garbage pass, which
        Python reports as leaked.
        """
        for font in list(self.fonts.values()):
            close = getattr(font, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # a file already closed is no failure
                    pass

    def __del__(self) -> None:
        self.close_fonts()

    def use(self, style: str, size: float) -> None:
        """Style "", "B", or "K" for the Black weight (Bold in the fallback)."""
        if not self.unicode_font:
            self.set_font("Helvetica", "B" if style == "K" else style, size)
        elif style == "K":
            self.set_font(BLACK_FAMILY, "", size)
        else:
            self.set_font(FAMILY, style, size)

    def quiet(self, text: str) -> str:
        """``txt`` for a piece of a text already reported whole: a trial line, a header part.

        Reporting every piece would fill the export's warning with fragments
        of one team line and push the riders' own names out of it.
        """
        kept = len(self.unprintable)
        out = self.txt(text)
        del self.unprintable[kept:]
        return out

    def quiet_fit(self, text: str, width: float, style: str, size: float) -> str:
        """``_fit`` at ``size`` with no shrinking, for a piece of a text already reported."""
        kept = len(self.unprintable)
        out = _fit(self, text, width, style, size, size)
        del self.unprintable[kept:]
        return out

    def txt(self, text: str) -> str:
        # The core-font fallback is Latin-1 only; fpdf2 would raise on anything else.
        if self.unicode_font:
            return self._drawable(text)
        # The minus sign of a lap count has a Latin-1 stand-in.
        text = text.replace(MINUS, "-").replace(ELLIPSIS, "...")
        out = text.encode("latin-1", "replace").decode("latin-1")
        # Reported as the bundled font's misses are, so a "?" in a name is
        # named to the scorer here too.
        if out != text and text not in self.unprintable:
            self.unprintable.append(text)
        return out

    def _drawable(self, text: str) -> str:
        """``text`` with each run of letters the font lacks shown as one "?".

        Inter has no CJK, Hangul, Arabic or emoji, and fpdf2 leaves such a
        name out of the file without a word: a blank cell on the archive
        copy. A "?" shows something is missing, and the text is kept in
        ``unprintable`` for the export to name. Marks that draw nothing on
        their own (joiners, variation selectors) are dropped quietly.
        """
        if self.glyphs is None or all(ord(ch) in self.glyphs for ch in text):
            return text
        out: list[str] = []
        missing = False
        for ch in text:
            if _missing(ch, self.glyphs):
                missing = True
                if not out or out[-1] != "?":
                    out.append("?")
            elif ord(ch) in self.glyphs or ch in " \t":
                out.append(ch)
        if missing and text not in self.unprintable:
            self.unprintable.append(text)
        return "".join(out)

    def get_string_width(self, s: str, normalized: bool = False, markdown: bool = False) -> float:
        # fpdf2 runs the bidi algorithm and HarfBuzz on every measure, and
        # the sheet measures the same few hundred strings (places, bibs,
        # names a rider carries from race to race, labels) thousands of
        # times while fitting them. The width depends only on the face,
        # the size and the text: shaping, stretching and spacing are set
        # once per document and never change.
        key = (self.font_family, self.font_style, self.font_size_pt, s, normalized, markdown)
        width = self._widths.get(key)
        if width is None:
            self._figures(s)
            width = super().get_string_width(s, normalized, markdown)
            self._widths[key] = width
        return width

    def cell(self, *args, **kwargs):
        text = kwargs.get("text", args[2] if len(args) > 2 else "")
        self._figures(text or "")
        return super().cell(*args, **kwargs)

    def _figures(self, text: str) -> None:
        """Tabular figures for a number, proportional ones for anything with letters in it.

        Inter's tnum also widens the hyphen to a figure's width, so a
        hyphenated name would read "Maximiliana - Josephine". A place, bib,
        points or lap count has no letters and keeps its aligned digits.
        The choice depends only on the text, so a remembered width stays
        right.
        """
        shaping = self.text_shaping
        if not shaping or shaping.get("features") is None:
            return
        shaping["features"] = {} if any(ch.isalpha() for ch in text) else dict(TNUM)

    @property
    def usable(self) -> float:
        return self.w - 2 * MARGIN

    @property
    def bottom(self) -> float:
        return self.h - MARGIN - FOOTER_H

    @property
    def later_top(self) -> float:
        """Where the body starts on a page after the first."""
        return MARGIN + RUN_H + RUN_GAP

    def header(self) -> None:
        if self.page_no() != 1:
            self._running_header()
            return
        left = 70.0
        logo_w = 0.0
        logo_h = BAND_H - 2 * BAND_PAD
        inner = self.usable - 2 * BAND_PAD
        if self.logo is not None:
            # Measured before the band is drawn, so the band can grow. A
            # very wide logo prints smaller rather than leave the event's
            # name no room (a 20:1 banner would take the whole band).
            logo_w = _logo_width(self.logo, logo_h)
            if logo_w > inner * LOGO_SHARE:
                logo_h *= inner * LOGO_SHARE / logo_w
                logo_w = inner * LOGO_SHARE
            left = max(left, logo_w)
        right = inner - left - 4
        # A long event name or venue wraps rather than being cut; the
        # band grows to hold it.
        title, title_pt = _wrap_lines(self, self.band_title, right, "B", 17, 12)
        sub, sub_pt = _part_lines(self, self.band_subtitle, right, "", 10, 8)
        venue: list[str] = []
        venue_pt = 15.0
        if self.logo is None and self.venue:
            venue, venue_pt = _wrap_lines(self, self.venue, left, "B", 15, 10)
        right_h = len(title) * _line_h(title_pt) + 1 + len(sub) * _line_h(sub_pt)
        band = max(
            BAND_H, 2 * BAND_PAD + 1 + right_h, 2 * BAND_PAD + len(venue) * _line_h(venue_pt)
        )
        self.set_fill_color(*BAND)
        self.rect(MARGIN, MARGIN, self.usable, band, style="F")
        self.set_text_color(255, 255, 255)
        # The logo, the venue's name, and the event's lines each sit as far
        # in from the band's side as from its top and foot.
        if logo_w:
            source = BytesIO(self.logo) if isinstance(self.logo, bytes) else str(self.logo)
            inset = (band - logo_h) / 2
            self.image(source, x=MARGIN + inset, y=MARGIN + inset, w=logo_w, h=logo_h)
        elif venue:
            inset = (band - len(venue) * _line_h(venue_pt)) / 2
            y = MARGIN + inset
            for line in venue:
                self.use("B", venue_pt)
                self.set_xy(MARGIN + inset - self.c_margin, y)
                self.cell(left, _line_h(venue_pt), line, align="L")
                y += _line_h(venue_pt)
        # The lines are centered on their ink, the first line's capitals
        # to the last line's baseline, and the side's air is the same.
        last_pt = sub_pt if sub else title_pt
        cap_top = _baseline(title_pt, _line_h(title_pt)) - _cap_h(title_pt)
        foot = right_h - _line_h(last_pt) + _baseline(last_pt, _line_h(last_pt))
        inset = (band - (foot - cap_top)) / 2
        x = self.w - MARGIN - inset + self.c_margin - right
        y = MARGIN + inset - cap_top
        for line in title:
            self.use("B", title_pt)
            self.set_xy(x, y)
            self.cell(right, _line_h(title_pt), line, align="R")
            y += _line_h(title_pt)
        y += 1
        for line in sub:
            self.use("", sub_pt)
            self.set_xy(x, y)
            self.cell(right, _line_h(sub_pt), line, align="R")
            y += _line_h(sub_pt)
        self.set_text_color(*INK)
        # fpdf2 resumes body output from wherever the header left the
        # cursor, which is inside the band; the first race starts below it.
        self.set_xy(MARGIN, MARGIN + band + BAND_GAP)
        self.body_top = MARGIN + band + BAND_GAP

    def _running_header(self) -> None:
        self.set_fill_color(*BAND)
        self.rect(MARGIN, MARGIN, self.usable, RUN_H, style="F")
        left = 50.0
        inner = self.usable - 2 * BAND_PAD
        # As on the first page's band, each side's air is its top's.
        if self.logo is not None:
            source = BytesIO(self.logo) if isinstance(self.logo, bytes) else str(self.logo)
            h = RUN_H - 4
            w = _logo_width(self.logo, h)
            if w > inner * LOGO_SHARE:
                h *= inner * LOGO_SHARE / w
                w = inner * LOGO_SHARE
            inset = (RUN_H - h) / 2
            self.image(source, x=MARGIN + inset, y=MARGIN + inset, w=w, h=h)
            left = max(left, w)
        elif self.venue:
            # As wide as the name needs, up to two fifths of the strip.
            self.use("B", 10)
            need = self.get_string_width(self.txt(self.venue)) + 2 * self.c_margin
            left = min(max(left, need), inner * 0.4)
            self.set_text_color(255, 255, 255)
            self.set_xy(MARGIN + (RUN_H - _line_h(10)) / 2 - self.c_margin, MARGIN)
            self.cell(left, RUN_H, _fit(self, self.venue, left, "B", 10, 7), align="L")
        # One line at the right: the event in bold, then the date and
        # series. The strip has room for one line, so what does not fit
        # is left off from the end (the venue, then the series), never cut:
        # the first page has all of it.
        self.set_text_color(255, 255, 255)
        right = inner - left - 4
        parts = [p for p in self.band_subtitle.split(SEP) if p] if self.band_subtitle else []
        self.use("B", 11)
        title_need = self.get_string_width(self.txt(self.band_title)) + 2 * self.c_margin
        while True:
            rest = "".join(SEP + p for p in parts)
            self.use("", 9)
            rest_w = self.get_string_width(self.quiet(rest)) + 2 * self.c_margin if rest else 0.0
            if not parts or title_need + rest_w <= right:
                break
            parts.pop()
        # The rest's cell starts where the title's text ends, not after
        # the two cells' own margins, so the gap before the first divider
        # is the divider's spaces, as between the others.
        join = 2 * self.c_margin if rest else 0.0
        title_w = min(right - rest_w + join, title_need)
        title = _fit(self, self.band_title, title_w, "B", 11, 8)
        # The event's capitals are centered on the strip and the smaller
        # rest shares their baseline; the side's air is the capitals' own.
        inset = (RUN_H - _cap_h(11)) / 2
        baseline = MARGIN + inset + _cap_h(11)
        x = self.w - MARGIN - inset + self.c_margin - title_w - rest_w + join
        self.set_xy(x, baseline - _baseline(11, RUN_H))
        self.cell(title_w, RUN_H, title, align="L")
        if rest:
            self.use("", 9)
            self.set_xy(x + title_w - join, baseline - _baseline(9, RUN_H))
            self.cell(rest_w, RUN_H, self.quiet(rest), align="L")
        self.set_text_color(*INK)
        self.set_xy(MARGIN, self.later_top)
        self.body_top = self.later_top

    def footer(self) -> None:
        y = self.h - MARGIN - 5
        self.set_draw_color(*RULE)
        self.line(MARGIN, y - 1.5, self.w - MARGIN, y - 1.5)
        self.set_text_color(*MUTED)
        self.set_xy(MARGIN, y)
        page_w = 28.0
        room = self.usable - page_w
        # The version, the event, and when it was made: a long event name
        # is left off here rather than cut, since the band above has it.
        parts = self.footer_text.split(SEP)
        text = self.footer_text
        self.use("", 6.5)
        while len(parts) > 2 and self.get_string_width(self.quiet(text)) > room - 2 * self.c_margin:
            parts.pop(1)
            text = SEP.join(parts)
        self.cell(room, 5, _fit(self, self.quiet(text), room, "", 8, 6.5), align="L")
        self.use("", 8)
        self.set_xy(self.w - MARGIN - page_w, y)
        self.cell(page_w, 5, f"Page {self.page_no()} of {{nb}}", align="R")
        self.set_text_color(*INK)


SEP = "  |  "


def _logo_width(logo: Path | bytes, height: float) -> float:
    """The logo's width at ``height``, read before the band is drawn so the band can grow."""
    try:
        with Image.open(BytesIO(logo) if isinstance(logo, bytes) else logo) as im:
            return height * im.width / im.height
    except (OSError, ValueError, ZeroDivisionError, Image.DecompressionBombError):
        return 70.0


def _line_h(size: float) -> float:
    """A line's height in mm at ``size`` points, with Inter's leading."""
    return size * 0.44


# Inter's capitals as a share of the size; fpdf2 sets a cell's baseline
# its height's middle plus BASELINE_DROP of the size below the top.
CAP = 0.7275
BASELINE_DROP = 0.3


def _baseline(size: float, h: float) -> float:
    """How far below a cell's top, ``h`` mm tall, its text's baseline sits at ``size`` points."""
    return h / 2 + BASELINE_DROP * size * 25.4 / 72


def _cap_h(size: float) -> float:
    return CAP * size * 25.4 / 72


def _wrap_words(pdf: _Doc, text: str, room: float) -> list[str]:
    # The spaces between words are kept as written, so a line reads on
    # its wrapped lines exactly as it was typed.
    lines: list[str] = []
    line = ""
    gap = ""
    for token in re.findall(r"\s+|\S+", text.strip()):
        if token.isspace():
            gap = token
            continue
        trial = f"{line}{gap}{token}" if line else token
        if line and pdf.get_string_width(pdf.quiet(trial)) > room:
            lines.append(line)
            line = token
        else:
            line = trial
        gap = ""
    if line:
        lines.append(line)
    return lines or [""]


def _wrap_lines(
    pdf: _Doc,
    text: str,
    width: float,
    style: str,
    size: float,
    min_size: float,
    max_lines: int = 2,
    keep: str = "",
) -> tuple[list[str], float]:
    """``text`` in at most ``max_lines`` lines of ``width``, and the size it fits at.

    One line comes first, shrinking at most 15%: a heading much smaller
    than its neighbors reads as a different kind of thing. Then two
    lines at the full size, shrinking toward ``min_size``. Then, at
    ``min_size``, a word too long for any line is broken over lines.
    Only what still does not fit is cut, on the last line, so a name is never cut
    while a second line would hold it. ``keep`` ends ``text`` and is never
    the part cut: a continued race's " (continued)" stays visible after
    a cut name.
    """
    room = width - 2 * pdf.c_margin
    sizes = [size - 0.5 * i for i in range(int((size - min_size) / 0.5) + 1)]
    for s in (s for s in sizes if s >= size * 0.85):
        pdf.use(style, s)
        if pdf.get_string_width(pdf.txt(text)) <= room:
            return [pdf.txt(text)], s
    for s in sizes:
        pdf.use(style, s)
        lines = _wrap_words(pdf, text, room)
        if len(lines) <= max_lines and all(
            pdf.get_string_width(pdf.quiet(ln)) <= room for ln in lines
        ):
            return [pdf.quiet(ln) for ln in lines], s
    pdf.use(style, min_size)
    text = text.strip()
    spans = _wrap_spans(pdf, text, room)
    if len(spans) <= max_lines:
        return [pdf.quiet(text[a:b]) for a, b in spans], min_size
    # The last line takes the rest of the text from where it starts, as
    # written, and only it is cut.
    kept = [text[a:b] for a, b in spans[: max_lines - 1]]
    last = text[spans[max_lines - 1][0] :]
    tail = ""
    if keep and last.endswith(keep.strip()):
        tail = pdf.quiet(keep)
        last = last[: -len(keep.strip())].rstrip()
        pdf.use(style, min_size)
        width -= pdf.get_string_width(tail)
    return [pdf.quiet(ln) for ln in kept] + [
        _fit(pdf, pdf.quiet(last), width, style, min_size, min_size) + tail
    ], min_size


def _clings(ch: str) -> bool:
    """True for a mark drawn on the character before it: an accent, a joiner, a variation selector."""
    code = ord(ch)
    return bool(unicodedata.combining(ch)) or code in SILENT or 0xFE00 <= code <= 0xFE0F


def _wrap_spans(pdf: _Doc, text: str, room: float) -> list[tuple[int, int]]:
    """``text`` wrapped at the current font into lines no wider than ``room``, as (start, end) spans.

    Lines break between words, and a word wider than ``room`` on its own
    is broken where it must be, so every line fits: a heading's lines
    are drawn as they come, and one long surname must not run under the
    tag or past the margin. The rest of a broken word starts the next
    line and the words after it follow on that line.
    """

    def fits(a: int, b: int) -> bool:
        return pdf.get_string_width(pdf.quiet(text[a:b])) <= room

    spans: list[tuple[int, int]] = []
    start = end = -1
    for word in re.finditer(r"\S+", text):
        a, b = word.span()
        if start >= 0 and fits(start, b):
            end = b
            continue
        if start >= 0:
            spans.append((start, end))
        while not fits(a, b) and b - a > 1:
            cut = a + 1
            while cut < b and fits(a, cut + 1):
                cut += 1
            # A hyphenated name breaks after its hyphen, so each line
            # holds whole parts of it.
            hyphen = text.rfind("-", a + 1, cut)
            if hyphen > a:
                cut = hyphen + 1
            # A mark that draws on the letter before it stays with that letter.
            while cut > a + 1 and _clings(text[cut]):
                cut -= 1
            spans.append((a, cut))
            a = cut
        start, end = a, b
    if start >= 0:
        spans.append((start, end))
    return spans or [(0, 0)]


def _part_lines(
    pdf: _Doc, text: str, width: float, style: str, size: float, min_size: float, max_lines: int = 3
) -> tuple[list[str], float]:
    """Parts joined by " | " in as few lines as fit, a part never split unless it alone is too wide."""
    if not text:
        return [], size
    room = width - 2 * pdf.c_margin
    parts = [p for p in text.split(SEP) if p]
    sizes = [size - 0.5 * i for i in range(int((size - min_size) / 0.5) + 1)]
    for s in sizes:
        pdf.use(style, s)
        if pdf.get_string_width(pdf.txt(text)) <= room:
            return [pdf.txt(text)], s
    for s in sizes:
        pdf.use(style, s)
        lines: list[str] = []
        for part in parts:
            trial = f"{lines[-1]}{SEP}{part}" if lines else part
            if lines and pdf.get_string_width(pdf.quiet(trial)) <= room:
                lines[-1] = trial
            elif pdf.get_string_width(pdf.quiet(part)) <= room:
                lines.append(part)
            else:
                lines.extend(_wrap_words(pdf, part, room))
        if len(lines) <= max_lines:
            return [pdf.quiet(ln) for ln in lines], s
    # Still more than max_lines at the smallest size: every line is kept
    # and the band grows, since a part left off here (the venue, last)
    # would vanish from the sheet without a mark.
    pdf.use(style, min_size)
    return [_fit(pdf, pdf.quiet(ln), width, style, min_size, min_size) for ln in lines], min_size


def _tabular_figures(pdf: _Doc) -> None:
    """Shape text with tabular figures, so digits line up in the columns."""
    try:
        pdf.set_text_shaping(use_shaping_engine=True, features=dict(TNUM))
    except FPDFException:
        # uharfbuzz is missing, a packaging bug like a missing font: the
        # sheet still prints, with proportional figures.
        pdf.set_text_shaping(use_shaping_engine=False)


def _fit(
    pdf: _Doc, text: str, width: float, style: str, size: float, min_size: float | None = None
) -> str:
    """Set the font so ``text`` fits a cell ``width`` wide, cutting it if it must.

    A long name must not run into the points column. The font shrinks to
    ``min_size`` first (by default 70% of the row size, which keeps a
    name readable at the podium), and what still does not fit is cut
    with an ellipsis, so the sheet shows that something was cut.
    """
    text = pdf.txt(text)
    floor = size * 0.7 if min_size is None else min_size
    # A hair of slack, so a cell sized to its own figure's width never
    # shrinks that figure over a rounding error.
    room = width - 2 * pdf.c_margin + 1e-6
    pdf.use(style, size)
    if pdf.get_string_width(text) <= room:
        return text
    while size - 0.5 >= floor:
        size -= 0.5
        pdf.use(style, size)
        if pdf.get_string_width(text) <= room:
            return text
    mark = pdf.txt(ELLIPSIS)
    while text and pdf.get_string_width(text.rstrip() + mark) > room:
        text = text[:-1]
    return text.rstrip() + mark


def _text(
    pdf: _Doc,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    align: str,
    style: str,
    size: float,
    min_size: float | None = None,
) -> None:
    if not text:
        return
    fitted = _fit(pdf, text, w, style, size, min_size)
    pdf.set_xy(x, y)
    pdf.cell(w, h, fitted, align=align)


def _wrapped(pdf: _Doc, text: str, width: float, style: str, size: float) -> T.Lines:
    if not text:
        return T.Lines((), size)
    return T.wrapped(pdf, text, width, style, size, size * T.NAME_SHRINK, T.NAME_LINES)


@dataclass(frozen=True)
class _Cols:
    """x and width of each column for one race; name takes what is left."""

    place: tuple[float, float]
    bib: tuple[float, float]
    name: tuple[float, float]
    # A team race's color swatch, and its team name's line across the bib
    # and name columns.
    swatch: float | None
    team: tuple[float, float] | None
    points: tuple[float, float] | None
    laps: tuple[float, float] | None
    # Only when a row carries a points ruling; a column empty in most
    # races is left off, as the laps column is.
    penalty: tuple[float, float] | None = None
    # One column per sprint, and the size their figures print at; or,
    # when they do not fit beside a readable name, the one summed column.
    sprints: tuple[tuple[float, float], ...] = ()
    sprint_pt: float = WORKING_PT
    sprints_sum: tuple[float, float] | None = None
    # The table column the race prints in: its left edge and width, or
    # None for the page's width.
    span: tuple[float, float] | None = None
    # A team's riders beside its name rather than under it.
    beside: bool = False

    @property
    def lead(self) -> T.Lead:
        return T.Lead(
            self.place, self.swatch, self.team, self.bib, self.name, self.span, self.beside
        )


def _widest_sprint(summary: RaceSummary) -> tuple[str, str]:
    """The widest sprint figure and the widest sprint sum as printed."""
    figures = [
        format_number(p) for row in summary.rows if row.is_finisher for p in row.sprint_points
    ]
    sums = [format_number(sum(row.sprint_points)) for row in summary.rows if row.is_finisher]
    return T.widest(figures), T.widest(sums)


def _sprint_columns(
    pdf: _Doc, summary: RaceSummary, x: float, right: float
) -> tuple[tuple[tuple[float, float], ...], float, tuple[float, float] | None, float]:
    """The sprint columns ending at ``right``, their size, or the one summed column; and the new right.

    A cell is sized to the race's own widest figure, so a table awarding
    100 a sprint widens the columns rather than overlap. The run ends one
    gap before Laps, whose own column has air left of its figure.
    """
    n = summary.sprint_count
    widest, widest_sum = _widest_sprint(summary)
    pt = WORKING_PT
    while True:
        cell = T.figure_w(pdf, widest, pt)
        need = n * (cell + SPRINT_GAP)
        if right - need - x >= NAME_MIN or pt - 0.5 < SPRINT_MIN_PT:
            break
        pt -= 0.5
    if right - need - x >= NAME_MIN:
        first = right - need + SPRINT_GAP
        return (
            tuple((first + i * (cell + SPRINT_GAP), cell) for i in range(n)),
            pt,
            None,
            right - need,
        )
    # More sprints than fit beside a readable name: the sum, as the
    # board's one SPRINT PTS column.
    head_w = T.figure_w(pdf, "Sprints", T.HEADER_PT, "B")
    w = max(T.figure_w(pdf, widest_sum, WORKING_PT), head_w)
    return (), WORKING_PT, (right - T.GAP - w, w), right - w - T.GAP


def _columns(pdf: _Doc, summary: RaceSummary, span: tuple[float, float] | None = None) -> _Cols:
    """The race's columns across the page, or across ``span``, one table column of it."""
    left, width = span or (MARGIN, pdf.usable)
    bibs = [str(r.bib) for row in summary.rows for r in row.riders or () if r.bib is not None]
    # The swatch has a column of its own; the team's name takes the bib
    # and name columns, as on the program: a 26 mm team column would cut
    # "Green Machine" at the podium sizes, where one word is wider than
    # the column. A team's riders print in the tier's rider face, the bib
    # with them, beside the name (``_team_block``) or under it.
    place, swatch, bib, x = T.lead_columns(
        pdf,
        T.PLACE_W,
        swatch=summary.is_team,
        bibs=bibs,
        bib_pt=T.TOP.rider_pt if summary.is_team else T.TOP.size,
        bib_gap=T.BIB_GAP,
        left=left,
    )
    assert bib is not None
    points = laps = penalty = sprints_sum = None
    sprints: tuple[tuple[float, float], ...] = ()
    sprint_pt = WORKING_PT
    right = left + width
    if summary.kind in ("points", "madison"):
        # The sprints, Laps, Penalty, Total, as the operator table and the
        # board run; the total sits at the right edge on all three. The
        # name column gives up the room.
        total_w = T.total_width(
            pdf, (format_number(r.total_points) for r in summary.rows if r.is_finisher)
        )
        points = (right - total_w, total_w)
        right -= total_w + T.GAP
        if any(r.adjust_points for r in summary.rows if not r.status):
            # A status row prints no figures, so only a placed row opens it.
            penalty = (right - T.PENALTY_W, T.PENALTY_W)
            right -= T.PENALTY_W + T.GAP
        laps = (right - LAPS_W, LAPS_W)
        right -= LAPS_W + T.GAP
        if summary.sprint_count:
            sprints, sprint_pt, sprints_sum, right = _sprint_columns(pdf, summary, x, right)
    elif any(r.laps_gained != r.laps_lost for r in summary.rows):
        # A finish order ranks a lapped rider by laps, so the sheet shows
        # them; a column empty in most races is left off.
        laps = (right - LAPS_W, LAPS_W)
        right -= LAPS_W + T.GAP
    name = (x, right - x)
    team = (bib[0], right - bib[0]) if swatch is not None else None
    block = _team_block(pdf, summary, bib[0], right) if swatch is not None else None
    beside = block is not None
    if block is not None:
        team, bib, name = block
    return _Cols(
        place,
        bib,
        name,
        swatch,
        team,
        points,
        laps,
        penalty,
        sprints,
        sprint_pt,
        sprints_sum,
        span,
        beside,
    )


def _team_block(
    pdf: _Doc, summary: RaceSummary, left: float, right: float
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None:
    """A team's name column from ``left``, then its riders' bib and name columns beside it;
    None when the riders go under the name.

    The bib column is as wide as the widest bib at the podium's rider
    size, so the riders sit close to the name.
    """
    rows = T.ordered(summary.rows, lambda r: r.is_finisher)
    riders = [(r, tier) for row, tier in rows for r in row.riders or ()]
    bib_w = max(
        [T.text_w(pdf, str(r.bib), T.TOP.rider_pt, "") for r, _ in riders if r.bib is not None],
        default=0.0,
    )
    riders_w = max([T.text_w(pdf, r.name, tier.rider_pt, "") for r, tier in riders], default=0.0)
    names = [(row.team or "", tier.size) for row, tier in rows]
    name_w = T.team_name_width(pdf, right - left, names, bib_w + T.BIB_GAP + riders_w)
    bib = (left + name_w + T.GAP, bib_w)
    x = bib[0] + bib_w + T.BIB_GAP
    if not T.riders_fit(pdf, right - x, [(r.name, tier.rider_pt) for r, tier in riders]):
        return None
    return (left, name_w), bib, (x, right - x)


def _two_columns(pdf: _Doc, summary: RaceSummary, cols: _Cols) -> tuple[_Cols, ...]:
    """The race's left and right columns, or just ``cols`` when it keeps the full width.

    Only a finish order goes to two columns: a race with sprint figures
    needs the width for them.
    """
    if cols.points is not None or summary.is_team or summary.finishers < TWO_COLUMN_MIN:
        return (cols,)
    width = (pdf.usable - COLUMN_GUTTER) / 2
    pair = tuple(
        _columns(pdf, summary, (MARGIN + k * (width + COLUMN_GUTTER), width)) for k in range(2)
    )
    if pair[0].name[1] < NAME_MIN:
        return (cols,)
    return pair


def _sprint_text(points: int, run: bool) -> str:
    """A sprint cell's text: blank for a sprint not yet run, since its 0 is
    not yet a fact, and blank where the rider scored nothing in a run
    sprint, so the figures that count stand out on a sheet that is mostly
    zeros."""
    return format_number(points) if run and points else ""


def _laps(row: ResultRow) -> str:
    return lap_text(row.laps_gained - row.laps_lost)


def _row_text(pdf: _Doc, row: ResultRow, cols: _Cols, tier: T.Tier) -> T.RowText:
    team = T.Lines((), tier.size)
    if cols.team is not None:
        team = _wrapped(pdf, row.team or "", cols.team[1], "B", tier.size)
        # Under a bold team name the riders are regular in the tier's
        # rider face, so the two read apart.
        rider_pt, rider_line, rider_style = tier.rider_pt, T.rider_line(tier.rider_pt), ""
    else:
        rider_pt, rider_line, rider_style = tier.size, tier.line, tier.name_style
    shown = (row.riders or ())[: None if cols.team is not None else 1]
    riders = tuple(
        (
            str(r.bib) if r.bib is not None else "",
            _wrapped(pdf, r.name, cols.name[1], rider_style, rider_pt),
        )
        for r in shown
    )
    return T.row_text(tier, team, riders, rider_line, rider_style, rider_pt, beside=cols.beside)


def _draw_row(
    pdf: _Doc,
    row: ResultRow,
    cols: _Cols,
    tier: T.Tier,
    y: float,
    text: T.RowText,
    run: frozenset[int] = frozenset(),
) -> float:
    """Draw one entrant at y and return the row height; ``run`` is the sprints scored so far."""

    def figures(top: float) -> None:
        # The figures sit on the row's first line, beside the team's name
        # or the rider's.
        working = cols.sprint_pt if cols.points is not None else tier.size
        for j, col in enumerate(cols.sprints):
            points = row.sprint_points[j] if j < len(row.sprint_points) else 0
            _text(
                pdf,
                col[0],
                top,
                col[1],
                tier.line,
                _sprint_text(points, j + 1 in run),
                "R",
                "",
                working,
            )
        if cols.sprints_sum is not None:
            x, w = cols.sprints_sum
            value = _sprint_text(sum(row.sprint_points), bool(run))
            _text(pdf, x, top, w, tier.line, value, "R", "", working)
        if cols.penalty is not None:
            x, w = cols.penalty
            _text(pdf, x, top, w, tier.line, lap_text(row.adjust_points), "R", "", working)
        if cols.points is not None:
            x, w = cols.points
            _text(pdf, x, top, w, tier.line, format_number(row.total_points), "R", "B", tier.size)
        if cols.laps is not None:
            x, w = cols.laps
            _text(pdf, x, top, w, tier.line, _laps(row), "R", "", working)

    return T.draw_row(
        pdf,
        cols.lead,
        tier,
        y,
        text,
        place=row.place,
        color_hex=row.color_hex,
        note=row.note,
        figures=figures,
    )


def _draw_header_row(pdf: _Doc, cols: _Cols, y: float) -> float:
    labels = [(cols.place, "Place", "R")]
    if cols.team is not None:
        # The team's name starts over the bibs, so "Team" heads both.
        labels.append((cols.team, "Team", "L"))
    else:
        labels += [(cols.bib, "Bib", "R"), (cols.name, "Rider", "L")]
    # S1, S2, ... as the operator table and the venue's own sheet head them.
    labels += [(col, f"S{i}", "R") for i, col in enumerate(cols.sprints, 1)]
    if cols.sprints_sum is not None:
        labels.append((cols.sprints_sum, "Sprints", "R"))
    if cols.laps is not None and cols.points is not None:
        labels.append((cols.laps, "Laps", "R"))
    if cols.penalty is not None:
        labels.append((cols.penalty, "Penalty", "R"))
    if cols.points is not None:
        labels.append((cols.points, "Total", "R"))
    if cols.laps is not None and cols.points is None:
        labels.append((cols.laps, "Laps", "R"))
    return T.draw_header_row(
        pdf, y, HEADER_ROW_H, labels, label_y=y, label_h=HEADER_ROW_H, span=cols.span
    )


def name_layout(
    pdf: _Doc,
    name: str,
    group: str,
    room: float,
    size: float,
    min_size: float,
    group_pt: float,
    suffix: str = "",
) -> tuple[list[str], float, bool]:
    """A race heading's name lines, their size, and whether the group fits beside the name.

    A long name wraps to a second line rather than being cut; a group
    that no longer fits beside it goes to the start of the gray line
    under it, where the caller puts it.
    """
    lines, pt = _wrap_lines(pdf, name + suffix, room, "B", size, min_size, keep=suffix)
    if not group:
        return lines, pt, False
    pdf.use("B", pt)
    name_w = pdf.get_string_width(lines[-1]) + 2 * pdf.c_margin
    pdf.use("", group_pt)
    beside = (
        len(lines) == 1
        and name_w + 1 + pdf.get_string_width(pdf.txt(group)) + 2 * pdf.c_margin <= room
    )
    return lines, pt, beside


# One race heading for both sheets, the results and the program, so
# the two never differ in size or layout: the race's
# number in gray, its name, its group in gray beside it, a slot at the
# right for the sheet's own mark (the results' state tag, the program's
# count), then gray lines saying how the race runs.
HEAD_PT = 15
HEAD_MIN_PT = 11
GROUP_PT = 13
DETAIL_PT = 9
HEADING_H = 6.5
DETAIL_H = 4.5
RIGHT_W = 36.0
CONTINUED = " (continued)"


@dataclass(frozen=True)
class Heading:
    number: str
    number_w: float
    lines: list[str]
    pt: float
    beside: bool
    group: str
    gray: list[str]

    @property
    def height(self) -> float:
        """The name's lines and the gray lines under it: what a page must hold above the rows."""
        return HEADING_H * len(self.lines) + DETAIL_H * len(self.gray)


def lay_heading(
    pdf: _Doc,
    number: int | None,
    name: str,
    group: str,
    detail: str,
    right: bool,
    *,
    more: bool = False,
) -> Heading:
    """Measure a race heading; ``right`` keeps the slot at the right clear for the sheet's mark.

    ``more`` marks the race's heading on a page after its first.
    """
    num = f"{number}." if number else ""
    pdf.use("B", HEAD_PT)
    num_w = pdf.get_string_width(pdf.txt(num)) + 2 * pdf.c_margin if num else 0.0
    room = pdf.usable - num_w - (RIGHT_W if right else 0.0)
    suffix = CONTINUED if more else ""
    lines, pt, beside = name_layout(pdf, name, group, room, HEAD_PT, HEAD_MIN_PT, GROUP_PT, suffix)
    full = SEP.join(t for t in ("" if beside else group, detail) if t)
    gray = _wrap_lines(pdf, full, pdf.usable, "", DETAIL_PT, 7)[0] if full else []
    return Heading(num, num_w, lines, pt, beside, group, gray)


def draw_heading(pdf: _Doc, h: Heading, y: float) -> float:
    """Draw a laid-out heading at ``y``; returns where the gray lines end."""
    top = y
    if h.number:
        pdf.set_text_color(*MUTED)
        pdf.use("B", h.pt)
        pdf.set_xy(MARGIN, y)
        pdf.cell(h.number_w, HEADING_H, h.number, align="L")
        pdf.set_text_color(*INK)
    x = MARGIN + h.number_w
    for line in h.lines:
        pdf.use("B", h.pt)
        pdf.set_xy(x, y)
        pdf.cell(pdf.get_string_width(line) + 2 * pdf.c_margin, HEADING_H, line, align="L")
        y += HEADING_H
    if h.beside:
        gx = pdf.get_x() + 1
        pdf.set_text_color(*MUTED)
        room = MARGIN + pdf.usable - RIGHT_W - gx
        _text(pdf, gx, top + 0.3, room, HEADING_H, h.group, "L", "", GROUP_PT)
        pdf.set_text_color(*INK)
    pdf.set_text_color(*MUTED)
    for line in h.gray:
        _text(pdf, MARGIN, y, pdf.usable, DETAIL_H, line, "L", "", DETAIL_PT, 7)
        y += DETAIL_H
    pdf.set_text_color(*INK)
    return y


def draw_tag(pdf: _Doc, tag: str, top: float, *, filled: bool = False) -> None:
    """A state tag in the heading's right slot: outlined in red, or filled in ink when final.

    The window draws Provisional outlined and Final filled; the sheets
    follow it, so the two read the same on paper.
    """
    tag_w = RIGHT_W - 2
    tx = MARGIN + pdf.usable - tag_w
    if filled:
        pdf.set_fill_color(*INK)
        pdf.rect(tx, top + 1, tag_w, HEADING_H - 2, style="F")
        pdf.set_text_color(255, 255, 255)
    else:
        pdf.set_draw_color(*ALERT)
        pdf.set_text_color(*ALERT)
        pdf.set_line_width(0.5)
        pdf.rect(tx, top + 1, tag_w, HEADING_H - 2)
        pdf.set_line_width(0.2)
    _text(pdf, tx, top + 1, tag_w, HEADING_H - 2, tag, "C", "B", 10)
    pdf.set_text_color(*INK)


def _provisional(summary: RaceSummary) -> bool:
    # The tag warns that a printed result may change; with no result
    # printed there is nothing for it to qualify.
    return summary.race.state != "final" and _has_result(summary)


def _tagged(summary: RaceSummary) -> bool:
    """True when the heading carries a tag, PROVISIONAL, IN PROGRESS, or FINAL, in its right slot."""
    return _provisional(summary) or summary.race.state == "final"


def _heading(pdf: _Doc, summary: RaceSummary, more: bool) -> Heading:
    race = summary.race
    number = pdf.race_numbers.get(race.race_id)
    return lay_heading(
        pdf,
        number,
        rulesets.race_short_name(race),
        race.group_label,
        _detail_line(summary),
        _tagged(summary),
        more=more,
    )


def _heading_h(pdf: _Doc, summary: RaceSummary) -> float:
    return _heading(pdf, summary, False).height


def _detail_line(summary: RaceSummary) -> str:
    race = summary.race
    parts = [summary.format_label]
    if race.rules_preset:
        parts.append(rulesets.ruleset_label(race.rules_preset))
    if summary.rules_line:
        parts.append(summary.rules_line)
    state = state_line(
        race,
        tagged=_tagged(summary),
        ended_after=summary.ended_after,
        shortened=summary.shortened,
    )
    if state:
        parts.append(state)
    return "  |  ".join(parts)


def _has_result(summary: RaceSummary) -> bool:
    """False for a race nobody has been placed in yet (its field is not a result)."""
    if summary.race.state in ("provisional", "final"):
        return True
    return any(r.is_finisher for r in summary.rows)


def _draw_heading(
    pdf: _Doc, summary: RaceSummary, columns: tuple[_Cols, ...], y: float, *, more: bool
) -> float:
    """The race's heading across the page, then a header row over each of its columns."""
    race = summary.race
    top = y
    y = draw_heading(pdf, _heading(pdf, summary, more), y)
    if _provisional(summary):
        # Anything not marked final can still change; say so where the
        # announcer looks first, at the right of the race's name.
        draw_tag(pdf, "PROVISIONAL" if race.state == "provisional" else "IN PROGRESS", top)
    elif race.state == "final":
        # And a final one says so the same way, filled as the window's
        # Final tag is, so the archive copy reads as settled at a glance;
        # the standings sheet does the same.
        draw_tag(pdf, "FINAL", top, filled=True)
    y += T.HEAD_TO_TABLE
    for cols in columns:
        _draw_header_row(pdf, cols, y)
    return y + HEADER_ROW_H + T.HEADER_TO_ROWS


def _race_section(pdf: _Doc, summary: RaceSummary) -> None:
    cols = _columns(pdf, summary)
    head = T.table_head(_heading_h(pdf, summary), HEADER_ROW_H)
    if not _has_result(summary):
        y = pdf.get_y()
        if y + head + T.REST.height(1) > pdf.bottom:
            pdf.add_page()
            y = pdf.get_y()
        y = _draw_heading(pdf, summary, (cols,), y, more=False)
        pdf.set_text_color(*MUTED)
        x = cols.name[0]
        line = y + T.REST.pad / 2
        w = MARGIN + pdf.usable - x
        _text(pdf, x, line, w, T.REST.line, "No result yet", "L", "", T.REST.size)
        pdf.set_text_color(*INK)
        pdf.set_xy(MARGIN, y + T.REST.height(1) + SECTION_GAP)
        return
    rows = T.ordered(summary.rows, lambda r: r.is_finisher)
    columns = _two_columns(pdf, summary, cols)
    # Both columns are one width, so a row wraps the same in either.
    texts = [_row_text(pdf, r, columns[0], t) for r, t in rows]
    y = T.draw_table(
        pdf,
        head,
        rows,
        texts,
        lambda y, more: _draw_heading(pdf, summary, columns, y, more=more),
        lambda row, tier, y, text, k: _draw_row(
            pdf, row, columns[k], tier, y, text, summary.sprints_run
        ),
        columns=len(columns),
    )
    if not rows:
        pdf.set_text_color(*MUTED)
        _text(pdf, MARGIN, y + 1, pdf.usable, 6, "No entrants", "L", "", 11)
        pdf.set_text_color(*INK)
        y += 7
    pdf.set_xy(MARGIN, y + SECTION_GAP)


def masthead(
    store: Store,
    logo_path: str | Path | None,
    venue_name: str | None,
    fallback_venue: str | None,
) -> tuple[str, Path | bytes | None]:
    """The venue's name and the logo at print size, for the band of any sheet.

    Logo: ``logo_path`` when given (and present), else the image stored in
    the data file, else the bundled placeholder wordmark. Venue name: the
    argument, else the setting, else ``fallback_venue`` (an event's venue).
    """
    venue = (
        venue_name or store.get_setting(venue_settings.NAME_KEY) or fallback_venue or ""
    ).strip()
    logo: Path | bytes | None
    if logo_path is not None:
        logo = Path(logo_path) if Path(logo_path).is_file() else None
    else:
        logo = venue_settings.logo_bytes(store)
    if logo:
        logo = _print_logo(logo)
    return venue, logo


def footer_line(name: str, generated: datetime | None) -> str:
    """The footer's text: the app and version, the sheet's name, and when it was made."""
    stamp = (generated or datetime.now()).astimezone()
    return SEP.join(
        (
            f"{APP_NAME} {__version__}",
            name,
            f"Generated {show_date_time(stamp)}",
        )
    )


def new_doc(
    *,
    title: str,
    subtitle: str,
    logo: Path | bytes | None,
    venue: str,
    footer_text: str,
    doc_title: str,
    landscape: bool = False,
) -> _Doc:
    """A sheet with the bundled Inter (or the core-font fallback) and its metadata set, no page yet."""
    font = find_font()

    def doc(unicode_font: bool) -> _Doc:
        return _Doc(
            unicode_font=unicode_font,
            title=title,
            subtitle=subtitle,
            logo=logo,
            venue=venue,
            footer_text=footer_text,
            landscape=landscape,
        )

    pdf = doc(font is not None)
    if font is not None:
        try:
            pdf.add_font(FAMILY, "", font[0])
            pdf.add_font(FAMILY, "B", font[1])
            pdf.add_font(BLACK_FAMILY, "", font[2])
            _tabular_figures(pdf)
            pdf.glyphs = frozenset(pdf.fonts[FAMILY.lower()].cmap)
        except Exception as exc:  # fontTools raises its own errors for a damaged file
            # A font file that is there but will not read is the same
            # packaging fault as a missing one, so the sheet takes the
            # same core-font fallback rather than failing the export.
            applog.warning(f"The PDF font could not be read, so the sheet uses Helvetica: {exc}")
            pdf.close_fonts()
            pdf = doc(False)
    pdf.set_title(doc_title)
    pdf.set_author(APP_NAME)
    pdf.set_creator(f"{APP_NAME} {__version__}")
    pdf.set_lang("en-US")
    return pdf


def write_results_pdf(
    store: Store,
    event_id: int,
    path: str | Path,
    *,
    logo_path: str | Path | None = None,
    venue_name: str | None = None,
    generated: datetime | None = None,
    races: Iterable[int] | None = None,
    unprintable: list[str] | None = None,
) -> Path:
    """Write the event's races (any race that has started) to a PDF at ``path``.

    ``unprintable``, when given, gets each name or title with letters the
    bundled font cannot draw; they print with "?" in their place, and the
    caller says which.

    ``races`` (race ids) narrows the sheet to those races, printed whatever
    their state, for the announcer who wants a race as it concludes.

    Logo: ``logo_path`` when given (and present), else the image stored
    in the data file, else the bundled placeholder wordmark, drawn on a
    dark band. With none, the venue name prints as text. Venue
    name: the argument, else the setting ``venue/name``, else the
    event's venue. ``generated`` is the time printed in the footer
    (now, by default).
    """
    event = store.event(event_id)
    wanted = None if races is None else set(races)
    all_races = store.races(event_id)
    if wanted is not None:
        unknown = wanted - {r.race_id for r in all_races}
        if unknown:
            raise ValueError(f"races not in event {event_id}: {sorted(unknown)}")
    venue, logo = masthead(store, logo_path, venue_name, event.venue)

    # The sheet names itself, as the program does: either may be the one
    # in someone's hand.
    subtitle = ["Results", _pretty_date(event.event_date)]
    if event.series:
        subtitle.append(event.series)
    if venue and logo:
        subtitle.append(venue)
    footer = footer_line(event.name, generated)

    pdf = new_doc(
        title=event.name,
        subtitle="  |  ".join(subtitle),
        logo=logo,
        venue=venue,
        footer_text=footer,
        doc_title=f"{event.name} results",
        landscape=True,
    )
    pdf.race_numbers = {r.race_id: n for n, r in enumerate(all_races, 1)}
    pdf.add_page()

    if wanted is None:
        shown = [r for r in all_races if r.state != "setup"]
    else:
        shown = [r for r in all_races if r.race_id in wanted]
    if not shown:
        pdf.use("", 11)
        pdf.cell(pdf.usable, 8, "No races scored yet")
    for race in shown:
        _race_section(pdf, build_summary(store, race))

    try:
        out = write_replacing(path, lambda partial: pdf.output(str(partial)))
    finally:
        pdf.close_fonts()
    if unprintable is not None:
        unprintable.extend(pdf.unprintable)
    return out


DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _pretty_date(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    # English words whatever the machine's language: strftime follows the
    # locale, which Qt sets from the system on macOS and Linux.
    return f"{DAYS[d.weekday()]}, {MONTH_NAMES[d.month - 1]} {d.day}, {d.year}"
