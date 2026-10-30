"""The cards: one per rider or team in the field, a click does the task.

A card is large and plain (design section 7): the bib on a plate and
the name beside it at the same size, because a call over the radio
comes as either and the scorer must find the rider from either at a
glance; a team card shows the color and the team's name on one line,
as a rider card shows its plate and name: its riders are listed in the
standings beside the cards. The badge is the place a click gave it in the
sprint being built, just left of the card's buttons so they never
overlap. The actions button is a full-height strip along the card's
right edge, a target as big as the card allows without stealing the
card's own click; it opens the actions on that rider, and so does a
right-click (or a long press) anywhere on the card, as a second way to
the same visible menu and never the only one; the
right button never places. Where laps count, +1 and −1 buttons sit beside
the strip: a lap is routine in a points race or a madison and
earns one click, so the menu keeps only the rare actions and each
action has one place. A rider with laps gained or lost shows them as a
chip beside the name, because before the finish the rider has no row in
the result to show them. The rest of the card opens no menu on a left
click, because that click is the entry.

A rider placed, out, or marked keeps a done card in the same slot until
the result completes, so no card moves under the scorer's finger: the
pale gray ground, the plate and the name dimmed, no lap buttons, and the
place in the badge's full blue or the status's short word in a chip of
the lap chip's shape. A click on it records nothing and the red line
says why; its ⋯ is the rider's result row's menu.

Every size comes from the font's line height, so the card is the same
shape on Windows, macOS and Linux. The grid picks its column count from
the width a card needs to show a name whole, because the scorer takes
calls by name and a cut name costs a look at the bib.
"""

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QMenu, QScrollArea, QToolButton, QWidget
from shiboken6 import isValid

from madtracker.board.payloads import lap_text, lap_words
from madtracker.control.race import BREAK_TIE, MOVE_TO, REVIEW_ACTIONS, Card
from madtracker.ui import style, widgets
from madtracker.ui.icons import mdi
from madtracker.ui.widgets import DOTS_PX, OneClickButton, OneClickToolButton, fill_menu

# Qt's own "no maximum".
QWIDGETSIZE_MAX = 16777215
NAME_PT = 15
# The type a card may grow to when it has the column's height (side by side).
NAME_PT_BASE = 15
NAME_PT_MAX = 24
MEMBER_PT = 12.5


def member_pt() -> float:
    """The lap chip: MEMBER_PT at the base type, grown with the card's type.

    Fixed at 12.5 it would stay small while a scaled card's name grew.
    """
    return MEMBER_PT * NAME_PT / NAME_PT_BASE


CARD_MIN_W = 220
# Between a team card's color line and its riders.
# A name of 16 characters, typical of a field's longer names; measured in
# the card's own font so the card's width follows the face.
NAME_SAMPLE = "Rosalind Vasquez"
# A full card is 2.6 name lines tall; a field too tall for the grid's cap
# gets shorter cards, down to the plate with SM above and below, before
# the grid scrolls.
FULL_LINES = 2.6
INK = QColor(style.INK)
DIM = QColor(style.DIM)
WHITE = QColor("#ffffff")
# A dark plate with white digits, like the number a rider wears, so the
# bib stands out of a white card as much as the name beside it.
PLATE = QColor(style.INK)
# A place badge past the places a sprint awards, in the window's disabled gray.
PAST_PLACES_BADGE = style.DISABLED_INK
PAST_PLACES_TIP = "Past the places this sprint awards: no points. Click to take it off."
PLATE_DIGITS = WHITE
# A rider with no bib yet: an empty plate with a dashed edge.
PLATE_EDGE = QColor("#b8bec7")
# A done card's plate, in the window's disabled gray: the number stays
# readable in white, and the plate no longer stands out as a live one's.
DONE_PLATE = QColor(style.DISABLED_INK)
# A done team card's swatch, washed with the gray ground: the color still
# names the team, without the weight of a team still in play.
DONE_SWATCH_ALPHA = 110
# A done card's place badge, the accent washed over the gray ground: the
# full blue reads as a live sprint's badge, the dimmed one as a place taken.
DONE_BADGE_ALPHA = 140
# The lap actions are buttons on the card, never items in its menu. The
# label's minus is the minus sign, as wide as the plus, so the two
# buttons read as a pair.
LAP_KEYS = ("lap_gained", "lap_lost")
LAP_LABELS = {"lap_gained": lap_text(1), "lap_lost": lap_text(-1)}
LAP_TIPS = {"lap_gained": "Gained a lap", "lap_lost": "Lost a lap"}
# The window's smallest text: a lap label never goes below it, and a
# card too short for two lines of it grows instead.
LAP_MIN_PT = 12


