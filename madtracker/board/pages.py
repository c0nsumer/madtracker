"""The scoreboard layouts, one painted widget each.

Painting by hand rather than composing labels keeps every size a pure
function of the board height, which is what makes one layout serve a
1080p and a 4K TV. Each page draws only from its payload; nothing here
knows how standings are computed.
"""

import copy
import math
from dataclasses import dataclass, field, replace
from typing import NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from madtracker.board import rotation, scorebug, team_rows
from madtracker.board import theme as t
from madtracker.board.motion import Clock, Ticker, ease_back, ease_in, ease_out, phase
from madtracker.board.payloads import (
    Between,
    Elimination,
    Entry,
    Finish,
    Placing,
    PreRace,
    StandingRow,
    Standings,
    lap_text,
    lap_words,
    ordinal,
    total_text,
)
from madtracker.board.scorebug import Frame, Key, Play, ScoreQueue, Step
from madtracker.board.texture import Texture

LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
CENTER = Qt.AlignmentFlag.AlignCenter

# What a team table's total column is sized for from the first lap, so it
# never widens as the race goes on: three figures (the figures are
# tabular, so 888 is as wide as any) and a negative two.
TOTAL_SAMPLES = ("888", total_text(-88))
# What a team page's size is decided for, beside the race's own figures: a
# lap and a penalty, so the first lap gained or penalty given never steps
# the totals down partway through a race.
LAP_SAMPLES = ("+8L", f"{lap_text(-8)}L")
PENALTY_SAMPLES = (lap_text(-88),)


def team_laps_text(n: int) -> str:
    """The Madison table's laps, "+1L" or "−1L": it has no headings, so the L
    keeps a lap apart from a penalty, which stays a bare "−5"."""
    return f"{lap_text(n)}L" if n else ""


# Between two figure columns on a team row.
FIGURE_GAP = 40


def lap_chip_height(u: float) -> float:
    """A lap chip whose type is the board's floor, so it reads from the stands."""
    return t.MIN_PX * u / t.CHIP_TYPE


