"""The result as a table: the result so far during a race, the review after it.

One table serves both (design sections 7 and 8): alternating rows, no
selection, one row per place. During the race a staged row's ⋯ offers
the tie; in the review each row's ⋯ offers Move up, Move down, Tie
with the rider above and Disqualify, and the sprint column headers of
a points race reopen that sprint. The Mark final and Reopen button is
the surface's, not the table's.
"""

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHeaderView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from madtracker.board.payloads import lap_text, total_text
from madtracker.control.describe import STATUS_WORDS
from madtracker.control.race import BREAK_TIE, MOVE_TO, REVIEW_ACTIONS, ResultRow, Screen
from madtracker.ui import style, widgets
from madtracker.ui.widgets import (
    ID_ROLE,
    dots_button,
    fill_menu,
    setup_table,
    swatch_icon,
)

# A row is a finger's height (style.TOUCH): its ⋯ is tapped on the touchscreen.
ROW_H = 44
# The ⋯ column: a finger wide, as the card's lap buttons are (style.TOUCH_LAP).
DOTS_COL_W = 56
LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
TEAM_ROW_H = 54
# The team column's cap, in average characters; a longer name wraps.
TEAM_MAX_CHARS = 12
STAGED_TINT = QColor("#eef4ff")
# DNS, DNF and DQ rows recede, but stay readable for an older scorer:
# at least 4.5:1 on white, the floor for text.
STATUS_INK = QColor(style.DIM)
# The rider column is never narrower than this many average characters:
# a 16-character name ("Rosalind Vasquez") whole. Stretched, it would give
# its width to the sprint columns on a narrow surface and read "T..."; below
# the floor the table scrolls sideways instead.
NAME_MIN_CHARS = 16


def medal_tint(row: ResultRow, screen: Screen) -> QColor | None:
    """Gold, silver or bronze for a row placed 1st, 2nd or 3rd; a tie shares the tint.

    A points race before anyone has a point ranks the whole field 1st,
    which is no podium, so a row there needs points to earn the tint.
    """
    if row.entry is None or row.status or not row.place_text.isdigit():
        return None
    place = int(row.place_text)
    if not 1 <= place <= len(style.MEDAL_TINTS):
        return None
    if screen.points and not row.total:
        return None
    return style.MEDAL_TINTS[place - 1]


def row_menu(screen: Screen, i: int) -> tuple[tuple[str, str], ...]:
    """Row ``i``'s actions as the menu words them.

    Moving up a tied rider takes them out of the tie, ahead of the rest,
    and passes nobody, so on every row of a tie the action reads Break
    Tie, the first row included: Move Up there would look like a swap
    with the place above.
    """
    row = screen.rows[i]
    if not row.tied or row.entrant_id is None:
        return row.actions
    return tuple((k, BREAK_TIE if k == "move_up" else label) for k, label in row.actions)


class _FullCellDelegate(QStyledItemDelegate):
    """Puts a cell widget over the whole cell, not the cell less its padding.

    The table's item rule pads each side by style.SM, and the stock
    delegate places a cell widget inside that padding: the ⋯ strip would
    come out 16 px narrower than its column, its tint and glyph off the
    column's edges and center.
    """

    def updateEditorGeometry(self, editor, option, index) -> None:
        editor.setGeometry(option.rect)


class _LinesDelegate(QStyledItemDelegate):
    """Draws each line of a cell on its own line, elided to the column.

    A team's riders are one per line in a row two lines tall. Wrapped,
    a long name would take the second line and the other rider would
    not be drawn at all, with nothing to say so; elided, both riders
    show and the long one ends in an ellipsis.
    """

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        # The text's rect is asked for with the text in place: it is as
        # tall as the lines and centered in the cell, as the stock
        # drawing has it; for the empty text it would be one line.
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, widget)
        text, opt.text = opt.text, ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, widget) + 1
        rect = rect.adjusted(margin, 0, -margin, 0)
        metrics = QFontMetrics(opt.font)
        lines = elided_lines(text, metrics, rect.width())
        step = metrics.lineSpacing()
        top = rect.top() + max(0, (rect.height() - step * len(lines)) // 2)
        painter.save()
        painter.setFont(opt.font)
        painter.setPen(opt.palette.color(QPalette.ColorRole.Text))
        for i, line in enumerate(lines):
            box = QRect(rect.left(), top + i * step, rect.width(), step)
            painter.drawText(
                box, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), line
            )
        painter.restore()


