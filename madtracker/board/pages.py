"""The scoreboard layouts, one painted widget each.

Painting by hand rather than composing labels keeps every size a pure
function of the board height, which is what makes one layout serve a
1080p and a 4K TV. Each page draws only from its payload; nothing here
knows how standings are computed.
"""

import copy
import math
from dataclasses import replace
from typing import NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QWidget

from madtracker.board import theme as t
from madtracker.board.payloads import (
    Between,
    Elimination,
    Entry,
    Finish,
    Placing,
    PreRace,
    SprintResult,
    Standings,
    lap_text,
    lap_words,
    ordinal,
    total_text,
)

LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
CENTER = Qt.AlignmentFlag.AlignCenter

# A team's total plate is set in from its bar by this share of the bar's
# height on the top, right, and bottom, so the color shows evenly around it.
PLATE_MARGIN = 0.12
# The air inside the plate on each side of the widest total, in ems of
# the total's type.
PLATE_PAD = 0.32
# What the plate is sized for from the first lap, so the plates never
# change width as the race goes on: three figures (the figures are
# tabular, so 888 is as wide as any) and a negative two.
PLATE_SAMPLES = ("888", total_text(-88))
# What a team page's size is decided for, beside the race's own figures: a
# lap and a penalty, so the first lap gained or penalty given never steps
# the totals down partway through a race.
LAP_SAMPLES = ("+8", lap_text(-8))
PENALTY_SAMPLES = (lap_text(-88),)
# Between two figure columns inside a bar.
FIGURE_GAP = 40
# The sprint card's points sit this far after the widest team block or rider.
SPRINT_GAP = 28
# The widest the sprint card grows, in the card's own unit.
SPRINT_CARD_MOST = 1200
# The card is drawn in a unit larger than the page's, up to this much,
# since it is up for a few seconds and must be read from the stands at a
# glance; a card with more places takes a smaller unit so it stays on
# the page with this much air above and below it.
SPRINT_CARD_SCALE = 1.5
SPRINT_CARD_AIR = 40
# The card's height in its unit: the title band, the rows, the foot.
SPRINT_ROW_H = 84
SPRINT_HEAD_H = 130
SPRINT_FOOT_H = 30
# The table behind the card is dimmed to this alpha: dark enough that
# the card is what the eye finds, light enough to show the table is there.
SPRINT_VEIL = 235


def sprint_card_scale(rows: int, area_h: float, u: float) -> float:
    """The card's unit over the page's: the largest up to the cap that fits ``area_h``."""
    h = (SPRINT_HEAD_H + rows * SPRINT_ROW_H + SPRINT_FOOT_H) * u
    fit = (area_h - 2 * SPRINT_CARD_AIR * u) / h
    return max(0.0, min(SPRINT_CARD_SCALE, fit))


def figure(p: QPainter, rect: QRectF, s: str, f: QFont, color: QColor, align=RIGHT) -> float:
    """One line centered on ``rect`` by its capitals; return the width it used.

    A team block centers its name by the capitals (``t.stacked_lines``),
    so figures set beside or on a block are centered the same way and
    share the name's baseline.
    """
    [line] = t.stacked_lines(rect, f, 1)
    return t.text(p, QRectF(rect.x(), line.y(), rect.width(), line.height()), s, f, color, align)


def block_name(p: QPainter, rect: QRectF, color: str, name: str, f: QFont, floor_px: float) -> None:
    """A team's name in its color's ink, centered in ``rect``, a part of its block.

    ``t.team_block`` centers a name in the whole block; a block that also
    carries figures centers its name in the part the figures leave. The
    name shrinks as ``t.team_block`` shrinks it, never under ``floor_px``.
    """
    if not name:
        return
    pad = f.pixelSize() * t.TEAM_PAD
    room = rect.width() - 2 * pad
    w = t.text_width(name, f)
    if w > room > 0:
        least = floor_px / f.pixelSize() if floor_px else t.NAME_FLOOR
        f = t.scaled(f, min(1.0, max(least, room / w)))
    shown = QRectF(rect.x() + pad, rect.y(), room, rect.height())
    figure(p, shown, name, f, t.team_ink(QColor(color)), CENTER)


def name_zone(bar: QRectF, names: list[str], f: QFont, figures_x: float, u: float) -> QRectF:
    """Where a bar's name is centered: the whole bar, or the part left of its figures.

    The whole bar while the widest name clears the figures, so the names
    sit in the middle of the row; one answer for the list, so the names
    stay one column.
    """
    gap = 24 * u
    pad = f.pixelSize() * t.TEAM_PAD
    half = max((t.text_width(n, f) for n in names), default=0.0) / 2 + pad
    if bar.center().x() + half <= figures_x - gap:
        return bar
    return QRectF(bar.x(), bar.y(), max(0.0, figures_x - gap - bar.x()), bar.height())


def lap_chip_height(u: float) -> float:
    """A lap chip whose type is the board's floor, so it reads from the stands."""
    return t.MIN_PX * u / t.CHIP_TYPE