def band_gap(pitch: float, u: float) -> float:
    """The space between two rows of a list ``pitch`` apart.

    It gives way in a dense list, so the plate keeps its size rather than
    the air around it.
    """
    return min(12 * u, pitch * 0.12)


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
        # The canvas sets the time source; None leaves the page at rest.
        self.clock: Clock | None = None
        self.rider_label = "bibs_names"
        # The venue's texture, shared by every page of one board.
        self.texture = Texture(None)
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
        # The page the board turns from while ``set_data`` runs, so a page
        # can turn in from what was on screen; None at any other time.
        self.outgoing: Page | None = None
        # The page paints its whole rect, so Qt can skip clearing it.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    @property
    def show_bibs(self) -> bool:
        return self.rider_label != "names"

    @property
    def bibs_only(self) -> bool:
        return self.rider_label == "bibs"

    def set_data(self, data, prev=None) -> None:
        """Show ``data``; ``prev`` is the payload the board last showed for the same race, if any."""
        self.data = data
        self.update()

    def stop_motion(self) -> None:
        """Drop any motion still to play, as the board turns to another page."""

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
        x = rect.x() + t.plate_width(self.plate_height(h)) + PLATE_NAME_GAP * u
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

    def line_start(self, line: QRectF, f: QFont, card: QRectF | None) -> float:
        """Where a line of ``f`` set in ``line`` may start: on ``card``, clear of its bar.

        The bar leans nearest the line at its capitals' top
        (``team_rows.bar_clear``).
        """
        if card is None:
            return line.left()
        return max(line.left(), team_rows.bar_clear(card, caps_top(line, f), self.u))

    def line_room(self, line: QRectF, f: QFont, card: QRectF | None) -> float:
        """How wide a line of ``f`` set in ``line`` may be: on ``card``, what its bar leaves."""
        return max(0.0, line.right() - self.line_start(line, f, card))

    def card_axis(self, card: QRectF, top: float, right: float) -> float:
        """The axis a card's content is centered on: the middle of what the card's bar leaves.

        ``top`` is the content's highest point at its largest, where the
        bar leans nearest it, and ``right`` its right limit; the content
        reads centered in the card's open room rather than under the bar.
        """
        return (team_rows.bar_clear(card, top, self.u) + right) / 2

    def card_line(
        self,
        p: QPainter,
        line: QRectF,
        s: str,
        f: QFont,
        color: QColor,
        card: QRectF | None = None,
        axis: float | None = None,
    ) -> None:
        """One line centered in ``line``; on ``card``, centered on ``axis`` and clear of its bar.

        A line too wide to center there keeps to the bar's clearance on
        the left and ``line``'s right edge, so it has the whole room the
        bar leaves rather than a centered share of it.
        """
        if card is None:
            t.text(p, line, s, f, color, CENTER)
            return
        start = self.line_start(line, f, card)
        w = t.text_width(s, f)
        x = max(start, min((line.center().x() if axis is None else axis) - w / 2, line.right() - w))
        t.text(p, QRectF(x, line.y(), line.right() - x, line.height()), s, f, color, LEFT)

    def block_scale(
        self, names: list[str], rect: QRectF, px: float, card: QRectF | None = None
    ) -> float:
        """One scale for a grid of ``name_block`` cards.

        Each name may use one line or two (first name over the rest), so
        its own best scale is the better of the two; the grid takes the
        smallest of those so every card matches. On ``card`` each line
        has the room the bar leaves it (``line_room``).
        """
        f = t.font(px, t.BOLD)

        def rooms(g: QFont) -> tuple[float, list[float]]:
            one = self.line_room(t.stacked_lines(rect, g, 1)[0], g, card)
            return one, [self.line_room(r, g, card) for r in t.stacked_lines(rect, g, 2)]

        one_w, two_w = rooms(f)
        scale = 1.0
        for name in names:
            one = t.fit_scale([(name, one_w, f)], floor=0.0)
            first, sep, rest = name.strip().partition(" ")
            two = (
                t.fit_scale([(first, two_w[0], f), (rest, two_w[1], f)], floor=0.0) if sep else 0.0
            )
            scale = min(scale, max(one, two))
        scale = max(t.NAME_FLOOR, scale)

        def fits(scale: float) -> bool:
            g = t.scaled(f, scale)
            one_w, two_w = rooms(g)
            for name in names:
                first, sep, rest = name.strip().partition(" ")
                if t.text_width(name.strip(), g) <= one_w:
                    continue
                if sep and t.text_width(first, g) <= two_w[0] and t.text_width(rest, g) <= two_w[1]:
                    continue
                return False
            return True

        # As in entry_scale: hinting makes widths not quite linear, and a
        # name one pixel too wide would lose its last name to an ellipsis.
        while scale > t.NAME_FLOOR and not fits(scale):
            scale = max(t.NAME_FLOOR, scale - 1 / max(px, 1))
        return scale

    def name_block(
        self,
        p: QPainter,
        rect: QRectF,
        name: str,
        px: float,
        color=t.TEXT,
        scale: float = 1.0,
        card: QRectF | None = None,
        axis: float | None = None,
    ) -> None:
        """A name centered in ``rect``, on two lines when one would not fit.

        Used where a card shows the name alone: "Jenna Whitfield" reads
        better as two big lines than as one line squeezed to fit. The
        first word goes on top so a multi-word last name stays together.
        Two lines are set as one block (``t.stacked_lines``) so they read
        as one name, centered in the card. On a rider row's ``card`` the
        lines center on ``axis`` and each keeps clear of the bar
        (``card_line``).
        """
        f = t.scaled(t.font(px, t.BOLD), scale)
        name = name.strip()
        first, sep, rest = name.partition(" ")
        rest = rest.strip()
        w = self.line_room(t.stacked_lines(rect, f, 1)[0], f, card)
        w1, w2 = (self.line_room(r, f, card) for r in t.stacked_lines(rect, f, 2))

        def fits(s: str, width: float = w) -> bool:
            return t.text_width(s, f) <= width

        # The steps run in the order of ``fit_name``: the first name gives
        # way to its initial before the last name is ever cut.
        short = t.initialed(name)
        if fits(name) or not short:
            lines = [t.fit_name(name, w, f)]
        elif fits(first, w1) and fits(rest, w2):
            lines = [first, rest]
        elif fits(short):
            lines = [short]
        else:
            # The initial keeps a line of its own so the last name gets
            # the whole width before it is elided.
            lines = [f"{first[0]}.", t.elide(rest, w2, f)]
        for r, s in zip(t.stacked_lines(rect, f, len(lines)), lines, strict=True):
            self.card_line(p, r, s, f, color, card, axis)

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

    def bar_lead(self, band_h: float, h: float, size: float, teams: bool = False) -> float:
        """How far a rider row's plate, or its name without one, stands from the row's left end.

        Past the bar and ROW_PAD, and as much further as keeps the plate's
        top and the name's capitals SLANT_AIR from the bar's slanted edge
        (``team_rows.clearance``), as the Madison start list's riders are:
        ``band_h`` is the row's height, ``h`` the entry's that the plate
        is sized in, and ``size`` the name's largest, so a list set
        smaller never moves its plates or names. ``teams`` is a list that
        holds a team, whose block is the entry's whole height.
        """
        u = self.u
        shift = team_rows.slant_shift(band_h, size, u)
        if self.show_bibs:
            ph = self.plate_height(h)
            # The name stands a plate's width and its gap further right.
            beside = shift - t.plate_width(ph) - PLATE_NAME_GAP * u
            shift = max(team_rows.clearance(band_h, ph / 2, u), beside)
        if teams:
            shift = max(shift, team_rows.clearance(band_h, h / 2, u))
        return (team_rows.SWATCH_W + team_rows.ROW_PAD) * u + shift

    def rows_geometry(
        self,
        area: QRectF,
        count: int,
        cols: int,
        pitch_cap: float = 112,
        name_cap: float = 46,
        barred: bool = False,
    ) -> tuple[int, float, float, QRectF, tuple[float, float, float, float]]:
        """``entry_rows``' layout: rows a column, pitch, name size, first entry rect, padding.

        ``barred`` lays out rider rows, whose entries stand clear of the bar.
        """
        u = self.u
        col_w = (area.width() - LIST_COL_GAP * u * (cols - 1)) / cols
        fit = max(1, int(area.height() // (LIST_MIN_PITCH * u)))
        per_col = min(fit, math.ceil(count / cols))
        pitch = min(pitch_cap * u, area.height() / per_col)
        size = min(name_cap * u, pitch * LIST_NAME_SHARE)
        band_h = pitch - band_gap(pitch, u)
        vpad = min(8 * u, pitch * 0.07)
        left = self.bar_lead(band_h, band_h - 2 * vpad, size) if barred else 18 * u
        pad = (left, vpad, -18 * u, -vpad)
        inner = QRectF(area.x(), area.y(), col_w, band_h).adjusted(*pad)
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
        bar: str | None = None,
    ) -> None:
        """Entries as banded rows in ``cols`` columns, filled top to bottom.

        The name is a fixed share of the row's pitch up to ``name_cap``, so
        a long list sets smaller type in shorter rows; at 24 riders a
        fixed 46 px name would lose its descenders to the next row. Rows never
        go tighter than LIST_MIN_PITCH: what still does not fit is left off,
        never drawn over itself. With ``bar`` the rows are rider rows, the
        Madison's row with a bar of that color (``team_rows.paint_band``);
        without it each is a rounded band of ``fill``.
        """
        u = self.u
        if not entries:
            return
        gap = LIST_COL_GAP * u
        per_col, pitch, size, inner, pad = self.rows_geometry(
            area, len(entries), cols, pitch_cap, name_cap, barred=bar is not None
        )
        col_w = (area.width() - gap * (cols - 1)) / cols
        band_h = inner.height() + pad[1] - pad[3]
        entries = entries[: per_col * cols]
        scale = self.entry_scale(entries, inner, size, laps=laps)
        for i, entry in enumerate(entries):
            c, r = divmod(i, per_col)
            row = QRectF(area.x() + c * (col_w + gap), area.y() + r * pitch, col_w, band_h)
            if bar is None:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(fill)
                p.drawRoundedRect(row, 10 * u, 10 * u)
            else:
                team_rows.paint_band(
                    p,
                    row,
                    bar,
                    u,
                    slant=t.SLANT,
                    texture=self.texture,
                    dpr=self.devicePixelRatioF(),
                )
            lap = laps[i] if laps and i < len(laps) else 0
            self.entry_line(p, row.adjusted(*pad), entry, size, scale=scale, laps=lap)


# Between a team block and its riders' names.
TEAM_GAP = 28
# Between a rider's bib plate and the name beside it.
PLATE_NAME_GAP = 26
# Between the columns of a list of entries.
LIST_COL_GAP = 48
# The most of an entry's width a team block takes for its name at full
# size; a longer name shrinks inside it, down to the board's floor.
TEAM_SHARE = 0.4
# How much of a row a block takes beside its riders when they leave the
# room (the result's podium): the color is the thing a rider at speed
# finds first, so it gets the spare room, and the riders keep one column
# beside it.
TEAM_FILL = 0.6
# A list row's name as a share of the row's pitch.
LIST_NAME_SHARE = 0.56
# The tightest a list of riders is set: its names at the board's minimum.
LIST_MIN_PITCH = t.MIN_PX / LIST_NAME_SHARE
# How much larger one column must set a list's names than its columns do
# to take their place: one long column of names barely larger has
# shorter rows and smaller plates.
ONE_COLUMN_GAIN = 1.03
# The widest lap chips a list keeps room for while it grows, so a lap
# taken mid-race never steps the list's names down.
LAP_CHIP_SAMPLES = (8, -8)


class PreRacePage(Page):
    """The start list: riders as a list of rows, or a Madison's teams as one row each.

    A team list longer than TEAM_PAGE_ROWS is shown a page at a time, as
    the team standings are; ``advance`` turns the page.
    """

    page = 0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The last list's layout and what it was worked out for: finding
        # the largest whole size measures the list many times over, and a
        # repaint of the same list on the same page needs none of that.
        self._layout: tuple[tuple, tuple[int, float, float]] | None = None

    def set_data(self, data, prev=None) -> None:
        if self.data is None or getattr(self.data, "header", None) != getattr(data, "header", None):
            self.page = 0
        super().set_data(data, prev)

    def teams(self) -> bool:
        return self.data is not None and any(e.color for e in self.data.roster)

    def page_count(self) -> int:
        if not self.teams():
            return 1
        n = len(self.data.roster)
        return max(1, -(-n // page_rows(n, TEAM_PAGE_ROWS)))

    def advance(self) -> None:
        if self.page_count() > 1:
            self.page = (self.page + 1) % self.page_count()
            self.update()

    def paint(self, p: QPainter, area: QRectF) -> None:
        d: PreRace = self.data
        u = self.u
        if self.teams():
            self.team_list(p, area, d)
            return
        # No count label, as on a Madison's: the list shows the field, so
        # the rows take the page from its top.
        laps = any(d.laps)
        room = QRectF(area)
        if self.bibs_only and not laps and all(e.bibs for e in d.roster):
            plate_grid(p, room, [e.bibs[0] for e in d.roster], u)
            return
        if not d.roster:
            return
        key = (room.width(), room.height(), u, self.rider_label, d)
        if self._layout is None or self._layout[0] != key:
            # A copy, so a payload changed where it stands is not taken for the one measured.
            self._layout = ((*key[:-1], copy.deepcopy(d)), self.list_layout(room, d))
        cols, pitch_cap, name_cap = self._layout[1]
        # Rider rows, every bar neutral: a start list has no leader.
        bar = team_rows.RIDER_BAR
        self.entry_rows(p, room, d.roster, cols, t.ROW, pitch_cap, name_cap, d.laps, bar)

    def team_list(self, p: QPainter, area: QRectF, d: PreRace) -> None:
        """A Madison's teams, one row each: the riders' names lead and the color identifies.

        No section label and no team word or name: the start list is
        riders only (design section 10). The rows share the page down to
        TEAM_FILL_LEAST rows' worth, so fewer teams get larger names and a
        lone team takes half the page. Every page is set for a full page's
        rows, so the names keep one size as the pages turn. The list
        leaves the board at the first sprint or lap, so a row keeps no
        room for a lap. The rows are the table's: a square left end and a
        swatch whose right edge leans at the score chip's slant
        (``theme.SLANT``), so the turn to the table crossfades like for
        like.
        """
        u = self.u
        pages = self.page_count()
        page = self.page % pages
        per_page = page_rows(len(d.roster), TEAM_PAGE_ROWS)
        rows = d.roster[page * per_page : (page + 1) * per_page]
        bottom = area.bottom() - (PAGE_DOTS_H * u if pages > 1 else 0)
        gap = team_rows.ROW_GAP * u
        rh = (bottom - area.y() - (per_page - 1) * gap) / max(per_page, TEAM_FILL_LEAST)
        last_px = min(team_rows.START_SURNAME_SHARE * rh, team_rows.START_SURNAME_MOST * u)
        first_px = min(
            max(team_rows.START_FIRST_SHARE * rh, t.MIN_PX * u), team_rows.START_FIRST_MOST * u
        )
        for i, e in enumerate(rows):
            row = QRectF(area.x(), area.y() + i * (rh + gap), area.width(), rh)
            team_rows.paint_band(
                p,
                row,
                e.color,
                u,
                slant=t.SLANT,
                texture=self.texture,
                dpr=self.devicePixelRatioF(),
            )
            team_rows.paint_start_riders(
                p, row, e.bibs, e.names, first_px, last_px, u, self.rider_label
            )
        if pages > 1:
            page_dots(p, area, pages, page, u)

    def list_layout(self, room: QRectF, d: PreRace) -> tuple[int, float, float]:
        """The list's columns and its pitch and name caps: the plan that sets its names largest."""
        u = self.u
        count = len(d.roster)
        if count <= 6:
            # A small field is one column of big names.
            plans = [(1, 128, 56)]
        else:
            cols = max(2, self.list_columns(count, room.height()))
            plans = [(cols, 112, 46)]
            if count <= room.height() // (LIST_MIN_PITCH * u):
                # A mid-size field may read larger in one column than in
                # two, whose half-width rows cap the names.
                plans.append((1, 112, 46))
        best = None
        for cols, pitch_cap, name_cap in plans:
            caps = self.grown_caps(room, d.roster, cols, pitch_cap, name_cap)
            _per, pitch, size, _inner, _pad = self.rows_geometry(
                room, count, cols, *caps, barred=True
            )
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

        The rows share the room down to RIDER_FILL_LEAST rows, as the race's
        own table does, shared by the list's columns; the type grows with
        them only while every name fits whole at its size. The list keeps
        room for a lap chip on every row, so the first lap taken never
        steps it down. The caps never go under ``pitch_cap`` and
        ``name_cap``, so a long list keeps its base sizes.
        """
        u = self.u
        per_col = math.ceil(len(roster) / cols)
        least = math.ceil(RIDER_FILL_LEAST / cols)
        fill = room.height() / max(per_col, least)
        base_size = min(name_cap * u, min(pitch_cap * u, room.height() / per_col) * LIST_NAME_SHARE)
        chip = max(LAP_CHIP_SAMPLES, key=self.lap_room)
        laps = [chip] * len(roster)
        size = fill * LIST_NAME_SHARE
        while size > base_size:
            # The rows never come out shorter than the base list's, which
            # would cost the plates what the names gain.
            caps = (max(size / LIST_NAME_SHARE / u, pitch_cap), size / u)
            _per, _pitch, got, inner, _pad = self.rows_geometry(
                room, len(roster), cols, *caps, barred=True
            )
            if self.entry_scale(roster, inner, got, True, laps) >= 1.0:
                return caps
            size *= 0.96
        return pitch_cap, name_cap


# The most riders still in that show as cards; more open as rows. Four
# columns of cards would set long names at 25 px, under the design's floor.
CARDS_UP_TO = 6
# A row's name size when the rows have room; a long list sets it smaller,
# down to the board's minimum (LIST_NAME_SHARE).
ROW_NAME_PX = 50
# The tallest bib plate on a remaining-rider card: the plate grid's own
# largest, which a three-digit bib fills from the far end of the stands.
PLATE_CAP = 170
# Elimination's side column and its gap from the riders still in, the
# gap a list's columns have. The last-out card's bar takes the left of
# the column, so the column is as wide as keeps a 17-letter surname such
# as Featherstonehaugh whole above the floor beside it, and the riders
# still in keep their room. On a board narrower than 16:9 the column
# takes no more than SIDE_SHARE of the page, so two cards still hold
# their plates beside their bars.
SIDE_W = 616
SIDE_GAP = 48
SIDE_SHARE = 0.38
# Between two cards of riders still in.
CARD_GAP = 24
# Between a card's content and its rounded right end.
CARD_PAD = 16


def caps_top(line: QRectF, f: QFont) -> float:
    """Where the capitals of a line of ``f`` set centered in ``line`` start."""
    fm = QFontMetricsF(f)
    return line.center().y() + (fm.ascent() - fm.descent()) / 2 - fm.capHeight()


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
    spectator who looked away can still see who went. Every card and row
    is a rider row (design section 10): the riders still in have the
    neutral bar, since an elimination has no leader, and the last-out
    card's bar is the out color.
    """

    fresh = True

    def paint(self, p: QPainter, area: QRectF) -> None:
        d: Elimination = self.data
        u = self.u
        side_w = min(SIDE_W * u, area.width() * SIDE_SHARE)
        gap = SIDE_GAP * u
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
        room_h = grid.bottom() - top
        cols, cw, ch = self.cards(grid.width(), room_h, n)
        cg = CARD_GAP * u
        # The last few riders are the race's climax: their cards grow.
        final = n <= 4
        names = [e.names[0] if e.names and not self.bibs_only else "" for e in d.remaining]
        block_px = min((88 if final else 52) * u, ch * 0.26)
        card_px = min((64 if final else 36) * u, ch * 0.15)
        # Every card has one geometry, worked out on one card at the
        # origin: the content centers on the room the bar leaves at the
        # content's top, at its largest, so every card reads the same.
        frame = QRectF(0, 0, cw, ch)
        right = cw - CARD_PAD * u
        if self.show_bibs:
            name_rect = QRectF(16 * u, ch * 0.64, cw - 32 * u, ch * 0.28)
            f = t.font(card_px, t.SEMI)
            room = self.line_room(name_rect, f, frame)
            scale = t.fit_scale(((n, room, f) for n in names), self.name_floor(card_px))
            plate_top = ch * 0.13
            axis = self.card_axis(frame, plate_top, right)
            # One plate size from four left to two, the least any of their
            # layouts holds, and never more for five or six: the plates
            # never shrink as riders go out. The last rider's card is the
            # widest, so it keeps its own.
            least = min(
                self.card_plate(*self.cards(grid.width(), room_h, k)[1:]) for k in range(2, 5)
            )
            own = self.card_plate(cw, ch)
            ph = own if n == 1 else (least if final else min(own, least))
        else:
            inner = QRectF(16 * u, 10 * u, cw - 32 * u, ch - 20 * u)
            scale = self.block_scale(names, inner, block_px, frame)
            # A name on two lines stands highest.
            f = t.font(block_px, t.BOLD)
            axis = self.card_axis(frame, caps_top(t.stacked_lines(inner, f, 2)[0], f), right)
        dpr = self.devicePixelRatioF()
        for i, entry in enumerate(d.remaining):
            r, c = divmod(i, cols)
            card = QRectF(grid.x() + c * (cw + cg), top + r * (ch + cg), cw, ch)
            team_rows.paint_band(
                p, card, team_rows.RIDER_BAR, u, slant=t.SLANT, texture=self.texture, dpr=dpr
            )
            at = card.topLeft()
            name = names[i]
            if not self.show_bibs:
                self.name_block(
                    p,
                    inner.translated(at),
                    name,
                    block_px,
                    scale=scale,
                    card=card,
                    axis=card.x() + axis,
                )
                continue
            pw = t.plate_width(ph)
            bib = entry.bibs[0] if entry.bibs else ""
            t.plate(p, QRectF(card.x() + axis - pw / 2, card.y() + plate_top, pw, ph), bib)
            line = name_rect.translated(at)
            f = t.scaled(t.font(card_px, t.SEMI), scale)
            shown = t.fit_name(name, self.line_room(line, f, card), f)
            self.card_line(p, line, shown, f, t.TEXT, card, card.x() + axis)
        self._side(p, side, n)

    def cards(self, width: float, height: float, n: int) -> tuple[int, float, float]:
        """The columns, card width, and card height for ``n`` cards in ``width`` by ``height``.

        Four to six left are two columns of cards: three across are too
        narrow for a name such as M. Vanderbilt-Rochester at the board's
        minimum, and four would leave the fourth alone on a second row.
        Three left go three across while that keeps their plates as large
        as two across, and otherwise two and one, as four are, so a
        narrow board's plates do not shrink at the race's climax.
        """
        u = self.u
        cg = CARD_GAP * u

        def layout(cols: int, final: bool) -> tuple[int, float, float]:
            rows = max(1, math.ceil(n / cols))
            cw = (width - cg * (cols - 1)) / cols
            ch = min((420 if final else 250) * u, (height - cg * (rows - 1)) / rows)
            return cols, cw, ch

        if n == 3:
            across, two = layout(3, True), layout(2, True)
            return across if self.card_plate(*across[1:]) >= self.card_plate(*two[1:]) else two
        return layout(2 if n >= 4 else max(n, 1), n <= 4)

    def card_plate(self, cw: float, ch: float) -> float:
        """The tallest plate a card ``cw`` by ``ch`` holds.

        The plate grows with the card, but never past the size a
        three-digit bib needs, and never wider than the card less a
        margin, or three left on a wide monitor would draw plates taller
        than the cards are wide, running into each other; nor wider than
        the room the bar leaves it at the plate's top.
        """
        u = self.u
        top = ch * 0.13
        room = cw - CARD_PAD * u - team_rows.bar_clear(QRectF(0, 0, cw, ch), top, u)
        unit = t.plate_width(1.0)
        return max(0.0, min(ch * 0.46, PLATE_CAP * u, (cw - 48 * u) / unit, room / unit))

    def _rows(self, p: QPainter, area: QRectF) -> None:
        """The riders still in as columns of rider rows, for a big field."""
        d: Elimination = self.data
        cols = max(2, self.list_columns(len(d.remaining), area.height()))
        self.entry_rows(
            p, area, d.remaining, cols, t.CARD, name_cap=ROW_NAME_PX, bar=team_rows.RIDER_BAR
        )

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
            team_rows.paint_band(
                p,
                card,
                t.OUT.name(),
                u,
                slant=t.SLANT,
                texture=self.texture,
                dpr=self.devicePixelRatioF(),
            )
            if fresh:
                # The bell's news: the card washed and edged in the out
                # color for a few seconds.
                p.save()
                p.setBrush(t.OUT_SOFT)
                p.setPen(QPen(t.OUT, 4 * u))
                p.drawPath(team_rows.band_shape(card.adjusted(2 * u, 2 * u, -2 * u, -2 * u), u))
                p.restore()
            out_name = d.last_eliminated.names[0] if d.last_eliminated.names else ""
            if self.bibs_only:
                out_name = ""
            if self.show_bibs:
                self._last_out_plate(p, card, out_name)
            else:
                inner = card.adjusted(32 * u, 40 * u, -CARD_PAD * u, -40 * u)
                # 76 px of Inter has the capitals of the 84 px this card was
                # designed at, and lets a 17-letter last name such as
                # Featherstonehaugh stay whole above the floor beside the bar.
                out_px = 76 * u
                f = t.font(out_px, t.BOLD)
                first = t.stacked_lines(inner, f, 2)[0]
                axis = self.card_axis(card, caps_top(first, f), inner.right())
                scale = self.block_scale([out_name], inner, out_px, card)
                self.name_block(p, inner, out_name, out_px, scale=scale, card=card, axis=axis)
            y = card.bottom() + 56 * u
        self._remaining(p, side, y, n)

    def _last_out_plate(self, p: QPainter, card: QRectF, name: str) -> None:
        u = self.u
        bibs = self.data.last_eliminated.bibs
        bib = bibs[0] if bibs else ""
        right = card.right() - 24 * u
        unit = t.plate_width(1.0)
        if not name:
            # Bibs only: the plate alone, larger, in the middle of its card.
            top = card.center().y() - 100 * u
            ph = min(200 * u, (right - team_rows.bar_clear(card, top, u)) / unit)
            pw = t.plate_width(ph)
            top = card.center().y() - ph / 2
            axis = self.card_axis(card, top, right)
            t.plate(p, QRectF(axis - pw / 2, top, pw, ph), bib)
            return
        ph = min(150 * u, (right - team_rows.bar_clear(card, card.y() + 44 * u, u)) / unit)
        pw = t.plate_width(ph)
        axis = self.card_axis(card, card.y() + 44 * u, right)
        t.plate(p, QRectF(axis - pw / 2, card.y() + 44 * u, pw, ph), bib)
        rect = QRectF(card.x() + 24 * u, card.y() + 220 * u, card.width() - 48 * u, 80 * u)
        f = t.font(50 * u, t.BOLD)
        f = t.scaled(f, self.names_scale([name], self.line_room(rect, f, card), 50 * u))
        shown = t.fit_name(name, self.line_room(rect, f, card), f)
        self.card_line(p, rect, shown, f, t.TEXT, card, axis)

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


# The most rows a page shows. Sixteen is the most riders a 166 m track
# may start (USAC 2B7), so a full field at the venue is one page the
# stands can read whole, its names at the design's floor (section 10). A
# longer table, from a bigger track, turns its pages every few seconds
# rather than shrinking its names, and its pages share the rows evenly, so
# 24 riders show as 12 and 12, not 16 and a lonely 8.
PAGE_ROWS = 16
# A madison row carries two riders, so a page holds half as many. USAC
# 2B7 allows twelve teams on a 166.66 m track; twelve rows would set the
# surnames under MIN_PX, so a full field shows as two pages of six.
TEAM_PAGE_ROWS = 8
# Team rows share the page's height whatever the field, so two teams read
# from the track as large as the page allows; a lone team takes half the
# page rather than one row the whole height.
TEAM_FILL_LEAST = 2
# A team row's total, its largest type, as a share of the row.
TEAM_FIGURE_SHARE = 0.62
# The place beside the total's size: Black weight like the total, a step
# under it, so the total stays the figure the eye finds first.
TEAM_PLACE_SCALE = 0.85
# The widest the place column grows, as a share of the page's width.
TEAM_PLACE_SHARE = 0.14
# The laps and the penalty grow with the row, under the total.
TEAM_LAPS_SHARE = 0.36
# The laps and the penalty stop growing here, as the surnames do: a lone
# team's or a pair's tall row would otherwise give their columns the width
# the surnames need, and the total is the figure the riders read.
TEAM_LAPS_MOST = 96
# The least the place and the total give way to, so the surnames fit
# whole beside them; past that a long surname shrinks instead.
TEAM_FIGURE_LEAST = 84
# The riders' surnames, side by side on the row, as a share of its height.
# They stop growing at the start list's largest surname
# (``team_rows.START_SURNAME_MOST``): surnames set to a lone team's or a
# pair's tall row would leave each other no room beside the figures, which
# give way to them only down to TEAM_FIGURE_LEAST.
TEAM_SURNAME_SHARE = 0.48
# The team's name in the color view, as a share of the row's height.
TEAM_LABEL_SHARE = 0.52
# The color view's solid color stops this far short of the first figure
# column, so the figures keep the dark row around them in both views.
COLOR_ZONE_GAP = 60
# The total's right edge is set in this far from the row's right end.
TEAM_FIGURE_PAD = 24
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


# The strip under a paged list that its page dots take.
PAGE_DOTS_H = 32


def page_dots(p: QPainter, area: QRectF, pages: int, page: int, u: float) -> None:
    """Page dots at the bottom right of ``area``, the page in view lit.

    Dots, not a "1-8 of 16" footer: they say there is more without asking
    anyone to read a line of small print.
    """
    dot, gap = 16 * u, 14 * u
    x = area.right() - pages * dot - (pages - 1) * gap - 20 * u
    y = area.bottom() - dot - 6 * u
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(pages):
        p.setBrush(t.TEXT if i == page else t.RULE)
        p.drawEllipse(QRectF(x + i * (dot + gap), y, dot, dot))


class TeamTable(NamedTuple):
    """A Madison table's layout, worked out once per payload and board size.

    A frame of the rotation only reads it, so the motion never measures
    text. ``labels`` holds each row's team name and its font, in the
    payload's row order.
    """

    rows_top: float
    rh: float
    gap: float
    row_x: float
    rank_w: float
    place_f: QFont
    total_f: QFont
    num: QFont
    total_r: float
    total_col: float
    pen_r: float
    pen_col: float
    laps_r: float
    laps_col: float
    penalized: bool
    zone_r: float
    names_x: float
    half: float
    surname_f: QFont
    plate_h: float
    labels: list[tuple[str, QFont]]


# A score chip: its type and its padding as shares of the total's type,
# and its height as a share of the row, so it covers the total it replaces.
CHIP_TYPE = 0.82
CHIP_PAD = 0.5
CHIP_HEIGHT = 0.78
# It drops from this many times its size, slanted at the board's slant
# (``theme.SLANT``), so it lands as a stamp cut like the rows it lands on.
CHIP_START = 2.4
# It fades in over its first moments, so its large start reads as a drop
# and not as a flash over the row above.
CHIP_IN_MS = 90
CHIP_RADIUS = 14
# The ring that grows out of the chip as it lands: its starting alpha,
# its growth over the chip's size, and its line.
RING_ALPHA = 0.6
RING_GROWTH = 0.6
RING_LINE = 6
# The sheen's alpha at its middle as it crosses the chip.
SHEEN_ALPHA = 150
# How far, in rows, the old total is knocked down, the chip lifts away,
# and the new total rises from.
OLD_DROP = 0.35
CHIP_LIFT = 0.9
NEW_RISE = 0.8


def score_chip(
    p: QPainter,
    rect: QRectF,
    s: str,
    f: QFont,
    fill: QColor,
    ink: QColor,
    ms: float,
    rh: float,
    u: float,
) -> None:
    """A score change's chip at rest in ``rect``, ``ms`` into its team's step.

    It drops from CHIP_START times its size with an overshoot, a ring in
    its color grows out of it and a sheen crosses it as it lands, and from
    ``SWAP_AT_MS`` it lifts away and fades. Only the painter's transform
    and opacity move; the chip's size is set once.
    """
    gone = ease_in(phase(ms, scorebug.SWAP_AT_MS, scorebug.SWAP_MS))
    if gone >= 1:
        return
    scale = CHIP_START - (CHIP_START - 1) * ease_back(phase(ms, 0, scorebug.SLAM_MS))
    c = rect.center()
    w, h = rect.width(), rect.height()
    radius = CHIP_RADIUS * u
    p.save()
    p.setOpacity(phase(ms, 0, CHIP_IN_MS) * (1 - gone))
    p.translate(c.x(), c.y() - gone * CHIP_LIFT * rh)
    p.scale(scale, scale)
    # Qt's shear moves x by its factor times y, and y runs down the
    # board, so the negative factor leans the top to the right.
    p.shear(-t.SLANT, 0)
    p.translate(-c.x(), -c.y())
    if scorebug.RING_AT_MS < ms < scorebug.RING_AT_MS + scorebug.RING_MS:
        k = ease_out(phase(ms, scorebug.RING_AT_MS, scorebug.RING_MS))
        ring = QColor(fill)
        ring.setAlphaF(RING_ALPHA * (1 - k))
        g = 1 + RING_GROWTH * k
        p.setPen(QPen(ring, RING_LINE * u))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(
            QRectF(c.x() - w * g / 2, c.y() - h * g / 2, w * g, h * g), radius * g, radius * g
        )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fill)
    p.drawRoundedRect(rect, radius, radius)
    sheen = phase(ms, scorebug.SLAM_MS, scorebug.SHEEN_MS)
    if 0 < sheen < 1:
        x = rect.left() - w * 0.4 + w * 1.8 * sheen
        light = QLinearGradient(x - w * 0.2, 0, x + w * 0.2, 0)
        light.setColorAt(0, QColor(255, 255, 255, 0))
        light.setColorAt(0.5, QColor(255, 255, 255, SHEEN_ALPHA))
        light.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(light))
        p.drawRoundedRect(rect, radius, radius)
    t.text(p, rect, s, f, ink, CENTER)
    p.restore()


class Scene(NamedTuple):
    """What a play's frames draw beside its steps.

    ``end`` is the payload the play ends on: a play waiting in the queue
    was built against the one before it, so a frame reads its rows, not
    the newest payload's. ``places``, ``penalties`` and ``sprints`` (a
    rider's SPRINT PTS) are each row's as the table stood before the
    play, ``leaders`` the rows ranked first then, and ``page`` the page
    it plays on.
    """

    end: Standings
    places: dict[Key, str]
    penalties: dict[Key, int]
    sprints: dict[Key, int]
    leaders: frozenset[Key]
    page: int


def place_ink(place: str) -> QColor:
    """The leader's place in the accent, as on the podium page; the rest in full ink."""
    return t.ACCENT if place in ("1", "1st") else t.TEXT


def row_key(row: StandingRow) -> Key:
    return tuple(row.entry.bibs)


def sprint_points(row: StandingRow) -> int:
    """A rider's sprint points so far, the figure under SPRINT PTS."""
    return sum(v for v in row.sprints if v)


class RiderTable(NamedTuple):
    """A rider table's layout, worked out once per payload and board size.

    A frame of a score change only reads it, so the motion never
    measures text. ``name_rect`` is the first row's name area and
    ``scale`` the names' shared fit.
    """

    head_h: float
    rows_top: float
    rh: float
    band_h: float
    cols: RiderColumns
    name_rect: QRectF
    name_size: float
    scale: float
    place_f: QFont
    total_f: QFont
    num: QFont
    pad: float
    penalized: bool


@dataclass
class Turn:
    """The start list turning into the Madison table before the race's first score plays.

    ``start`` is the clock's time at the turn and ``picture`` the start
    list as the board showed it (None when there was none to take).
    ``rows`` turn on ``page``. ``plays`` are the score changes that wait
    for the turn and its hold: they join the queue at ``release``, a time
    worked out from the turn's start and not from when a board next
    paints, so the TV and the preview start them at one moment.
    """

    start: float
    picture: QPixmap | None
    rows: int
    page: int
    plays: list[Play] = field(default_factory=list)

    @property
    def release(self) -> float:
        return self.start + scorebug.intro_ms(self.rows) + scorebug.INTRO_HOLD_MS


def reorder_progress(play: Play, frame: Frame) -> float:
    """How far the rows have slid to their new order, 0 to 1; 0 for a play that keeps its order."""
    after = {k: j for j, k in enumerate(play.after)}
    for i, k in enumerate(play.before):
        if after[k] != i:
            return (frame.rows[k] - i) / (after[k] - i)
    return 0.0


class StandingsPage(Page):
    """Points race, madison and tempo standings: place, who, sprint points, laps, total.

    No per-sprint columns: riders read the board at speed for their
    place, their total and their laps, and on a TV the columns squeeze a
    long name and make the table too busy to parse. One SPRINT PTS
    column carries the sprint points so far and LAPS the laps alone
    ("+1"): a bare number under SPRINTS reads as a count of sprints, and
    "+1 (+20)" mixes laps with points. The Madison page drops SPRINT PTS,
    names each team by its riders' surnames on a row of its color, and
    turns to the team's color and name on a timer (``team_table``). With
    a clock, each score change plays on its rider's or team's TOTAL as a
    chip, then the rows reorder (``team_play``, ``rider_play``); the
    operator table and the results sheet keep every sprint. More than
    PAGE_ROWS rows (TEAM_PAGE_ROWS for teams) are shown a page at a time;
    ``advance`` turns the page, and a Madison table with a clock turns its
    own pages with its rotation.
    """

    page = 0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The Madison table's layout and what it was worked out for, so a
        # frame of the rotation measures nothing; the rider table's, so a
        # frame of a score change measures nothing.
        self._layout: tuple[tuple, TeamTable] | None = None
        self._rider_layout: tuple[tuple, RiderTable] | None = None
        # The clock's time when the rotation last started: a new race
        # starts it over on the names view, and a sprint's new header
        # leaves it running, so the look in view never jumps.
        self._rotation_from = 0.0
        # Frames run only while a change between views moves; between
        # changes one timer waits for the next, so the board idles.
        self._ticker = Ticker(self, self._busy)
        # Precise, since a coarse timer may fire a few percent of its 10 s
        # late, and a change's first frame would land partway through it.
        self._wake = QTimer(self, singleShot=True, timerType=Qt.TimerType.PreciseTimer)
        self._wake.timeout.connect(self._wake_up)
        # The table's score changes, one play a scoring entry, and
        # what each play's frames draw beside its steps (``Scene``), by the
        # play's id.
        self._queue = ScoreQueue()
        self._scenes: dict[int, Scene] = {}
        # Milliseconds into the rotation when the playing sequence began:
        # the rotation holds that look until the queue is empty. None while
        # nothing plays.
        self._held: float | None = None
        # The turn from the start list while it plays or holds, else None.
        self._turn: Turn | None = None

    def now(self) -> float:
        return self.clock.now() if self.clock is not None else 0.0

    def set_data(self, data, prev=None) -> None:
        now = self.now()
        self._settle(now)
        if self.data is None or getattr(self.data, "header", None) != getattr(data, "header", None):
            self.page = 0
        if prev is None or self.data is None or self.data.header.race_id != data.header.race_id:
            self.stop_motion()
            self._rotation_from = now
        super().set_data(data, prev)
        if self.clock is None:
            self.stop_motion()
            return
        same_race = (
            isinstance(prev, (Standings, PreRace)) and prev.header.race_id == data.header.race_id
        )
        if data.scored is not None and same_race:
            if isinstance(prev, PreRace) and self.teams():
                self._turn_from_start_list(data, now)
            # New scoring with nothing in view to play (every entrant that
            # scored is on another page, or no total changed) updates
            # quietly: it leaves what plays alone, and shows when that ends.
            built = self._play_for(data, prev)
            if built is not None:
                play, scene = built
                if self._held is None:
                    self._held = self.since()
                self._scenes[id(play)] = scene
                if self._turn is not None:
                    # Behind the turn, in the order the entries came.
                    self._turn.plays.append(play)
                else:
                    self._queue.push(play, now)
                self._ticker.poke()
            return
        # A redraw (the scorer staging the next sprint's places) leaves a
        # running sequence alone; any other quiet change stops it, so the
        # board never announces points that no longer stand.
        if not self._redraw(data, prev):
            self.stop_motion()

    def stop_motion(self) -> None:
        if self._held is not None:
            self._rotation_from = self.now() - rotation.resumed(self._held, self.per_page())
        self._queue.cancel()
        self._scenes.clear()
        self._held = None
        self._turn = None

    def _turn_from_start_list(self, data: Standings, now: float) -> None:
        """Start the turn from the start list in view to this table, before its first score.

        The table is new to the stands, so it starts on the names view of
        its first page, which is where the start list's rows stand.
        """
        self.stop_motion()
        self._rotation_from = now
        self._held = 0.0
        outgoing = self.outgoing
        picture = outgoing.grab() if isinstance(outgoing, PreRacePage) else None
        rows = min(self.per_page(), len(data.rows))
        self._turn = Turn(start=now, picture=picture, rows=rows, page=0)
        self._ticker.poke()

    def _release(self, now: float) -> None:
        """Once the turn and its hold end, the plays behind it join the queue at that moment."""
        turn = self._turn
        if turn is None or now < turn.release:
            return
        self._turn = None
        for play in turn.plays:
            self._queue.push(play, turn.release)
        if not turn.plays and self._held is not None:
            # Nothing to play: the rotation goes on from the zero table.
            self._rotation_from = turn.release - rotation.resumed(self._held, self.per_page())
            self._held = None

    def scoring_now(self) -> bool:
        """Whether the turn from the start list or a score change plays, or one waits to play."""
        if self.clock is None:
            return False
        now = self.clock.now()
        self._release(now)
        return self._turn is not None or self._queue.busy(now)

    def _settle(self, now: float) -> None:
        """Once the last play ends, the rotation goes on from the look it held.

        A table held on the names view starts its names hold over; one
        held anywhere else eases back to names first (``rotation.resumed``).
        It goes on from the moment the queue emptied, not from when this
        board next looks: the TV and the preview get the same calls but
        paint at their own times, and one hidden while the queue drains
        must still turn its views and pages with the other.
        """
        self._release(now)
        if self._held is None or self._turn is not None or self._queue.busy(now):
            return
        ended = self._queue.ended_at(now)
        resume = rotation.resumed(self._held, self.per_page())
        self._held = None
        self._scenes.clear()
        self._rotation_from = (ended if ended is not None else now) - resume

    @staticmethod
    def _redraw(data: Standings, prev) -> bool:
        """Whether ``data`` draws the same table ``prev`` did."""

        def table(d: Standings) -> tuple:
            rows = [(row_key(r), r.total, r.laps, r.penalty, r.status) for r in d.rows]
            return d.header, rows

        return isinstance(prev, Standings) and table(prev) == table(data)

    def _play_for(self, data: Standings, prev: Standings | PreRace) -> tuple[Play, Scene] | None:
        """The play from ``prev``'s table to ``data``'s, for the entrants on the page in view.

        The first score of a race plays from the start list: every rider
        or team at 0, in start-list order, with no leader. One that scored
        on another page goes straight to its new values, and one whose
        total did not change has no step. None when no step is left.
        """
        olds: dict[Key, StandingRow] = {}
        if isinstance(prev, PreRace):
            old_order = [tuple(e.bibs) for e in prev.roster]
            places = {k: str(i + 1) for i, k in enumerate(old_order)}
        else:
            olds = {row_key(r): r for r in prev.rows}
            old_order = list(olds)
            # The rider table words its places as numbers, decided or not.
            decided = self.teams() and self.ordinals(prev)
            places = {row_key(r): ordinal(r.rank) if decided else str(r.rank) for r in prev.rows}
        rows = {row_key(r): r for r in data.rows}
        new_order = list(rows)
        before = [k for k in old_order if k in rows]
        seen = set(before)
        before += [k for k in new_order if k not in seen]
        per_page = self.per_page()
        page = self.shown_page()
        lo, hi = page * per_page, (page + 1) * per_page
        shown_before, shown_after = before[lo:hi], new_order[lo:hi]
        steps: list[Step] = []
        for k in dict.fromkeys(tuple(k) for k in data.scored.keys):
            row = rows.get(k)
            if row is None or row.status or k not in shown_before:
                continue
            old = olds.get(k)
            old_total, old_laps = (old.total, old.laps) if old is not None else (0, 0)
            if row.total != old_total:
                steps.append(Step(k, old_total, row.total, old_laps, row.laps))
        if not steps:
            return None
        # Both orders hold every row drawn: a row that moves onto the page
        # in the reorder starts below it, and one that leaves ends below it.
        play = Play(
            steps=tuple(steps),
            before=(*shown_before, *(k for k in shown_after if k not in shown_before)),
            after=(*shown_after, *(k for k in shown_before if k not in shown_after)),
        )
        penalties = {k: r.penalty for k, r in olds.items()}
        sprints = {k: sprint_points(r) for k, r in olds.items()}
        leaders = frozenset(k for k, r in olds.items() if r.rank == 1 and not r.status)
        return play, Scene(data, places, penalties, sprints, leaders, page)

    def teams(self) -> bool:
        return self.data is not None and any(r.entry.color for r in self.data.rows)

    def rotates(self) -> bool:
        """Whether the table turns between its names and color views, and its pages, on its own."""
        return self.clock is not None and self.teams()

    def page_most(self) -> int:
        return TEAM_PAGE_ROWS if self.teams() else PAGE_ROWS

    def per_page(self) -> int:
        return page_rows(len(self.data.rows), self.page_most()) if self.data is not None else 1

    def page_count(self) -> int:
        rows = len(self.data.rows) if self.data is not None else 0
        return max(1, -(-rows // page_rows(rows, self.page_most())))

    def shown_page(self) -> int:
        """The page in view when nothing plays: the rotation's, or the one ``advance`` turned to."""
        pages = self.page_count()
        if self.rotates():
            return rotation.page_at(self.since(), self.per_page(), pages)
        return self.page % pages

    def ordinals(self, d: Standings) -> bool:
        """Whether the places read "1st", "2nd": once the officials have decided the race.

        A decided table is the result, worded as the result page words
        its places; while the race runs a bare number is a standing that
        can still change.
        """
        return d.header.status in DECIDED

    def advance(self) -> None:
        # A score change plays out on the page it began on; the page turns
        # on the pager's next tick after it.
        if self.page_count() > 1 and not self.scoring_now():
            self.page = (self.page + 1) % self.page_count()
            self.update()

    # The rotation ------------------------------------------------------

    def since(self) -> float:
        """Milliseconds into the rotation; 0 with no clock, so the table rests on its names.

        Held while a score change plays, so the table keeps its look and
        its page under the slams.
        """
        if self._held is not None:
            return self._held
        return self.clock.now() - self._rotation_from if self.clock is not None else 0.0

    def moving_now(self) -> bool:
        """Whether a change between the names and color views is playing."""
        return self.rotates() and rotation.moving(self.since(), self.per_page())

    def wake_in(self) -> float | None:
        """Milliseconds the last paint set to wait for the next change; None while none waits.

        The delay as scheduled, not the time left on the wall clock, so a
        test reads it the same however long its own steps took.
        """
        return float(self._wake.interval()) if self._wake.isActive() else None

    def _busy(self) -> bool:
        return self.isVisible() and (self.scoring_now() or self.moving_now())

    def _wake_up(self) -> None:
        if self.isVisible() and self.rotates():
            self._ticker.poke()
            self.update()

    def _schedule(self) -> None:
        """Frames while anything moves, else one timer for the next change's start."""
        if self._held is not None:
            self._wake.stop()
            self._ticker.poke()
            return
        if not self.rotates():
            self._wake.stop()
            return
        since, rows = self.since(), self.per_page()
        if rotation.moving(since, rows):
            self._wake.stop()
            self._ticker.poke()
        else:
            self._wake.start(math.ceil(rotation.until_change(since, rows)) + 1)

    def paint(self, p: QPainter, area: QRectF) -> None:
        d: Standings = self.data
        u = self.u
        now = self.now()
        self._settle(now)
        turn = self._turn if self.clock is not None else None
        play = self._queue.playing(now) if self.clock is not None else None
        scene = self._scenes.get(id(play)) if play is not None else None
        pages = self.page_count()
        per_page = page_rows(len(d.rows), self.page_most())
        if turn is not None:
            page = min(turn.page, pages - 1)
        elif scene is not None:
            page = min(scene.page, pages - 1)
        else:
            page = self.shown_page()
        rows = d.rows[page * per_page : (page + 1) * per_page]
        n = max(1, min(len(d.rows), per_page))
        bottom = area.bottom() - (PAGE_DOTS_H * u if pages > 1 else 0)
        playing = None
        if scene is not None:
            playing = (play, self._queue.frame(now), scene)
        if self.teams():
            self.team_table(p, area, d, page * per_page, rows, n, bottom, playing, turn)
        else:
            self.rider_table(p, area, d, rows, n, bottom, playing)

        if pages > 1:
            page_dots(p, area, pages, page, u)
        self._schedule()

    def rider_table(
        self,
        p: QPainter,
        area: QRectF,
        d: Standings,
        rows: list,
        n: int,
        bottom: float,
        playing: tuple[Play, Frame, Scene] | None = None,
    ) -> None:
        """The Points Race and Tempo Race page: a heading row, then a rider row per rider.

        The place stands left of the row, as on the Madison's table. The
        row is the Madison's, its bar the accent for the leader and
        neutral for the rest (``team_rows.rider_bar``); the plate and the
        name stand clear of the bar at their largest (``bar_lead``), and
        RIDER stands over them. ``playing`` is a score change's play, its
        frame now, and its scene, drawn over the same layout
        (``rider_play``).
        """
        u = self.u
        key = (area.x(), area.y(), area.width(), area.height(), bottom, u, self.rider_label, n, d)
        if self._rider_layout is None or self._rider_layout[0] != key:
            # A copy, so a payload changed where it stands is not taken for the one measured.
            self._rider_layout = (
                (*key[:-1], copy.deepcopy(d)),
                self.rider_table_layout(area, d, n, bottom),
            )
        lay = self._rider_layout[1]
        cols = lay.cols
        top = area.y()
        head_h = lay.head_h
        pad = lay.pad
        lab = t.label(u)
        # Room to the left for a heading wider than its column.
        reach = 120 * u
        name_x, name_w = lay.name_rect.x(), lay.name_rect.width()
        t.text(p, QRectF(area.x(), top, cols.rank_w, head_h), "#", lab, t.MUTED)
        t.text(p, QRectF(name_x, top, name_w, head_h), "RIDER", lab, t.MUTED)
        rect = QRectF(cols.sprints_x - reach, top, cols.sprints_w - pad + reach, head_h)
        t.text(p, rect, "SPRINT PTS", lab, t.MUTED, RIGHT)
        rect = QRectF(cols.laps_x, top, cols.laps_w - pad, head_h)
        t.text(p, rect, "LAPS", lab, t.MUTED, RIGHT)
        if lay.penalized:
            rect = QRectF(cols.penalty_x - reach, top, cols.penalty_w - pad + reach, head_h)
            t.text(p, rect, "PENALTY", lab, t.MUTED, RIGHT)
        rect = QRectF(cols.total_x, top, cols.total_w - 20 * u, head_h)
        t.text(p, rect, "TOTAL", lab, t.TEXT, RIGHT)
        if playing is not None:
            self.rider_play(p, area, lay, bottom, *playing)
            return
        for i, row in enumerate(rows):
            y = lay.rows_top + i * lay.rh
            place = str(row.rank)
            # The leader in the accent, as "1st" is on the result page; the
            # rest in full ink, not the row's dimmest text.
            t.text(
                p, QRectF(area.x(), y, cols.rank_w, lay.rh), place, lay.place_f, place_ink(place)
            )
            total = row.status or total_text(row.total)
            leader = row.rank == 1
            self.rider_row(
                p, area, lay, y, row, leader, sprint_points(row), row.laps, row.penalty, total
            )

    def rider_table_layout(self, area: QRectF, d: Standings, n: int, bottom: float) -> RiderTable:
        """The rider table's rows, columns and fonts for this payload on this board."""
        u = self.u
        head_h = 44 * u
        rows_top = area.y() + head_h + 8 * u
        # The feed leaves a status row off the board; a page given one
        # prints the status for a total and no figures, so a penalty on it
        # opens no column.
        penalized = any(r.penalty for r in d.rows if not r.status)
        entries = [r.entry for r in d.rows]
        fill = (bottom - rows_top) / max(n, RIDER_FILL_LEAST)
        # The entry takes nearly the whole row, so the bib plate keeps its
        # size in a dense table; the gaps between the rows carry the
        # separation.
        inset = 0.05

        def layout(g: float, reserve: bool = False):
            rh = min(fill, RIDER_ROW_FULL * g)
            cols = rider_columns(area, g, 24 * u, penalized or reserve)
            size = min(46 * g, rh * STANDINGS_NAME_SHARE)
            h = rh * (1 - 2 * inset)
            lead = self.bar_lead(rh - band_gap(rh, u), h, size)
            name_w = max(0.0, cols.name_w - lead)
            return rh, cols, QRectF(cols.name_x + lead, rows_top + rh * inset, name_w, h), size

        # The figures' unit: the page's for nine riders or more; for fewer,
        # as large as the rows allow while every name still fits whole, so
        # a small field's type and columns grow as one and no name gives
        # up its first name to the larger figures. The names are measured
        # beside a PENALTY column whether or not one stands, so the first
        # penalty given never steps the table down while it is read.
        g = u * max(1.0, fill / (RIDER_ROW_FULL * u))
        while g > u and not self.names_whole(entries, *layout(g, reserve=True)[2:]):
            g = max(u, g * 0.96)
        rh, cols, _rect, name_size = layout(g)
        # The names are fitted and drawn in the room a PENALTY column
        # leaves, so the first penalty given neither shrinks nor cuts them.
        name_rect = layout(g, reserve=True)[2]
        self.team_fill = 0.0
        # Measured over every row, not the page's, as the rank and total
        # columns are, so the names hold still as the page turns.
        scale = self.entry_scale(entries, name_rect, name_size, True)
        return RiderTable(
            head_h=head_h,
            rows_top=rows_top,
            rh=rh,
            band_h=rh - band_gap(rh, u),
            cols=cols,
            name_rect=name_rect,
            name_size=name_size,
            scale=scale,
            place_f=t.font(min(46 * g, rh * 0.7), t.BOLD, tabular=True),
            total_f=t.font(min(60 * g, rh * 0.84), t.HEAVY, tabular=True),
            # The figures keep pace with the names: at sixteen rows a sprint
            # value set at half the row would be 26 px, under the board's minimum.
            num=t.font(min(48 * g, rh * 0.7), t.BOLD, tabular=True),
            pad=24 * g,
            penalized=penalized,
        )

    def rider_row(
        self,
        p: QPainter,
        area: QRectF,
        lay: RiderTable,
        y: float,
        row: StandingRow,
        leader: bool,
        sprints: int,
        laps: int,
        penalty: int,
        total: str | None,
    ) -> None:
        """One rider's row at ``y``: band, plate and name, and figures.

        ``sprints``, ``laps``, ``penalty`` and ``total`` are the figures in
        view, which a score change holds at their old values until its new
        total rises in; ``total`` is None while the change plays on the
        cell, which then draws it (``total_change``). ``leader`` gives the
        bar the accent.
        """
        u = self.u
        cols = lay.cols
        band_y = y + (lay.rh - lay.band_h) / 2
        band = QRectF(cols.name_x, band_y, area.right() - cols.name_x, lay.band_h)
        bar = team_rows.rider_bar(1 if leader else 2, t.ACCENT)
        dpr = self.devicePixelRatioF()
        team_rows.paint_band(p, band, bar, u, slant=t.SLANT, texture=self.texture, dpr=dpr)
        name_rect = lay.name_rect.translated(0, y - lay.rows_top)
        self.entry_line(
            p, name_rect, row.entry, lay.name_size, two_line_names=True, scale=lay.scale
        )
        cell = QRectF(0, y, 0, lay.rh)
        pad = lay.pad
        # The sprint points so far, a plain number: a "+" here is the
        # laps chip's language and would read as a lap. Zero stays
        # blank so the TV stays quiet until a rider scores.
        if sprints and not row.status:
            rect = cell.adjusted(cols.sprints_x, 0, cols.sprints_x + cols.sprints_w - pad, 0)
            t.text(p, rect, str(sprints), lay.num, t.TEXT, RIGHT)
        if laps and not row.status:
            # The laps alone: the points they earn are the venue's
            # known value and are already in the total.
            rect = cell.adjusted(cols.laps_x, 0, cols.laps_x + cols.laps_w - pad, 0)
            t.text(p, rect, lap_text(laps), lay.num, t.GAIN if laps > 0 else t.LOSS, RIGHT)
        if lay.penalized and penalty and not row.status:
            # Written as a lap lost is, in the loss color: points taken.
            rect = cell.adjusted(cols.penalty_x, 0, cols.penalty_x + cols.penalty_w - pad, 0)
            t.text(p, rect, lap_text(penalty), lay.num, t.LOSS if penalty < 0 else t.GAIN, RIGHT)
        if total is not None:
            t.text(p, self.rider_total_cell(area, lay, y), total, lay.total_f, t.TEXT, RIGHT)

    def rider_total_cell(self, area: QRectF, lay: RiderTable, y: float) -> QRectF:
        """A rider row's TOTAL cell at ``y``: the total and its chip stand to its right edge."""
        return QRectF(lay.cols.total_x, y, area.right() - 20 * self.u - lay.cols.total_x, lay.rh)

    def rider_play(
        self,
        p: QPainter,
        area: QRectF,
        lay: RiderTable,
        bottom: float,
        play: Play,
        frame: Frame,
        scene: Scene,
    ) -> None:
        """A score change's frame on the rider table, as ``team_play`` draws the Madison's.

        Each row's SPRINT PTS, laps and penalty settle with its new total.
        The accent bar stays with the leader the stands saw until the last
        total has risen in, then goes with the new leader as the rows slide.
        """
        rows = {row_key(r): r for r in scene.end.rows}
        steps = {s.key: s for s in play.steps}
        landed = not frame.chips and all(frame.totals[s.key] == s.new for s in play.steps)
        clip = len(play.before) > self.per_page()
        if clip:
            # A row moving onto the page or off it slides in or out below the last row.
            p.save()
            p.setClipRect(QRectF(0, lay.rows_top, self.width(), bottom - lay.rows_top))
        for k in play.before:
            row = rows.get(k)
            if row is None:
                continue
            y = lay.rows_top + frame.rows[k] * lay.rh
            shown = frame.totals.get(k, row.total)
            # The figures beside the total settle with it.
            settled = shown == row.total
            penalty = row.penalty if settled else scene.penalties.get(k, 0)
            sprints = sprint_points(row) if settled else scene.sprints.get(k, 0)
            total = None if k in frame.chips else (row.status or total_text(shown))
            laps = frame.laps.get(k, row.laps)
            leader = row.rank == 1 if landed else k in scene.leaders
            self.rider_row(p, area, lay, y, row, leader, sprints, laps, penalty, total)
        if clip:
            p.restore()
        x, w = area.x(), lay.cols.rank_w
        self.play_places(p, x, w, lay.rows_top, lay.rh, lay.rh, lay.place_f, play, frame, scene)
        for k, ms in frame.chips.items():
            cell = self.rider_total_cell(area, lay, lay.rows_top + frame.rows[k] * lay.rh)
            self.total_change(p, cell, lay.total_f, steps[k], ms, self.u)

    def play_places(
        self,
        p: QPainter,
        x: float,
        w: float,
        top: float,
        pitch: float,
        h: float,
        f: QFont,
        play: Play,
        frame: Frame,
        scene: Scene,
        decided: bool = False,
    ) -> None:
        """A play's places, each slot's old place turning to its new one as the rows slide.

        The places stay with their slots, ``pitch`` apart from ``top``,
        each ``w`` by ``h`` from ``x``; ``decided`` words them as ordinals.
        """
        rows = {row_key(r): r for r in scene.end.rows}
        moved = reorder_progress(play, frame)
        for slot in range(min(self.per_page(), len(play.before))):
            rect = QRectF(x, top + slot * pitch, w, h)
            after = rows.get(play.after[slot])
            new = (ordinal(after.rank) if decided else str(after.rank)) if after else ""
            old = scene.places.get(play.before[slot], new)
            if old == new:
                t.text(p, rect, new, f, place_ink(new))
                continue
            for s, k in ((old, 1 - moved), (new, moved)):
                if k > 0:
                    p.save()
                    p.setOpacity(k)
                    t.text(p, rect, s, f, place_ink(s))
                    p.restore()

    def team_table(
        self,
        p: QPainter,
        area: QRectF,
        d: Standings,
        first: int,
        rows: list,
        n: int,
        bottom: float,
        playing: tuple[Play, Frame, Scene] | None = None,
        turn: Turn | None = None,
    ) -> None:
        """The Madison page: place, then each team's row, its riders' surnames leading.

        The row is the start list's: a square left end with the swatch
        flush against it, and the swatch's right edge, the fade's start,
        and the color view's moving edge at the score chip's slant
        (``theme.SLANT``). The figures sit on its dark right end: the
        laps in the gain or loss color, the penalty while one stands, and
        the total in white, the row's largest type. There is no heading
        row: the figures' colors and order say which is which. On a timer
        the row turns to its color view, the name area solid in the team's
        color with the team's name on it, and back (design section 10). ``first`` is the
        payload index of the page's first row. ``playing`` is a score
        change's play, its frame now, and its scene, drawn over the same
        layout (``team_play``); ``turn`` is the turn from the start list
        (``team_turn``).
        """
        u = self.u
        key = (area.x(), area.y(), area.width(), area.height(), bottom, u, self.rider_label, n, d)
        if self._layout is None or self._layout[0] != key:
            # A copy, so a payload changed where it stands is not taken for the one measured.
            self._layout = (
                (*key[:-1], copy.deepcopy(d)),
                self.team_table_layout(area, d, n, bottom),
            )
        lay = self._layout[1]
        ordinals = self.ordinals(d)
        if turn is not None:
            self.team_turn(p, area, lay, rows, turn)
            return
        if playing is not None:
            self.team_play(p, area, lay, bottom, *playing)
            return
        since, per_page = self.since(), self.per_page()
        for i, row in enumerate(rows):
            y = lay.rows_top + i * (lay.rh + lay.gap)
            look = rotation.look(since, i, per_page) if self.rotates() else rotation.NAMES
            # The leader in the accent, running or decided, as the winner
            # alone is on the podium page.
            place = ordinal(row.rank) if ordinals else str(row.rank)
            t.text(p, QRectF(area.x(), y, lay.rank_w, lay.rh), place, lay.place_f, place_ink(place))
            total = row.status or total_text(row.total)
            label = lay.labels[first + i]
            self.team_row(p, area, lay, y, look, row, label, row.laps, row.penalty, total)

    def team_row(
        self,
        p: QPainter,
        area: QRectF,
        lay: TeamTable,
        y: float,
        look: rotation.RowLook,
        row: StandingRow,
        label: tuple[str, QFont] | None,
        laps: int,
        penalty: int,
        total: str | None,
    ) -> None:
        """One team's row at ``y``: band, riders or team name, and figures.

        ``laps``, ``penalty`` and ``total`` are the figures in view, which a
        score change holds at their old values until its new total rises
        in; ``total`` is None while the change plays on the cell, which
        then draws it (``total_change``).
        """
        u = self.u
        e = row.entry
        band = QRectF(lay.row_x, y, area.right() - lay.row_x, lay.rh)
        team_rows.paint_band(
            p,
            band,
            e.color,
            u,
            sweep=look.sweep,
            zone_right=lay.zone_r,
            slant=t.SLANT,
            texture=self.texture,
            dpr=self.devicePixelRatioF(),
        )
        # The views' fades scale the painter's opacity, so a row fading in
        # whole (the turn from the start list) keeps its parts in step.
        if look.names > 0:
            p.save()
            p.setOpacity(p.opacity() * look.names)
            self.team_riders(p, band, e, lay)
            p.restore()
        if look.label > 0 and label is not None:
            name, f = label
            rise = (1 - look.label) * 12 * u
            # Inside the color's square left end and its slanted right end
            # where it crosses the row's middle, so the name keeps its air
            # from both at every height.
            pad = team_rows.ROW_PAD * u
            right = lay.zone_r - team_rows.run(band, t.SLANT) / 2 - pad
            rect = QRectF(band.x() + pad, y + rise, right - band.x() - pad, lay.rh)
            p.save()
            p.setOpacity(p.opacity() * look.label)
            t.text(p, rect, name, f, t.team_ink(QColor(e.color)), CENTER)
            p.restore()
        cell = QRectF(0, y, 0, lay.rh)
        # A status row shows its status and no figures, laps included.
        if laps and not row.status:
            # The laps alone: the points they earn are in the total.
            rect = cell.adjusted(lay.laps_r - lay.laps_col, 0, lay.laps_r, 0)
            t.text(p, rect, team_laps_text(laps), lay.num, t.GAIN if laps > 0 else t.LOSS, RIGHT)
        if lay.penalized and penalty and not row.status:
            # Written as a lap lost is, in the loss color: points taken.
            rect = cell.adjusted(lay.pen_r - lay.pen_col, 0, lay.pen_r, 0)
            color = t.LOSS if penalty < 0 else t.GAIN
            t.text(p, rect, lap_text(penalty), lay.num, color, RIGHT)
        if total is not None:
            rect = cell.adjusted(lay.total_r - lay.total_col, 0, lay.total_r, 0)
            t.text(p, rect, total, lay.total_f, t.TEXT, RIGHT)

    def team_turn(self, p: QPainter, area: QRectF, lay: TeamTable, rows: list, turn: Turn) -> None:
        """The start list turning into the table, a row at a time, then the table held.

        The start list's rows and the table's start at the page's top with
        one height and gap, so each row's band of the start list's picture
        fades out drifting left while the table's row fades in from the
        right over the same band; only opacity and position move. The
        table's rows stand as the first play starts from them, so the
        play's first frame follows on with nothing moving but its chip.
        """
        u = self.u
        ms = self.now() - turn.start
        drift = scorebug.INTRO_DRIFT * u
        pitch = lay.rh + lay.gap
        for i, (row, place, laps, penalty, total, label) in enumerate(
            self._turn_rows(lay, rows, turn)
        ):
            y = lay.rows_top + i * pitch
            k = scorebug.intro_row(ms, i)
            if k < 1 and turn.picture is not None:
                p.save()
                # The band and half the gap on each side, so the rows'
                # bands of the picture meet with nothing left between.
                p.setClipRect(QRectF(0, y - lay.gap / 2, self.width(), pitch))
                # The start list leaves faster than the table arrives, so
                # the two rows' names are never on the row at full strength
                # together.
                p.setOpacity((1 - k) ** 3)
                p.drawPixmap(QPointF(-drift * k, 0), turn.picture)
                p.restore()
            if k > 0:
                p.save()
                p.setOpacity(k)
                p.translate(drift * (1 - k), 0)
                rect = QRectF(area.x(), y, lay.rank_w, lay.rh)
                t.text(p, rect, place, lay.place_f, place_ink(place))
                self.team_row(p, area, lay, y, rotation.NAMES, row, label, laps, penalty, total)
                p.restore()

    def _turn_rows(self, lay: TeamTable, rows: list, turn: Turn) -> list[tuple]:
        """The table's rows as the turn shows them: row, place, laps, penalty, total and label.

        In the first play's starting order and figures, so the turn hands
        over to the play with nothing jumping; the page's rows as they
        stand when nothing plays.
        """
        labels = {row_key(r): label for r, label in zip(self.data.rows, lay.labels, strict=True)}
        if not turn.plays:
            decided = self.ordinals(self.data)
            return [
                (
                    r,
                    ordinal(r.rank) if decided else str(r.rank),
                    r.laps,
                    r.penalty,
                    r.status or total_text(r.total),
                    labels.get(row_key(r)),
                )
                for r in rows
            ]
        play = turn.plays[0]
        scene = self._scenes[id(play)]
        ends = {row_key(r): r for r in scene.end.rows}
        steps = {s.key: s for s in play.steps}
        out = []
        for k in play.before[: turn.rows]:
            row = ends[k]
            place = scene.places.get(k, str(row.rank))
            step = steps.get(k)
            if step is None:
                figures = (row.laps, row.penalty, row.status or total_text(row.total))
            else:
                figures = (step.old_laps, scene.penalties.get(k, 0), total_text(step.old))
            out.append((row, place, *figures, labels.get(k)))
        return out

    def team_play(
        self,
        p: QPainter,
        area: QRectF,
        lay: TeamTable,
        bottom: float,
        play: Play,
        frame: Frame,
        scene: Scene,
    ) -> None:
        """A score change's frame: rows where the frame puts them, then the slams on their totals.

        The rows and their figures are the scene's: a waiting play was
        built against the play ahead, so the newest payload's totals are
        not yet the ones in view. The places stay with their slots and
        turn to the new places as the rows slide.
        """
        u = self.u
        pitch = lay.rh + lay.gap
        rows = {row_key(r): r for r in scene.end.rows}
        labels = {row_key(r): label for r, label in zip(self.data.rows, lay.labels, strict=True)}
        steps = {s.key: s for s in play.steps}
        since, per_page = self.since(), self.per_page()
        clip = len(play.before) > per_page
        if clip:
            # A row moving onto the page or off it slides in or out below the last row.
            p.save()
            p.setClipRect(QRectF(0, lay.rows_top, self.width(), bottom - lay.rows_top))
        for i, k in enumerate(play.before):
            row = rows.get(k)
            if row is None:
                continue
            y = lay.rows_top + frame.rows[k] * pitch
            look = rotation.look(since, i, per_page) if self.rotates() else rotation.NAMES
            shown = frame.totals.get(k, row.total)
            # The penalty settles with the new total.
            penalty = row.penalty if shown == row.total else scene.penalties.get(k, 0)
            total = None if k in frame.chips else (row.status or total_text(shown))
            laps = frame.laps.get(k, row.laps)
            self.team_row(p, area, lay, y, look, row, labels.get(k), laps, penalty, total)
        if clip:
            p.restore()
        decided = self.ordinals(scene.end)
        x, w = area.x(), lay.rank_w
        self.play_places(
            p, x, w, lay.rows_top, pitch, lay.rh, lay.place_f, play, frame, scene, decided
        )
        for k, ms in frame.chips.items():
            y = lay.rows_top + frame.rows[k] * pitch
            cell = QRectF(lay.total_r - lay.total_col, y, lay.total_col, lay.rh)
            self.total_change(p, cell, lay.total_f, steps[k], ms, u)

    def total_change(
        self, p: QPainter, cell: QRectF, f: QFont, step: Step, ms: float, u: float
    ) -> None:
        """A TOTAL ``cell`` ``ms`` into its step: the old total knocked out, the chip, the new total.

        The total and the chip stand to the cell's right edge, and the new
        total rises in clipped to the cell; ``f`` is the total's font.
        """
        rh = cell.height()
        y = cell.y()
        out = ease_out(phase(ms, 0, scorebug.OLD_OUT_MS))
        if out < 1:
            p.save()
            p.setOpacity(1 - out)
            t.text(
                p, cell.translated(0, out * OLD_DROP * rh), total_text(step.old), f, t.TEXT, RIGHT
            )
            p.restore()
        rise = ease_out(phase(ms, scorebug.SWAP_AT_MS, scorebug.SWAP_MS))
        if rise > 0:
            p.save()
            p.setClipRect(cell)
            p.setOpacity(rise)
            moved = cell.translated(0, (1 - rise) * NEW_RISE * rh)
            t.text(p, moved, total_text(step.new), f, t.TEXT, RIGHT)
            p.restore()
        chip_f = t.font(max(f.pixelSize() * CHIP_TYPE, t.MIN_PX * u), t.HEAVY, tabular=True)
        w = t.text_width(step.text, chip_f) + CHIP_PAD * f.pixelSize()
        h = CHIP_HEIGHT * rh
        rect = QRectF(cell.right() - w, y + (rh - h) / 2, w, h)
        # A gain in the accent, a loss (a lap lost, a penalty) in the loss red.
        fill, ink = (t.ACCENT, t.ACCENT_INK) if step.gain else (t.OUT, t.TEXT)
        score_chip(p, rect, step.text, chip_f, fill, ink, ms, rh, u)

    def team_riders(self, p: QPainter, band: QRectF, e: Entry, lay: TeamTable) -> None:
        """A team's two riders side by side: their surnames, or with Bibs Only their plates.

        A rider with no bib yet is named with Bibs Only too, never shown
        an empty plate, as on the start list.
        """
        u = self.u
        for k, name in enumerate(e.names[:2]):
            x = lay.names_x + k * lay.half
            room = max(0.0, lay.half - team_rows.RIDER_GAP * u)
            bib = e.bibs[k] if k < len(e.bibs) else ""
            if self.bibs_only and bib:
                ph = lay.plate_h
                t.plate(p, QRectF(x, band.center().y() - ph / 2, t.plate_width(ph), ph), bib)
                continue
            last = team_rows.split_name(name)[1]
            rect = QRectF(x, band.y(), room, band.height())
            t.text(p, rect, t.elide(last, room, lay.surname_f), lay.surname_f, t.TEXT)

    def team_table_layout(self, area: QRectF, d: Standings, n: int, bottom: float) -> TeamTable:
        """The Madison table's rows, columns and fonts for this payload on this board.

        The rows share the page down to TEAM_FILL_LEAST rows' worth, each
        page set for a full page's rows. Every column and size is measured
        over every row, not the page's, so nothing moves as the page
        turns, and the sizes are decided as though a lap, a penalty, and
        ordinal places stood, so the first lap gained, the first penalty
        given, or the race being decided never steps the totals or the
        surnames down while the riders read them.
        """
        u = self.u
        # The rows take the page from its top: there is no heading row.
        rows_top = area.y()
        gap = team_rows.ROW_GAP * u
        rh = (bottom - rows_top - (n - 1) * gap) / max(n, TEAM_FILL_LEAST)
        # A PENALTY column opens only while a placed row carries one, as on
        # the rider table, and a status row opens none.
        penalized = any(r.penalty for r in d.rows if not r.status)
        ordinals = self.ordinals(d)

        def widest(strings, f: QFont) -> float:
            return max((t.text_width(s, f) for s in strings if s), default=0.0)

        places = [ordinal(r.rank) if ordinals else str(r.rank) for r in d.rows]
        decided = [ordinal(r.rank) for r in d.rows]
        totals = [total_text(r.total) for r in d.rows if not r.status]
        lasts = [team_rows.split_name(n)[1] for r in d.rows for n in r.entry.names[:2]]
        size = min(rh * TEAM_SURNAME_SHARE, team_rows.START_SURNAME_MOST * u)
        fig_gap = FIGURE_GAP * u
        total_r = area.right() - TEAM_FIGURE_PAD * u
        # The swatch's right edge leans right as it rises; a tall row's
        # surnames, and with Bibs Only its plates at their largest, step
        # right of it, a short row's stay where they are.
        shift = team_rows.slant_shift(rh, size, u)
        if self.bibs_only:
            most = min(rh * team_rows.BIBS_ONLY_PLATE_SHARE, team_rows.BIBS_ONLY_PLATE_MOST * u)
            shift = max(shift, team_rows.clearance(rh, most / 2, u))
        pad = (team_rows.SWATCH_W + team_rows.ROW_PAD) * u + shift

        def columns(big_px: float) -> dict:
            """The fonts and columns with the total at ``big_px``, and the surnames' room.

            The room is what a penalty and ordinal places would leave, so
            neither steps the surnames down when it comes.
            """
            total_f = t.font(big_px, t.HEAVY, tabular=True)
            # The laps and penalty keep pace with the total, never under the
            # floor and never past TEAM_LAPS_MOST; their reserved columns are
            # measured at that size, so the cap gives the surnames the width.
            laps_px = big_px * TEAM_LAPS_SHARE / TEAM_FIGURE_SHARE
            num_px = min(max(min(48 * u, rh * 0.7), laps_px), TEAM_LAPS_MOST * u)
            num = t.font(num_px, t.BOLD, tabular=True)
            # A column is as wide as its widest figure, the samples standing
            # in for a lap or a penalty not yet given. The feed leaves a
            # status row off the board; a page given one keeps the word
            # clear of the figures beside it.
            total_col = widest([*totals, *TOTAL_SAMPLES, *(r.status for r in d.rows)], total_f)
            shown_laps = [team_laps_text(r.laps) for r in d.rows if not r.status]
            shown_pens = [lap_text(r.penalty) for r in d.rows if not r.status]
            laps_col = widest([*shown_laps, *LAP_SAMPLES], num)
            pen_col = widest([*shown_pens, *PENALTY_SAMPLES], num)
            pen_r = total_r - total_col - fig_gap
            reserve_laps_r = pen_r - pen_col - fig_gap

            def place_column(shown: list[str]) -> tuple[QFont, float]:
                # The place matches the total's scale until its column would
                # pass TEAM_PLACE_SHARE of the page: a decided two-team field
                # sets "2nd" at a row's height, which would take the names' room.
                f = t.font(big_px * TEAM_PLACE_SCALE, t.HEAVY, tabular=True)
                most = area.width() * TEAM_PLACE_SHARE - 32 * u
                if widest(shown, f) > most:
                    f = t.font(f.pixelSize() * most / widest(shown, f), t.HEAVY, tabular=True)
                return f, max(80 * u, widest(shown, f) + 32 * u)

            place_f, rank_w = place_column(places)
            _f, reserve_rank_w = place_column([*places, *decided])
            zone_l = area.x() + reserve_rank_w + pad
            zone_r = reserve_laps_r - laps_col - COLOR_ZONE_GAP * u
            half = max(0.0, (zone_r - zone_l) / 2)
            return {
                "total_f": total_f,
                "num": num,
                "total_col": total_col,
                "laps_col": laps_col,
                "pen_col": pen_col,
                "pen_r": pen_r,
                "reserve_laps_r": reserve_laps_r,
                "place_f": place_f,
                "rank_w": rank_w,
                "room": max(0.0, half - team_rows.RIDER_GAP * u),
                "reserve_row_x": area.x() + reserve_rank_w,
                "reserve_zone_r": zone_r,
            }

        # The place and the total give way to the surnames: they step down
        # from their share of the row, never under TEAM_FIGURE_LEAST, until
        # the widest surname fits whole at its size. Only then does the
        # surnames' shared size shrink. The surnames are what the stands
        # match to the jerseys, and a small field's growth is for both.
        big_px = rh * TEAM_FIGURE_SHARE
        least = min(big_px, TEAM_FIGURE_LEAST * u)
        surname_f = t.font(size, t.HEAVY)
        cols = columns(big_px)
        while big_px > least and widest(lasts, surname_f) > cols["room"]:
            big_px = max(least, big_px * 0.96)
            cols = columns(big_px)
        total_f, num, place_f, rank_w = (
            cols["total_f"],
            cols["num"],
            cols["place_f"],
            cols["rank_w"],
        )
        total_col, laps_col, pen_col, pen_r = (
            cols["total_col"],
            cols["laps_col"],
            cols["pen_col"],
            cols["pen_r"],
        )
        room = cols["room"]
        laps_r = cols["reserve_laps_r"] if penalized else pen_r
        row_x = area.x() + rank_w
        zone_r = laps_r - laps_col - COLOR_ZONE_GAP * u
        names_x = row_x + pad
        half = max(0.0, (zone_r - names_x) / 2)
        floor_px = round(t.MIN_PX * u)
        scale = t.fit_scale([(s, room, surname_f) for s in lasts], floor=t.MIN_PX * u / size)
        surname_f = t.font(max(math.floor(size * scale), floor_px), t.HEAVY)
        # Text width is not exactly linear in pixel size (hinting).
        while surname_f.pixelSize() > floor_px and widest(lasts, surname_f) > room:
            surname_f = t.font(surname_f.pixelSize() - 1, t.HEAVY)
        plate_h = min(
            rh * team_rows.BIBS_ONLY_PLATE_SHARE,
            team_rows.BIBS_ONLY_PLATE_MOST * u,
            room / t.plate_width(1.0),
        )

        # The color view's team name: as large as its share of the row
        # while it fits the area, then smaller down to the floor, then cut.
        # Like the surnames and the plates, it is sized for the area a
        # penalty and ordinal places would leave, and placed in the area
        # drawn, so neither steps it down when it comes.
        # The room is inside the color's square left end and its slanted
        # right end where it crosses the row's middle, as the name is
        # placed (``team_row``).
        run = t.SLANT * rh
        label_room = (
            cols["reserve_zone_r"] - cols["reserve_row_x"] - 2 * team_rows.ROW_PAD * u - run / 2
        )
        labels = []
        for r in d.rows:
            name = r.entry.team or ""
            f = t.font(rh * TEAM_LABEL_SHARE, t.HEAVY)
            w = t.text_width(name, f)
            if w > label_room > 0:
                px = max(t.MIN_PX * u, f.pixelSize() * label_room / w)
                f = t.font(px, t.HEAVY)
                # Text width is not exactly linear in pixel size (hinting).
                while f.pixelSize() > round(t.MIN_PX * u) and t.text_width(name, f) > label_room:
                    f = t.font(f.pixelSize() - 1, t.HEAVY)
            labels.append((name, f))
        return TeamTable(
            rows_top=rows_top,
            rh=rh,
            gap=gap,
            row_x=row_x,
            rank_w=rank_w,
            place_f=place_f,
            total_f=total_f,
            num=num,
            total_r=total_r,
            total_col=total_col,
            pen_r=pen_r,
            pen_col=pen_col,
            laps_r=laps_r,
            laps_col=laps_col,
            penalized=penalized,
            zone_r=zone_r,
            names_x=names_x,
            half=half,
            surname_f=surname_f,
            plate_h=plate_h,
            labels=labels,
        )


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
# Between a place and its row on the result, as the table's place stands
# left of its row.
PLACE_GAP = 20
# The places the rows below the podium may show (FINISH_PLANS' last plan
# holds 27). Until a result is decided its place column is as wide as the
# widest of them, so the rows hold still while a Win-and-Out's bells
# decide its places; a decided result's places stand, so its column is as
# wide as they need.
REST_PLACES = range(4, 28)
# Between an entry and its row's rounded right end, as on a list's rows.
ROW_END_PAD = 18


class FinishPage(Page):
    """The result of a race placed by its finish: a podium of three, the rest in columns.

    Every place is a rider row (design section 10), its place standing
    left of it as on the table: the podium's bars are the accent, as
    1st is, and the rest are neutral. A points race never comes here:
    its standings table stays up to the end and reads as the result
    once stamped (``StandingsPage.ordinals``).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The page's growth over its base sizes (``growth``): every size
        # on the page is its base times this, so the podium and the rows
        # below it keep their proportions as a small result fills the page.
        self.g = 1.0
        # The last growth and what it was worked out for, as on the start list.
        self._growth: tuple[tuple, float] | None = None
        # The places the rows below the podium measure their column by.
        self.rest_places: list[int] | range = REST_PLACES

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
        decided = d.header.status in DECIDED
        self.rest_places = [pl.place for pl in rest] if decided and rest else REST_PLACES
        key = (area.width(), area.height(), u, self.rider_label, d)
        if self._growth is None or self._growth[0] != key:
            g = self.growth(area, d, podium, rest, big, cols)
            self._growth = ((*key[:-1], copy.deepcopy(d)), g)
        self.g = g = self._growth[1]
        big_h = big * u * g
        teams = any(pl.entry.color for pl in podium)
        entry = self.podium_rect(area, y, big, g, teams)
        self.team_fill = TEAM_FILL
        podium_scale = self.entry_scale(
            [pl.entry for pl in podium],
            entry,
            64 * u * g,
            False,
            laps=[pl.laps for pl in podium],
        )
        place_f = t.font(72 * u * g, t.HEAVY, tabular=True)
        dpr = self.devicePixelRatioF()
        for pl in podium:
            band = self.podium_band(area, y, big, g)
            bar = t.ACCENT.name()
            team_rows.paint_band(p, band, bar, u, slant=t.SLANT, texture=self.texture, dpr=dpr)
            color = t.ACCENT if pl.place == 1 else t.TEXT
            t.text(
                p,
                QRectF(area.x(), y, band.x() - area.x(), band.height()),
                ordinal(pl.place),
                place_f,
                color,
            )
            self.entry_line(
                p,
                entry.translated(0, y - area.y()),
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
        teams = any(pl.entry.color for pl in rest)
        # Blocks alone in two columns: at their names, so the lap chips
        # sit beside them rather than at the far end of a bar.
        self.team_fill = 0.0
        scale = self.entry_scale(
            [pl.entry for pl in rest],
            self._small_name_rect(QRectF(0, y, col_w, rh), teams),
            38 * u * g,
            False,
            laps=[pl.laps for pl in rest],
        )
        for i, pl in enumerate(rest):
            c, r = divmod(i, per_col)
            x = area.x() + c * (col_w + gap)
            ry = y + r * rh
            self.small_placing(p, QRectF(x, ry, col_w, rh), pl, scale, teams)

    def podium_band(self, area: QRectF, y: float, big: float, g: float) -> QRectF:
        """A podium row at growth ``g``: from just past the widest podium place to the page's edge."""
        u = self.u
        f = t.font(72 * u * g, t.HEAVY, tabular=True)
        left = area.x() + max(t.text_width(ordinal(k), f) for k in (1, 2, 3)) + PLACE_GAP * u * g
        return QRectF(left, y, area.right() - left, (big - 14) * u * g)

    def podium_rect(
        self, area: QRectF, y: float, big: float, g: float, teams: bool = False
    ) -> QRectF:
        """A podium entry at growth ``g``: its row less a margin, clear of the bar at its largest.

        The entry fills its row less a margin, so the podium's plates are
        a size with the names beside them.
        """
        u = self.u
        band = self.podium_band(area, y, big, g)
        h = (big - 28) * u * g
        lead = self.bar_lead(band.height(), h, 64 * u * g, teams)
        x = band.x() + lead
        return QRectF(x, y + 7 * u * g, max(0.0, band.right() - ROW_END_PAD * u - x), h)

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
        teams = any(pl.entry.color for pl in podium)
        rest_teams = any(pl.entry.color for pl in alone)

        def rest_h(g: float) -> float:
            below = area.bottom() - area.y() - (3 * big + 30) * u * g
            return min(84 * u * g, below / per_col)

        while g > 1.0:
            # The name's own rect, less its margin, as well as the band.
            if alone and rest_h(g) - 12 * u * g < rest_h(1.0) - 12 * u:
                g = max(1.0, g * 0.96)
                continue
            self.team_fill = TEAM_FILL
            whole = (
                self.entry_scale(
                    [pl.entry for pl in podium],
                    self.podium_rect(area, 0, big, g, teams),
                    64 * u * g,
                    False,
                    laps=[pl.laps for pl in podium],
                )
                >= 1.0
            )
            if whole and alone:
                self.g = g
                self.team_fill = 0.0
                rest_rect = self._small_name_rect(QRectF(0, 0, col_w, rest_h(g)), rest_teams)
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

    def _rest_place_font(self) -> QFont:
        return t.font(38 * self.u * self.g, t.BOLD, tabular=True)

    def rest_band(self, r: QRectF) -> QRectF:
        """The row below the podium in the slot ``r``: past the widest place, to the column's end."""
        f = self._rest_place_font()
        place_w = max(t.text_width(ordinal(k), f) for k in self.rest_places)
        left = r.x() + place_w + PLACE_GAP * self.u * self.g
        gap = band_gap(r.height(), self.u)
        return QRectF(left, r.y() + gap / 2, r.right() - left, r.height() - gap)

    def _small_name_rect(self, r: QRectF, teams: bool = False) -> QRectF:
        u = self.u * self.g
        band = self.rest_band(r)
        h = r.height() - 12 * u
        x = band.x() + self.bar_lead(band.height(), h, 38 * u, teams)
        return QRectF(x, r.y() + 6 * u, max(0.0, band.right() - ROW_END_PAD * self.u - x), h)

    def small_placing(
        self, p: QPainter, r: QRectF, pl: Placing, scale: float, teams: bool = False
    ) -> None:
        u = self.u * self.g
        band = self.rest_band(r)
        # A rider tied onto the podium below its first three rows is on
        # the podium, so takes its accent.
        team_rows.paint_band(
            p,
            band,
            t.ACCENT.name() if pl.place <= 3 else team_rows.RIDER_BAR,
            self.u,
            slant=t.SLANT,
            texture=self.texture,
            dpr=self.devicePixelRatioF(),
        )
        t.text(
            p,
            QRectF(r.x(), r.y(), band.x() - r.x(), r.height()),
            ordinal(pl.place),
            self._rest_place_font(),
            t.MUTED,
        )
        self.entry_line(
            p,
            self._small_name_rect(r, teams),
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