def _line(pt: float) -> int:
    return QFontMetrics(style.ui_font(pt, bold=True)).height()


def _name_metrics() -> QFontMetrics:
    return QFontMetrics(style.ui_font(NAME_PT, bold=True))


def plate_height() -> float:
    return _line(NAME_PT) * 1.15


def plate_width(bib: str) -> float:
    """The bib plate: a 1.5 to 1 plate, wider only for a bib that would not fit."""
    return max(plate_height() * 1.5, _name_metrics().horizontalAdvance(bib) + style.MD)


def badge_side() -> int:
    return round(_line(NAME_PT) * 1.3)


def card_want_width(
    laps: bool = False, teams: Sequence[str] = (), names: Sequence[str] = ()
) -> int:
    """The width at which a card shows a two-digit bib, NAME_SAMPLE whole and a badge.

    The same with or without the lap column: a card without one gives
    its width to the actions strip. ``laps`` is kept for the callers
    that name the field they measure. ``teams`` is a field of team
    cards' names: those cards are a swatch and the team's name, so the
    longest name sets the width, and short ones ("Blue", "Red") sit two
    to a row where a rider's 16 characters would not. ``names`` are the
    riders' names on the cards: one longer than the sample widens the
    cards so it shows whole, and the grid loses a column rather than
    the scorer the end of a name.
    """
    if teams:
        lead = _line(NAME_PT)
        text = max(_name_metrics().horizontalAdvance(t) for t in teams)
        # The lap chip may sit on the name's line too.
        text += (
            QFontMetrics(style.ui_font(member_pt(), bold=True)).horizontalAdvance(lap_words(-2))
            + 3 * style.SM
        )
    else:
        lead = round(plate_width("88"))
        metrics = _name_metrics()
        text = max(metrics.horizontalAdvance(n) for n in (NAME_SAMPLE, *names))
    return (
        style.MD
        + lead
        + style.SM
        + text
        + style.SM
        + badge_side()
        + style.SM
        + strip_width(True)
        + laps_width()
        + 1
    )


def full_card_height() -> int:
    return round(_line(NAME_PT) * FULL_LINES)


def short_card_height(laps: bool = False) -> int:
    """The shortest card: never so short that its buttons fall under a finger's size.

    ``laps`` is kept for the callers that name the field they measure;
    side by side, the lap buttons are the card's height, as the strip is.
    """
    # The card's border takes 3 px of the buttons' height (1 top, 2 bottom).
    return max(round(plate_height()) + 2 * style.SM, style.TOUCH + 3)


def strip_width(laps: bool = True) -> int:
    """The actions strip: TOUCH wide, the only door to the card's menu.

    A little under a name line, 20 px at 1366, would be too narrow for
    a finger on the scorer's touchscreen. ``laps`` is
    kept for the callers that name the field they measure.
    """
    return max(style.TOUCH, round(_line(NAME_PT) * 0.85))


def dots_side() -> int:
    """The ⋯ glyph: the result row's DOTS_PX at the base type, grown with the card's type.

    The glyph keeps inside its strip, which stays a finger wide.
    """
    return min(round(DOTS_PX * NAME_PT / NAME_PT_BASE), strip_width())


def lap_width() -> int:
    """One lap button: TOUCH_LAP wide, at least a third wider than a name line.

    -1 and +1 sit side by side, each the card's full height. Stacked,
    each would be half a card, about 30 px at 1366, under a finger's
    size; side by side the card keeps its height.
    """
    return max(style.TOUCH_LAP, round(_line(NAME_PT) * 4 / 3))


def laps_width() -> int:
    """Both lap buttons: the room the lap column takes on a card."""
    return 2 * lap_width()


def lap_pt(half: int) -> float:
    """The largest bold size, up to a point under the name's, that fits a lap button.

    The label fits the button's height and width, leaving XS each side,
    so it reads centered rather than touching the dividers.
    """
    room = lap_width() - 2 * style.XS

    def wide(pt: float) -> int:
        return QFontMetrics(style.ui_font(pt, bold=True)).horizontalAdvance(lap_text(-1))

    pt = NAME_PT - 1
    while pt > LAP_MIN_PT and (_line(pt) > half or wide(pt) > room):
        pt -= 0.5
    return pt


