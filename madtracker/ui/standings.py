"""File > Multi-Race Standings: the file's standings, each an omnium over ticked events.

The dialog has the standings on the left with Add..., Duplicate..., and
Delete under them, the selected one's page beside them, and the Standings
box in the rest. Every change is saved as it is made (a tick, a kind, a name
or the place points when the field is left), and the Standings box is computed again from the races
each time, as the PDF will be, so what the scorer reads here is what
the PDF shows. Nothing here scores a race: there is no Undo and nothing goes
in a race's log.

Each prompt (a name, a confirmation) is a method argument with a dialog
behind it when the argument is left out, so the tests drive the same
code the buttons do without a modal box.
"""

import re
import sqlite3
from collections.abc import Callable

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from madtracker.board.payloads import lap_text, total_text
from madtracker.control import multi_race, rulesets
from madtracker.dates import short_date, show_date
from madtracker.inputs import MAX_TEXT, clean_line, is_blank
from madtracker.store import Store, StoreError
from madtracker.ui import icons, style
from madtracker.ui.help import HELP_HERE
from madtracker.ui.look import DIALOG_BASE_PT
from madtracker.ui.review import LEFT, RIGHT, ROW_H, TEAM_MAX_CHARS, TEAM_ROW_H
from madtracker.ui.rulesets import TABLE_TIP
from madtracker.ui.surface import restyle, state_pill
from madtracker.ui.widgets import (
    ID_ROLE,
    CheckList,
    ElidedLabel,
    Form,
    NameDialog,
    RowToggleDelegate,
    apply_style,
    close_on_shortcut,
    error_label,
    fit_popup,
    fit_to_screen,
    note_unprintable,
    run_dialog,
    setup_table,
    show_message,
    swatch_icon,
)

TITLE = "Multi-Race Standings"
# The one tag a standings wears: Final, once every counting race is
# final and none is left to run. Short of that it wears none: a season's
# table would read "Provisional" for months, a warning that says nothing
# the count line does not, and no club posts a season that way.
FINAL_WORD = "Final"
# The Races list's one line when the ticked events have none the kind counts.
NO_MADISON = "No Madison in the ticked events"
NO_RACE = "No race in the ticked events"
BLANK_NAME = "The standings needs a name."
BAD_PLACES = (
    f"Place points are up to {rulesets.MAX_COUNT} whole numbers from 0 to 999,"
    " such as 7, 5, 3, 2, 1."
)
PLACES_MAX = rulesets.TABLE_MAX
NO_GROUP = multi_race.NO_GROUP
NOT_YET_RACED = "(not yet raced)"
RACING = "(racing)"
# A Races row's gray note after its name.
NOTE_ROLE = Qt.ItemDataRole.UserRole + 2
# A refusal quotes at most this much of a name: 200 characters with no
# space in them cannot wrap, and would widen the dialog off the screen.
QUOTE_MAX = 40
# The three columns share the width by these weights (parts of 1000),
# each held between its least and its most: the list and the page come
# near their most on a 1366 laptop and near their least at 150 percent
# there (911 px of logical width), where the Standings box keeps three
# Madisons in view. On the 1366 laptop the list shows "Oktoberfest 2 Day
# Omnium" whole, and the page "Team Omnium by Place" beside the Place
# points label; a longer name, or an event's, is cut with its whole in
# the tooltip.
LIST_MIN, LIST_W, LIST_STRETCH = 120, 190, 145
PAGE_MIN, PAGE_W, PAGE_STRETCH = 210, 336, 254
STANDINGS_STRETCH = 601
# The whole dialog on a screen with room for it; fit_to_screen keeps it
# on a 1366 by 768 laptop.
NATURAL = (1340, 720)
# The Riders column gives way first, down to this many average
# characters, each name still on a line of its own. A rider kind's Rider
# column is the row's identity, so its least keeps a first name and the
# start of the surname: "Maya Petrakis" and "Maya Peterson" stay apart.
RIDERS_MIN_CHARS = 8
RIDER_MIN_CHARS = 14
# Scrolling, a rider kind keeps this many race columns in view beside
# the names, which take the rest up to their natural width.
SCROLL_RACES = 3
# A race column's name is cut to about this many characters before the
# riders give way: "4 Mile Madi..." still says which Madison it is.
RACE_EASE_CHARS = 11
# A little room past the style's cell padding keeps a number clear of
# the next column's word.
GAP = style.XS
# Qt shows a cell's "\n" as this, the Unicode line separator.
LINE_SEP = " "


def event_text(name: str, iso_date: str) -> str:
    return f"{name} ({show_date(iso_date)})"


def race_text(column: multi_race.RaceColumn) -> str:
    return f"{column.race_name} ({column.group})" if column.group.strip() else column.race_name


def column_header(column: multi_race.RaceColumn) -> str:
    # The date over the race: a weekend's two "4 Mile Madison" columns
    # are told apart by the night they were raced, as the sheet does.
    return f"{short_date(column.event_date)}\n{column.race_name}"


def parse_places(text: str) -> list[int] | None:
    """The place points typed as the Rulesets fields take a table, as a list.

    None for a blank, a word, a negative, a number past PLACES_MAX, or
    more places than the Rulesets editor allows a race (a table longer
    than the field, shown back, would be cut and saved short).
    ASCII digits only: int() would also take other scripts' digits.
    """
    parts = rulesets.split_table(text)
    if not parts or len(parts) > rulesets.MAX_COUNT:
        return None
    if not all(re.fullmatch(r"[0-9]+", p) for p in parts):
        return None
    points = [int(p) for p in parts]
    return points if all(p <= PLACES_MAX for p in points) else None


def quoted_short(text: str) -> str:
    """``text`` with a name past QUOTE_MAX characters cut, "..." at the cut.

    The name is the quoted one, or the one a refusal says is "named"
    and "already exists".
    """

    def short(name: str) -> str:
        if len(name) > QUOTE_MAX:
            name = name[: QUOTE_MAX - 3].rstrip() + "..."
        return name

    text = re.sub(r"(['\"])(.*)\1", lambda m: f"{m.group(1)}{short(m.group(2))}{m.group(1)}", text)
    return re.sub(r"(?<=named )(.*)(?= already exists)", lambda m: short(m.group(1)), text)


class RidersDelegate(QStyledItemDelegate):
    """A Riders cell: one rider per line, each cut on the right when the column narrows.

    Qt would wrap a narrowed name onto a second line and push the next
    rider out of the row; a line per rider, cut, keeps the pair readable.
    """

    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:
        super().initStyleOption(option, index)
        if option.rect.width() <= 0:
            return
        # Each line cut a little inside the cell's padding, so none wraps.
        room = max(0, option.rect.width() - 2 * style.SM - 2 * GAP)
        metrics = option.fontMetrics
        option.text = LINE_SEP.join(
            metrics.elidedText(line, Qt.TextElideMode.ElideRight, room)
            for line in option.text.replace(LINE_SEP, "\n").split("\n")
        )