class Page(QWidget):
    """Base for one layout: holds the payload, the size unit and how riders are named.

    ``rider_label`` is the venue's choice (design section 10): names
    only, bibs and names, or bibs only. Every layout honors it where a
    rider is named; the payloads stay the same.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data = None
        self.u = 1.0
        self.rider_label = "bibs_names"
        # The team column of the list being drawn and how its riders are
        # set beside it (``entry_scale`` sets both, see ``team_layout``).
        self.team_w = 0.0
        self.team_mode = ""
        # The least of a row a team block takes when its riders leave it
        # the room, as a share of the row; 0 is the widest team name. The
        # color is what a rider at speed sees first, so a list with room
        # to spare gives it to the block rather than leave small bars and
        # names in an empty row.
        self.team_fill = 0.0
        # The page paints its whole rect, so Qt can skip clearing it.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    @property
    def show_bibs(self) -> bool:
        return self.rider_label != "names"

    @property
    def bibs_only(self) -> bool:
        return self.rider_label == "bibs"

    def set_data(self, data) -> None:
        self.data = data
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), t.BG)
        if self.data is not None:
            self.paint(p, self.margin_rect())
        p.end()

    def margin_rect(self) -> QRectF:
        u = self.u
        edge, top, bottom = t.EDGE * u, t.PAGE_TOP * u, t.PAGE_BOTTOM * u
        return QRectF(edge, top, self.width() - 2 * edge, self.height() - top - bottom)

    def paint(self, p: QPainter, area: QRectF) -> None:
        raise NotImplementedError

    # Shared row pieces -------------------------------------------------

    def entry_texts(
        self,
        rect: QRectF,
        entry: Entry,
        size: float,
        two_line_names: bool,
        scale: float = 1.0,
    ) -> list[tuple[QRectF, str, QFont, str]]:
        """Where each piece of an entry's text goes: ``(rect, string, font, kind)``.

        ``size`` sets the geometry and ``scale`` only the type, so a list
        drawn at a smaller scale keeps its columns where they were. Kind
        is "team" for the team block (its rect is the block's) and "name"
        for a rider's name, a team's riders taking one line each.
        """
        u = self.u
        h = rect.height()
        k = size * scale
        if entry.color:
            if self.team_w:
                team_w, mode = self.team_w, self.team_mode
            else:
                team_w, mode = self.team_layout([entry], rect, size, two_line_names)
            out = [
                (
                    QRectF(rect.x(), rect.y(), team_w, h),
                    entry.team or "",
                    t.font(self.team_px(k, size, h), t.BOLD),
                    "team",
                )
            ]
            if mode == "alone" or not entry.names:
                return out
            x = rect.x() + team_w + TEAM_GAP * u
            names_rect = QRectF(x, rect.y(), max(0.0, rect.right() - x), h)
            small = t.font(self.pair_size(k), t.SEMI)
            if len(entry.names) > 1:
                lines = t.stacked_lines(names_rect, small, 2)
                for r, name in zip(lines, entry.names[:2], strict=True):
                    out.append((r, name, small, "name"))
            else:
                out.append((names_rect, entry.names[0], small, "name"))
            return out
        name = entry.names[0] if entry.names else ""
        # A rider with no bib yet is named in every mode, and keeps the
        # name's column, so the start list still reads as one list.
        if self.bibs_only and entry.bibs:
            name = ""
        if not self.show_bibs:
            # Without the plate the name is the whole row, so it takes the
            # weight the plate had.
            return [(rect, name, t.font(k, t.BOLD), "name")]
        x = rect.x() + t.plate_width(self.plate_height(h)) + 26 * u
        return [(QRectF(x, rect.y(), rect.right() - x, h), name, t.font(k, t.SEMI), "name")]

    def team_px(self, k: float, size: float, h: float) -> float:
        """A team name's type in a row ``h`` tall: the list's, never larger than the block holds."""
        return min(max(k, min(size, t.MIN_PX * self.u)), h * 0.56)

    def team_want(self, entries: list[Entry], rect: QRectF, size: float) -> float:
        """A block wide enough for the list's widest team name at its own type."""
        f = t.font(self.team_px(size, size, rect.height()), t.BOLD)
        widest = max((t.text_width(e.team or "", f) for e in entries if e.color), default=0.0)
        return widest + 2 * f.pixelSize() * t.TEAM_PAD

    def team_least(self, entries: list[Entry], rect: QRectF, size: float) -> float:
        """The narrowest block that holds the widest team name whole, at the board's floor."""
        px = self.team_px(size, size, rect.height())
        f = t.font(min(px, t.MIN_PX * self.u), t.BOLD)
        widest = max((t.text_width(e.team or "", f) for e in entries if e.color), default=0.0)
        # The padding stays the list type's, as ``t.team_block`` sets it.
        pad = 2 * t.font(px, t.BOLD).pixelSize() * t.TEAM_PAD
        return min(self.team_want(entries, rect, size), widest + pad)

    def team_layout(
        self,
        entries: list[Entry],
        rect: QRectF,
        size: float,
        two_line_names: bool = False,
        reserve: list[float] | None = None,
    ) -> tuple[float, str]:
        """The team block's width and how the riders sit beside it: "stack" or "alone".

        One width for the whole list keeps the blocks a column and the
        riders' names aligned beside them. The block is the list's widest
        team name and its padding, capped at TEAM_SHARE of the row so one
        long name ("The Fast and the Furious Crew!") shrinks inside its
        own block rather than widening every row; past the cap a name
        shrinks to the board's floor, and the block grows to hold it
        there. Then, when the riders fit beside it with room to spare,
        the block widens into that room up to ``team_fill`` of the row,
        so the color is as big as the list allows (a block alone takes
        the whole row at a fill of 1). The riders sit stacked one per
        line beside the block when ``two_line_names`` asks for it or the
        row has the height for two lines; otherwise the block is alone.
        A team name has no initial to give up, so the riders give way
        first, in order: their initials, the block shrunk toward its
        widest name at the floor, and last the riders left off, the
        block alone with the row. Only a team name too long for the
        whole row is ever cut. ``reserve`` is each entry's lap chip,
        which the riders give way to as well.
        """
        u = self.u
        room, h = rect.width(), rect.height()
        want = self.team_want(entries, rect, size)
        least = self.team_least(entries, rect, size)
        reserve = reserve or [0.0] * len(entries)
        named = [
            (e, chip) for e, chip in zip(entries, reserve, strict=False) if e.color and e.names
        ]
        if not named:
            return self.filled(min(room, want), room, room), "alone"
        block = min(room, want, max(room * TEAM_SHARE, least))
        # The riders at the least they are set before an initial is
        # taken; past that the initial is all they have to give.
        small = t.font(self.pair_size(size * self.name_floor(size)), t.SEMI)

        def short(name: str) -> str:
            return t.initialed(name) or name

        if not two_line_names and h < small.pixelSize() * (1 + t.STACK_LEADING):
            return min(room, want), "alone"
        gap = TEAM_GAP * u
        riders = max(max(t.text_width(short(n), small) for n in e.names[:2]) + c for e, c in named)
        # The riders at their full names: what the fill must leave them.
        whole = max(max(t.text_width(n, small) for n in e.names[:2]) + c for e, c in named)
        if riders <= room - block - gap:
            # The spare room is what the full names leave, so widening the
            # block never costs a rider an initial.
            return self.filled(block, room - gap - whole, room), "stack"
        # The block gives up what the riders need, down to its widest
        # name at the floor.
        width = room - gap - riders
        if width >= least:
            return width, "stack"
        return min(room, want), "alone"

    def filled(self, block: float, spare: float, room: float) -> float:
        """``block`` widened into ``spare`` up to ``team_fill`` of ``room``, never narrowed."""
        return max(block, min(spare, room * self.team_fill))

    def pair_size(self, k: float) -> float:
        """A team's rider names: 80% of its team name, never under the design's floor.

        Still legible from the stands, and the block stays the row's
        anchor.
        """
        return max(k * 0.8, min(k, t.MIN_PX * self.u))

    def plate_height(self, h: float) -> float:
        """A bib plate's height in an entry ``h`` tall.

        Three quarters of the row when the row is roomy; in a dense list
        the plate takes more of its row, up to nearly all of it, so its
        digits stay near the board's minimum instead of shrinking with the
        row. The digits are 0.68 of the plate (``t.plate``).
        """
        return min(h * 0.92, max(h * 0.74, t.MIN_PX * self.u / 0.68))

    def lap_room(self, laps: int) -> float:
        """The width a lap chip takes at the end of an entry, its gap included."""
        words = lap_words(laps)
        return t.chip_width(lap_chip_height(self.u), words) + 16 * self.u if words else 0.0

    def lap_rooms(self, laps: list[int] | None, n: int) -> list[float]:
        """``lap_room`` for each of ``n`` entries; ``laps`` may be short or empty."""
        return [self.lap_room(laps[i] if laps and i < len(laps) else 0) for i in range(n)]

    def entry_scale(
        self,
        entries: list[Entry],
        rect: QRectF,
        size: float,
        two_line_names: bool = True,
        laps: list[int] | None = None,
    ) -> float:
        """One type scale for a whole list, the largest at which every name fits.

        Every row of a table at the same size reads as one table; a row
        shrunk on its own looks like a mistake. Team labels are left out:
        one long label should not shrink every rider's name. ``laps``,
        each entry's, measures the names in what the lap chips leave.
        """
        reserve = self.lap_rooms(laps, len(entries))

        def needs(scale: float):
            for e, chip in zip(entries, reserve, strict=True):
                r0 = rect.adjusted(0, 0, -chip, 0)
                texts = self.entry_texts(r0, e, size, two_line_names, scale)
                for r, s, f, kind in texts:
                    if kind != "team":
                        yield s, r.width(), f

        # The list's team column, set here because every list is measured
        # once, whole, before its rows are drawn.
        if any(e.color for e in entries):
            self.team_w, self.team_mode = self.team_layout(
                entries, rect, size, two_line_names, reserve
            )
        else:
            self.team_w, self.team_mode = 0.0, ""
        floor = self.name_floor(size)
        scale = t.fit_scale(needs(1.0), floor)
        # Text width is not exactly linear in pixel size (hinting), so step
        # down a pixel at a time until the real widths fit; otherwise a name
        # that should fit would lose its first name to a rounding error.
        while scale > floor and any(t.text_width(s, f) > w for s, w, f in needs(scale)):
            scale = max(floor, scale - 1 / max(size, 1))
        return scale

    def names_whole(self, entries: list[Entry], rect: QRectF, size: float) -> bool:
        """Whether every rider's name in the list fits ``rect`` whole on one line at ``size`` itself.

        At ``size`` and not at the list's shrink: a table whose figures grow
        while its names shrink to fit beside them has traded the names for
        the figures.
        """
        return all(
            t.text_width(s, f) <= r.width()
            for e in entries
            for r, s, f, kind in self.entry_texts(rect, e, size, True, 1.0)
            if kind == "name"
        )

    def name_floor(self, size: float) -> float:
        """The least a list set at ``size`` may shrink: NAME_FLOOR, but never under MIN_PX.

        A dense table already sets its names near the board's minimum; the
        usual shrink would take one long name's whole list under it, so
        such a list initials the long name instead.
        """
        if size <= 0:
            return t.NAME_FLOOR
        return max(t.NAME_FLOOR, min(1.0, t.MIN_PX * self.u / size))

    def entry_line(
        self,
        p: QPainter,
        rect: QRectF,
        entry: Entry,
        size: float,
        two_line_names: bool = True,
        scale: float | None = None,
        laps: int = 0,
    ) -> None:
        """Plate and name for a rider, or the team block and both names for a team.

        ``scale`` comes from ``entry_scale`` over the whole list; without
        one the entry is fitted on its own. ``laps``, when not even, adds
        a lap chip just after the name.
        """
        h = rect.height()
        if scale is None:
            scale = self.entry_scale([entry], rect, size, two_line_names, [laps])
        chip_h = lap_chip_height(self.u)
        words = lap_words(laps)
        chip_w = self.lap_room(laps)
        # The name gives way to the chip, never the chip to the name: a
        # lap is part of the result, a long name has an initial to spare.
        names_rect = rect.adjusted(0, 0, -chip_w, 0)
        end = self._entry_body(p, rect, names_rect, entry, size, two_line_names, scale)
        if words:
            x = min(end + 16 * self.u, rect.right() - chip_w + 16 * self.u)
            y = rect.y() + (h - chip_h) / 2
            # Neutral, not the accent: beside a winner's "1st" a second
            # accent object would split the emphasis, and a light accent
            # would make the chip look like a second bib plate.
            t.chip(p, x, y, chip_h, words, t.RULE, t.TEXT)

    def _entry_body(
        self,
        p: QPainter,
        rect: QRectF,
        names_rect: QRectF,
        entry: Entry,
        size: float,
        two_line_names: bool,
        scale: float,
    ) -> float:
        """Draw the entry's plate or team block and its text; return where the text ends."""
        h = rect.height()
        if not entry.color and self.show_bibs and entry.bibs:
            ph = self.plate_height(h)
            t.plate(
                p,
                QRectF(rect.x(), rect.y() + (h - ph) / 2, t.plate_width(ph), ph),
                entry.bibs[0] if entry.bibs else "",
            )
        end = rect.x()
        texts = self.entry_texts(names_rect, entry, size, two_line_names, scale)
        for r, s, f, kind in texts:
            if kind == "team":
                t.team_block(p, r, entry.color, s, f, t.MIN_PX * self.u)
                end = max(end, r.right())
                continue
            s = t.fit_name(s, r.width(), f)
            t.text(p, r, s, f, t.TEXT)
            end = max(end, r.x() + min(r.width(), t.text_width(s, f)))
        return end

    def names_scale(self, names: list[str], width: float, px: float) -> float:
        """One scale for a list of single-line names drawn bold at ``px``."""
        return t.fit_scale((n, width, t.font(px, t.BOLD)) for n in names)

    def block_scale(self, names: list[str], width: float, px: float) -> float:
        """One scale for a grid of ``name_block`` cards.

        Each name may use one line or two (first name over the rest), so
        its own best scale is the better of the two; the grid takes the
        smallest of those so every card matches.
        """
        f = t.font(px, t.BOLD)
        scale = 1.0
        for name in names:
            one = t.fit_scale([(name, width, f)], floor=0.0)
            first, sep, rest = name.strip().partition(" ")
            two = t.fit_scale([(first, width, f), (rest, width, f)], floor=0.0) if sep else 0.0
            scale = min(scale, max(one, two))
        scale = max(t.NAME_FLOOR, scale)

        def fits(scale: float) -> bool:
            g = t.scaled(f, scale)
            for name in names:
                first, sep, rest = name.strip().partition(" ")
                if t.text_width(name.strip(), g) <= width:
                    continue
                if sep and t.text_width(first, g) <= width and t.text_width(rest, g) <= width:
                    continue
                return False
            return True

        # As in entry_scale: hinting makes widths not quite linear, and a
        # name one pixel too wide would lose its last name to an ellipsis.
        while scale > t.NAME_FLOOR and not fits(scale):
            scale = max(t.NAME_FLOOR, scale - 1 / max(px, 1))
        return scale

    def name_block(
        self, p: QPainter, rect: QRectF, name: str, px: float, color=t.TEXT, scale: float = 1.0
    ) -> None:
        """A name centered in ``rect``, on two lines when one would not fit.

        Used where a card shows the name alone: "Jenna Whitfield" reads
        better as two big lines than as one line squeezed to fit. The
        first word goes on top so a multi-word last name stays together.
        Two lines are set as one block (``t.stacked_lines``) so they read
        as one name, centered in the card.
        """
        f = t.scaled(t.font(px, t.BOLD), scale)
        w = rect.width()
        name = name.strip()
        first, sep, rest = name.partition(" ")
        rest = rest.strip()

        def fits(s: str) -> bool:
            return t.text_width(s, f) <= w

        # The steps run in the order of ``fit_name``: the first name gives
        # way to its initial before the last name is ever cut.
        short = t.initialed(name)
        if fits(name) or not short:
            lines = [t.fit_name(name, w, f)]
        elif fits(first) and fits(rest):
            lines = [first, rest]
        elif fits(short):
            lines = [short]
        else:
            # The initial keeps a line of its own so the last name gets
            # the whole width before it is elided.
            lines = [f"{first[0]}.", t.elide(rest, w, f)]
        for r, s in zip(t.stacked_lines(rect, f, len(lines)), lines, strict=True):
            t.text(p, r, s, f, color, CENTER)

    def section_label(
        self, p: QPainter, x: float, y: float, s: str, color: QColor = t.MUTED
    ) -> None:
        t.text(p, QRectF(x, y, 1200 * self.u, 44 * self.u), s.upper(), t.label(self.u), color)

    def list_columns(self, count: int, height: float, most: int = 3) -> int:
        """How many columns a list of ``count`` rows needs in ``height``.

        Two columns are the start list's usual shape; a third opens only
        when two would set rows tighter than LIST_MIN_PITCH, which is where
        the names reach the board's minimum.
        """
        fit = max(1, int(height // (LIST_MIN_PITCH * self.u)))
        return max(1, min(most, -(-count // fit)))

    def rows_geometry(
        self, area: QRectF, count: int, cols: int, pitch_cap: float = 112, name_cap: float = 46
    ) -> tuple[int, float, float, QRectF, tuple[float, float, float, float]]:
        """``entry_rows``' layout: rows a column, pitch, name size, first entry rect, padding."""
        u = self.u
        col_w = (area.width() - LIST_COL_GAP * u * (cols - 1)) / cols
        fit = max(1, int(area.height() // (LIST_MIN_PITCH * u)))
        per_col = min(fit, math.ceil(count / cols))
        pitch = min(pitch_cap * u, area.height() / per_col)
        size = min(name_cap * u, pitch * LIST_NAME_SHARE)
        # The band and its padding give way in a dense list, so the plate
        # keeps its size rather than the air around it.
        band_gap = min(12 * u, pitch * 0.12)
        vpad = min(8 * u, pitch * 0.07)
        pad = (18 * u, vpad, -18 * u, -vpad)
        inner = QRectF(area.x(), area.y(), col_w, pitch - band_gap).adjusted(*pad)
        return per_col, pitch, size, inner, pad

    def team_fit(
        self,
        entries: list[Entry],
        rect: QRectF,
        size: float,
        two_line_names: bool,
        laps: list[int] | None = None,
    ) -> int:
        """How whole a team list is in entries the size of ``rect``.

        2 is every team with its riders, 1 the blocks alone, 0 a team name
        cut even alone. A list picks its columns by this, so a narrow
        column never cuts a team name or leaves riders off while a wider
        one would not.
        """
        reserve = self.lap_rooms(laps, len(entries))
        width, mode = self.team_layout(entries, rect, size, two_line_names, reserve)
        if width < self.team_least(entries, rect, size):
            return 0
        return 1 if mode == "alone" and any(e.names for e in entries if e.color) else 2

    def entry_rows(
        self,
        p: QPainter,
        area: QRectF,
        entries: list[Entry],
        cols: int,
        fill: QColor,
        pitch_cap: float = 112,
        name_cap: float = 46,
        laps: list[int] | None = None,
    ) -> None:
        """Entries as banded rows in ``cols`` columns, filled top to bottom.

        The name is a fixed share of the row's pitch up to ``name_cap``, so
        a long list sets smaller type in shorter rows; at 24 riders a
        fixed 46 px name would lose its descenders to the next row. Rows never
        go tighter than LIST_MIN_PITCH: what still does not fit is left off,
        never drawn over itself.
        """
        u = self.u
        if not entries:
            return
        gap = LIST_COL_GAP * u
        per_col, pitch, size, inner, pad = self.rows_geometry(
            area, len(entries), cols, pitch_cap, name_cap
        )
        col_w = (area.width() - gap * (cols - 1)) / cols
        band_h = inner.height() + pad[1] - pad[3]
        entries = entries[: per_col * cols]
        scale = self.entry_scale(entries, inner, size, laps=laps)
        for i, entry in enumerate(entries):
            c, r = divmod(i, per_col)
            row = QRectF(area.x() + c * (col_w + gap), area.y() + r * pitch, col_w, band_h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(row, 10 * u, 10 * u)
            lap = laps[i] if laps and i < len(laps) else 0
            self.entry_line(p, row.adjusted(*pad), entry, size, scale=scale, laps=lap)


# Between a team block and its riders' names.
TEAM_GAP = 28
# Between the columns of a list of entries.
LIST_COL_GAP = 48
# The most of an entry's width a team block takes for its name at full
# size; a longer name shrinks inside it, down to the board's floor.
TEAM_SHARE = 0.4
# How much of a row a block takes beside its riders when they leave the
# room (the start list, the result's podium): the color is the thing a
# rider at speed finds first, so it gets the spare room, and the riders
# keep one column beside it.
TEAM_FILL = 0.6
# A list row's name as a share of the row's pitch.
LIST_NAME_SHARE = 0.56
# The tightest a list of riders is set: its names at the board's minimum.
LIST_MIN_PITCH = t.MIN_PX / LIST_NAME_SHARE
# How much larger one column must set a list's names than its columns do
# to take their place: one long column of names barely larger has
# shorter rows and smaller plates.
ONE_COLUMN_GAIN = 1.03
# A team list row's name as a share of its pitch: less than a rider's, as
# the row stacks the team's two riders beside the block.
TEAM_LIST_NAME_SHARE = 0.4
# The widest lap chips a list keeps room for while it grows, so a lap
# taken mid-race never steps the list's names down.
LAP_CHIP_SAMPLES = (8, -8)


class PreRacePage(Page):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The last list's layout and what it was worked out for: finding
        # the largest whole size measures the list many times over, and a
        # repaint of the same list on the same page needs none of that.
        self._layout: tuple[tuple, tuple[int, float, float]] | None = None

    def paint(self, p: QPainter, area: QRectF) -> None:
        d: PreRace = self.data
        u = self.u
        count = len(d.roster)
        teams = any(e.color for e in d.roster)
        noun = ("team" if teams else "rider") + ("" if count == 1 else "s")
        # The top bar already says Start list; the count is the news here.
        self.section_label(p, area.x(), area.y(), f"{count} {noun}")
        top = area.y() + 64 * u
        laps = any(d.laps)
        room = QRectF(area.x(), top, area.width(), area.bottom() - top)
        if self.bibs_only and not teams and not laps and all(e.bibs for e in d.roster):
            plate_grid(p, room, [e.bibs[0] for e in d.roster], u)
            return
        if not d.roster:
            return
        self.team_fill = TEAM_FILL
        key = (room.width(), room.height(), u, self.rider_label, d)
        if self._layout is None or self._layout[0] != key:
            # A copy, so a payload changed where it stands is not taken for the one measured.
            self._layout = ((*key[:-1], copy.deepcopy(d)), self.list_layout(room, d))
        cols, pitch_cap, name_cap = self._layout[1]
        self.entry_rows(p, room, d.roster, cols, t.ROW, pitch_cap, name_cap, d.laps)

    def list_layout(self, room: QRectF, d: PreRace) -> tuple[int, float, float]:
        """The list's columns and its pitch and name caps: the plan that sets its names largest."""
        u = self.u
        count = len(d.roster)
        teams = any(e.color for e in d.roster)
        if count <= 6:
            # A small field is one column of big names.
            plans = [(1, 128, 56)]
        else:
            cols = max(2, self.list_columns(count, room.height()))
            if teams:
                cols = self.team_columns(room, d.roster, cols, d.laps)
            plans = [(cols, 112, 46)]
            if not teams and count <= room.height() // (LIST_MIN_PITCH * u):
                # A mid-size field may read larger in one column than in
                # two, whose half-width rows cap the names.
                plans.append((1, 112, 46))
        best = None
        for cols, pitch_cap, name_cap in plans:
            caps = self.grown_caps(room, d.roster, cols, pitch_cap, name_cap)
            _per, pitch, size, _inner, _pad = self.rows_geometry(room, count, cols, *caps)
            if best is None:
                best, least_pitch = (size, cols, caps), pitch
            elif size > best[0] * ONE_COLUMN_GAIN and pitch >= least_pitch:
                # One column takes the place of the columns only with rows
                # as tall as theirs, so the plates keep their size.
                best = (size, cols, caps)
        _size, cols, (pitch_cap, name_cap) = best
        return cols, pitch_cap, name_cap

    def grown_caps(
        self, room: QRectF, roster: list[Entry], cols: int, pitch_cap: float, name_cap: float
    ) -> tuple[float, float]:
        """The list's pitch and name caps, grown so a small field's rows share the page.

        The rows share the room down to a least field, as the race's own
        table does, shared by the list's columns; the type grows with them
        only while every name fits whole at its size and, for teams, every
        team keeps its riders beside it. A rider list keeps room for a lap
        chip on every row, so the first lap taken never steps it down. The
        caps never go under ``pitch_cap`` and ``name_cap``, so a long list
        keeps its base sizes.
        """
        u = self.u
        teams = any(e.color for e in roster)
        per_col = math.ceil(len(roster) / cols)
        least = math.ceil((TEAM_FILL_LEAST if teams else RIDER_FILL_LEAST) / cols)
        share = TEAM_LIST_NAME_SHARE if teams else LIST_NAME_SHARE
        fill = room.height() / max(per_col, least)
        base_size = min(name_cap * u, min(pitch_cap * u, room.height() / per_col) * LIST_NAME_SHARE)
        # A team list leaves the board at its first lap, for the race's table.
        chip = 0 if teams else max(LAP_CHIP_SAMPLES, key=self.lap_room)
        laps = [chip] * len(roster)
        size = fill * share
        while size > base_size:
            # The rows never come out shorter than the base list's, which
            # would cost the plates what the names gain.
            caps = (max(size / share / u, pitch_cap), size / u)
            _per, _pitch, got, inner, _pad = self.rows_geometry(room, len(roster), cols, *caps)
            whole = self.entry_scale(roster, inner, got, True, laps) >= 1.0
            if whole and teams:
                whole = self.team_fit(roster, inner, got, True, laps) == 2
                whole = whole and self.pair_height(got) <= inner.height()
            if whole:
                return caps
            size *= 0.96
        return pitch_cap, name_cap

    def pair_height(self, size: float) -> float:
        """The height a team's two riders need in a list set at ``size``.

        The lines are centered by their capitals (``t.stacked_lines``), so
        the descenders below need the same room above.
        """
        f = t.font(self.pair_size(size), t.SEMI)
        fm = QFontMetricsF(f)
        return fm.capHeight() + t.STACK_LEADING * f.pixelSize() + 2 * fm.descent()

    def team_columns(self, room: QRectF, roster: list[Entry], cols: int, laps: list[int]) -> int:
        """Fewer, wider columns for a team list whose riders or names a column would lose.

        Eight long team names in two columns would show blocks alone over
        half an empty page; one column holds them with their riders. A list
        keeps its columns when it is whole in them, and
        never takes fewer than show every entry.
        """
        best = (-1, cols)
        for c in range(cols, 0, -1):
            per_col, _pitch, size, inner, _pad = self.rows_geometry(room, len(roster), c)
            if per_col * c < len(roster):
                break
            best = max(best, (self.team_fit(roster, inner, size, True, laps), c))
        return best[1]


# The most riders still in that show as cards; more open as rows. Four
# columns of cards would set long names at 25 px, under the design's floor.
CARDS_UP_TO = 6
# A row's name size when the rows have room; a long list sets it smaller,
# down to the board's minimum (LIST_NAME_SHARE).
ROW_NAME_PX = 50
# The tallest bib plate on a remaining-rider card: the plate grid's own
# largest, which a three-digit bib fills from the far end of the stands.
PLATE_CAP = 170


def plate_grid(p: QPainter, area: QRectF, bibs: list[str], u: float) -> None:
    """Bibs as a grid of plates as big as the area allows, for the bibs-only board.

    A venue that shows bibs only is saying the number is everything;
    rows sized for a name would leave a small plate beside empty space.
    """
    n = len(bibs)
    if not n:
        return
    gap = 28 * u
    best = (0.0, 1)
    for cols in range(1, 9):
        rows = math.ceil(n / cols)
        ph = min((area.height() - gap * (rows - 1)) / rows, 170 * u)
        pw = t.plate_width(ph)
        if pw * cols + gap * (cols - 1) > area.width():
            ph = (area.width() - gap * (cols - 1)) / cols * ph / pw
        if ph > best[0]:
            best = (ph, cols)
    ph, cols = best
    pw = t.plate_width(ph)
    # Centered across the area, so a grid narrower than the page sits
    # under the title rather than leaving the right half empty.
    x0 = area.x() + (area.width() - cols * pw - (cols - 1) * gap) / 2
    for i, bib in enumerate(bibs):
        r, c = divmod(i, cols)
        t.plate(p, QRectF(x0 + c * (pw + gap), area.y() + r * (ph + gap), pw, ph), bib)


class EliminationPage(Page):
    """Remaining riders as cards, with the last one out called out loudly.

    ``fresh`` is set by the window for a few seconds after an elimination
    and drives the red treatment; afterwards the card stays, quieter, so a
    spectator who looked away can still see who went.
    """

    fresh = True

    def paint(self, p: QPainter, area: QRectF) -> None:
        d: Elimination = self.data
        u = self.u
        side_w = 600 * u
        gap = 64 * u
        grid = QRectF(area.x(), area.y(), area.width() - side_w - gap, area.height())
        side = QRectF(grid.right() + gap, area.y(), side_w, area.height())

        self.section_label(p, grid.x(), grid.y(), "Still racing")
        n = len(d.remaining)
        top = grid.y() + 64 * u
        if self.bibs_only and all(e.bibs for e in d.remaining):
            room = QRectF(grid.x(), top, grid.width(), grid.bottom() - top)
            plate_grid(p, room, [e.bibs[0] for e in d.remaining], u)
            self._side(p, side, n)
            return
        if n > CARDS_UP_TO:
            # Cards narrow enough for a big field put names under the
            # floor; it opens as two columns of start-list rows instead.
            self._rows(p, QRectF(grid.x(), top, grid.width(), grid.bottom() - top))
            self._side(p, side, n)
            return
        # Four to six left are two columns of cards: three across are too
        # narrow for a name such as M. Vanderbilt-Rochester at the board's
        # minimum, and four would leave the fourth alone on a second row.
        cols = 2 if n >= 4 else max(n, 1)
        rows = max(1, math.ceil(n / cols))
        cg = 24 * u
        cw = (grid.width() - cg * (cols - 1)) / cols
        # The last few riders are the race's climax: their cards grow.
        final = n <= 4
        ch = min((420 if final else 250) * u, (grid.bottom() - top - cg * (rows - 1)) / rows)
        names = [e.names[0] if e.names and not self.bibs_only else "" for e in d.remaining]
        block_px = min((88 if final else 52) * u, ch * 0.26)
        card_px = min((64 if final else 36) * u, ch * 0.15)
        if self.show_bibs:
            f = t.font(card_px, t.SEMI)
            scale = t.fit_scale(((n, cw - 32 * u, f) for n in names), self.name_floor(card_px))
        else:
            scale = self.block_scale(names, cw - 32 * u, block_px)
        for i, entry in enumerate(d.remaining):
            r, c = divmod(i, cols)
            card = QRectF(grid.x() + c * (cw + cg), top + r * (ch + cg), cw, ch)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.CARD)
            p.drawRoundedRect(card, 14 * u, 14 * u)
            name = names[i]
            if not self.show_bibs:
                inner = card.adjusted(16 * u, 10 * u, -16 * u, -10 * u)
                self.name_block(p, inner, name, block_px, scale=scale)
                continue
            # The plate grows with the card, but never past the size a
            # three-digit bib needs, and never wider than the card less a
            # margin, or three left on a wide monitor would draw plates taller
            # than the cards are wide, running into each other.
            ph = min(ch * 0.46, PLATE_CAP * u, (cw - 48 * u) / t.plate_width(1.0))
            pw = t.plate_width(ph)
            bib = entry.bibs[0] if entry.bibs else ""
            t.plate(p, QRectF(card.center().x() - pw / 2, card.y() + ch * 0.13, pw, ph), bib)
            name_rect = QRectF(card.x() + 16 * u, card.y() + ch * 0.64, cw - 32 * u, ch * 0.28)
            f = t.scaled(t.font(card_px, t.SEMI), scale)
            t.text(p, name_rect, t.fit_name(name, name_rect.width(), f), f, t.TEXT, CENTER)
        self._side(p, side, n)

    def _rows(self, p: QPainter, area: QRectF) -> None:
        """The riders still in as columns of start-list rows, for a big field."""
        d: Elimination = self.data
        cols = max(2, self.list_columns(len(d.remaining), area.height()))
        self.entry_rows(p, area, d.remaining, cols, t.CARD, name_cap=ROW_NAME_PX)

    def _side(self, p: QPainter, side: QRectF, n: int) -> None:
        """The side column: who just went, how many are left, who went before."""
        d: Elimination = self.data
        u = self.u
        side_w = side.width()
        y = side.y()
        if d.last_eliminated is not None:
            fresh = self.fresh
            self.section_label(
                p, side.x(), y, "Eliminated" if fresh else "Last out", t.OUT if fresh else t.MUTED
            )
            card = QRectF(side.x(), y + 56 * u, side_w, 330 * u)
            p.setBrush(t.OUT_SOFT if fresh else t.CARD)
            p.setPen(QPen(t.OUT, 4 * u) if fresh else Qt.PenStyle.NoPen)
            p.drawRoundedRect(card.adjusted(2 * u, 2 * u, -2 * u, -2 * u), 16 * u, 16 * u)
            out_name = d.last_eliminated.names[0] if d.last_eliminated.names else ""
            if self.bibs_only:
                out_name = ""
            if self.show_bibs:
                self._last_out_plate(p, card, out_name)
            else:
                inner = card.adjusted(32 * u, 40 * u, -32 * u, -40 * u)
                # 76 px of Inter has the capitals of the 84 px this card was
                # designed at, and lets a 17-letter last name such as
                # Featherstonehaugh stay whole above the floor.
                out_px = 76 * u
                scale = self.block_scale([out_name], inner.width(), out_px)
                self.name_block(p, inner, out_name, out_px, scale=scale)
            y = card.bottom() + 56 * u
        self._remaining(p, side, y, n)

    def _last_out_plate(self, p: QPainter, card: QRectF, name: str) -> None:
        u = self.u
        bibs = self.data.last_eliminated.bibs
        bib = bibs[0] if bibs else ""
        if not name:
            # Bibs only: the plate alone, larger, in the middle of its card.
            ph = 200 * u
            pw = t.plate_width(ph)
            t.plate(p, QRectF(card.center().x() - pw / 2, card.center().y() - ph / 2, pw, ph), bib)
            return
        ph = 150 * u
        pw = t.plate_width(ph)
        t.plate(p, QRectF(card.center().x() - pw / 2, card.y() + 44 * u, pw, ph), bib)
        rect = QRectF(card.x() + 24 * u, card.y() + 220 * u, card.width() - 48 * u, 80 * u)
        f = t.scaled(t.font(50 * u, t.BOLD), self.names_scale([name], rect.width(), 50 * u))
        t.text(p, rect, t.fit_name(name, rect.width(), f), f, t.TEXT, CENTER)

    def _remaining(self, p: QPainter, side: QRectF, y: float, n: int) -> None:
        """How many are left, then who went before the last one out."""
        d: Elimination = self.data
        u = self.u
        side_w = side.width()
        # Below the eliminated rider in size: the news is who went, not
        # how many stay.
        big = t.font(96 * u, t.HEAVY)
        w = t.text(p, QRectF(side.x(), y, side_w, 110 * u), str(n), big, t.ACCENT)
        t.text(
            p,
            QRectF(side.x() + w + 24 * u, y + 20 * u, side_w - w, 80 * u),
            "riders remaining" if n != 1 else "rider remaining",
            t.font(40 * u, t.SEMI),
            t.TEXT,
        )
        y += 140 * u
        if not d.eliminated:
            return
        self.section_label(p, side.x(), y, "Out earlier")
        y += 52 * u
        if not self.show_bibs:
            # Names, newest first, one a line, dimmed like the plates.
            lh = 50 * u
            names = [e.names[0] if e.names else "" for e in reversed(d.eliminated)]
            # Already at the board's minimum: a long name is initialed by
            # fit_name, never shrunk under it.
            f = t.font(t.MIN_PX * u, t.SEMI)
            for name in names:
                if y + lh > side.bottom():
                    break
                t.text(p, QRectF(side.x(), y, side_w, lh), t.fit_name(name, side_w, f), f, t.MUTED)
                y += lh
            return
        # The chips are small by role, not by type: their digits stay at
        # the board's minimum size. They wrap onto as many rows as the
        # column holds, so a long Elimination shows more than its last few.
        ph = 72 * u
        gap = 16 * u
        x = side.x()
        for e in reversed(d.eliminated):
            pw = t.plate_width(ph)
            if x + pw > side.right() and x > side.x():
                x = side.x()
                y += ph + gap
            if y + ph > side.bottom() or x + pw > side.right():
                break
            t.plate(p, QRectF(x, y, pw, ph), e.bibs[0] if e.bibs else "", out=True)
            x += pw + gap


def sprint_title(res: SprintResult) -> str:
    """The card's title, worded like the header's "After Sprint 2 of 3"."""
    # "Final sprint" is the task line's phrase for the last sprint, so the
    # audience reads the same words the scorer does.
    if res.of is not None and res.number >= res.of:
        return "Final sprint"
    if res.of is not None:
        return f"Sprint {res.number} of {res.of}"
    return f"Sprint {res.number}"


# The most rows a page shows. Sixteen is the most riders a 166 m track
# may start (USAC 2B7), so a full field at the venue is one page the
# stands can read whole, its names at the design's floor (section 10). A
# longer table, from a bigger track, turns its pages every few seconds
# rather than shrinking its names, and its pages share the rows evenly, so
# 24 riders show as 12 and 12, not 16 and a lonely 8.
PAGE_ROWS = 16
# A madison row carries a team block, so a page holds half as many. USAC
# 2B7 allows twelve teams on a 166.66 m track; twelve rows would set the
# team names under MIN_PX, so a full field shows as two pages of six.
TEAM_PAGE_ROWS = 8
# Team rows share the page's height whatever the field, so two teams read
# from the track as large as the page allows; a lone team takes half the
# page rather than one bar the whole height.
TEAM_FILL_LEAST = 2
# A team row's place and total, its largest type, as a share of the row.
TEAM_FIGURE_SHARE = 0.62
# The team name as a share of the row; ``team_px`` holds it inside the bar.
TEAM_NAME_SHARE = 0.5
# The widest the place column grows, as a share of the page's width.
TEAM_PLACE_SHARE = 0.14
# LAPS and PENALTY grow with the row, under the total so it stays the
# figure the eye finds first.
TEAM_LAPS_SHARE = 0.36
# A small field's figures give way to its team names: they step down from
# their share of the row until the widest name fits whole left of them at
# TEAM_NAME_LEAST or larger, and never below TEAM_FIGURE_LEAST. A name is
# what the stands match to the jerseys, and the growth is for both.
TEAM_NAME_LEAST = 84
TEAM_FIGURE_LEAST = 84
# Row height to type in a rider table: the name is this share of the row,
# so sixteen rows set it at MIN_PX and fewer rows set it larger.
STANDINGS_NAME_SHARE = 0.69
# The rider row at which the table's type and columns reach their base
# sizes; nine riders or more fill a 1080p page at it or less. A smaller
# field's taller rows scale the type and the columns together, so the
# figures keep their columns.
RIDER_ROW_FULL = 96
# Rider rows share the page down to this many rows' worth. A smaller field
# takes rows that tall at most: its riders' names, not the page, then limit
# how far the type grows, as the wider figure columns leave a name less
# room, and a name that holds the type back shortens the rows with it.
RIDER_FILL_LEAST = 5


# The header words of a race the officials have decided.
DECIDED = ("Provisional", "Final")


class RiderColumns(NamedTuple):
    """The rider table's columns at one figure unit: each column's left edge and width."""

    rank_w: float
    name_x: float
    name_w: float
    sprints_x: float
    sprints_w: float
    laps_x: float
    laps_w: float
    penalty_x: float
    penalty_w: float
    total_x: float
    total_w: float


def rider_columns(area: QRectF, g: float, gutter: float, penalized: bool) -> RiderColumns:
    """The rider table's columns at figure unit ``g``, laid out from the right.

    The total keeps the page's right edge, row to row and page to page. Every figure
    column is right-aligned, heading and figures to one padded edge, as
    TOTAL is: a heading wider than its figures ("SPRINT PTS" is 236u in
    the label face over 93u of figures; "PENALTY" 184u over "−20" at
    93u) then runs left over the heading row's empty middle instead of
    into the next column, and the columns stay as narrow as their
    figures. "LAPS" is 104u over "+1" at 62u; "TOTAL" 129u over a
    three-digit total at 116u; a rank 62u. The rest is the names'. A
    PENALTY column opens between LAPS and TOTAL only while a row on the
    board carries one, so the names keep the room on every other night.
    """
    total_w, laps_w, sprints_w, rank_w = 170 * g, 150 * g, 150 * g, 80 * g
    # Wide enough for its heading to clear LAPS's by a gutter.
    penalty_w = 210 * g if penalized else 0
    total_x = area.right() - total_w
    penalty_x = total_x - penalty_w
    laps_x = penalty_x - laps_w
    sprints_x = laps_x - sprints_w
    name_x = area.x() + rank_w
    return RiderColumns(
        rank_w,
        name_x,
        sprints_x - name_x - gutter,
        sprints_x,
        sprints_w,
        laps_x,
        laps_w,
        penalty_x,
        penalty_w,
        total_x,
        total_w,
    )


def page_rows(count: int, most: int = PAGE_ROWS) -> int:
    """Rows on each page of a ``count``-row table, the pages balanced."""
    pages = max(1, -(-count // most))
    return max(1, -(-count // pages))


class StandingsPage(Page):
    """Points race, madison and tempo standings: place, who, sprint points, laps, total.

    No per-sprint columns: riders read the board at speed for their
    place, their total and their laps, and on a TV the columns squeeze a
    long team name ("Stars and Stripes") and make the table too busy to
    parse. One SPRINT PTS column carries the sprint points so far and
    LAPS the laps alone ("+1"): a bare number under SPRINTS reads as a
    count of sprints, and "+1 (+20)" mixes laps with points. The team
    page drops SPRINT PTS and the riders' names and sets its place, team
    bar and total as the row's largest things (``team_table``). Each
    sprint shows for a few seconds on the sprint-result card as it lands; the operator table and the
    results sheet keep every sprint. More than PAGE_ROWS rows
    (TEAM_PAGE_ROWS for teams) are shown a page at a time; ``advance``
    turns the page.
    """

    page = 0

    def set_data(self, data) -> None:
        if self.data is None or getattr(self.data, "header", None) != getattr(data, "header", None):
            self.page = 0
        super().set_data(data)

    def page_most(self) -> int:
        teams = self.data is not None and any(r.entry.color for r in self.data.rows)
        return TEAM_PAGE_ROWS if teams else PAGE_ROWS

    def page_count(self) -> int:
        rows = len(self.data.rows) if self.data is not None else 0
        return max(1, -(-rows // page_rows(rows, self.page_most())))

    def ordinals(self, d: Standings) -> bool:
        """Whether the places read "1st", "2nd": once the officials have decided the race.

        A decided table is the result, worded as the result page words
        its places; while the race runs a bare number is a standing that
        can still change.
        """
        return d.header.status in DECIDED

    def advance(self) -> None:
        if self.page_count() > 1:
            self.page = (self.page + 1) % self.page_count()
            self.update()

    def paint(self, p: QPainter, area: QRectF) -> None:
        d: Standings = self.data
        u = self.u
        pages = self.page_count()
        page = self.page % pages
        per_page = page_rows(len(d.rows), self.page_most())
        rows = d.rows[page * per_page : (page + 1) * per_page]
        n = max(1, min(len(d.rows), per_page))
        bottom = area.bottom() - (32 * u if pages > 1 else 0)
        if any(r.entry.color for r in d.rows):
            self.team_table(p, area, d, rows, n, bottom, self.ordinals(d))
        else:
            self.rider_table(p, area, d, rows, n, bottom)

        if pages > 1:
            # Page dots, not a "1-8 of 16" footer: they say there is more
            # without asking anyone to read a line of small print.
            dot, gap = 16 * u, 14 * u
            x = area.right() - pages * dot - (pages - 1) * gap - 20 * u
            y = area.bottom() - dot - 6 * u
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(pages):
                p.setBrush(t.TEXT if i == page else t.RULE)
                p.drawEllipse(QRectF(x + i * (dot + gap), y, dot, dot))

        if d.sprint_result is not None:
            self.paint_overlay(p, area, d)

    def row_band(self, p: QPainter, area: QRectF, i: int, y: float, rh: float) -> None:
        """Every other row on a faint band, so a row reads across the page."""
        if i % 2:
            return
        u = self.u
        band = QRectF(area.x() - 20 * u, y + 3 * u, area.width() + 40 * u, rh - 6 * u)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 10))
        p.drawRoundedRect(band, 10 * u, 10 * u)

    def rider_table(
        self, p: QPainter, area: QRectF, d: Standings, rows: list, n: int, bottom: float
    ) -> None:
        u = self.u
        head_h = 44 * u
        top = area.y()
        rows_top = top + head_h + 8 * u
        # The feed leaves a status row off the board; a page given one
        # prints the status for a total and no figures, so a penalty on it
        # opens no column.
        penalized = any(r.penalty for r in d.rows if not r.status)
        entries = [r.entry for r in d.rows]
        fill = (bottom - rows_top) / max(n, RIDER_FILL_LEAST)
        # The entry takes nearly the whole row, so the bib plate keeps its
        # size in a dense table; the row bands carry the separation.
        inset = 0.05

        def layout(g: float, reserve: bool = False):
            rh = min(fill, RIDER_ROW_FULL * g)
            cols = rider_columns(area, g, 24 * u, penalized or reserve)
            rect = QRectF(cols.name_x, rows_top + rh * inset, cols.name_w, rh * (1 - 2 * inset))
            return rh, cols, rect, min(46 * g, rh * STANDINGS_NAME_SHARE)

        # The figures' unit: the page's for nine riders or more; for fewer,
        # as large as the rows allow while every name still fits whole, so
        # a small field's type and columns grow as one and no name gives
        # up its first name to the larger figures. The names are measured
        # beside a PENALTY column whether or not one stands, so the first
        # penalty given never steps the table down while it is read.
        g = u * max(1.0, fill / (RIDER_ROW_FULL * u))
        while g > u and not self.names_whole(entries, *layout(g, reserve=True)[2:]):
            g = max(u, g * 0.96)
        rh, cols, name_rect, name_size = layout(g)
        place_f = t.font(min(46 * g, rh * 0.7), t.BOLD, tabular=True)
        total_f = t.font(min(60 * g, rh * 0.84), t.HEAVY, tabular=True)
        pad = 24 * g
        right = area.right()
        (
            rank_w,
            name_x,
            name_w,
            sprints_x,
            sprints_w,
            laps_x,
            laps_w,
            penalty_x,
            penalty_w,
            total_x,
            total_w,
        ) = cols
        lab = t.label(u)
        # Room to the left for a heading wider than its column.
        reach = 120 * u

        t.text(p, QRectF(area.x(), top, rank_w, head_h), "#", lab, t.MUTED)
        t.text(p, QRectF(name_x, top, name_w, head_h), "RIDER", lab, t.MUTED)
        t.text(
            p,
            QRectF(sprints_x - reach, top, sprints_w - pad + reach, head_h),
            "SPRINT PTS",
            lab,
            t.MUTED,
            RIGHT,
        )
        t.text(p, QRectF(laps_x, top, laps_w - pad, head_h), "LAPS", lab, t.MUTED, RIGHT)
        if penalized:
            t.text(
                p,
                QRectF(penalty_x - reach, top, penalty_w - pad + reach, head_h),
                "PENALTY",
                lab,
                t.MUTED,
                RIGHT,
            )
        t.text(p, QRectF(total_x, top, total_w - 20 * u, head_h), "TOTAL", lab, t.TEXT, RIGHT)

        # The figures keep pace with the names: at sixteen rows a sprint
        # value set at half the row would be 26 px, under the board's minimum.
        num = t.font(min(48 * g, rh * 0.7), t.BOLD, tabular=True)
        self.team_fill = 0.0
        # Measured over every row, not the page's, as the rank and total
        # columns are, so the names hold still as the page turns.
        scale = self.entry_scale(entries, name_rect, name_size, True)
        for i, row in enumerate(rows):
            y = rows_top + i * rh
            self.row_band(p, area, i, y, rh)
            cell = QRectF(0, y, 0, rh)
            t.text(
                p,
                QRectF(area.x(), y, rank_w, rh),
                str(row.rank),
                place_f,
                # The leader in the accent, as "1st" is on the result page;
                # the rest in full ink, not the row's dimmest text.
                t.ACCENT if row.rank == 1 else t.TEXT,
            )
            self.entry_line(
                p,
                QRectF(name_x, y + rh * inset, name_w, rh * (1 - 2 * inset)),
                row.entry,
                name_size,
                two_line_names=True,
                scale=scale,
            )
            # The sprint points so far, a plain number: a "+" here is the
            # laps chip's language and would read as a lap. Zero stays
            # blank so the TV stays quiet until a rider scores.
            sprint_points = sum(v for v in row.sprints if v)
            if sprint_points and not row.status:
                t.text(
                    p,
                    cell.adjusted(sprints_x, 0, sprints_x + sprints_w - pad, 0),
                    str(sprint_points),
                    num,
                    t.TEXT,
                    RIGHT,
                )
            if row.laps and not row.status:
                # The laps alone: the points they earn are the venue's
                # known value and are already in the total.
                t.text(
                    p,
                    cell.adjusted(laps_x, 0, laps_x + laps_w - pad, 0),
                    lap_text(row.laps),
                    num,
                    t.GAIN if row.laps > 0 else t.LOSS,
                    RIGHT,
                )
            if penalized and row.penalty and not row.status:
                # Written as a lap lost is, in the loss color: points taken.
                t.text(
                    p,
                    cell.adjusted(penalty_x, 0, penalty_x + penalty_w - pad, 0),
                    lap_text(row.penalty),
                    num,
                    t.LOSS if row.penalty < 0 else t.GAIN,
                    RIGHT,
                )
            shown_total = row.status or total_text(row.total)
            t.text(
                p, cell.adjusted(total_x, 0, right - 20 * u, 0), shown_total, total_f, t.TEXT, RIGHT
            )

    def team_table(
        self,
        p: QPainter,
        area: QRectF,
        d: Standings,
        rows: list,
        n: int,
        bottom: float,
        ordinals: bool = False,
    ) -> None:
        """The madison page while the race runs: place, then one bar per team carrying its figures.

        The bar runs from the place to the page's edge and LAPS, PENALTY
        and TOTAL sit inside its right end, so a rider finds the color and
        reads the team's figures on it without tracking across bare
        background. LAPS and PENALTY take the bar's ink: a lap's green or
        red on a red or green bar would vanish, so the sign carries the
        gain or loss. The total sits dark on a plate (``t.figure_plate``),
        and a status row keeps its word in the bar's ink with no plate, so
        it reads apart from a scored row. The place and the total are the
        row's largest type.
        """
        u = self.u
        head_h = 44 * u
        top = area.y()
        rows_top = top + head_h + 8 * u
        rh = (bottom - rows_top) / max(n, TEAM_FILL_LEAST)
        inset = 0.05
        bh = rh * (1 - 2 * inset)
        lab = t.label(u)
        # A PENALTY column opens only while a placed row carries one, as on
        # the rider table, and a status row opens none.
        penalized = any(r.penalty for r in d.rows if not r.status)

        def widest(strings: list[str], f: QFont) -> float:
            return max((t.text_width(s, f) for s in strings if s), default=0.0)

        # Every column is measured over every row, not the page's, so the
        # bars and the figures hold still as the page turns.
        def place(rank: int) -> str:
            return ordinal(rank) if ordinals else str(rank)

        places = [place(r.rank) for r in d.rows]
        decided = [ordinal(r.rank) for r in d.rows]
        names = [r.entry.team or "" for r in d.rows]
        totals = [total_text(r.total) for r in d.rows if not r.status]
        gap = FIGURE_GAP * u

        def columns(big_px: float, reserve: bool = False) -> dict:
            """The fonts and right edges of the place and the figures at ``big_px``.

            ``reserve`` lays the figures out as a race may come to need
            them, with a lap, a penalty, and its places worded as ordinals
            once decided, for deciding the page's size.
            """
            # The plate's margin is the bar's at full size and gives way
            # with the figures, as the plate itself does.
            margin = bh * PLATE_MARGIN * big_px / (rh * TEAM_FIGURE_SHARE)
            place_f = t.font(big_px, t.HEAVY, tabular=True)
            total_f = t.font(big_px, t.HEAVY, tabular=True)
            # The laps and penalty keep pace with the figures, never under
            # the floor.
            laps_px = big_px * TEAM_LAPS_SHARE / TEAM_FIGURE_SHARE
            num = t.font(max(min(48 * u, rh * 0.7), laps_px), t.BOLD, tabular=True)
            # The place matches the total until its column would pass
            # TEAM_PLACE_SHARE of the page: a decided two-team field sets
            # "2nd" at a row's height, which would take the bars' room.
            most = area.width() * TEAM_PLACE_SHARE - 32 * u
            shown = [*places, *decided] if reserve else places
            if widest(shown, place_f) > most:
                place_f = t.font(big_px * most / widest(shown, place_f), t.HEAVY, tabular=True)
            rank_w = max(80 * u, widest(shown, place_f) + 32 * u)
            # A column is as wide as its heading or its widest figure, so
            # each heading sits over its figures, right edges together.
            plate_col = max(widest([*totals, *PLATE_SAMPLES], total_f), t.text_width("TOTAL", lab))
            # The feed leaves a status row off the board; a page given one
            # keeps the word clear of the figures beside it.
            total_col = max(plate_col, widest([r.status for r in d.rows], total_f))
            laps_col = max(
                widest(
                    [
                        *(lap_text(r.laps) for r in d.rows if not r.status),
                        *(LAP_SAMPLES if reserve else ()),
                    ],
                    num,
                ),
                t.text_width("LAPS", lab),
            )
            pen_col = max(
                widest(
                    [
                        *(lap_text(r.penalty) for r in d.rows if not r.status),
                        *(PENALTY_SAMPLES if reserve else ()),
                    ],
                    num,
                ),
                t.text_width("PENALTY", lab),
            )
            bar_x = area.x() + rank_w
            pad = big_px * PLATE_PAD
            total_r = area.right() - margin - pad
            # One width for every plate, so they stand as one column with
            # the same air on both sides of its widest figure.
            plate_l = total_r - plate_col - pad
            pen_r = min(plate_l, total_r - total_col) - gap
            laps_r = pen_r - pen_col - gap if penalized or reserve else pen_r
            return {
                "place_f": place_f,
                "total_f": total_f,
                "num": num,
                "rank_w": rank_w,
                "bar_x": bar_x,
                "total_col": total_col,
                "laps_col": laps_col,
                "pen_col": pen_col,
                "total_r": total_r,
                "plate_l": plate_l,
                "pen_r": pen_r,
                "laps_r": laps_r,
                "figures_x": laps_r - laps_col,
                "margin": margin,
            }

        # The team name near the figures' size: with no riders on the row
        # the bar is the row, and its name is read with the place and the
        # total. ``team_px`` holds it inside the bar's height.
        name_cap = self.team_px(rh * TEAM_NAME_SHARE, rh * TEAM_NAME_SHARE, bh)

        def name_px(cols: dict) -> float:
            """The largest name size up to ``name_cap`` at which the widest name fits left of the figures."""
            room = cols["figures_x"] - 24 * u - cols["bar_x"]
            wide = widest(names, t.font(name_cap, t.BOLD))
            if not wide:
                return name_cap
            need = wide + 2 * name_cap * t.TEAM_PAD
            if need <= room:
                return name_cap
            px = name_cap * max(0.0, room) / need
            # Text width is not exactly linear in pixel size (hinting).
            while px > 1 and widest(names, t.font(px, t.BOLD)) + 2 * px * t.TEAM_PAD > room:
                px -= 1
            return max(px, 0.0)

        big_px = rh * TEAM_FIGURE_SHARE
        least_big = min(big_px, TEAM_FIGURE_LEAST * u)
        least_name = min(name_cap, TEAM_NAME_LEAST * u)
        # The size is decided as though a lap and a penalty stood, and the
        # names' size with it, so neither moves when the race gets one.
        sizing = columns(big_px, reserve=True)

        def short(cols: dict) -> bool:
            # The names want more room, or the figures would start left
            # of the bar, over the place column.
            return name_px(cols) < least_name or cols["figures_x"] < cols["bar_x"] + 24 * u

        while short(sizing) and big_px > least_big:
            big_px = max(least_big, big_px * 0.96)
            sizing = columns(big_px, reserve=True)
        name_f = t.font(max(name_px(sizing), t.MIN_PX * u), t.BOLD)
        cols = columns(big_px)
        place_f, total_f, num = cols["place_f"], cols["total_f"], cols["num"]
        rank_w, bar_x, bar_r = cols["rank_w"], cols["bar_x"], area.right()
        total_col, laps_col, pen_col = cols["total_col"], cols["laps_col"], cols["pen_col"]
        total_r, plate_l, pen_r, laps_r = (
            cols["total_r"],
            cols["plate_l"],
            cols["pen_r"],
            cols["laps_r"],
        )
        figures_x = cols["figures_x"]
        # A plate keeps to its figures when they gave way to the names, so
        # a bar taller than its figures does not hold a tall, narrow plate
        # with a heavy edge.
        give = big_px / (rh * TEAM_FIGURE_SHARE)
        margin = cols["margin"]
        plate_h = (bh - 2 * bh * PLATE_MARGIN) * give
        zone = name_zone(QRectF(bar_x, 0, bar_r - bar_x, bh), names, name_f, figures_x, u)

        reach = 200 * u
        t.text(p, QRectF(area.x(), top, rank_w, head_h), "#", lab, t.MUTED)
        t.text(p, QRectF(bar_x, top, reach, head_h), "TEAM", lab, t.MUTED)
        t.text(p, QRectF(laps_r - reach, top, reach, head_h), "LAPS", lab, t.MUTED, RIGHT)
        if penalized:
            t.text(p, QRectF(pen_r - reach, top, reach, head_h), "PENALTY", lab, t.MUTED, RIGHT)
        t.text(p, QRectF(total_r - reach, top, reach, head_h), "TOTAL", lab, t.TEXT, RIGHT)

        for i, row in enumerate(rows):
            y = rows_top + i * rh
            self.row_band(p, area, i, y, rh)
            # The leader in the accent, running or decided, as the winner
            # alone is on the podium page.
            top = t.ACCENT if row.rank == 1 else t.TEXT
            t.text(p, QRectF(area.x(), y, rank_w, rh), place(row.rank), place_f, top)
            e = row.entry
            bar = QRectF(bar_x, y + rh * inset, bar_r - bar_x, bh)
            t.team_block(p, bar, e.color, "", name_f)
            name_rect = QRectF(zone.x(), bar.y(), zone.width(), bh)
            block_name(p, name_rect, e.color, e.team or "", name_f, t.MIN_PX * u)
            ink = t.team_ink(QColor(e.color))
            # A status row shows its status and no figures, laps included.
            if row.laps and not row.status:
                # The laps alone: the points they earn are in the total.
                lap = QRectF(laps_r - laps_col, bar.y(), laps_col, bh)
                figure(p, lap, lap_text(row.laps), num, ink, RIGHT)
            if penalized and row.penalty and not row.status:
                pen = QRectF(pen_r - pen_col, bar.y(), pen_col, bh)
                figure(p, pen, lap_text(row.penalty), num, ink, RIGHT)
            if not row.status:
                plate_y = bar.y() + (bh - plate_h) / 2
                plate = QRectF(plate_l, plate_y, bar_r - margin - plate_l, plate_h)
                t.figure_plate(p, plate, bh * give)
            total = QRectF(total_r - total_col, bar.y(), total_col, bh)
            total_ink = ink if row.status else t.PLATE_TEXT
            figure(p, total, row.status or total_text(row.total), total_f, total_ink, RIGHT)

    def paint_overlay(self, p: QPainter, area: QRectF, d: Standings) -> None:
        """The sprint's result over the standings: place, who, and the points one gap after.

        The card is as wide as its content and centered on the board, so
        each "+5" sits beside its team block or rider, where the eye
        already is, rather than across an empty row; the blocks share the
        widest name's width so the points stand in one right-aligned
        column.
        """
        res = d.sprint_result
        p.fillRect(self.rect(), QColor(5, 6, 9, SPRINT_VEIL))
        # A team is its color and name on a three-second card; its pair
        # of names would be cut to fragments there and add nothing.
        placings = [
            (pl, replace(e, names=[]) if e.color else e, pts) for pl, e, pts in res.placings
        ]
        # The page's unit is scaled for the card alone, so every helper the
        # card calls (plates, name fitting) measures as it draws; the team
        # blocks are sized for the table behind at the page's own unit.
        scale = sprint_card_scale(len(placings), area.height(), self.u)
        # The page's unit follows its height, so on a board narrower than
        # 16:9 (a window of any shape) a card of long names can be wider
        # than the page: it takes a smaller unit until it fits with air at
        # its sides.
        room = self.width() - 2 * SPRINT_CARD_AIR * self.u
        for _ in range(8):
            w = self._card_at(p, area, placings, res, scale, draw=False)
            if w <= room:
                break
            scale *= min(0.995, room / w)
        self.card_scale = scale
        self._card_at(p, area, placings, res, scale)

    def _card_at(self, p, area, placings, res, scale: float, draw: bool = True) -> float:
        """``_paint_card`` in the card's unit, ``scale`` times the page's; the card's width."""
        page_u, self.u = self.u, self.u * scale
        page_team_w, self.team_w = self.team_w, self.team_w * scale
        try:
            return self._paint_card(p, area, placings, res, draw)
        finally:
            self.u, self.team_w = page_u, page_team_w

    def _paint_card(self, p: QPainter, area: QRectF, placings, res, draw: bool = True) -> float:
        u = self.u
        rh = SPRINT_ROW_H * u
        size = 46 * u
        side, place_w, gap = 48 * u, 120 * u, SPRINT_GAP * u
        title = sprint_title(res)
        title_f = t.font(54 * u, t.HEAVY)
        pts_f = t.font(60 * u, t.HEAVY, tabular=True)
        figs = [f"+{pts}" for _, _, pts in placings]
        pts_w = max((t.text_width(s, pts_f) for s in figs), default=0.0)
        # The card grows to SPRINT_CARD_MOST at most: wide enough that a
        # long name stays at a size the stands read in the few seconds
        # the card is up.
        most = SPRINT_CARD_MOST * u - 2 * side - place_w - gap - pts_w
        room = QRectF(0, 0, most, rh - 16 * u)
        entries = [e for _, e, _ in placings]
        # The blocks keep to the widest name: a bar the card's width would
        # be a second row band, not a label.
        self.team_fill = 0.0
        fit = self.entry_scale(entries, room, size, False)
        if any(e.color for e in entries):
            entry_w = self.team_w
        else:
            # Rounded up to the pixel: the column is the sum of a name's
            # parts, and float sums can land a hair under the name they were
            # measured from, which would initial the widest name.
            entry_w = math.ceil(
                max((self.entry_width(room, e, size, fit) for e in entries), default=0.0)
            )
        w = max(2 * side + place_w + entry_w + gap + pts_w, 2 * side + t.text_width(title, title_f))
        if not draw:
            return w
        h = SPRINT_HEAD_H * u + len(placings) * rh + SPRINT_FOOT_H * u
        card = QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)
        p.setPen(QPen(t.ACCENT, 3 * u))
        p.setBrush(t.BAR)
        p.drawRoundedRect(card, 20 * u, 20 * u)
        t.text(
            p,
            QRectF(card.x() + side, card.y() + 30 * u, w - 2 * side, 70 * u),
            title,
            title_f,
            t.ACCENT,
        )
        # A rule under the title: the card reads as a card over the
        # table, not as a brighter part of it.
        p.setPen(QPen(t.ACCENT, 2 * u))
        rule_y = card.y() + 108 * u
        p.drawLine(QPointF(card.x() + side, rule_y), QPointF(card.right() - side, rule_y))
        x = card.x() + side
        y = card.y() + 124 * u
        place_f = t.font(40 * u, t.BOLD, tabular=True)
        for (place, entry, _pts), fig in zip(placings, figs, strict=True):
            t.text(p, QRectF(x, y, 110 * u, rh), ordinal(place), place_f, t.MUTED)
            entry_rect = QRectF(x + place_w, y + 8 * u, entry_w, rh - 16 * u)
            self.entry_line(p, entry_rect, entry, size, two_line_names=False, scale=fit)
            figs_rect = QRectF(entry_rect.right() + gap, y, pts_w, rh)
            t.text(p, figs_rect, fig, pts_f, t.TEXT, RIGHT)
            y += rh
        return w

    def entry_width(self, rect: QRectF, entry: Entry, size: float, scale: float) -> float:
        """How much of ``rect`` a rider's plate and name take, the name as ``fit_name`` sets it."""
        texts = self.entry_texts(rect, entry, size, False, scale)
        end = rect.x()
        if self.show_bibs and entry.bibs:
            end += t.plate_width(self.plate_height(rect.height()))
        for r, s, f, _kind in texts:
            if s:
                shown = t.fit_name(s, r.width(), f)
                end = max(end, r.x() + min(r.width(), t.text_width(shown, f)))
        return end - rect.x()


# The closest the result's rows below the podium are set: a 72 px row
# keeps the bib plate's digits at the design's floor.
REST_PITCH = 72
# How the result makes room for a long field, in order: a smaller podium
# first, then a third column below it. Sixteen riders (a full field at
# 166 m) take the smaller podium; 24 (a 250 m track) the third column.
FINISH_PLANS = ((136, 2), (112, 2), (112, 3))
# The least result whose rows share the page: a smaller one is set as
# this many places would be, so a podium of three is not one huge band.
FINISH_FILL_LEAST = 5


class FinishPage(Page):
    """The result of a race placed by its finish: a podium of three, the rest in columns.

    A points race never comes here: its standings table stays up to the
    end and reads as the result once stamped (``StandingsPage.ordinals``).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The page's growth over its base sizes (``growth``): every size
        # on the page is its base times this, so the podium and the rows
        # below it keep their proportions as a small result fills the page.
        self.g = 1.0
        # The last growth and what it was worked out for, as on the start list.
        self._growth: tuple[tuple, float] | None = None

    def paint(self, p: QPainter, area: QRectF) -> None:
        d: Finish = self.data
        u = self.u
        podium = d.placings[:3]
        rest = d.placings[3:]
        y = area.y()
        # Below the podium every row keeps REST_PITCH, so the plates (what
        # the stands match to the track) stay readable. A long result takes
        # room from the podium, then opens a third column; only past that
        # (more than 27 places) does it leave off its last places.
        for big, cols in FINISH_PLANS:
            big_h = big * u
            room = area.bottom() - y - 3 * big_h - 30 * u
            per_col = max(1, int(room // (REST_PITCH * u)))
            if math.ceil(len(rest) / cols) <= per_col:
                break
        rest = rest[: cols * per_col]
        key = (area.width(), area.height(), u, self.rider_label, d)
        if self._growth is None or self._growth[0] != key:
            g = self.growth(area, d, podium, rest, big, cols)
            self._growth = ((*key[:-1], copy.deepcopy(d)), g)
        self.g = g = self._growth[1]
        big_h = big * u * g
        name_x = area.x() + 230 * u * g
        podium_rect = QRectF(name_x, y, area.right() - name_x, big_h - 28 * u * g)
        self.team_fill = TEAM_FILL
        podium_scale = self.entry_scale(
            [pl.entry for pl in podium],
            podium_rect,
            64 * u * g,
            False,
            laps=[pl.laps for pl in podium],
        )
        for pl in podium:
            row = QRectF(area.x() - 20 * u, y, area.width() + 40 * u, big_h - 14 * u * g)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.CARD)
            p.drawRoundedRect(row, 14 * u, 14 * u)
            color = t.ACCENT if pl.place == 1 else t.TEXT
            t.text(
                p,
                QRectF(area.x() + 8 * u, y, 200 * u * g, big_h - 14 * u * g),
                ordinal(pl.place),
                t.font(72 * u * g, t.HEAVY, tabular=True),
                color,
            )
            self.entry_line(
                p,
                # The entry fills its band less a margin, so the podium's plates
                # are a size with the names beside them.
                QRectF(name_x, y + 7 * u * g, area.right() - name_x, big_h - 28 * u * g),
                pl.entry,
                64 * u * g,
                two_line_names=False,
                scale=podium_scale,
                laps=pl.laps,
            )
            y += big_h
        if not rest:
            return
        y += 30 * u * g
        per_col = math.ceil(len(rest) / cols)
        gap = (56 if cols == 2 else 40) * u
        col_w = (area.width() - gap * (cols - 1)) / cols
        rh = min(84 * u * g, (area.bottom() - y) / per_col)
        rest = self.blocks_alone(rest)
        # Blocks alone in two columns: at their names, so the lap chips
        # sit beside them rather than at the far end of a bar.
        self.team_fill = 0.0
        scale = self.entry_scale(
            [pl.entry for pl in rest],
            self._small_name_rect(QRectF(0, y, col_w, rh)),
            38 * u * g,
            False,
            laps=[pl.laps for pl in rest],
        )
        for i, pl in enumerate(rest):
            c, r = divmod(i, per_col)
            x = area.x() + c * (col_w + gap)
            ry = y + r * rh
            self.small_placing(p, QRectF(x, ry, col_w, rh), pl, scale)

    def growth(
        self,
        area: QRectF,
        d: Finish,
        podium: list[Placing],
        rest: list[Placing],
        big: float,
        cols: int,
    ) -> float:
        """How much larger than its base sizes a small result is set, 1 for a full one.

        The podium and the rows below it share the page as a result of
        FINISH_FILL_LEAST places would, and grow as one while every name
        on the page fits whole at its size and the rows below the podium
        are no shorter than at the base sizes; a result that needs the
        smaller podium or a third column is set at its base sizes. Only a
        decided result grows: a Win-and-Out shows its places here as the
        bells decide them, and sized by the places so far it would step
        down with every bell.
        """
        u = self.u
        if (big, cols) != FINISH_PLANS[0] or d.header.status not in DECIDED:
            return 1.0
        rows = math.ceil(max(len(rest), FINISH_FILL_LEAST - 3) / cols)
        base = (3 * big + 30 + rows * REST_PITCH) * u
        g = area.height() / base
        gap = 56 * u
        col_w = (area.width() - gap * (cols - 1)) / cols
        alone = self.blocks_alone(rest)
        per_col = max(1, math.ceil(len(rest) / cols))

        def rest_h(g: float) -> float:
            below = area.bottom() - area.y() - (3 * big + 30) * u * g
            return min(84 * u * g, below / per_col)

        while g > 1.0:
            # The name's own rect, less its margin, as well as the band.
            if alone and rest_h(g) - 12 * u * g < rest_h(1.0) - 12 * u:
                g = max(1.0, g * 0.96)
                continue
            name_x = area.x() + 230 * u * g
            podium_rect = QRectF(name_x, 0, area.right() - name_x, (big - 28) * u * g)
            self.team_fill = TEAM_FILL
            whole = (
                self.entry_scale(
                    [pl.entry for pl in podium],
                    podium_rect,
                    64 * u * g,
                    False,
                    laps=[pl.laps for pl in podium],
                )
                >= 1.0
            )
            if whole and alone:
                self.g = g
                self.team_fill = 0.0
                rest_rect = self._small_name_rect(QRectF(0, 0, col_w, rest_h(g)))
                whole = (
                    self.entry_scale(
                        [pl.entry for pl in alone],
                        rest_rect,
                        38 * u * g,
                        False,
                        laps=[pl.laps for pl in alone],
                    )
                    >= 1.0
                )
            if whole:
                return g
            g = max(1.0, g * 0.96)
        return 1.0

    def blocks_alone(self, rest: list[Placing]) -> list[Placing]:
        # Teams below the podium are their color and name: the pair, at
        # this size, would be cut to fragments.
        return [
            replace(pl, entry=replace(pl.entry, names=[])) if pl.entry.color else pl for pl in rest
        ]

    def _small_name_rect(self, r: QRectF) -> QRectF:
        u = self.u * self.g
        return QRectF(r.x() + 120 * u, r.y() + 6 * u, r.width() - 120 * u, r.height() - 12 * u)

    def small_placing(self, p: QPainter, r: QRectF, pl: Placing, scale: float) -> None:
        u = self.u * self.g
        t.text(
            p,
            QRectF(r.x(), r.y(), 110 * u, r.height()),
            ordinal(pl.place),
            t.font(38 * u, t.BOLD, tabular=True),
            t.MUTED,
        )
        self.entry_line(
            p,
            self._small_name_rect(r),
            pl.entry,
            38 * u,
            two_line_names=False,
            scale=scale,
            laps=pl.laps,
        )


# The closest the Between page sets two lines of names: the pitch of a
# ten-rider list, where a 40 px name and its plate still have air.
ROSTER_PITCH = 58


class BetweenPage(Page):
    def paint(self, p: QPainter, area: QRectF) -> None:
        d: Between = self.data
        u = self.u
        gap = 80 * u
        # With no result yet (the first race of the night) there is no
        # Last result column to keep: an empty half of the screen reads as
        # broken, so the next race takes the whole width.
        has_last = bool(d.last_title or d.last_placings)
        left_w = area.width() * 0.56 if has_last else area.width()
        left = QRectF(area.x(), area.y(), left_w, area.height())
        right = QRectF(left.right() + gap, area.y(), area.width() - left_w - gap, area.height())

        self.section_label(p, left.x(), left.y(), "Up next", t.ACCENT)
        y = left.y() + 50 * u
        t.text(
            p,
            QRectF(left.x(), y, left.width(), 110 * u),
            d.next_title,
            t.font(92 * u, t.HEAVY),
            t.TEXT,
            shrink=True,
        )
        y += 124 * u
        x = left.x()
        # The group and the kind of race at the board's minimum, like the
        # top bar's: sized from a 52 px chip the type would be 29 px.
        chip_h = lap_chip_height(u)
        if d.next_group:
            x += t.accent_chip(p, x, y, chip_h, d.next_group) + 24 * u
        if d.next_detail:
            t.text(
                p,
                QRectF(x, y, left.right() - x, chip_h),
                d.next_detail,
                t.font(t.MIN_PX * u, t.SEMI),
                t.MUTED,
            )
        y += 100 * u
        n = len(d.next_roster)
        if n:
            # Rows never closer than ROSTER_PITCH: a big field takes more
            # columns, and what still does not fit is left off rather than
            # drawn over itself (design section 10: drop, never shrink).
            col_gap = 48 * u
            avail = left.bottom() - y
            per_col = max(1, int(avail // (ROSTER_PITCH * u)))
            most_cols = 3 if not has_last else 2
            # Enough columns for full-pitch rows when the width allows,
            # since the plate grows with the row.
            roomy = max(1, int(avail // (96 * u)))
            cols = min(most_cols, max(-(-n // per_col), -(-n // roomy)))

            def grid(cols: int) -> tuple[int, float, float]:
                rows = min(per_col, -(-n // cols))
                rh = min(96 * u, avail / rows)
                return rows, rh, (left.width() - (cols - 1) * col_gap) / cols

            if any(e.color for e in d.next_roster):
                # A team list takes fewer, wider columns when a column
                # would cut a team name: eight long names in two columns
                # would cut "Hamtramck Velo Collective" with room below to spare.
                best = (-1, cols)
                for c in range(cols, 0, -1):
                    rows, rh, col_w = grid(c)
                    if rows * c < min(n, per_col * cols):
                        break
                    rect = QRectF(0, 0, col_w, rh - 10 * u)
                    best = max(best, (self.team_fit(d.next_roster, rect, 40 * u, False), c))
                cols = best[1]
            rows, rh, col_w = grid(cols)
            shown = d.next_roster[: rows * cols]
            first = QRectF(left.x(), y, col_w, rh - 10 * u)
            # Teams in narrow columns are their color and name, as below
            # the podium: "L. Ferreira ..." tells the stands nothing. The
            # list's layout leaves the riders off when they would be cut
            # (``team_layout``), and the block then has the column.
            scale = self.entry_scale(shown, first, 40 * u, False)
            for i, e in enumerate(shown):
                col, row = divmod(i, rows)
                x = left.x() + col * (col_w + col_gap)
                r = QRectF(x, y + row * rh, col_w, rh - 10 * u)
                self.entry_line(p, r, e, 40 * u, two_line_names=False, scale=scale)

        if not has_last:
            return
        p.setPen(QPen(t.RULE, 2 * u))
        p.drawLine(
            int(right.x() - gap / 2), int(area.y()), int(right.x() - gap / 2), int(area.bottom())
        )

        self.section_label(p, right.x(), right.y(), "Last result")
        y = right.y() + 50 * u
        t.text(
            p,
            QRectF(right.x(), y, right.width(), 80 * u),
            d.last_title,
            t.font(56 * u, t.BOLD),
            t.TEXT,
            shrink=True,
        )
        y += 88 * u
        if d.last_group:
            t.chip(p, right.x(), y, lap_chip_height(u), d.last_group, t.RULE, t.TEXT)
        y += 96 * u
        # The top of the last result, as many places as fit at a readable
        # pitch; the rest of it is on the sheet.
        fit = max(1, int((right.bottom() - y) // (ROSTER_PITCH * u)))
        placings = d.last_placings[:fit]
        n = len(placings)
        if n:
            rh = min(88 * u, (right.bottom() - y) / n)
            # Rows take most of their pitch, so a plate in a tight list
            # still shows its digits rather than a white sliver.
            vpad = rh * 0.08
            first = QRectF(right.x() + 106 * u, y + vpad, right.width() - 106 * u, rh - 2 * vpad)
            entries = [pl.entry for pl in placings]
            scale = self.entry_scale(entries, first, 36 * u, False)
            for i, pl in enumerate(placings):
                r = QRectF(right.x(), y + i * rh, right.width(), rh)
                t.text(
                    p,
                    QRectF(r.x(), r.y(), 100 * u, rh),
                    ordinal(pl.place),
                    t.font(36 * u, t.BOLD, tabular=True),
                    t.ACCENT if pl.place == 1 else t.MUTED,
                )
                self.entry_line(
                    p,
                    QRectF(r.x() + 106 * u, r.y() + vpad, r.width() - 106 * u, rh - 2 * vpad),
                    pl.entry,
                    36 * u,
                    two_line_names=False,
                    scale=scale,
                )


PAGES: dict[str, type[Page]] = {
    "pre_race": PreRacePage,
    "elimination": EliminationPage,
    "sprint_points": StandingsPage,
    "madison": StandingsPage,
    "finish": FinishPage,
    "between": BetweenPage,
}
