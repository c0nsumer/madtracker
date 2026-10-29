"""The left region: the event's races in order under its name; the Edit | Score switch it owns.

The pane's heading is the event's name and date: the title bar carries
them too, but macOS full screen hides it. The Edit | Score switch is
the pane's, but the window places it: in the bar along the bottom,
under this column and as wide as it, beside Undo. It is the event's
two screens, not part of the list.

Each row is the race's name and group, and one word of status when it
is not the obvious one (design section 5). The selected race is the
one being scored; selecting another is how the scorer moves on.

There are no right-click menus: each of their items had a visible
control already, and a hidden second door to setup from the scoring
screen goes against the night's order.
"""

import math
from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from madtracker.dates import show_date
from madtracker.ui import style
from madtracker.ui.icons import BUTTON_ICON_GAP, mdi_pixmap

ID_ROLE = Qt.ItemDataRole.UserRole
GROUP_ROLE = Qt.ItemDataRole.UserRole + 1
STATUS_ROLE = Qt.ItemDataRole.UserRole + 2
ROW_H = 50
# The group and the status word: the window's smallest text.
SMALL_PT = 12
SELECTED_BAR = 4

# The one word a row shows when its state is not the obvious one. Racing
# marks a race with entries and no result yet: switching to another race
# asks first, and the list says which race that is.
STATUS_WORD = {"running": "Racing", "provisional": "Provisional", "final": "Final"}

EDIT = "Edit"
SCORE = "Score"
MODE_ICON_PX = 18
NO_EVENT_TIP = "No event yet. File > New Event..."


@dataclass(frozen=True)
class ProgramRow:
    race_id: int
    name: str
    group: str
    state: str

    @property
    def status(self) -> str:
        return STATUS_WORD.get(self.state, "")


# The race name wraps rather than being cut: a row is as tall as its
# name and group lines at the list's width, and never under ROW_H. The
# two lines are centered as one block, so a row with room to spare
# shares it above and below rather than leaving a gap under the name.
ROW_PAD = 2
# Wrapped at word breaks, and inside a word only when one word is wider
# than the row: cut at the edge, it would lose letters. Only a QTextOption
# offers that mode; QPainter's flags give one or the other.
NAME_WRAP = QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
# The row's text inset, each side.
ROW_INSET = 12


def _name_font():
    return style.ui_font(13, bold=True)


def _tag_font():
    return style.ui_font(SMALL_PT, bold=True)


def _tag_height() -> int:
    return QFontMetrics(_tag_font()).height() + style.XS


def _group_line_h() -> int:
    """The group line's height: its text's, and never under the tag it carries."""
    return max(QFontMetrics(style.ui_font(SMALL_PT)).height(), _tag_height())