def chip_font() -> QFont:
    """The chip's type: the lap chip's and the status chip's, so the two read as one mark."""
    return style.ui_font(member_pt(), bold=True)


def chip_size(text: str) -> QSize:
    """A chip around ``text``: SM each side, XS taller than the line."""
    metrics = QFontMetrics(chip_font())
    return QSize(metrics.horizontalAdvance(text) + 2 * style.SM, metrics.height() + style.XS)


def draw_chip(p: QPainter, rect: QRect, text: str, ink: QColor) -> None:
    """A chip: ``text`` on white in a rounded outline, both in ``ink``, so it reads as a tag.

    The lap chip on a live card and the status chip on a done one; the
    ink is what tells them apart.
    """
    p.setPen(QPen(ink, 1))
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
    p.setFont(chip_font())
    p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)


def lap_button(parent: QWidget, key: str) -> QToolButton:
    """+1 or −1 beside the strip; style.py draws its divider and hover."""
    b = OneClickToolButton(parent)
    b.setObjectName("cardLap")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setFont(style.ui_font(LAP_MIN_PT, bold=True))
    b.setText(LAP_LABELS[key])
    b.setToolTip(LAP_TIPS[key])
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    return b


def actions_strip(parent: QWidget) -> QToolButton:
    """The ⋯ strip on a card's right edge; style.py draws its divider and hover."""
    b = QToolButton(parent)
    b.setObjectName("cardActions")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    side = dots_side()
    b.setIcon(mdi("dots-horizontal", side, DIM.name()))
    b.setIconSize(QSize(side, side))
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    return b


def card_laps(card: Card) -> bool:
    """Whether the card shows +1 and −1: where laps count, and never on a done card.

    A done rider's laps are in their result row; the buttons on a card
    that takes no click would be the one live thing on it.
    """
    keys = {k for k, _ in card.actions}
    return not card.done and all(k in keys for k in LAP_KEYS)


def menu_items(card: Card) -> list[tuple[str, str]]:
    """The card's ⋯ items as the menu words them: no laps, and Break Tie on a shared badge.

    The lap actions are the card's own buttons. Moving up a rider who
    shares a place takes them out of the tie and passes nobody, so it
    reads Break Tie, as the result row's does (review.row_menu).
    """
    items = [(k, label) for k, label in card.actions if k not in LAP_KEYS]
    if card.tied:
        items = [(k, BREAK_TIE if k == "move_up" else label) for k, label in items]
    return items