class NoteDelegate(RowToggleDelegate):
    """A tick row with a gray note after its text, "(not yet raced)".

    Short of room, the row's own text is cut, not the note: the note is
    the news, and the race's name and group are in the tooltip.
    """

    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:
        super().initStyleOption(option, index)
        note = index.data(NOTE_ROLE)
        if not note or option.rect.width() <= 0 or option.widget is None:
            return
        metrics = QFontMetrics(option.font)
        text_rect = self._text_rect(option)
        room = text_rect.width() - metrics.horizontalAdvance(" " + note) - style.SM
        option.text = metrics.elidedText(option.text, Qt.TextElideMode.ElideRight, max(0, room))

    @staticmethod
    def _text_rect(option: QStyleOptionViewItem) -> QRect:
        widget = option.widget
        return widget.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, widget)

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        note = index.data(NOTE_ROLE)
        if not note:
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        metrics = QFontMetrics(opt.font)
        x = self._text_rect(opt).left() + metrics.horizontalAdvance(opt.text + " ")
        room = QRect(x, opt.rect.top(), opt.rect.right() - x - style.SM, opt.rect.height())
        if room.width() <= 0:
            return
        painter.save()
        painter.setPen(QColor(style.DIM))
        painter.setFont(opt.font)
        shown = metrics.elidedText(note, Qt.TextElideMode.ElideRight, room.width())
        painter.drawText(room, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, shown)
        painter.restore()


def refusal_view(refusal: multi_race.Refusal) -> QWidget:
    """The refusal where the tables would be: the rule in red, then each event and its lines.

    The rule is the one red line; the events under it are plain detail,
    bold headings over a line per group as the sheet's notes are, so a
    weekend short of two formats reads as a list rather than a red block.
    """
    view = QWidget()
    lay = QVBoxLayout(view)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    # The whole refusal on every part of it: a label cut at the edge is
    # whole here.
    view.setToolTip(refusal.text)

    def add(label: QLabel) -> None:
        # A group or event named with an angle bracket stays text, never markup.
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # Never wider than the Standings box: a name with no spaces cannot
        # wrap, so it is cut at the edge.
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(label)

    lead = error_label()
    lead.setText(refusal.lead)
    add(lead)
    for night, lines in refusal.nights:
        lay.addSpacing(style.MD)
        heading = QLabel(night)
        heading.setFont(style.ui_font(13, bold=True))
        add(heading)
        lay.addSpacing(style.XS)
        for line in lines:
            add(QLabel(line))
    return view