class _RowDelegate(QStyledItemDelegate):
    def _wrap_width(self, fallback: int) -> int:
        """The name's width, the same with or without the scroll bar.

        Measured at the viewport's width, the rows would be laid out before
        a long program's scroll bar appeared and narrowed it, so a wrapped
        row would overlap the next. The scroll bar's room is always kept
        instead, and the paint wraps at the same width.
        """
        view = self.parent()
        if view is None:
            return max(1, fallback - 2 * ROW_INSET)
        bar = view.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, view)
        return max(1, view.maximumViewportSize().width() - bar - 2 * ROW_INSET)

    def _name_height(self, index, width: int) -> int:
        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        layout = QTextLayout(name, _name_font())
        option = QTextOption()
        option.setWrapMode(NAME_WRAP)
        layout.setTextOption(option)
        height = 0.0
        layout.beginLayout()
        while (line := layout.createLine()).isValid():
            line.setLineWidth(width)
            height += line.height()
        layout.endLayout()
        return max(QFontMetrics(_name_font()).height(), math.ceil(height))

    def sizeHint(self, option, index) -> QSize:
        name_h = self._name_height(index, self._wrap_width(option.rect.width()))
        group_h = _group_line_h()
        return QSize(option.rect.width(), max(ROW_H, ROW_PAD + name_h + group_h + ROW_PAD))

    def paint(self, p: QPainter, option, index) -> None:
        p.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            # The race being scored: the "you are here" fill, with an accent
            # bar on its edge so it holds the eye down a long program.
            p.fillRect(rect, QColor(style.NEXT_BLUE))
            p.fillRect(rect.x(), rect.y(), SELECTED_BAR, rect.height(), QColor(style.ACCENT))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            # The pointer's row, as every other control lights under the
            # pointer; the list tracks the mouse for it.
            p.fillRect(rect, QColor(style.ACCENT_TINT))
        elif index.row() % 2:
            p.fillRect(rect, QColor("#f5f6f8"))
        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        group = index.data(GROUP_ROLE) or ""
        status = index.data(STATUS_ROLE) or ""
        x = rect.x() + ROW_INSET
        w = rect.width() - 2 * ROW_INSET
        p.setPen(QColor("#11151b"))
        p.setFont(_name_font())
        wrap = min(w, self._wrap_width(rect.width()))
        name_h = self._name_height(index, wrap)
        group_h = _group_line_h()
        top = rect.y() + max(ROW_PAD, (rect.height() - name_h - group_h) // 2)
        option = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        option.setWrapMode(NAME_WRAP)
        p.drawText(QRectF(x, top, wrap, name_h), name, option)
        group_y = top + name_h
        font = _tag_font()
        metrics = QFontMetrics(font)
        pw = metrics.horizontalAdvance(status) + 2 * style.SM if status else 0
        # The group stops short of the tag, cut with "...": under the
        # hollow Provisional tag a long group would show through.
        group_w = w - (pw + style.SM if status else 0)
        small = style.ui_font(SMALL_PT)
        p.setFont(small)
        p.setPen(QColor("#5b6472"))
        shown = QFontMetrics(small).elidedText(group, Qt.TextElideMode.ElideRight, max(0, group_w))
        p.drawText(x, group_y, group_w, group_h, int(Qt.AlignmentFlag.AlignVCenter), shown)
        if status:
            # A tag, so the one word reads as a state at a glance down the
            # list: amber for Racing (the surface's own color for it), accent
            # for Provisional (still to be confirmed), green for Final, the
            # window's own meaning for each color, and the surface's shape.
            ph = _tag_height()
            pill = QRectF(x + w - pw, group_y + (group_h - ph) / 2, pw, ph)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if status == "Final":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(style.OK_GREEN))
                ink = QColor("#ffffff")
            elif status == "Racing":
                # Filled amber with the ink, as the surface's Racing pill.
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(style.LIVE))
                ink = QColor(style.INK)
            else:
                # Hollow while provisional, as on the surface and the board.
                ink = QColor(style.ACCENT)
                # A whole 2 px, inset by half of it, so the line lands on
                # pixels at 100, 125 and 150 percent; 1.5 px is soft.
                p.setPen(QPen(ink, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                pill = pill.adjusted(1, 1, -1, -1)
            p.drawRoundedRect(pill, style.TAG_RADIUS, style.TAG_RADIUS)
            p.setPen(ink)
            p.setFont(font)
            p.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), status)
        p.restore()


class _RaceList(QListWidget):
    """The race rows, where the right button never selects.

    Qt's item views select the row under any button's press. Here the
    selected race is the one being scored and shown on the TV, so the
    right button is dropped before the view sees it.
    """

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        super().mousePressEvent(event)