class RiderCard(OneClickButton):
    """One rider or team. ``pressed_entrant`` is the task click; ``action`` a menu pick."""

    pressed_entrant = Signal(int)
    action = Signal(int, str)

    def __init__(self, card: Card, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.card = card
        self.setObjectName("rider")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumWidth(CARD_MIN_W)
        self._height = self.card_height()
        self.setFixedHeight(self._height)
        self.clicked.connect(self._task_click)
        self.laps = card_laps(card)
        self.menu_actions = menu_items(card)
        self._set_done(card)
        self.lap_up = lap_button(self, "lap_gained")
        self.lap_down = lap_button(self, "lap_lost")
        # -1 then +1, left to right, as a stepper reads.
        for button, key in ((self.lap_up, "lap_gained"), (self.lap_down, "lap_lost")):
            button.setVisible(self.laps)
            button.clicked.connect(lambda _=False, k=key: self.action.emit(self.card.entrant_id, k))
        self.dots = actions_strip(self)
        self.dots.setVisible(bool(self.menu_actions))
        self.dots.clicked.connect(lambda: self.open_actions())

    def _task_click(self) -> None:
        # A done card's result is taken, so its click does nothing at all:
        # no task, and no red line answering a click the card never invites.
        if not self.card.done:
            self.pressed_entrant.emit(self.card.entrant_id)

    def set_card(self, card: Card) -> None:
        """The same entrant after a click: badge, laps, names and actions as the card now says.

        Everything the card shows is drawn from ``card`` in paintEvent or
        set here, so the card reads exactly as a new one built from it.
        """
        self.card = card
        laps = card_laps(card)
        self.menu_actions = menu_items(card)
        self._set_done(card)
        if laps != self.laps:
            self.laps = laps
            self.lap_up.setVisible(laps)
            self.lap_down.setVisible(laps)
            self._place_buttons()
        self.dots.setVisible(bool(self.menu_actions))
        self.update()

    def _set_done(self, card: Card) -> None:
        """The done look, cursor and tooltip, or the live ones, as ``card`` says.

        The style sheet's [done] rule is read again only on a fresh
        polish of this card, as set_lit does for [lit]. A done card takes
        no task click, so the pointer is the arrow over it; its tooltip
        is the status's long name, as the chip shows the short word.
        """
        if card.done:
            tip = card.done_tip
        else:
            tip = PAST_PLACES_TIP if card.past_awarded else ""
        if self.toolTip() != tip:
            self.setToolTip(tip)
        hand = Qt.CursorShape.ArrowCursor if card.done else Qt.CursorShape.PointingHandCursor
        if self.cursor().shape() != hand:
            self.setCursor(hand)
        if bool(self.property("done")) == card.done:
            return
        self.setProperty("done", card.done)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_height(self, height: int) -> None:
        """A height the grid chose for this card, kept through the style sheet's polish."""
        if height != self._height or self.height() != height:
            self._height = height
            self.setFixedHeight(height)

    def card_height(self) -> int:
        """A rider's or a team's card alike: one line, the grid chooses the height."""
        return full_card_height()

    def contextMenuEvent(self, event) -> None:
        if not self.menu_actions:
            event.ignore()
            return
        event.accept()
        self.open_actions(event.globalPos())

    def open_actions(self, where: QPoint | None = None) -> None:
        """The card's ⋯ menu, under the strip or at ``where`` (a right-click).

        The card stays lit while the menu is open, so the menu says whose
        it is.
        """
        if not self.menu_actions:
            return
        menu = QMenu(self)
        # Tapped on the touchscreen: TOUCH-tall items (style.py).
        menu.setObjectName("touchMenu")
        # The long moves fold into one submenu of places, where the first
        # of them sits, so a six-rider sprint's menu stays short.
        fill_menu(
            menu,
            self.menu_actions,
            lambda key: self.action.emit(self.card.entrant_id, key),
            fold=(MOVE_TO, REVIEW_ACTIONS["move_to"], "Move to "),
        )
        if where is None:
            where = self.dots.mapToGlobal(QPoint(0, self.dots.height()))
        self.set_lit(True)
        try:
            widgets.run_menu(menu, where)
        finally:
            # The chosen action can rebuild the grid and delete this card
            # before the menu's loop returns (the pick that completes the
            # result takes the cards away), so the look comes back only on
            # a card still alive.
            if isValid(self):
                self.set_lit(False)

    def set_lit(self, lit: bool) -> None:
        """The open-menu look, through the style sheet's [lit] rule."""
        if bool(self.property("lit")) == lit:
            return
        self.setProperty("lit", lit)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_buttons()

    def _place_buttons(self) -> None:
        # Inside the card's border (1 px, 2 px along the bottom shade), so
        # the strip's rounded corners follow the card's and its divider
        # runs border to border. The lap buttons run the same height, side
        # by side, -1 then +1, so each is a finger's size.
        w = strip_width(self.laps)
        x = self.width() - 1 - w
        h = self.height() - 3
        self.dots.setGeometry(x, 1, w, h)
        # The ⋯ glyph grows with the card's type, as the name and the
        # lap labels do; made once at the base size, it would read as a speck
        # on a scaled card.
        side = dots_side()
        if self.dots.iconSize().width() != side:
            self.dots.setIcon(mdi("dots-horizontal", side, DIM.name()))
            self.dots.setIconSize(QSize(side, side))
        lw = lap_width()
        self.lap_down.setGeometry(x - 2 * lw, 1, lw, h)
        self.lap_up.setGeometry(x - lw, 1, lw, h)
        font = style.ui_font(lap_pt(h), bold=True)
        for b in (self.lap_up, self.lap_down):
            b.setFont(font)

    def _dots_left(self, width: int | None = None) -> int:
        """Where the card's buttons start; near the card's right edge when it has none.

        ``width`` measures a card not yet resized: the grid asks what a
        card would show at the width a column will give it.
        """
        w = self.width() if width is None else width
        if self.laps:
            return w - 1 - strip_width() - laps_width()
        if self.menu_actions:
            return w - 1 - strip_width(False)
        return w - style.XS

    def badge_text(self) -> str:
        """The place, the same number on both cards of a dead heat.

        The table, the sheet, the board, and the CSV all repeat the number
        for a shared place (1, 1, 3), so the badge does too; the Break Tie
        item is what says the place is shared. A done card
        shows its place or its status word here.
        """
        if self.card.done:
            return self.card.done_text
        if not self.card.badge:
            return ""
        return str(self.card.badge)

    def badge_rect(self, width: int | None = None) -> QRect | None:
        """The place badge, left of the card's buttons so they never overlap.

        A circle; a pill as tall when the text needs more width ("10").
        A done card's status sits here as a chip, right-aligned where the
        badge would end, centered on the card.
        """
        text = self.badge_text()
        if not text:
            return None
        if self.card.done and self.card.done_status:
            size = chip_size(text)
            right = self._dots_left(width) - style.SM
            top = (self.height() - size.height()) // 2
            return QRect(right - size.width(), top, size.width(), size.height())
        r = badge_side()
        metrics = QFontMetrics(style.ui_font(NAME_PT - 2, bold=True))
        w = max(r, metrics.horizontalAdvance(self.badge_text()) + style.SM * 2)
        bx = self._dots_left(width) - style.SM - w
        by = (self.height() - r) // 2
        return QRect(bx, by, w, r)

    def chip_text(self) -> str:
        """The rider's net laps in words, empty when even or done (the result row has them)."""
        if self.card.done:
            return ""
        return lap_words(self.card.laps)

    def chip_rect(self, width: int | None = None) -> QRect | None:
        """The lap chip, left of the badge on the name's line; the name gives way, never the chip."""
        text = self.chip_text()
        if not text:
            return None
        size = chip_size(text)
        w, h = size.width(), size.height()
        badge = self.badge_rect(width)
        right = (badge.left() if badge is not None else self._dots_left(width)) - style.SM
        line_top = (self.height() - _line(NAME_PT)) // 2
        line_h = _line(NAME_PT)
        return QRect(right - w, line_top + (line_h - h) // 2, w, h)

    def _text_right(self, width: int | None = None) -> int:
        badge = self.badge_rect(width)
        if badge is not None:
            # The text stops short of the badge.
            return badge.left() - style.SM
        return self._dots_left(width) - style.SM

    def _name_right(self, width: int | None = None) -> int:
        """Where the name or the team's name stops: short of the chip, else of the badge."""
        chip = self.chip_rect(width)
        if chip is not None:
            return min(chip.left() - style.SM, self._text_right(width))
        return self._text_right(width)

    def team_name_fits(self, width: int) -> bool:
        """Whether a team's name shows whole on a card ``width`` wide at NAME_PT as set now.

        A rider card is measured by the grid's sample name; a team card
        has the team's own name, beside its swatch, and a scale the
        sample passes can still cut "Stars and Stripes" to "Stars an...".
        """
        e = self.card.entry
        if not e.color:
            return True
        swatch = _line(NAME_PT)
        room = self._name_right(width) - (style.MD + swatch + style.SM)
        return _name_metrics().horizontalAdvance(e.team or "") <= room

    def _bib_name(self) -> tuple[str, str]:
        e = self.card.entry
        return (e.bibs[0] if e.bibs else "", e.names[0] if e.names else "")

    def _name_left(self) -> float:
        return style.MD + plate_width(self._bib_name()[0]) + style.SM

    def name_room(self) -> int:
        """The width the name gets between the plate and the chip, the badge or the buttons."""
        return int(self._name_right() - self._name_left())

    def shown_name(self) -> str:
        """The rider's name as the card draws it, elided when the card is too narrow."""
        name = self._bib_name()[1]
        return _name_metrics().elidedText(name, Qt.TextElideMode.ElideRight, self.name_room())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        e = self.card.entry
        name_font = style.ui_font(NAME_PT, bold=True)
        lh = _line(NAME_PT)
        x = style.MD
        badge = self.badge_rect()
        done = self.card.done
        ink = DIM if done else INK
        left_mid = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if e.color:
            # One line, centered as a rider card's plate and name are; the
            # riders are in the standings beside the cards.
            top = (self.height() - lh) / 2
            # A swatch as tall as the team's name, the same chip the result
            # table and the scoreboard show, so the color is found the same
            # way everywhere (a bar down the card's edge would read as decoration).
            swatch = lh
            p.setPen(QPen(QColor(0, 0, 0, 90), 1))
            color = QColor(e.color)
            if done:
                color.setAlpha(DONE_SWATCH_ALPHA)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, top, swatch, swatch), 5, 5)
            p.setPen(ink)
            p.setFont(name_font)
            team_right = self._name_right()
            team_rect = QRectF(x + swatch + style.SM, top, team_right - x - swatch - style.SM, lh)
            team = QFontMetrics(name_font).elidedText(
                e.team or "", Qt.TextElideMode.ElideRight, int(team_rect.width())
            )
            p.drawText(team_rect, left_mid, team)
        else:
            # The plate and the name share one line and one size.
            bib = self._bib_name()[0]
            plate_h = plate_height()
            plate_w = plate_width(bib)
            top = (self.height() - plate_h) / 2
            # A rider with no bib yet keeps the plate, so the names stay in
            # line, and the dashed edge shows the scorer whose number is missing.
            plate = QRectF(x, top, plate_w, plate_h)
            if bib:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(DONE_PLATE if done else PLATE)
            else:
                p.setPen(QPen(PLATE_EDGE, 1, Qt.PenStyle.DashLine))
                p.setBrush(WHITE)
            p.drawRoundedRect(plate, 5, 5)
            p.setFont(name_font)
            p.setPen(PLATE_DIGITS)
            p.drawText(plate, int(Qt.AlignmentFlag.AlignCenter), bib)
            p.setPen(ink)
            text_x = self._name_left()
            name_w = self._name_right() - text_x
            p.drawText(QRectF(text_x, top, name_w, plate_h), left_mid, self.shown_name())
        chip = self.chip_rect()
        if chip is not None:
            # Green for a lap gained, red for a lap lost: the window's own
            # OK and danger colors, on white so the chip reads as a tag.
            lap_ink = QColor(style.OK_GREEN if self.card.laps > 0 else style.DANGER)
            draw_chip(p, chip, self.chip_text(), lap_ink)
        if badge is not None and done and self.card.done_status:
            # A status is a note, not a place: the lap chip's shape, in the
            # dim ink of a card that takes no click.
            draw_chip(p, badge, self.badge_text(), DIM)
        elif badge is not None:
            p.setPen(Qt.PenStyle.NoPen)
            # Gray past the places the sprint awards: clicked, but no points.
            # A done card's place is the accent dimmed, with white digits, so a
            # blue number means a place on every card of every format and the
            # full blue stays the live sprint's.
            fill = QColor(PAST_PLACES_BADGE if self.card.past_awarded else style.ACCENT)
            if done and not self.card.past_awarded:
                fill.setAlpha(DONE_BADGE_ALPHA)
            p.setBrush(fill)
            radius = badge.height() / 2
            p.drawRoundedRect(QRectF(badge), radius, radius)
            p.setPen(QColor("#ffffff"))
            p.setFont(style.ui_font(NAME_PT - 2, bold=True))
            p.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), self.badge_text())
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(CARD_MIN_W, self._height)