class GroupStandings(QWidget):
    """One group's table as the PDF sets it out, in three parts side by side.

    Place, Team, and Riders on the left (Place, Bib, and Rider for a rider
    kind) and Total on the right stay in view; the race columns between
    them narrow and then scroll sideways on their own, so the total the
    omnium is about is never off screen (at 1366 px one table would cut
    the Total of three Madisons, and scrolling it whole would lose the
    team names). Riders give way first, then the race names, then the
    races scroll. No selection, no focus, every row shown: the scroll
    area around the groups scrolls up and down, so a second group is
    never a scroll inside a scroll.
    """

    BORDER = 1

    def __init__(self, group: multi_race.GroupTable, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("groupStandings")
        # A plain QWidget paints a style sheet border only when asked.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.columns = group.columns
        self.rider_rows = group.riders
        race_headers = [column_header(c) for c in group.columns]
        fixed_headers = ["Place", "Bib", "Rider"] if group.riders else ["Place", "Team", "Riders"]
        # A rider out of the omnium has no total to take it off: only a
        # ranked row's penalty brings the column in.
        has_penalty = any(r.penalty and not r.status for r in group.rows)
        self.full_headers = [
            *fixed_headers,
            *race_headers,
            *(["Penalty"] if has_penalty else []),
            "Total",
        ]
        self._row_count = len(group.rows)
        # A bib is a number: right against the name, as the results table has it.
        fixed_numbers = [False, group.riders, False]
        self.fixed = self._part(fixed_headers, numbers=fixed_numbers)
        self.races = self._part(
            race_headers,
            numbers=True,
            tips=[f"{show_date(c.event_date)}\n{c.race_name}" for c in group.columns],
        )
        # The penalty beside the total, there only when a row carries one,
        # as the results table and the sheet have it.
        self.total_headers = ["Penalty", "Total"] if has_penalty else ["Total"]
        self.total = self._part(self.total_headers, numbers=True)
        self.parts = (self.fixed, self.races, self.total)
        self.rows = group.rows
        for i, row in enumerate(group.rows):
            place = self._cell(str(row.rank) if row.rank is not None else row.status, LEFT)
            place.setFont(self._bold(place))
            self.fixed.setItem(i, 0, place)
            if group.riders:
                bib = self._cell("" if row.bib is None else str(row.bib), RIGHT)
                self.fixed.setItem(i, 1, bib)
                name = self._cell(row.team, LEFT)
                name.setFont(self._bold(name))
                self.fixed.setItem(i, 2, name)
            else:
                team = self._cell(row.team, LEFT)
                team.setIcon(swatch_icon(row.color))
                team.setFont(self._bold(team))
                self.fixed.setItem(i, 1, team)
                # One rider per line, as the results table lists a Madison's pair.
                self.fixed.setItem(i, 2, self._cell("\n".join(row.riders), LEFT))
            # A status row prints no figures on the sheet: a rider out of
            # the omnium has no standing to total.
            for j, points in enumerate(row.per_race):
                text = "" if points is None or row.status else total_text(points)
                self.races.setItem(i, j, self._cell(text, RIGHT))
            total = self._cell("" if row.status else total_text(row.total), RIGHT)
            total.setFont(self._bold(total))
            if len(self.total_headers) == 2:
                penalty = "" if row.status or not row.penalty else lap_text(-row.penalty)
                self.total.setItem(i, 0, self._cell(penalty, RIGHT))
            self.total.setItem(i, len(self.total_headers) - 1, total)
        self._fitted = False

    def _part(
        self,
        headers: list[str],
        numbers: bool | list[bool],
        tips: list[str] | None = None,
    ) -> QTableWidget:
        table = QTableWidget(self)
        table.setObjectName("standingsPart")
        table.setShowGrid(False)
        table.setFrameShape(QTableWidget.Shape.NoFrame)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        setup_table(table, headers, selectable=False)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        # The header items are set with the model's signals held, then
        # the header told once: each change it hears lays every section
        # out again, and a season's Standings box has a hundred of them.
        model = table.model()
        model.blockSignals(True)
        right = numbers if isinstance(numbers, list) else [numbers] * len(headers)
        for col, text in enumerate(headers):
            item = QTableWidgetItem(text)
            # Words left, numbers right, each header over its cells.
            item.setTextAlignment(RIGHT if right[col] else LEFT)
            if tips is not None:
                item.setToolTip(tips[col])
            table.setHorizontalHeaderItem(col, item)
        model.blockSignals(False)
        if headers:
            header.headerDataChanged(Qt.Orientation.Horizontal, 0, len(headers) - 1)
        table.setRowCount(self._row_count)
        return table

    @staticmethod
    def _cell(text: str, align: Qt.AlignmentFlag) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(align)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        return item

    @staticmethod
    def _bold(item: QTableWidgetItem):
        f = item.font()
        f.setBold(True)
        return f

    # ----- measuring ------------------------------------------------------

    def fit(self) -> None:
        """Each column's natural and least width, and every row's height.

        Measured once the parts sit in the dialog and have its style,
        since the dialog's type is what the cells are drawn in.
        """
        for part in self.parts:
            part.ensurePolished()
            part.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            part.resizeColumnsToContents()
        metrics = self.fixed.fontMetrics()
        avg = metrics.averageCharWidth()
        letter = metrics.horizontalAdvance("x")
        self.place_w = self.fixed.columnWidth(0) + GAP
        # A long team name wraps over the row's lines, as in the results
        # table and the PDF, rather than taking the riders' room. A bib
        # column is its widest bib.
        cap = avg * TEAM_MAX_CHARS + 2 * style.MD
        self.team_w = self.fixed.columnWidth(1) + GAP
        if not self.rider_rows:
            self.team_w = min(self.fixed.columnWidth(1), cap) + GAP
        self.riders_nat = self.fixed.columnWidth(2) + GAP
        least_chars = RIDER_MIN_CHARS if self.rider_rows else RIDERS_MIN_CHARS
        self.riders_min = min(self.riders_nat, letter * least_chars + 2 * style.SM + GAP)
        # The floor under that, once the races scroll: the whole Standings box
        # must never scroll sideways, so a narrow box takes letters off
        # the names before it takes the Total out of view.
        self.riders_floor = min(self.riders_nat, letter * RIDERS_MIN_CHARS + 2 * style.SM + GAP)
        self.fixed.setItemDelegateForColumn(2, RidersDelegate(self.fixed))
        self.total_ws = [self.total.columnWidth(c) + GAP for c in range(len(self.total_headers))]
        self.total_w = sum(self.total_ws)
        # A race column's least is its date over its widest figure; its
        # name is cut to fit under the date when room is short.
        head_font = QFont(self.races.horizontalHeader().font())
        head_font.setWeight(QFont.Weight.DemiBold)
        head = QFontMetrics(head_font)
        cell = self.races.fontMetrics()
        self.race_nat: list[int] = []
        self.race_min: list[int] = []
        self.race_ease: list[int] = []
        ease = head.horizontalAdvance("x") * RACE_EASE_CHARS + 2 * style.SM + GAP
        for col, c in enumerate(self.columns):
            figures = [
                cell.horizontalAdvance(self.races.item(r, col).text())
                for r in range(self.races.rowCount())
            ]
            least = max([head.horizontalAdvance(short_date(c.event_date)), *figures])
            least += 2 * style.SM
            natural = max(least, self.races.columnWidth(col) + GAP)
            self.race_min.append(least)
            self.race_nat.append(natural)
            self.race_ease.append(min(natural, max(least, ease)))
        self.head_metrics = head
        self.header_h = max(p.horizontalHeader().sizeHint().height() for p in self.parts)
        for part in self.parts:
            part.horizontalHeader().setFixedHeight(self.header_h)
        self.row_h = [self._row_height(i, row) for i, row in enumerate(self.rows)]
        for part in self.parts:
            for i, h in enumerate(self.row_h):
                part.setRowHeight(i, h)
        self.scroll_h = max(style.SCROLL_PX, self.races.horizontalScrollBar().sizeHint().height())
        self._fitted = True
        self.updateGeometry()
        self._place(self.width())

    def _row_height(self, i: int, row: multi_race.MultiRaceRow) -> int:
        """Tall enough for the riders, one a line, and the team's name wrapped whole."""
        if self.rider_rows:
            # One line: a rider's name is cut on the right, never wrapped.
            return ROW_H
        plain = self.fixed.fontMetrics()
        # Measured in the font the name is drawn in: the item's own.
        bold = QFontMetrics(self.fixed.item(i, 1).font())
        # The swatch and its gap, and the cell's padding, come off the text's room.
        room = self.team_w - GAP - 2 * style.SM - 18 - 3 * style.XS
        team_h = bold.boundingRect(
            QRect(0, 0, max(1, room), 100_000),
            int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere),
            row.team,
        ).height()
        riders_h = max(1, len(row.riders)) * plain.lineSpacing()
        pad = TEAM_ROW_H - 2 * plain.lineSpacing()
        least = TEAM_ROW_H if len(row.riders) > 1 else ROW_H
        return max(least, max(team_h, riders_h) + pad)

    def _widths(self, width: int) -> tuple[int, list[int], bool, int]:
        """At ``width``: the Riders width, each race column's, whether the races
        scroll, and the Total's width.

        In turn: a long race name is cut to RACE_EASE_CHARS, then the
        riders narrow to their least, then every race name is cut down to
        its date, then the riders go (at 150 percent on a 1366 laptop that
        keeps three Madisons whole), and only then do the races scroll. A
        rider kind's name is the row's identity, so it gives way last:
        the race names are cut to their dates before the names narrow,
        the names never go, and scrolling, the names take their room back
        with SCROLL_RACES columns in view beside them.
        """
        room = width - 2 * self.BORDER - self.place_w - self.team_w - self.total_w
        eased = self._squeeze(self.race_ease, room - self.riders_nat)
        if eased is not None:
            return room - sum(eased), eased, False, self.total_w
        if self.rider_rows:
            least = self._squeeze(self.race_min, room - self.riders_nat)
            if least is not None:
                return room - sum(least), least, False, self.total_w
            least = self._squeeze(self.race_min, room - self.riders_min)
            if least is not None:
                return room - sum(least), least, False, self.total_w
            widest = max(self.race_min, default=0)
            names = max(self.riders_floor, min(self.riders_nat, room - SCROLL_RACES * widest))
            return names, list(self.race_min), True, self.total_w
        eased = list(self.race_ease)
        if room - sum(eased) >= self.riders_min:
            return room - sum(eased), eased, False, self.total_w
        least = self._squeeze(self.race_min, room - self.riders_min)
        if least is not None:
            return room - sum(least), least, False, self.total_w
        # No riders: what the races leave goes to the Total, whose figure
        # sits on the right edge either way.
        least = self._squeeze(self.race_min, room)
        if least is not None:
            return 0, least, False, self.total_w + room - sum(least)
        return 0, list(self.race_min), True, self.total_w

    def _squeeze(self, floors: list[int], room: int) -> list[int] | None:
        """The race widths in ``room``, each cut to one cap and none under its floor.

        One cap for all, so the names are cut alike rather than the last
        one alone; None when the floors alone overflow ``room``.
        """
        if sum(floors) > room:
            return None
        pairs = list(zip(floors, self.race_nat, strict=True))
        lo, hi = 0, max(self.race_nat, default=0)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if sum(max(f, min(n, mid)) for f, n in pairs) <= room:
                lo = mid
            else:
                hi = mid - 1
        return [max(f, min(n, lo)) for f, n in pairs]

    def hasHeightForWidth(self) -> bool:
        return self._fitted

    def heightForWidth(self, width: int) -> int:
        if not self._fitted:
            return super().heightForWidth(width)
        scrolls = self._widths(width)[2]
        height = self.header_h + sum(self.row_h) + 2 * self.BORDER
        return height + (self.scroll_h if scrolls else 0)

    def sizeHint(self) -> QSize:
        if not self._fitted:
            return super().sizeHint()
        width = (
            2 * self.BORDER
            + self.place_w
            + self.team_w
            + self.riders_nat
            + sum(self.race_nat)
            + self.total_w
        )
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        if not self._fitted:
            return super().minimumSizeHint()
        width = 2 * self.BORDER + self.place_w + self.team_w + self.total_w
        width += min(self.race_min, default=0)
        if self.rider_rows:
            width += self.riders_floor
        return QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fitted:
            self._place(event.size().width())

    def _place(self, width: int) -> None:
        riders, widths, scrolls, total_w = self._widths(width)
        for col, w in enumerate((self.place_w, self.team_w, riders)):
            self.fixed.setColumnWidth(col, w)
        self.fixed.setColumnHidden(2, riders == 0)
        for col, w in enumerate(widths):
            self.races.setColumnWidth(col, w)
            c = self.columns[col]
            room = w - 2 * style.SM - GAP
            name = self.head_metrics.elidedText(c.race_name, Qt.TextElideMode.ElideRight, room)
            self.races.horizontalHeaderItem(col).setText(f"{short_date(c.event_date)}\n{name}")
        # Room past the least goes to the Total, whose figure sits on the right edge.
        for c, w in enumerate(self.total_ws):
            self.total.setColumnWidth(c, w)
        self.total.setColumnWidth(len(self.total_ws) - 1, total_w - sum(self.total_ws[:-1]))
        self.races.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            if scrolls
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        b = self.BORDER
        height = max(0, self.height() - 2 * b)
        fixed_w = self.place_w + self.team_w + riders
        races_w = max(0, width - 2 * b - fixed_w - total_w)
        self.fixed.setGeometry(b, b, fixed_w, height)
        # Scrolling, the races sit between two hairlines of the frame's color,
        # so a column cut at either edge reads as passing under, not missing.
        sep = b if scrolls else 0
        self.races.setGeometry(b + fixed_w + sep, b, max(0, races_w - 2 * sep), height)
        self.total.setGeometry(width - b - total_w, b, total_w, height)

    # ----- reading it back (the tests and the design walk) ----------------

    def table_of(self, col: int) -> tuple[QTableWidget, int]:
        """The part a column of the whole table is in, and its column there."""
        first_total = len(self.full_headers) - len(self.total_headers)
        if col < 3:
            return self.fixed, col
        if col >= first_total:
            return self.total, col - first_total
        return self.races, col - 3

    def headers(self) -> list[str]:
        """Every column's heading as the sheet heads it, a race's name whole."""
        return list(self.full_headers)

    def shown_headers(self) -> list[str]:
        return [
            t.horizontalHeaderItem(c).text()
            for t, c in (self.table_of(i) for i in range(len(self.full_headers)))
        ]

    def column(self, word: str) -> list[str]:
        table, col = self.table_of(self.full_headers.index(word))
        return [table.item(r, col).text() for r in range(table.rowCount())]

    def cells(self) -> tuple[str, ...]:
        return tuple(
            t.item(r, c).text()
            for r in range(len(self.rows))
            for t, c in (self.table_of(i) for i in range(len(self.full_headers)))
        )

    def total_in_view(self) -> bool:
        """The Total column wholly inside this table's own width."""
        g = self.total.geometry()
        return g.width() >= self.total_w and g.right() < self.width()