def _mode_icon(name: str) -> QIcon:
    """Dim on the side that is off, white on the side that is on.

    The icon's On state is what Qt draws for a checked button, so the
    switch needs no handler to recolor it, and no re-polish. The glyph
    carries the same clear space on its right as every icon button's.
    """
    icon = QIcon()
    for dpr in (1.0, 2.0):
        for mode, state, tint in (
            (QIcon.Mode.Normal, QIcon.State.Off, style.DIM),
            (QIcon.Mode.Normal, QIcon.State.On, "#ffffff"),
            (QIcon.Mode.Disabled, QIcon.State.Off, "#9aa1ad"),
            (QIcon.Mode.Disabled, QIcon.State.On, "#9aa1ad"),
        ):
            pix = QPixmap(round((MODE_ICON_PX + BUTTON_ICON_GAP) * dpr), round(MODE_ICON_PX * dpr))
            pix.setDevicePixelRatio(dpr)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.drawPixmap(0, 0, mdi_pixmap(name, MODE_ICON_PX, tint, dpr))
            painter.end()
            icon.addPixmap(pix, mode, state)
    return icon


class ModeSwitch(QFrame):
    """Edit | Score: which of the two screens the event is on, and the way to the other.

    A single button named for where it goes (Edit event while scoring,
    Score event in setup) would not say where the scorer is; the switch
    shows both.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modeSwitch")
        self.edit = self._side(EDIT, "playlist-edit")
        self.score = self._side(SCORE, "bike")
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(3)
        for side in (self.edit, self.score):
            self.group.addButton(side)
            lay.addWidget(side, 1)
        self.open = False
        self.score.setChecked(True)

    @staticmethod
    def _side(text: str, icon: str) -> QPushButton:
        side = QPushButton(text)
        side.setObjectName("mode")
        side.setCheckable(True)
        side.setFont(style.ui_font(12, bold=True))
        side.setIcon(_mode_icon(icon))
        side.setIconSize(QSize(MODE_ICON_PX + BUTTON_ICON_GAP, MODE_ICON_PX))
        # No focus, as the scoreboard switch and Undo beside the screen:
        # on Windows the window would hand focus to the side that is off,
        # and its ring would make that side look half chosen.
        side.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return side

    def show_mode(self, open: bool) -> None:
        self.open = open
        side = self.edit if open else self.score
        if not side.isChecked():
            side.setChecked(True)


class ProgramPane(QWidget):
    race_selected = Signal(int)
    setup_requested = Signal()
    score_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.heading = QLabel("")
        self.heading.setObjectName("eventName")
        self.heading.setFont(style.ui_font(14, bold=True))
        self.heading.setWordWrap(True)
        self.date = QLabel("No event")
        self.date.setObjectName("raceDetail")
        # The event sits on a tinted band in the accent, the pairing the
        # selected row, Undo, and the preview's hover use, so the night's
        # name has a place of its own at the top of the column without
        # pulling the eye from the race's title and tag.
        self.band = QFrame()
        self.band.setObjectName("eventBand")
        band = QVBoxLayout(self.band)
        band.setContentsMargins(style.MD, style.SM, style.MD, style.SM)
        band.setSpacing(style.XS)
        band.addWidget(self.heading)
        band.addWidget(self.date)
        self.list = _RaceList()
        self.list.setObjectName("outline")
        self.list.setItemDelegate(_RowDelegate(self.list))
        # The row under the pointer is tinted (the delegate's State_MouseOver),
        # which needs move events without a button down.
        self.list.setMouseTracking(True)
        # A new width lays the rows out again, so a name rewraps.
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self._row_changed)
        self.mode = ModeSwitch()
        self.mode.edit.clicked.connect(self._edit_clicked)
        self.mode.score.clicked.connect(self._score_clicked)
        self.box = QFrame()
        self.box.setObjectName("pane")
        box = QVBoxLayout(self.box)
        box.setContentsMargins(10, 10, 10, 10)
        box.setSpacing(8)
        box.addWidget(self.band)
        box.addWidget(self.list, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # The gap between any two of the window's panes.
        lay.setSpacing(style.SM)
        lay.addWidget(self.box, 1)
        self._lay = lay
        self._rows: list[ProgramRow] = []
        self._loading = False

    def place_preview(self, pane: QWidget) -> None:
        """The TV preview under the races, the column's bottom."""
        self._lay.addWidget(pane)

    def set_setup_open(self, open: bool) -> None:
        """Which side of the switch is on: Edit while setup is open, Score otherwise."""
        self.mode.show_mode(open)

    def setup_open(self) -> bool:
        return self.mode.edit.isChecked()

    def _edit_clicked(self) -> None:
        # A click on the side already on is the screen the scorer is on;
        # the exclusive group keeps it checked, and nothing is asked.
        if not self._open:
            self.setup_requested.emit()
        self.mode.show_mode(self._open)

    def _score_clicked(self) -> None:
        if self._open:
            self.score_requested.emit()
        self.mode.show_mode(self._open)

    @property
    def _open(self) -> bool:
        return self.mode.open

    def set_event(self, name: str, date: str) -> None:
        """The open event over its races; with none, the heading says so rather than stand empty."""
        self.heading.setText(name)
        self.heading.setVisible(bool(name))
        self.date.setText(show_date(date) if date else "" if name else "No event")
        self.date.setVisible(bool(self.date.text()))
        self.set_has_event(bool(name))

    def set_has_event(self, has_event: bool) -> None:
        # With no event there is nothing to set up or score; a click that
        # did nothing would read as broken, so the switch says why it is off.
        self.mode.setEnabled(has_event)
        self.mode.setToolTip("" if has_event else NO_EVENT_TIP)

    def set_races(
        self,
        rows: list[ProgramRow],
        current: int | None,
    ) -> None:
        """The races in order, with ``current`` selected."""
        index = next((i for i, r in enumerate(rows) if r.race_id == current), -1)
        # Every click redraws the program, and almost every click leaves
        # it as it was; rebuilding the list then would make and style every row
        # again for nothing. The selection is still set: a click on
        # another race that the scorer then declined to switch to must
        # come back to the race being scored.
        same = list(rows) == self._rows and self.list.count() == len(rows)
        # The same races with a word changed (Final, Racing) keep their
        # items: a cleared list starts at the top, and the scorer who had
        # scrolled to the race being marked would be thrown back up.
        same_races = [r.race_id for r in rows] == [r.race_id for r in self._rows]
        in_place = same_races and self.list.count() == len(rows)
        self._rows = list(rows)
        self._loading = True
        try:
            if not same and in_place:
                for i, row in enumerate(rows):
                    item = self.list.item(i)
                    item.setText(row.name)
                    item.setData(GROUP_ROLE, row.group)
                    item.setData(STATUS_ROLE, row.status)
            elif not same:
                # A race added, removed, or moved: the list is built again
                # where it was scrolled, as far as the new list reaches.
                bar = self.list.verticalScrollBar()
                at = bar.value()
                self.list.clear()
                for row in rows:
                    item = QListWidgetItem(row.name)
                    item.setData(ID_ROLE, row.race_id)
                    item.setData(GROUP_ROLE, row.group)
                    item.setData(STATUS_ROLE, row.status)
                    self.list.addItem(item)
                self.list.setCurrentRow(index)
                self.list.doItemsLayout()
                bar.setValue(at)
            if self.list.currentRow() != index:
                self.list.setCurrentRow(index)
        finally:
            self._loading = False

    def _row_changed(self, index: int) -> None:
        if self._loading:
            return
        if 0 <= index < len(self._rows):
            self.race_selected.emit(self._rows[index].race_id)

    def current_race_id(self) -> int | None:
        index = self.list.currentRow()
        return self._rows[index].race_id if 0 <= index < len(self._rows) else None

    def select(self, race_id: int) -> None:
        index = next((i for i, r in enumerate(self._rows) if r.race_id == race_id), -1)
        self.list.setCurrentRow(index)

    def row_texts(self) -> list[tuple[str, str, str]]:
        return [(r.name, r.group, r.status) for r in self._rows]