def elided_lines(text: str, metrics: QFontMetrics, width: int) -> list[str]:
    """The lines of ``text``, each elided to ``width``.

    A style option carries the text with each newline made a line
    separator, so both are line breaks here.
    """
    lines = text.replace("\u2028", "\n").split("\n")
    return [metrics.elidedText(line, Qt.TextElideMode.ElideRight, width) for line in lines]


class ResultTable(QTableWidget):
    """``row_action(entrant_id, key)`` from a row's ⋯; ``sprint_clicked(n)`` from a header."""

    row_action = Signal(int, str)
    sprint_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("standings")
        self.screen: Screen | None = None
        self._sprint_columns: dict[int, int] = {}
        self._name_col = 2
        self._dots_delegate = _FullCellDelegate(self)
        self._lines_delegate = _LinesDelegate(self)
        self._place_laps_col: int | None = None
        self._laps_col: int | None = None
        self._penalty_col: int | None = None
        self._total_col: int | None = None
        # Counts the fills, so a row lit for its menu knows whether the
        # menu's own action refilled it under the light.
        self._fills = 0
        self.horizontalHeader().sectionClicked.connect(self._header_clicked)
        self.horizontalHeader().setSectionsClickable(False)
        self.setShowGrid(False)
        setup_table(self, ["Place", "Bib", "Rider"], selectable=False)

    # Filling -----------------------------------------------------------

    @staticmethod
    def _drawn_from(screen: Screen) -> tuple:
        """Everything in the screen the table is drawn from, to tell a redraw that changes nothing."""
        return (
            screen.team,
            screen.points,
            screen.review,
            screen.rows,
            screen.sprint_columns,
            screen.sprint_headers_open,
            screen.open_sprints,
            screen.current_sprint,
        )

    @staticmethod
    def _columns_of(screen: Screen) -> tuple:
        """What decides the columns; a screen that keeps them refills the rows in place."""
        return (
            screen.team,
            screen.points,
            tuple(screen.sprint_columns),
            screen.points and any(r.penalty for r in screen.rows),
            not screen.points and any(r.laps for r in screen.rows),
        )

    def show_screen(self, screen: Screen) -> None:
        old = self.screen
        self.screen = screen
        if old is not None and self._drawn_from(old) == self._drawn_from(screen):
            # The same rows as shown: refilling them would scroll the
            # table for nothing.
            return
        # A record, a lap, an Undo, or a staged click's tint changes rows,
        # not columns: the rows are refilled in place and keep their items
        # and ⋯ buttons, as a button made and polished per row is most of
        # a redraw. Only a change of columns lays the table out again.
        if old is None or self._columns_of(old) != self._columns_of(screen):
            self._lay_out(screen)
        self._style_headers(screen)
        self._fills += 1
        self.setRowCount(len(screen.rows))
        for i, row in enumerate(screen.rows):
            self._fill_row(i, row, screen)
        self._size_columns()
        # An elimination fills from the bottom up and a chase adds the
        # newest place last: keep the newest row in view. Standings rank
        # from the top, so the leaders stay in view there.
        newest_last = screen.rows and not screen.review and not screen.points
        if newest_last and screen.rows[-1].entrant_id is not None:
            self.scrollToBottom()
        else:
            self.scrollToTop()

    def _lay_out(self, screen: Screen) -> None:
        """The columns for ``screen``, with no rows yet."""
        # Items and cell widgets of the last layout go first: a column
        # count that changes would otherwise leave a ⋯ in a stale cell.
        self.clearContents()
        self.setRowCount(0)
        # A rider's bib has its own column so it never reads as part of
        # the name; a team is called by its name and has no one bib, and
        # its riders get their own column so the name is found alone.
        headers = ["Place", "Team", "Riders"] if screen.team else ["Place", "Bib", "Rider"]
        self._name_col = len(headers) - 1
        self._sprint_columns = {}
        self._laps_col = self._penalty_col = self._total_col = None
        if screen.points:
            for n in screen.sprint_columns:
                self._sprint_columns[n] = len(headers)
                headers.append(f"S{n}")
            self._laps_col = len(headers)
            headers.append("Laps")
            # A points ruling is rare: the column appears with the first
            # one, so the table carries no column that is usually empty.
            if any(r.penalty for r in screen.rows):
                self._penalty_col = len(headers)
                headers.append("Penalty")
            self._total_col = len(headers)
            headers.append("Total")
        # A finish order ranks a lapped rider by laps, so a lap entry
        # shows; a column that would be empty in most races does not.
        self._place_laps_col = None
        if not screen.points and any(r.laps for r in screen.rows):
            self._place_laps_col = len(headers)
            headers.append("Laps")
        headers.append("")
        setup_table(self, headers, selectable=False)
        header = self.horizontalHeader()
        # Fixed while the columns are sized here, once per redraw, not the
        # table's usual resize-to-contents: with that, every width set
        # below would measure every column again (hundreds of thousands of
        # style calls a click in a 50-sprint race). _fit_name stretches
        # the name column at the end.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        # The platform's minimum section size differs by platform and
        # font; the floors below size every column, so the minimum is the
        # cell's own overhead and no more, the same everywhere.
        header.setMinimumSectionSize(self._cell_overhead())
        header.setStretchLastSection(False)
        header.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(len(headers) - 1, DOTS_COL_W)
        # The ⋯ delegate on whichever column is last this redraw, the
        # riders' on a team race's name column, and none left on another.
        for col in range(len(headers)):
            delegate = None
            if col == len(headers) - 1:
                delegate = self._dots_delegate
            elif col == self._name_col and screen.team:
                delegate = self._lines_delegate
            if self.itemDelegateForColumn(col) is not delegate:
                self.setItemDelegateForColumn(col, delegate)
        # Headers sit where their cells do: words left, numbers right.
        for col in range(self.columnCount()):
            item = self.horizontalHeaderItem(col)
            if item is not None:
                # A team race's second column is the team, a word; else the bib.
                words = col in (0, self._name_col) or col == len(headers) - 1
                words = words or (col == 1 and screen.team)
                item.setTextAlignment(LEFT if words else RIGHT)

    def _style_headers(self, screen: Screen) -> None:
        """The sprint headers' open tint, tips, and the current sprint's weight."""
        self.horizontalHeader().setSectionsClickable(screen.sprint_headers_open)
        for n, col in self._sprint_columns.items():
            item = self.horizontalHeaderItem(col)
            is_open = n in screen.open_sprints
            item.setToolTip(f"Reopen Sprint {n} for correction" if is_open else "")
            item.setForeground(QColor(style.ACCENT) if is_open else QBrush())
            if n == screen.current_sprint:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            else:
                item.setData(Qt.ItemDataRole.FontRole, None)

    def _size_columns(self) -> None:
        """Size every column to its contents, each number column at least its header's width."""
        header = self.horizontalHeader()
        self.resizeColumnsToContents()
        # With no rows yet, a column is sized to its cells, which are none,
        # and "Place" is clipped; the header's own word sets the floor.
        # Every width is read before any is set: reading one after a set
        # lays the whole header out again, per column, which would make each
        # click of a 50-sprint race take most of a second.
        # The header is painted at the style sheet's weight, so it is
        # measured at that weight, not the font the widget reports.
        heavy = QFont(header.font())
        heavy.setWeight(QFont.Weight.DemiBold)
        metrics = QFontMetrics(heavy)
        widths = [header.sectionSize(col) for col in range(self.columnCount())]
        sprint_cols = set(self._sprint_columns.values())
        # A number column is at least its header's word with a gap each
        # side, and at least its widest value with the cell's overhead (the
        # padding and the margin the text is drawn inside) and a little
        # air: a floor that left the overhead out read fine only where the
        # platform's minimum section size happened to cover it, and lost a
        # two-digit value where it did not.
        overhead = self._cell_overhead()
        floors = {}
        for col in range(self.columnCount() - 1):
            item = self.horizontalHeaderItem(col)
            if item is not None and col != self._name_col:
                # A sprint column holds one or two digits: the narrow gap,
                # so a long race's columns all show (the scorer checks each
                # sprint by eye).
                gap = style.SM if col in sprint_cols else style.MD
                floors[col] = max(
                    metrics.horizontalAdvance(item.text()) + 2 * gap,
                    self._widest_cell(col) + overhead + 2 * style.XS,
                )
        # The sprint columns share one width, the widest's, and are held
        # to it: columns that differ by a digit's width read as a mistake.
        shared = max((floors[col] for col in sprint_cols if col in floors), default=0)
        raise_to = {}
        for col, floor in floors.items():
            if col in sprint_cols:
                if widths[col] != shared:
                    raise_to[col] = shared
            elif widths[col] < floor:
                raise_to[col] = floor
        # The ⋯ column is a finger wide whatever its contents measured.
        last = self.columnCount() - 1
        if widths[last] != DOTS_COL_W:
            raise_to[last] = DOTS_COL_W
        for col, floor in raise_to.items():
            header.resizeSection(col, floor)
        if self.screen is not None and self.screen.team:
            # A long team name ("Stars and Stripes") wraps onto the row's
            # second line rather than taking the riders' room.
            cap = self.fontMetrics().averageCharWidth() * TEAM_MAX_CHARS + 2 * style.MD
            if header.sectionSize(1) > cap:
                header.resizeSection(1, cap)
        self._fit_name()

    def _widest_cell(self, col: int) -> int:
        """The widest text in the column's cells, each in the font it is drawn in."""
        widest = 0
        plain = QFontMetrics(self.font())
        for row in range(self.rowCount()):
            item = self.item(row, col)
            if item is not None and item.text():
                own = item.data(Qt.ItemDataRole.FontRole) is not None
                metrics = QFontMetrics(item.font()) if own else plain
                widest = max(widest, metrics.horizontalAdvance(item.text()))
        return widest

    def _cell_overhead(self) -> int:
        """What a cell takes from its column before the text: the style sheet's
        padding and the delegate's own text margin, SM a side between them."""
        return 2 * style.SM

    def _name_floor(self) -> int:
        return self.fontMetrics().averageCharWidth() * NAME_MIN_CHARS + 2 * style.SM

    def needed_width(self) -> int:
        """The width at which every column shows and the names are at their floor.

        The surface gives the standings this much before the cards get
        their share, so a long race's sprint columns never scroll out of
        sight beside the cards.
        """
        if self.columnCount() == 0:
            return 0
        col = self._name_col
        others = sum(self.columnWidth(c) for c in range(self.columnCount()) if c != col)
        bar = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, self)
        return others + self._name_floor() + 2 * self.frameWidth() + bar

    def whole_width(self) -> int:
        """The width at which every column shows and every name is whole on one line.

        Beside cards that hold room their names do not use, the surface
        gives the standings up to this much, so a long name is not cut
        in the table while the cards stand half empty.
        """
        if self.columnCount() == 0:
            return 0
        col = self._name_col
        metrics = QFontMetrics(self.font())
        widest = 0
        for row in range(self.rowCount()):
            item = self.item(row, col)
            if item is not None:
                for line in item.text().split("\n"):
                    widest = max(widest, metrics.horizontalAdvance(line))
        name = max(self._name_floor(), widest + self._cell_overhead() + 2 * style.XS)
        return self.needed_width() - self._name_floor() + name

    def _fit_name(self) -> None:
        """Stretch the name column over the room left, but never below its floor."""
        if self.columnCount() <= self._name_col:
            return
        header = self.horizontalHeader()
        col = self._name_col
        others = sum(self.columnWidth(c) for c in range(self.columnCount()) if c != col)
        floor = self._name_floor()
        # Only a change of mode or width is applied, so a resize that
        # leaves the column as it was does no layout work at all.
        stretch = self.viewport().width() - others >= floor
        mode = QHeaderView.ResizeMode.Stretch if stretch else QHeaderView.ResizeMode.Fixed
        if header.sectionResizeMode(col) != mode:
            header.setSectionResizeMode(col, mode)
        if not stretch and header.sectionSize(col) != floor:
            header.resizeSection(col, floor)

    def resizeEvent(self, event) -> None:
        # Column widths only, from the width alone; the widget's own
        # geometry and style are left as they are.
        super().resizeEvent(event)
        self._fit_name()

    def _fill_row(self, i: int, row: ResultRow, screen: Screen) -> None:
        team = row.entry is not None and bool(row.entry.color)
        self.setRowHeight(i, TEAM_ROW_H if team else ROW_H)
        self._cell(i, 0, row.place_text, bold=True).setData(ID_ROLE, row.entrant_id)
        if row.entry is None:
            who = ""
        elif screen.team:
            # One rider per line, no divider: a slash would float between
            # wrapped names. The team row is two lines tall.
            who = "\n".join(row.entry.names)
        else:
            who = row.entry.names[0] if row.entry.names else ""
        if screen.team:
            name = self._cell(
                i, 1, row.entry.team or "" if row.entry is not None else "", bold=True
            )
            color = row.entry.color if row.entry is not None else ""
            name.setIcon(swatch_icon(color) if color else QIcon())
        else:
            bib = str(row.entry.bibs[0]) if row.entry is not None and row.entry.bibs else ""
            self._cell(i, 1, bib, RIGHT)
        self._cell(i, self._name_col, who)
        if screen.points:
            for n, col in self._sprint_columns.items():
                value = row.sprints[n - 1] if n - 1 < len(row.sprints) else None
                cell = self._cell(i, col, "" if value is None else str(value), RIGHT)
                if value == 0:
                    cell.setForeground(STATUS_INK)
            self._cell(i, self._laps_col or 0, lap_text(row.laps), RIGHT)
            if self._penalty_col is not None:
                self._cell(i, self._penalty_col, lap_text(row.penalty), RIGHT)
            total = "" if row.total is None or row.entry is None else total_text(row.total)
            self._cell(i, self._total_col or 0, total, RIGHT, bold=True)
        if self._place_laps_col is not None:
            self._cell(i, self._place_laps_col, lap_text(row.laps), RIGHT)
        last = self.columnCount() - 1
        self._cell(i, last, "")
        dots = self.cellWidget(i, last)
        if row.actions:
            if dots is None:
                b = dots_button(self)
                b.clicked.connect(lambda _c=False, r=i: self.open_row_menu(r))
                self.setCellWidget(i, last, b)
        elif dots is not None:
            # The table deletes the button on the next pass of the event
            # loop and leaves it shown until then; hidden here, so a grab
            # or a menu's nested loop never sees a ⋯ on a row without one.
            self.removeCellWidget(i, last)
            dots.hide()
        if row.status or row.note:
            # A placed row with a status (an elimination's DNF, out at
            # that moment) or a note (a mishap kept the rider out of the
            # final sprint) shows its number; the gray says something
            # happened and the tip says what.
            if row.note:
                tip = row.note
            else:
                tip = (
                    STATUS_WORDS.get(row.status, row.status) if row.place_text != row.status else ""
                )
            for c in range(self.columnCount()):
                item = self.item(i, c)
                if item is not None:
                    item.setForeground(STATUS_INK)
                    item.setToolTip(tip)
        tint = STAGED_TINT if row.staged else medal_tint(row, screen)
        if tint is not None:
            for c in range(self.columnCount()):
                item = self.item(i, c)
                if item is not None:
                    item.setBackground(tint)

    def _cell(self, i: int, col: int, text: str, align=LEFT, *, bold: bool = False):
        """The item at (``i``, ``col``) with ``text``, made on the first fill and plain again on the next.

        Its ink, tint, and tip are cleared here and set after by the row;
        a column's weight never changes while the columns stand, so it is
        set once, when the item is made.
        """
        item = self.item(i, col)
        if item is None:
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if bold:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.setItem(i, col, item)
        item.setText(text)
        item.setTextAlignment(align)
        item.setForeground(QBrush())
        item.setBackground(QBrush())
        item.setToolTip("")
        return item

    # Menus -------------------------------------------------------------

    def row_of(self, entrant_id: int) -> int:
        if self.screen is None:
            return -1
        return next((i for i, r in enumerate(self.screen.rows) if r.entrant_id == entrant_id), -1)

    def contextMenuEvent(self, event) -> None:
        # A second way to the row's visible ⋯, never the only one; a
        # right-click on a row without one opens nothing.
        i = self.indexAt(self.viewport().mapFromGlobal(event.globalPos())).row()
        if i >= 0 and self.open_row_menu(i, event.globalPos()):
            event.accept()
        else:
            event.ignore()

    def open_row_menu(self, i: int, where: QPoint | None = None) -> bool:
        """Open row ``i``'s actions, under its ⋯ or at ``where``; False when the row has none."""
        if self.screen is None or not 0 <= i < len(self.screen.rows):
            return False
        row = self.screen.rows[i]
        if not row.actions or row.entrant_id is None:
            return False
        menu = QMenu(self)
        # Tapped on the touchscreen: TOUCH-tall items (style.py).
        menu.setObjectName("touchMenu")
        items = row_menu(self.screen, i)
        slot = lambda key, e=row.entrant_id: self.row_action.emit(e, key)  # noqa: E731
        # The long moves fold into one submenu of places, so a 16-rider
        # elimination's menu stays five items long.
        moves = [(k, label.removeprefix("Move to ")) for k, label in items if k.startswith(MOVE_TO)]
        plain = [(k, label) for k, label in items if not k.startswith(MOVE_TO)]
        fill_menu(menu, [(k, label) for k, label in plain if k != "dq"], slot)
        if moves:
            places = menu.addMenu(REVIEW_ACTIONS["move_to"])
            places.setObjectName("touchMenu")
            fill_menu(places, moves, slot)
        # Disqualify stays last, after the moves.
        fill_menu(menu, [(k, label) for k, label in plain if k == "dq"], slot)
        if where is None:
            w = self.cellWidget(i, self.columnCount() - 1)
            where = w.mapToGlobal(QPoint(0, w.height())) if w else self.mapToGlobal(QPoint(0, 0))
        # The row stays lit while its menu is open, so the menu says whose
        # it is; its own shading comes back after.
        was = self._light_row(i)
        try:
            widgets.run_menu(menu, where)
        finally:
            self._unlight_row(i, was)
        return True

    def _light_row(self, i: int) -> tuple[list, QWidget | None, int]:
        """Tint row ``i`` as a pressed control; returns what to put back.

        The chosen action can refill the rows before the menu's loop
        returns, so what comes back is keyed to the fill it was taken
        from: a refilled row already has its shading, and only its ⋯,
        kept across fills, is still lit.
        """
        was: list = []
        for c in range(self.columnCount()):
            item = self.item(i, c)
            if item is not None:
                was.append(item.background())
                item.setBackground(QColor(style.ACCENT_TINT_STRONG))
            else:
                was.append(None)
        w = self.cellWidget(i, self.columnCount() - 1)
        if w is not None:
            w.setProperty("lit", True)
            w.style().unpolish(w)
            w.style().polish(w)
        return was, w, self._fills

    def _unlight_row(self, i: int, lit: tuple[list, QWidget | None, int]) -> None:
        was, dots, fill = lit
        if i >= self.rowCount():
            return
        if fill == self._fills:
            for c, brush in enumerate(was):
                item = self.item(i, c)
                if item is not None and brush is not None:
                    item.setBackground(brush)
        w = self.cellWidget(i, self.columnCount() - 1)
        if w is not None and (w is dots or w.property("lit")):
            w.setProperty("lit", False)
            w.style().unpolish(w)
            w.style().polish(w)

    def _header_clicked(self, section: int) -> None:
        if self.screen is None or not self.screen.sprint_headers_open:
            return
        for n, col in self._sprint_columns.items():
            if col == section:
                # A column not yet recorded answers with the refusal, not silence.
                self.sprint_clicked.emit(n)
                return

    def sprint_column(self, n: int) -> int | None:
        return self._sprint_columns.get(n)