class StandingsDialog(QDialog):
    """``export(standings_id)`` writes the PDF; the app supplies it, with its save box."""

    def __init__(
        self,
        store: Store,
        parent: QWidget | None = None,
        export: Callable[[int], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.export = export
        self.table: multi_race.MultiRaceTable | None = None
        self.standings_views: list[GroupStandings] = []
        self.race_states: dict[int, str] = {}
        # Each race replayed once and read by every tick, kind change, and
        # selection: the dialog is modal, so no race is scored while it is
        # open, and refresh() reads the races again.
        self.sessions: multi_race.Sessions = {}
        # The running races the kind waits for (no column yet), noted in the list.
        self.racing_ids: set[int] = set()
        # The standings the page shows, so a name left on a selection
        # change is saved to the standings it was typed for.
        self.shown_id: int | None = None
        # A refused name or place points on the red line holds the next
        # Close once, so the scorer reads why; the field has the old
        # value back by then.
        self.name_refused = False
        self.help_window = None
        self.setWindowTitle(TITLE)
        apply_style(self)
        close_on_shortcut(self)

        left_box = self._build_list()
        form = self._build_form()
        events_box = self._build_events_box()
        races_box = self._build_races_box()
        self._build_page(form, events_box, races_box)
        standings_box = self._build_standings()
        self._build_footer()
        self._lay_out(left_box, standings_box)

        # No default button: Enter in the Name field saves the name and
        # nothing else. As the default, Add... would open its name box too.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

        self._add_help_key()

        fit_to_screen(self, *NATURAL)
        self.refresh()

    def _build_list(self) -> QWidget:
        """The standings list and its Add..., Duplicate..., and Delete under it."""
        self.list = QListWidget()
        # A long name is cut, its whole in the tooltip, where a narrow
        # list would scroll sideways under its one row.
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.currentItemChanged.connect(lambda *_: self._show_selected())
        self.add_button = QPushButton("Add...")
        self.add_button.clicked.connect(lambda: self.add())
        self.duplicate_button = QPushButton("Duplicate...")
        self.duplicate_button.clicked.connect(lambda: self.duplicate())
        # Delete, as in Rulesets: a standings is a thing of its own in the
        # file, not a member of a list.
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(lambda: self.delete())
        # One under another, the width of the list: the Standings box needs the
        # room a row of three would take at 1366 px.
        list_buttons = QVBoxLayout()
        list_buttons.setSpacing(style.SM)
        for b in (self.add_button, self.duplicate_button, self.delete_button):
            list_buttons.addWidget(b)
        left = QVBoxLayout()
        left.setSpacing(style.SM)
        left.addWidget(self.list, 1)
        left.addLayout(list_buttons)
        left_box = QWidget()
        left_box.setLayout(left)
        left.setContentsMargins(0, 0, 0, 0)
        return left_box

    def _build_form(self) -> Form:
        self.name = QLineEdit()
        self.name.setMaxLength(MAX_TEXT)
        self.name.editingFinished.connect(self.save_name)
        self.kind = QComboBox()
        for key, label in multi_race.KINDS.items():
            self.kind.addItem(label, key)
        fit_popup(self.kind)
        # The page narrows to PAGE_MIN; a box as wide as its longest
        # choice would hang past it, so a narrow one cuts the choice.
        self.kind.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.kind.setMinimumContentsLength(6)
        self.kind.currentIndexChanged.connect(lambda _i: self.set_kind(self.kind.currentData()))
        # The place kinds' table, typed as the sheet reads it: "7, 5, 3, 2, 1".
        self.place_points = QLineEdit()
        self.place_points.setMaxLength(rulesets.TABLE_TEXT_MAX)
        self.place_points.setToolTip(TABLE_TIP)
        self.place_points.editingFinished.connect(self.save_place_points)
        form = Form()
        form.addRow("Name", self.name)
        form.addRow("Kind", self.kind)
        form.addRow("Place points", self.place_points)
        self.form = form
        return form

    def _build_events_box(self) -> QGroupBox:
        self.events = CheckList()
        self.events.itemChanged.connect(lambda _item: self._events_ticked())
        events_box = QGroupBox("Events")
        QVBoxLayout(events_box).addWidget(self.events)
        return events_box

    def _build_races_box(self) -> QGroupBox:
        self.races = CheckList()
        self.races.setItemDelegate(NoteDelegate(self.races))
        self.races.itemChanged.connect(lambda _item: self._races_ticked())
        self.no_races = QLabel(NO_MADISON)
        self.no_races.setObjectName("hint")
        self.no_races.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        races_box = QGroupBox("Races")
        races_lay = QVBoxLayout(races_box)
        races_lay.addWidget(self.races, 1)
        races_lay.addWidget(self.no_races, 1)
        return races_box

    def _build_page(self, form: Form, events_box: QGroupBox, races_box: QGroupBox) -> None:
        # Each list at least a row and a half tall (one row whole and the
        # next showing there is more), under Qt's 90 px default: at 150
        # percent on a 1366 by 768 laptop the Kind choice and the Place
        # points row need that height for the dialog to fit.
        least = style.control_height(DIALOG_BASE_PT, 1.7) * 3 // 2
        for check_list in (self.events, self.races):
            check_list.setMinimumHeight(least + 2 * check_list.frameWidth())

        middle = QVBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(style.SM)
        middle.addLayout(form)
        middle.addWidget(events_box, 2)
        middle.addWidget(races_box, 3)
        self.page = QWidget()
        self.page.setLayout(middle)

    def _build_standings(self) -> QGroupBox:
        # The count alone ("2 of 4 races raced over 2 events"), since Kind names the
        # kind, on one line, cut when short of room: the sheet's whole
        # detail, wrapped beside the tag, would take six lines of a narrow Standings box.
        self.detail = ElidedLabel("")
        self.detail.setObjectName("hint")
        self.state = QLabel("")
        self.state.setFont(style.ui_font(DIALOG_BASE_PT, bold=True))
        self.state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top = QHBoxLayout()
        top.addWidget(self.detail, 1)
        top.addWidget(self.state, 0, Qt.AlignmentFlag.AlignVCenter)
        self.groups = QWidget()
        # A plain QWidget paints a style sheet background only when asked.
        self.groups.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.groups_lay = QVBoxLayout(self.groups)
        self.groups_lay.setContentsMargins(0, 0, 0, 0)
        self.groups_lay.setSpacing(style.SM)
        self.groups.setObjectName("standingsGroups")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setWidget(self.groups)
        # The groups sit on the box's white, as the PDF's tables sit on
        # paper; the scroll area's viewport would show the dialog's gray.
        # A group's three parts read as one table: one frame around them,
        # its color showing between them only where the races scroll.
        self.scroll.viewport().setObjectName("standingsViewport")
        self.scroll.setStyleSheet(
            "QWidget#standingsViewport, QWidget#standingsGroups { background: #ffffff; }\n"
            f"QWidget#groupStandings {{ background: {style.PANE_EDGE};"
            f" border: {GroupStandings.BORDER}px solid {style.PANE_EDGE}; }}\n"
            "QTableWidget#standingsPart { border: none; }"
        )
        self.export_button = QPushButton("Export PDF...")
        self.export_button.clicked.connect(self.export_pdf)
        # The Four-Race Omnium's one ruling (USAC 2O3(e)), on the standings
        # and never on a race; the Standings box's rows are read, so this is
        # the door. Hidden for the other kinds, which have no article for one.
        self.penalty_button = QPushButton("Omnium Penalty...")
        self.penalty_button.clicked.connect(lambda: self.omnium_penalty())
        export_row = QHBoxLayout()
        export_row.addWidget(self.penalty_button)
        export_row.addStretch(1)
        export_row.addWidget(self.export_button)
        standings_box = QGroupBox("Standings")
        box = QVBoxLayout(standings_box)
        box.setSpacing(style.SM)
        box.addLayout(top)
        box.addWidget(self.scroll, 1)
        box.addLayout(export_row)
        return standings_box

    def _build_footer(self) -> None:
        """The red line and Close."""
        self.status = error_label()
        note_unprintable(self.name, self.status)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        self.close_button.setMinimumWidth(style.control_height(DIALOG_BASE_PT) * 3)

    def _lay_out(self, left_box: QWidget, standings_box: QGroupBox) -> None:
        # The columns share the width by weight between their least and
        # most (LIST_MIN and on): at their own size hints the list and the
        # page would keep 580 px and leave the Standings box what was left.
        for widget, least, most in (
            (left_box, LIST_MIN, LIST_W),
            (self.page, PAGE_MIN, PAGE_W),
        ):
            widget.setMinimumWidth(least)
            widget.setMaximumWidth(most)
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        standings_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        body = QHBoxLayout()
        body.setSpacing(style.MD)
        body.addWidget(left_box, LIST_STRETCH)
        body.addWidget(self.page, PAGE_STRETCH)
        body.addWidget(standings_box, STANDINGS_STRETCH)
        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.close_button)
        lay = QVBoxLayout(self)
        lay.setSpacing(style.MD)
        lay.addLayout(body, 1)
        lay.addLayout(bottom)

    def _add_help_key(self) -> None:
        # F1 opens the Multi-Race Standings page in a help window of the
        # dialog's own: the main window's help would sit behind this modal
        # dialog, seen but out of reach.
        help_here = QAction(self)
        help_here.setShortcut(QKeySequence(Qt.Key.Key_F1))
        help_here.triggered.connect(self.open_help)
        self.addAction(help_here)
        self.help_action = help_here

    # ----- list -----------------------------------------------------------

    def refresh(self, select: int | None = None) -> None:
        """The list and the page read from the store again, the races' results with them."""
        self.sessions = {}
        current = select if select is not None else self.selected_id()
        try:
            listed = self.store.list_standings()
        except READ_FAILURES as exc:
            self._unreadable(exc)
            return
        self.list.blockSignals(True)
        self.list.clear()
        for s in listed:
            item = QListWidgetItem(s.name)
            item.setData(ID_ROLE, s.standings_id)
            item.setToolTip(s.name)
            self.list.addItem(item)
            if s.standings_id == current:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._show_selected()

    def _resort(self) -> None:
        """The list in the store's order again, the selection kept by its id.

        Run after a rename once the click that left the Name field has
        landed: rebuilt during that click, the list would move under the
        mouse and the click would pick whatever standings then sat there.
        """
        order = {s.standings_id: i for i, s in enumerate(self.store.list_standings())}
        current = self.selected_id()
        self.list.blockSignals(True)
        items = [self.list.takeItem(0) for _ in range(self.list.count())]
        items.sort(key=lambda it: order.get(it.data(ID_ROLE), len(order)))
        for item in items:
            self.list.addItem(item)
            if item.data(ID_ROLE) == current:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)

    def names(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def selected_id(self) -> int | None:
        item = self.list.currentItem()
        return None if item is None else item.data(ID_ROLE)

    def select(self, name: str) -> None:
        self.list.setCurrentRow(self.names().index(name))

    def _say(self, exc_or_text) -> None:
        show_message(self.status, self._sentence(exc_or_text))

    @staticmethod
    def _sentence(exc_or_text) -> str:
        text = quoted_short(str(exc_or_text))
        text = text[0].upper() + text[1:] if text else "That did not work"
        return text if text.endswith(".") else text + "."

    def _clear_status(self) -> None:
        self.status.clear()
        self.name_refused = False

    def _set_name(self, text: str) -> None:
        if self.name.text() != text:
            self.name.setText(text)
        if not self.name.hasFocus():
            # The start in view: a narrow field would show "emo 2 Day Omnium".
            self.name.setCursorPosition(0)

    # ----- the page -------------------------------------------------------

    def _show_selected(self) -> None:
        standings_id = self.selected_id()
        if standings_id != self.shown_id and not self.name_refused:
            # A message about the last standings says nothing about this
            # one, unless it is the refusal of what was typed there: the
            # click that moved the selection is the one that lost the
            # typed value, and the scorer must get to read why.
            self._clear_status()
        self.shown_id = standings_id
        has = standings_id is not None
        self.duplicate_button.setEnabled(has)
        self.delete_button.setEnabled(has)
        self.page.setEnabled(has)
        if not has:
            self.name.setText("")
            self._show_kind(None)
            self.events.clear()
            self._fill_races(None)
            self._fill_standings()
            return
        try:
            self._show_standings(standings_id)
        except READ_FAILURES as exc:
            self._unreadable(exc)

    def _unreadable(self, exc: Exception) -> None:
        """A file that fails a read while the dialog is up (a page damaged under
        it) is said on the status line, and the page takes no edits that would
        write beside the damage."""
        self._say(exc)
        self.page.setEnabled(False)
        self.duplicate_button.setEnabled(False)
        self.delete_button.setEnabled(False)

    def _show_standings(self, standings_id: int) -> None:
        standings = self.store.get_standings(standings_id)
        self._set_name(standings.name)
        self._show_kind(standings)
        ticked = set(standings.event_ids)
        self.events.blockSignals(True)
        self.events.clear()
        for event in self.store.events():
            text = event_text(event.name, event.event_date)
            item = self.events.add(event.event_id, text, event.event_id in ticked)
            item.setToolTip(text)
        self.events.blockSignals(False)
        self._fill_races(standings)
        self._fill_standings()
        self._renote()

    def _renote(self) -> None:
        """The list's notes follow the table: which running races wait for their places."""
        self.racing_ids = set() if self.table is None else {c.race_id for c in self.table.racing}
        self.races.blockSignals(True)
        for i in range(self.races.count()):
            item = self.races.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                self._note(item)
        self.races.blockSignals(False)

    def _show_kind(self, standings) -> None:
        """The Kind choice and, for the place kinds alone, the Place points row."""
        kind = None if standings is None else standings.kind
        self.kind.blockSignals(True)
        self.kind.setCurrentIndex(self.kind.findData(kind))
        self.kind.blockSignals(False)
        # Whole in the tooltip: a narrow page cuts the box's text.
        self.kind.setToolTip(self.kind.currentText())
        places = kind in multi_race.PLACE_KINDS
        # Hidden, not grayed, for the other kinds: the totals kind has no
        # table, and the Four-Race Omnium's is the rulebook's.
        self.form.setRowVisible(self.place_points, places)
        text = ""
        if places:
            text = rulesets.table_text(multi_race.rules_for(standings).points_by_place or ())
        self.place_points.setText(text)

    def _fill_races(self, standings) -> None:
        self.races.blockSignals(True)
        self.races.clear()
        candidates = (
            []
            if standings is None
            else multi_race.candidate_races(self.store, standings, self.sessions)
        )
        # Newest event first, as the Events list above; each in program order.
        by_event: dict[int, list[multi_race.RaceColumn]] = {}
        for column in candidates:
            by_event.setdefault(column.event_id, []).append(column)
        self.race_states = {c.race_id: c.state for c in candidates}
        for event_id in reversed(list(by_event)):
            columns = by_event[event_id]
            heading_text = event_text(columns[0].event_name, columns[0].event_date)
            heading = QListWidgetItem(heading_text)
            heading.setToolTip(heading_text)
            # A heading, not a choice: no box, and a click on it does nothing.
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            heading.setForeground(self.palette().text())
            f = heading.font()
            f.setBold(True)
            heading.setFont(f)
            heading.setSizeHint(QSize(0, style.control_height(DIALOG_BASE_PT, 1.7)))
            self.races.addItem(heading)
            for column in columns:
                self._note(self.races.add(column.race_id, race_text(column), not column.excluded))
        self.races.blockSignals(False)
        any_race = bool(candidates)
        self.races.setVisible(any_race)
        if standings is not None:
            self.no_races.setText(NO_RACE if multi_race.rider_kind(standings.kind) else NO_MADISON)
        self.no_races.setVisible(not any_race and standings is not None)

    def _note(self, item: QListWidgetItem) -> None:
        """A ticked race still in setup, or still racing, says so: it is no column yet."""
        ticked = item.checkState() == Qt.CheckState.Checked
        state = self.race_states.get(item.data(ID_ROLE))
        note = None
        if ticked and state == "setup":
            note = NOT_YET_RACED
        elif ticked and state == "running" and item.data(ID_ROLE) in self.racing_ids:
            note = RACING
        item.setData(NOTE_ROLE, note)
        item.setToolTip(f"{item.text()} {note}" if note else item.text())

    def _fill_standings(self) -> None:
        while self.groups_lay.count():
            item = self.groups_lay.takeAt(0)
            if item.widget() is not None:
                # Hidden now: deleteLater waits for the event loop, and the
                # old table would show under the new one until then.
                item.widget().hide()
                item.widget().deleteLater()
        self.standings_views = []
        standings_id = self.shown_id
        self.table = (
            None
            if standings_id is None
            else multi_race.compute(self.store, standings_id, self.sessions)
        )
        if self.table is None:
            self.detail.setText("")
            self.state.setText("")
            restyle(self.state, "")
            self.export_button.setEnabled(False)
            self.penalty_button.setVisible(False)
            self.groups_lay.addStretch(1)
            return
        self.detail.setText(self.table.counted)
        word = FINAL_WORD if self.table.state == "final" else ""
        self.state.setText(word)
        restyle(self.state, state_pill(word) if word else "")
        if self.table.refusal:
            self.groups_lay.addWidget(refusal_view(self.table.refusal))
        for group in self.table.groups:
            # Cut, not scrolled: a label with no spaces would otherwise
            # widen the Standings box and push the Total off the edge.
            heading = ElidedLabel(group.group or NO_GROUP)
            heading.setFont(style.ui_font(13, bold=True))
            self.groups_lay.addWidget(heading)
            table = GroupStandings(group, self.groups)
            self.groups_lay.addWidget(table)
            self.standings_views.append(table)
        self.groups_lay.addStretch(1)
        for table in self.standings_views:
            table.fit()
        self.export_button.setEnabled(self.row_count() > 0)
        four = self.table.kind == multi_race.FOUR_RACE
        self.penalty_button.setVisible(four)
        self.penalty_button.setEnabled(four and bool(self.penalty_riders()))

    def penalty_riders(self) -> list[tuple[int, str, int]]:
        """Each ranked rider in the table, once, in bib order: id, "#12 Name", the penalty.

        A rider out of the omnium (DNF, DQ) is not offered: there is no
        total to take it off. A rider in two groups' tables is one rider.
        """
        if self.table is None:
            return []
        seen: dict[int, tuple[int | None, str, int]] = {}
        for group in self.table.groups:
            for row in group.rows:
                if row.status or row.rider_id is None or row.rider_id in seen:
                    continue
                who = f"#{row.bib} {row.team}" if row.bib is not None else row.team
                seen[row.rider_id] = (row.bib, who, row.penalty)
        ordered = sorted(seen.items(), key=lambda item: (item[1][0] is None, item[1][0] or 0))
        return [(rider_id, who, penalty) for rider_id, (_bib, who, penalty) in ordered]

    def omnium_penalty(self, rider_id: int | None = None, points: int | None = None) -> bool:
        """Set a rider's omnium penalty, from the dialog when the arguments are left out."""
        if self.shown_id is None or self.table is None or self.table.kind != multi_race.FOUR_RACE:
            return False
        if rider_id is None or points is None:
            from madtracker.ui.penalty import OmniumPenaltyDialog

            riders = self.penalty_riders()
            if not riders:
                return False
            dialog = OmniumPenaltyDialog(riders, parent=self)
            if run_dialog(dialog) != QDialog.DialogCode.Accepted:
                return False
            rider_id, points = dialog.rider_id(), dialog.points()
        try:
            self.store.set_standings_penalty(self.shown_id, rider_id, points)
        except StoreError as exc:
            self._say(exc)
            return False
        self._clear_status()
        self._fill_standings()
        return True

    def row_count(self) -> int:
        return 0 if self.table is None else sum(len(g.rows) for g in self.table.groups)

    def ticked_events(self) -> list[int]:
        return [
            self.events.item(i).data(ID_ROLE)
            for i in range(self.events.count())
            if self.events.item(i).checkState() == Qt.CheckState.Checked
        ]

    def race_ticks(self) -> dict[int, bool]:
        out = {}
        for i in range(self.races.count()):
            item = self.races.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                out[item.data(ID_ROLE)] = item.checkState() == Qt.CheckState.Checked
        return out

    def _events_ticked(self) -> None:
        if self.shown_id is None:
            return
        try:
            standings = self.store.update_standings(self.shown_id, event_ids=self.ticked_events())
        except StoreError as exc:
            self._say(exc)
            self._show_selected()
            return
        self._clear_status()
        self._fill_races(standings)
        self._fill_standings()
        self._renote()

    def _races_ticked(self) -> None:
        if self.shown_id is None:
            return
        ticks = self.race_ticks()
        stored = set(self.store.get_standings(self.shown_id).excluded_race_ids)
        # A race of an event unticked for now keeps its exclusion, so
        # ticking the night again brings it back as the scorer left it.
        excluded = (stored - set(ticks)) | {race_id for race_id, on in ticks.items() if not on}
        try:
            self.store.update_standings(self.shown_id, excluded_race_ids=sorted(excluded))
        except StoreError as exc:
            self._say(exc)
            self._show_selected()
            return
        self._clear_status()
        self._fill_standings()
        self._renote()

    def set_kind(self, kind: str) -> bool:
        """Change the selected standings' kind; True when it changed."""
        if self.shown_id is None or kind not in multi_race.KINDS:
            return False
        standings = self.store.get_standings(self.shown_id)
        if standings.kind == kind:
            return False
        try:
            # The new kind's defaults: a value set for the other kind
            # would otherwise sit over them, and a penalty kept under a
            # kind that never shows it would come back unasked.
            standings = self.store.update_standings(self.shown_id, kind=kind, rules={})
            for rider_id in list(standings.penalties):
                standings = self.store.set_standings_penalty(self.shown_id, rider_id, 0)
        except StoreError as exc:
            self._say(exc)
            self._show_selected()
            return False
        self._clear_status()
        self._show_kind(standings)
        # The kind says which races are candidates: the Madisons, or the rest.
        self._fill_races(standings)
        self._fill_standings()
        self._renote()
        return True

    def save_place_points(self) -> bool:
        """The place points as typed, when they changed; a refusal puts the old ones back."""
        return self._save_places() == "saved"

    def _save_places(self, *, keep_status: bool = False) -> str:
        """``"saved"``, ``"same"``, or ``"refused"``, as ``_save_name``.

        ``keep_status`` leaves the red line alone on a save, for a refusal
        of the name in the same close that still has to be read.
        """
        if self.shown_id is None:
            return "same"
        standings = self.store.get_standings(self.shown_id)
        if standings.kind not in multi_race.PLACE_KINDS:
            return "same"
        old = list(multi_race.rules_for(standings).points_by_place or ())
        typed = parse_places(self.place_points.text())
        if typed is None:
            self._show_kind(standings)
            self._say(BAD_PLACES)
            self.name_refused = True
            return "refused"
        if typed == old:
            # "7,5 3" is the stored table: shown again the one way.
            self._show_kind(standings)
            return "same"
        try:
            standings = self.store.update_standings(
                self.shown_id, rules={**(standings.rules or {}), "points_by_place": typed}
            )
        except (StoreError, ValueError) as exc:
            self._show_kind(standings)
            self._say(exc)
            self.name_refused = True
            return "refused"
        if not keep_status:
            self._clear_status()
        self._show_kind(standings)
        self._fill_standings()
        return "saved"

    def save_name(self) -> bool:
        """The name as typed, when it changed; a refusal puts the old name back."""
        return self._save_name() == "saved"

    def _save_name(self) -> str:
        """``"saved"``, ``"same"`` (nothing to save), or ``"refused"`` (the old name is back)."""
        if self.shown_id is None:
            return "same"
        old = self.store.get_standings(self.shown_id).name
        typed = clean_line(self.name.text())
        if typed == old:
            # Typed text that cleans to the saved name (spaces squashed)
            # shows as saved, so the field never differs from the store.
            self._set_name(old)
            return "same"
        if is_blank(typed):
            self._set_name(old)
            self._say(BLANK_NAME)
            self.name_refused = True
            return "refused"
        try:
            self.store.update_standings(self.shown_id, name=typed)
        except (StoreError, ValueError) as exc:
            self._set_name(old)
            self._say(exc)
            self.name_refused = True
            return "refused"
        self._clear_status()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(ID_ROLE) == self.shown_id:
                item.setText(typed)
                item.setToolTip(typed)
        self._set_name(typed)
        # The list takes its new order once the click that left the field
        # has landed on the row the scorer pointed at.
        QTimer.singleShot(0, self, self._resort)
        return "saved"

    # ----- actions ----------------------------------------------------------

    def _make_named(
        self, name: str | None, title: str, verb: str, text: str, make: Callable[[str], int]
    ) -> int | None:
        """``make`` under ``name``, or under one typed into a dialog that refuses in place.

        A name handed in (a test, the fuzzer) is refused on the status
        line instead, as there is no dialog to keep open.
        """

        def take(typed: str) -> str | None:
            if is_blank(clean_line(typed)):
                return BLANK_NAME
            try:
                made.append(make(typed))
            except (StoreError, ValueError) as exc:
                return self._sentence(exc)
            return None

        made: list[int] = []
        if name is None:
            dialog = NameDialog(title, verb, take, text=text, parent=self)
            if run_dialog(dialog) != QDialog.DialogCode.Accepted or not made:
                return None
        else:
            refusal = take(name)
            if refusal:
                self._say(refusal)
                return None
        self._clear_status()
        self.refresh(made[-1])
        return made[-1]

    def add(self, name: str | None = None) -> int | None:
        """A new Team Omnium by Points with no events ticked; returns its id when made."""
        return self._make_named(
            name, "Add Standings", "Add", "", lambda n: self.store.add_standings(n).standings_id
        )

    def duplicate(self, name: str | None = None) -> int | None:
        """A copy of the selected standings: its kind, values, events, left-out races, and penalties."""
        if self.shown_id is None:
            return None
        source = self.store.get_standings(self.shown_id)

        def copy(typed: str) -> int:
            made = self.store.add_standings(typed, source.kind, source.rules)
            self.store.update_standings(
                made.standings_id,
                event_ids=source.event_ids,
                excluded_race_ids=source.excluded_race_ids,
            )
            for rider_id, points in source.penalties.items():
                self.store.set_standings_penalty(made.standings_id, rider_id, points)
            return made.standings_id

        return self._make_named(
            name, "Duplicate Standings", "Duplicate", f"{source.name} copy", copy
        )

    def delete(self, confirm: bool = True) -> bool:
        if self.shown_id is None:
            return False
        standings = self.store.get_standings(self.shown_id)
        if confirm and not icons.ask(
            self,
            "Delete Standings",
            f"Delete {standings.name}? The races and their results are not changed.",
            verb="Delete",
        ):
            return False
        try:
            self.store.remove_standings(standings.standings_id)
        except StoreError as exc:
            self._say(exc)
            return False
        self._clear_status()
        self.shown_id = None
        self.refresh()
        return True

    def export_pdf(self) -> None:
        if self.shown_id is not None and self.export is not None and self.row_count():
            self.export(self.shown_id)

    def open_help(self) -> None:
        from madtracker.ui.help import HelpWindow

        if self.help_window is None:
            self.help_window = HelpWindow(self)
        self.help_window.show_page(*HELP_HERE["standings"])

    def done(self, result: int) -> None:
        # Escape closes the dialog without leaving a field, so a name or
        # place points typed and not yet saved are saved here. A refusal
        # holds the dialog open once, on the red line with the old value
        # back in the field, so the next Close closes: nothing typed is
        # dropped unsaid, and the dialog never traps.
        refused = self._save_name() == "refused" or self.name_refused
        # The table still saves under a refused name, but the red line
        # keeps the name's refusal: it is why the dialog stays open.
        refused = self._save_places(keep_status=refused) == "refused" or refused
        self.name_refused = False
        if refused:
            return
        if self.help_window is not None:
            # The dialog's own help goes with it.
            self.help_window.close()
        super().done(result)


# A read the file refuses: the store's own refusal, or SQLite finding a
# damaged page under an open connection.
READ_FAILURES = (StoreError, sqlite3.Error)


def open_standings(
    store: Store, parent: QWidget | None = None, export: Callable[[int], object] | None = None
) -> None:
    """File > Multi-Race Standings. Returns when the dialog closes."""
    dialog = StandingsDialog(store, parent, export=export)
    run_dialog(dialog)