class CardGrid(QScrollArea):
    """The cards in rows that follow the width, scrolling only past a full field."""

    pressed_entrant = Signal(int)
    action = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Before setWidget, which already routes events through eventFilter.
        self._watched: QWidget | None = None
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("central")
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(style.SM)
        self.setWidget(self.body)
        self.cards: list[RiderCard] = []
        self._columns = 0
        # The most the surface lets the cards have so the result table
        # below them stays readable; None while there is no result yet.
        self.limit: int | None = None
        # Beside the table rather than above it: the grid takes the
        # column's whole height and scrolls past it, and nothing caps a
        # card's height.
        self.fill = False

    def set_cards(self, cards: list[Card]) -> None:
        """Show these cards: an entrant's card already shown takes its new state in place.

        A click changes a card's badge or laps, or turns a card done in its
        slot (a rider placed or eliminated); making a new card per entrant on
        every click would style 40 to 50 new widgets against the style sheet
        each time, the work Windows is slowest at. A card is kept only for
        the same entrant and the same kind (rider or team), and
        ``RiderCard.set_card`` makes it read as a new one would.
        """
        ids = [c.entrant_id for c in cards]
        shown = {w.card.entrant_id: w for w in self.cards}
        if len(set(ids)) != len(ids) or len(shown) != len(self.cards):
            shown = {}
        same_order = ids == [w.card.entrant_id for w in self.cards]
        widgets = []
        for card in cards:
            w = shown.pop(card.entrant_id, None)
            if w is not None and bool(w.card.entry.color) == bool(card.entry.color):
                w.set_card(card)
            else:
                if w is not None:
                    self._drop(w)
                w = RiderCard(card, self.body)
                w.pressed_entrant.connect(self.pressed_entrant)
                w.action.connect(self.action)
                same_order = False
            widgets.append(w)
        kept = {id(w) for w in widgets}
        for w in self.cards:
            if id(w) not in kept:
                self._drop(w)
        self.cards = widgets
        if not same_order:
            # The cards are laid out again in their new places.
            self._columns = 0
        self._flow()
        self._size_cards()
        self._fit_height()

    def _drop(self, card: "RiderCard") -> None:
        # Hidden and unparented now: deleteLater runs on the next turn
        # of the event loop, and a card that lingers until then would
        # paint under the new field.
        self.grid.removeWidget(card)
        card.hide()
        card.setParent(None)
        card.deleteLater()

    def needed_height(self) -> int:
        """The height of every row of cards at the current width."""
        if not self.cards:
            return 0
        cols = self.columns()
        rows = (len(self.cards) + cols - 1) // cols
        # The height the grid chose, not the one the card has now: the
        # style sheet's min-height lets a layout squeeze a card below it.
        tallest = max(c.sizeHint().height() for c in self.cards)
        return rows * tallest + (rows - 1) * style.SM + 2

    def _want(self) -> int:
        """card_want_width for the cards shown, at NAME_PT as set now."""
        teams = [c.card.entry.team or "" for c in self.cards if c.card.entry.color]
        names = [
            c.card.entry.names[0]
            for c in self.cards
            if not c.card.entry.color and c.card.entry.names
        ]
        return card_want_width(
            any(c.laps for c in self.cards),
            teams if teams and len(teams) == len(self.cards) else (),
            names,
        )

    def _riders_shown(self) -> bool:
        return any(not c.card.entry.color for c in self.cards)

    def columns(self) -> int:
        """The most columns whose cards still show a name whole; one at the least."""
        width = max(self.viewport().width(), CARD_MIN_W)
        return max(1, min(6, (width + style.SM) // (self._want() + style.SM)))

    def least_width(self, width: int, height: int) -> int:
        """The narrowest the cards may be in a column ``width`` by ``height``.

        As many columns as ``width`` gives at the base type, each as
        wide as the cards' names want: narrower would cut a name or lose
        a column. Past it the type grows into the room.
        """
        global NAME_PT
        if not self.cards:
            return CARD_MIN_W
        shown = NAME_PT
        try:
            NAME_PT = NAME_PT_BASE
            want = self._want()
            cols = max(1, min(6, (width + style.SM) // (want + style.SM)))
            rows = (len(self.cards) + cols - 1) // cols
            tall = rows * full_card_height() + (rows - 1) * style.SM + 2
        finally:
            NAME_PT = shown
        # A field taller than the column scrolls, and the scroll bar
        # takes its width from the cards.
        bar = 0 if tall <= height else self.verticalScrollBar().sizeHint().width()
        return min(width, cols * want + (cols - 1) * style.SM + bar)

    def set_limit(self, limit: int | None) -> None:
        if limit == self.limit:
            return
        self.limit = limit
        self._size_cards()
        self._fit_height()

    def _cap(self) -> int | None:
        # Only the rows that exist, so the result table gets the rest of
        # the surface; a field too tall for 60% of the window scrolls here
        # (with finger-sized buttons a 16-rider start list at 1366 by 768
        # needs that much).
        if self.fill or not self.window():
            return None
        cap = max(200, int(self.window().height() * 0.6))
        if self.limit is not None:
            # Once there are standings to read the table keeps its rows:
            # the cards go short and then scroll, but always show one row.
            laps = any(c.laps for c in self.cards)
            cap = min(cap, max(self.limit, short_card_height(laps) + 2))
        return cap

    def _fit_scale(self) -> None:
        """Side by side, the cards grow into the column: the largest type whose rows fit.

        The whole card scales with its name line (plate, badge, lap
        buttons, strip), so a 1920 display gets cards a scorer reads and
        taps from arm's length instead of five short rows over empty
        space. Not past NAME_PT_MAX, and never so
        wide that a column loses a whole name.
        """
        global NAME_PT
        want = NAME_PT_BASE
        if self.fill and self.cards:
            room_h = self.viewport().height()
            room_w = self.viewport().width()
            cols_at_base = None
            for pt in range(NAME_PT_MAX, NAME_PT_BASE - 1, -1):
                NAME_PT = pt
                self._columns = 0
                cols = self.columns()
                if cols_at_base is None:
                    NAME_PT = NAME_PT_BASE
                    cols_at_base = self.columns()
                    NAME_PT = pt
                rows = (len(self.cards) + cols - 1) // cols
                # A team card is as tall as its member lines, which grow
                # with the type too; the rows are as tall as the tallest.
                tallest = max(c.card_height() for c in self.cards)
                # The width a column gives each card: a team's name must
                # show whole there, as the sample name does.
                card_w = (room_w - (cols - 1) * style.SM) // cols
                # A rider's name too: one column is the least the grid
                # gives, so a long name at a larger type would be cut.
                if (
                    cols >= cols_at_base
                    and rows * tallest + (rows - 1) * style.SM + 2 <= room_h
                    and all(c.team_name_fits(card_w) for c in self.cards)
                    and (not self._riders_shown() or self._want() <= card_w)
                ):
                    want = pt
                    break
        if NAME_PT != want:
            NAME_PT = want
            self._columns = 0
            for card in self.cards:
                card.update()
        self._flow()

    def _size_cards(self) -> None:
        # Wide cards mean fewer columns and more rows, so a big field
        # trades vertical padding for rows before it scrolls. The plate
        # and the name, or the swatch and the team, keep their size.
        self._fit_scale()
        riders = list(self.cards)
        if not riders:
            return
        height = full_card_height()
        cap = self._cap()
        if cap is not None:
            cols = self.columns()
            rows = (len(self.cards) + cols - 1) // cols
            room = (cap - 2 - (rows - 1) * style.SM) // rows
            laps = any(c.laps for c in self.cards)
            height = max(short_card_height(laps), min(height, room))
        for card in riders:
            card.set_height(height)

    def _flow(self) -> None:
        cols = self.columns()
        if cols == self._columns and self.grid.count() == len(self.cards):
            return
        self._columns = cols
        while self.grid.count():
            self.grid.takeAt(0)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // cols, i % cols)
        # A column left stretched by an earlier, wider flow would hold an
        # empty share of the width and keep the cards narrow.
        for c in range(max(cols, self.grid.columnCount()) + 1):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)
        rows = (len(self.cards) + cols - 1) // cols
        # A stretch left on a row by an earlier, wider flow would squeeze
        # that row's cards (the style sheet's min-height lets them shrink).
        for r in range(self.grid.rowCount() + 1):
            self.grid.setRowStretch(r, 0)
        self.grid.setRowStretch(max(rows, 0), 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._flow()
        self._size_cards()
        self._fit_height()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The cap follows the window's height, and a taller window does
        # not resize the grid on its own; watching the window lets short
        # cards grow back.
        top = self.window()
        if top is not self and top is not self._watched:
            if self._watched is not None:
                self._watched.removeEventFilter(self)
            top.installEventFilter(self)
            self._watched = top

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._watched and event.type() == QEvent.Type.Resize:
            self._size_cards()
            self._fit_height()
        return super().eventFilter(obj, event)

    def _fit_height(self) -> None:
        need = self.needed_height()
        if self.fill:
            self.setMinimumHeight(0)
            self.setMaximumHeight(QWIDGETSIZE_MAX)
            self.body.setMinimumHeight(need)
            return
        cap = self._cap() or need
        if need > cap:
            # A scrolling grid shows whole rows; the part row it would cut
            # goes to the result table below.
            step = max(c.sizeHint().height() for c in self.cards) + style.SM
            cap = max(1, (cap - 2 + style.SM) // step) * step - style.SM + 2
        # A floor as well as a ceiling: with only a ceiling the layout would
        # give the grid a couple of pixels under its rows (the result table
        # below takes all it can), and a field of five would show one row
        # and a scroll bar. A grid only scrolls past its cap, never because
        # of the layout.
        height = min(need, cap) if need else 0
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        # Past the cap the body keeps the cards' full rows and the grid
        # scrolls, rather than the layout squeezing every card to fit.
        self.body.setMinimumHeight(need)

    def card_for(self, entrant_id: int) -> RiderCard | None:
        return next((c for c in self.cards if c.card.entrant_id == entrant_id), None)
