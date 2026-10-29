"""The scoring surface: the state line, the task line, the cards, the result so far.

Top to bottom as docs/design.md section 7 lists it. The only buttons
are the ones a format or a state needs: Record sprint in a points race
or madison (with Cancel to its left while a reopened sprint is being
corrected), Place the Rest Together in a finish-order race once someone
is placed and two or more are not, Mark final once the result is
complete, and Reopen once it is final. A race's field is set in Edit
event, never here. Everything else is a click on a card, a ⋯ on a card
or a row, or a sprint column header. A refused click says why in the
one red line under the task line, which is empty otherwise.
"""

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from madtracker.control.race import REST_TOGETHER_LABEL, Screen
from madtracker.ui import style, widgets
from madtracker.ui.cards import CARD_MIN_W, CardGrid
from madtracker.ui.icons import mdi, set_button_icon
from madtracker.ui.review import ResultTable
from madtracker.ui.widgets import ElidedLabel, OneClickButton

TITLE_PT = 18
TASK_PT = 16
STATE_PT = 14
PROBLEM_STYLE = "color: #b3261e; font-weight: 600;"
STATE_STYLE = {
    "Start list": style.DIM,
    "Racing": style.LIVE,
    "Final sprint": style.LIVE,
    "Provisional": style.ACCENT,
    "Final": style.OK_GREEN,
}
# White reads on every state color but amber, which takes the ink.
STATE_INK = {style.LIVE: style.INK}
# The state's color as a stripe along the pane's top edge, so the
# race's state shows from across the table, not only in the pill.
STRIPE_PX = 4


def state_color(label: str) -> str:
    return STATE_STYLE.get(label, style.DIM)


# Hollow, as the scoreboard's stamp is: a result waiting to be confirmed
# is outlined, and only Final is filled, on every screen.
HOLLOW_STATES = {"Provisional"}


def state_pill(label: str) -> str:
    """The state label's style sheet: a pill in the state's color, hollow while provisional."""
    color = state_color(label)
    radius = f" border-radius: {style.TAG_RADIUS}px;"
    if label in HOLLOW_STATES:
        # The 2 px border comes out of the padding, so the pill keeps its size.
        return (
            f"background: transparent; color: {color}; border: 2px solid {color};"
            f"{radius} padding: {style.XS - 2}px {style.MD - 2}px;"
        )
    return (
        f"background: {color}; color: {STATE_INK.get(color, '#ffffff')};"
        f"{radius} padding: {style.XS}px {style.MD}px;"
    )


def paint_stripe(pane: QWidget, color: str) -> None:
    """The state's band along a pane's top edge, inside its border and rounding."""
    p = QPainter(pane)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    inner = QRectF(pane.rect()).adjusted(1, 1, -1, -2)
    path = QPainterPath()
    path.addRoundedRect(inner, 5, 5)
    p.setClipPath(path)
    p.fillRect(QRectF(inner.x(), inner.y(), inner.width(), STRIPE_PX), QColor(color))
    p.end()


PRIMARY_H = 44
# From this width the cards and the standings sit side by side, the cards
# taking this share of it: on a 1920 display two columns of whole names
# with finger-sized buttons beside a points table with its sprint
# columns (0.55 would leave one column); a 1366 laptop stacks.
WIDE_W = 1300
WIDE_PRIMARY_H = 60
CARDS_SHARE = 0.6
# Standings rows kept visible under the cards once a race has a result:
# enough to read the top of the order without scrolling the table.
RESULT_ROWS = 5
# The fewest the standings keep when the cards need the room: a card
# under a scroll cannot be clicked at a glance, so the standings give up
# rows first, as two columns of finger-sized cards at 1366 need; team
# cards are one line as rider cards are.
RIDER_RESULT_ROWS = 3


def restyle(widget: QWidget, sheet: str) -> None:
    """Set a widget's own style sheet only when it changes.

    Qt re-polishes the widget on every setStyleSheet, even with the same
    text, and the surface is redrawn on every click; a re-polish is the
    work Windows is slowest at.
    """
    if widget.styleSheet() != sheet:
        widget.setStyleSheet(sheet)


def primary_button(text: str) -> QPushButton:
    """The surface's one filled button: Record sprint, or Mark final."""
    # One click per double-click: Mark final's first click puts Reopen
    # under the pointer, and the second press would reopen the race.
    b = OneClickButton(text)
    set_button_icon(b, "check", "#ffffff")
    b.setMinimumHeight(PRIMARY_H)
    b.setFont(style.ui_font(13, bold=True))
    b.setStyleSheet(
        f"QPushButton {{ background: {style.ACCENT}; color: white; border-radius: 6px;"
        # No vertical padding: the height is PRIMARY_H, as for every button
        # in the row, so trading one for another never moves the table.
        " padding: 0 18px; }"
        " QPushButton:disabled { background: #c3c9d2; color: #ffffff; }"
    )
    return b


def task_text(screen: Screen) -> str:
    """The task line; a reopened sprint says it is a correction, not the next sprint."""
    task = screen.task
    if task.editing and task.sprint_no is not None:
        # The sprint's own line, how many to click included, as a correction.
        head, _, rest = task.text.partition(": ")
        what = "the final sprint" if head == "Final sprint" else f"Sprint {task.sprint_no}"
        return f"Correcting {what}: {rest}"
    return task.text


class TaskLabel(QLabel):
    """The task line. A right-click opens the race's ⋯ menu, as it does on a card."""

    def __init__(self, open_menu) -> None:
        super().__init__("")
        self._open_menu = open_menu

    def contextMenuEvent(self, event) -> None:
        if self._open_menu(event.globalPos()):
            event.accept()
        else:
            event.ignore()


class Surface(QFrame):
    card_clicked = Signal(int)
    rider_action = Signal(int, str)
    race_action = Signal(str)
    record_requested = Signal()
    rest_together_requested = Signal()
    row_action = Signal(int, str)
    sprint_clicked = Signal(int)
    final_requested = Signal()
    reopen_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pane")
        self.screen: Screen | None = None

        self.title = ElidedLabel("")
        self.title.setObjectName("raceTitle")
        self.title.setFont(style.ui_font(TITLE_PT, bold=True))
        self.detail = QLabel("")
        self.detail.setObjectName("raceDetail")
        self.detail.setFont(style.ui_font(12))
        # The field's size, before the state: the scorer's quick check
        # that everyone is at the rail.
        self.field = QLabel("")
        self.field.setObjectName("raceDetail")
        self.field.setFont(style.ui_font(STATE_PT))
        self.state = QLabel("")
        self.state.setFont(style.ui_font(STATE_PT, bold=True))
        self.state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(self.title)
        head.addWidget(self.detail, 1)
        head.addWidget(self.field)
        head.addWidget(self.state)
        # The ruleset's line about the format, when the venue wrote one;
        # takes no room otherwise.
        self.description = QLabel("")
        self.description.setObjectName("raceDescription")
        self.description.setFont(style.ui_font(12))
        self.description.setWordWrap(True)
        self.description.setVisible(False)

        self.task = TaskLabel(self.open_race_actions)
        self.task.setFont(style.ui_font(TASK_PT, bold=True))
        self.task.setWordWrap(True)
        # The race's own ⋯, at the end of the task line: a finger-sized
        # strip in the card's glyph, there from the race's first screen in
        # every format that has a call of its own (End Race Now, Result
        # As-Is; Shorten Race), so the line keeps one height as the race
        # goes; an item not open yet is grayed in the menu.
        self.task_dots = QToolButton(self)
        self.task_dots.setObjectName("taskActions")
        self.task_dots.setCursor(Qt.CursorShape.PointingHandCursor)
        self.task_dots.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.task_dots.setFixedSize(style.TOUCH, style.TOUCH)
        side = round(style.TOUCH * 0.55)
        self.task_dots.setIcon(mdi("dots-horizontal", side, style.DIM))
        self.task_dots.setIconSize(QSize(side, side))
        self.task_dots.setToolTip("The race's own actions")
        self.task_dots.clicked.connect(lambda: self.open_race_actions())
        self.task_dots.setVisible(False)
        task_row = QHBoxLayout()
        task_row.setContentsMargins(0, 0, 0, 0)
        task_row.setSpacing(style.SM)
        task_row.addWidget(self.task, 1)
        task_row.addWidget(self.task_dots, 0, Qt.AlignmentFlag.AlignTop)
        self._flash = QTimer(self)
        self._flash.setSingleShot(True)
        self._flash.setInterval(700)
        self._flash.timeout.connect(self._end_flash)
        self.problem = QLabel("")
        self.problem.setStyleSheet(PROBLEM_STYLE)
        self.problem.setWordWrap(True)
        self.problem.setVisible(False)

        self.cards = CardGrid()
        self.cards.pressed_entrant.connect(self.card_clicked)
        self.cards.action.connect(self.rider_action)

        self.cancel_button = OneClickButton("Cancel")
        self.cancel_button.setMinimumHeight(PRIMARY_H)
        self.cancel_button.setFont(style.ui_font(13))
        self.cancel_button.setToolTip("Leave the sprint as it was scored")
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.record_button = primary_button("Record Sprint")
        self.record_button.clicked.connect(self.record_requested)
        # Record Sprint's slot in a finish-order race: the one button
        # that completes the order, so it sits where the scorer's hand
        # already goes.
        self.rest_button = primary_button(REST_TOGETHER_LABEL)
        self.rest_button.setToolTip("The riders still unplaced share the next place")
        self.rest_button.clicked.connect(self.rest_together_requested)
        self.final_button = primary_button("Mark Final")
        self.final_button.clicked.connect(self.final_requested)
        # Mark final's height and type: one replaces the other in the same
        # row, and a shorter button would move the table under it.
        self.reopen_button = OneClickButton("Reopen")
        set_button_icon(self.reopen_button, "lock-open-variant-outline")
        self.reopen_button.setMinimumHeight(PRIMARY_H)
        self.reopen_button.setFont(style.ui_font(13))
        self.reopen_button.clicked.connect(self.reopen_requested)
        # No focus, as the cards above them: Mark final's click would leave
        # focus on it, and when Reopen took its place the ring would move to
        # Reopen, where Space or Enter would reopen the race.
        for b in self._buttons():
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # The row under the cards: what records them. Stacked, the
        # finishing buttons sit in it too; side by side they go under the
        # table they close.
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.record_button)
        buttons.addWidget(self.rest_button)
        self.buttons = buttons
        self.final_row = QHBoxLayout()
        self.final_row.addStretch(1)
        self.final_box = QWidget()
        self.final_box.setLayout(self.final_row)
        self.final_row.setContentsMargins(0, 0, 0, 0)

        self.table = ResultTable()
        self.table.row_action.connect(self.row_action)
        self.table.sprint_clicked.connect(self.sprint_clicked)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Two parts: the cards to click, and the standings to read. Side
        # by side when the surface is wide enough for both (a 1920
        # display), the cards above the standings when it is not (a 1366
        # laptop), where they share the height.
        self.left = QVBoxLayout()
        self.left.setContentsMargins(0, 0, 0, 0)
        self.left.setSpacing(8)
        self.left.addWidget(self.cards, 1)
        self.left.addLayout(buttons)
        self.left_box = QWidget()
        self.left_box.setLayout(self.left)
        self.right = QVBoxLayout()
        self.right.setContentsMargins(0, 0, 0, 0)
        self.right.setSpacing(8)
        self.right.addWidget(self.table, 1)
        self.right.addWidget(self.final_box)
        self.right_box = QWidget()
        self.right_box.setLayout(self.right)
        self.body = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.body.setSpacing(8)
        self.body.addWidget(self.left_box, 0)
        self.body.addWidget(self.right_box, 1)
        self.wide = False
        self._arrange(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)
        lay.addLayout(head)
        lay.addWidget(self.description)
        lay.addLayout(task_row)
        lay.addWidget(self.problem)
        lay.addLayout(self.body, 1)
        self.show_screen(None)

    def _arrange(self, wide: bool) -> None:
        """Side by side or stacked; the finishing buttons follow the table."""
        self.wide = wide
        self.cards.fill = wide
        for b in (self.final_button, self.reopen_button):
            self.buttons.removeWidget(b)
            self.final_row.removeWidget(b)
            (self.final_row if wide else self.buttons).addWidget(b)
        self.final_box.setVisible(wide)
        # Side by side, Record Sprint is the column's full width and
        # taller: the one button every sprint ends on, a thumb's target.
        for b in (self.record_button, self.rest_button):
            b.setSizePolicy(
                QSizePolicy.Policy.Expanding if wide else QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Fixed,
            )
            b.setMinimumHeight(WIDE_PRIMARY_H if wide else PRIMARY_H)
            # The stretch, not the size policy alone: the leading spacer
            # expands too and would take half the row.
            self.buttons.setStretchFactor(b, 1 if wide else 0)
        self.buttons.setStretch(0, 0 if wide else 1)
        if wide:
            self.body.setDirection(QBoxLayout.Direction.LeftToRight)
            self.left.setStretch(0, 1)
        else:
            self.body.setDirection(QBoxLayout.Direction.TopToBottom)
            self.left_box.setMinimumWidth(0)
            self.left_box.setMaximumWidth(16777215)
            self.left.setStretch(0, 0)
        self.cards.set_limit(None)
        self.cards._size_cards()
        self.cards._fit_height()

    def _buttons(self) -> tuple[QPushButton, ...]:
        """The surface's buttons in row order; one or two show at a time."""
        return (
            self.cancel_button,
            self.record_button,
            self.rest_button,
            self.final_button,
            self.reopen_button,
        )

    def show_screen(self, screen: Screen | None) -> None:
        self.screen = screen
        if screen is None:
            for w in (self.cards, *self._buttons()):
                w.setVisible(False)
            self.table.setVisible(False)
            self.title.setText("")
            self.detail.setText("")
            self.description.setText("")
            self.description.setVisible(False)
            self.field.setText("")
            self.state.setText("")
            restyle(self.state, "")
            self.task.setText("")
            self.task_dots.setVisible(False)
            self.update()
            return
        self.title.setText(screen.title)
        # The format only when the title is not already the format (an
        # unnamed race), as on the board.
        detail = screen.detail if screen.detail != screen.title else ""
        self.detail.setText("  |  ".join(part for part in (screen.group, detail) if part))
        self.description.setText(screen.description)
        self.description.setVisible(bool(screen.description))
        self.field.setText(screen.field)
        self.state.setText(screen.state_label)
        restyle(self.state, state_pill(screen.state_label))
        self.update()
        self.task.setText(task_text(screen))
        self.task_dots.setVisible(bool(screen.race_menu))
        # A race that cannot be scored says why in the task line, in the
        # refusal's red: it is the one thing to fix before anything else.
        blocked = screen.task.kind == "blocked"
        restyle(self.task, f"color: {style.DANGER};" if blocked else "")
        self.cards.setVisible(bool(screen.cards))
        self.cards.set_cards(list(screen.cards))
        self.cancel_button.setVisible(screen.task.editing)
        self.record_button.setVisible(screen.record)
        self.record_button.setEnabled(screen.record_enabled)
        if screen.record_enabled:
            record_tip = ""
        elif screen.task.kind == "blocked":
            record_tip = screen.task.text
        else:
            record_tip = f"Click the {screen.noun}s in order first"
        self.record_button.setToolTip(record_tip)
        self.rest_button.setVisible(screen.rest_together)
        self.final_button.setVisible(screen.mark_final)
        self.reopen_button.setVisible(screen.reopen)
        # Side by side, a result with no cards left gives the standings
        # the whole width.
        self.left_box.setVisible(not self.wide or bool(screen.cards))
        self.table.setVisible(True)
        self.table.show_screen(screen)
        if self.wide:
            # The columns may have changed with the race.
            self._split_columns()
        self._fit_cards()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wide = self.width() >= WIDE_W
        if wide != self.wide:
            self._arrange(wide)
            if self.screen is not None:
                self.left_box.setVisible(not wide or bool(self.screen.cards))
        if wide:
            self._split_columns()
        self._fit_cards()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.wide:
            self._split_columns()

    def _split_columns(self) -> None:
        """Side by side: the standings get what their columns need, the cards the rest.

        The cards' share is the default; a long race's sprint columns
        take more, since the scorer checks every sprint by eye and a
        table that scrolls sideways hides some, and a name the table
        would cut takes back the room the cards' names do not use. The
        cards keep one column at the least.
        """
        margins = self.layout().contentsMargins()
        inner = self.width() - margins.left() - margins.right() - self.body.spacing()
        cards_w = round(inner * CARDS_SHARE)
        if self.table.isVisibleTo(self):
            cards_w = min(cards_w, inner - self.table.needed_width())
            # A table that would cut a name takes the cards' room past
            # what their names want, as much as its names need: a card's
            # larger type is worth less than a name the scorer can read.
            whole = self.table.whole_width()
            if inner - cards_w < whole:
                least = self.cards.least_width(cards_w, self.cards.viewport().height())
                cards_w = min(cards_w, max(least, inner - whole))
        self.left_box.setFixedWidth(max(CARD_MIN_W + 2, cards_w))

    def _fit_cards(self) -> None:
        """Stacked: hold back room for RESULT_ROWS of standings once the race has any."""
        screen = self.screen
        if self.wide or screen is None or not screen.rows or screen.state_label == "Start list":
            # Side by side the cards have the column; a start list has
            # nothing to read yet, so the cards keep the room.
            self.cards.set_limit(None)
            return
        lay = self.layout()
        margins = lay.contentsMargins()
        room = self.height() - margins.top() - margins.bottom()
        width = self.width() - margins.left() - margins.right()
        shown = 0
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item.isEmpty() or item.layout() is self.body:
                continue
            shown += 1
            if item.hasHeightForWidth():
                room -= item.heightForWidth(width)
            else:
                room -= item.sizeHint().height()
        # The gaps above the body, then inside it: the cards' row of
        # buttons and the two gaps around it.
        room -= lay.spacing() * shown
        room -= self.buttons.sizeHint().height() + 2 * self.left.spacing()
        # A field that would scroll takes rows from the standings instead,
        # down to RIDER_RESULT_ROWS: an entrant with no card to click
        # cannot be scored, and the standings scroll.
        for rows in range(RESULT_ROWS, RIDER_RESULT_ROWS - 1, -1):
            limit = room - self._table_need(rows)
            if self.cards.needed_height() <= limit:
                break
        self.cards.set_limit(limit)

    def _table_need(self, rows: int) -> int:
        """The table's height with ``rows`` of standings showing."""
        t = self.table
        header = t.horizontalHeader()
        need = max(header.height(), header.sizeHint().height()) + 2 * t.frameWidth()
        # The table sets its own row heights (a team row is taller).
        shown_rows = min(rows, t.rowCount())
        need += sum(t.rowHeight(r) for r in range(shown_rows))
        need += (rows - shown_rows) * t.verticalHeader().defaultSectionSize()
        if header.length() > t.viewport().width():
            need += t.horizontalScrollBar().sizeHint().height()
        return need

    def stripe_color(self) -> str | None:
        """The top stripe's color, the state's; none with no race up."""
        return None if self.screen is None else state_color(self.screen.state_label)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        color = self.stripe_color()
        if color is not None:
            paint_stripe(self, color)

    def show_problem(self, text: str | None) -> None:
        # A blocked race's task line is already the refusal, in red; the
        # same sentence again under it would read as a drawing fault, so the
        # click flashes the line it already says instead.
        if text and text == self.task.text():
            self._flash_task()
            text = None
        self.problem.setText(text or "")
        self.problem.setVisible(bool(text))
        self._fit_cards()

    def _flash_task(self) -> None:
        self.task.setStyleSheet(
            f"color: {style.DANGER}; background: {style.DANGER_TINT.name()}; border-radius: 4px;"
        )
        self._flash.start()

    def _end_flash(self) -> None:
        blocked = self.screen is not None and self.screen.task.kind == "blocked"
        restyle(self.task, f"color: {style.DANGER};" if blocked else "")

    def flashing(self) -> bool:
        """Whether the task line is flashing a refusal it already says (for the tests)."""
        return self._flash.isActive()

    def open_race_actions(self, where: QPoint | None = None) -> bool:
        """The race's ⋯ menu, under the strip or at ``where`` (a right-click).

        False when the race's format has no menu of its own, so a
        right-click on a plain task line is left alone.
        """
        if self.screen is None or not self.screen.race_menu:
            return False
        menu = QMenu(self)
        menu.setObjectName("touchMenu")
        widgets.fill_menu(
            menu,
            [(key, label) for key, label, _why in self.screen.race_menu],
            self.race_action.emit,
            closed={key: why for key, _label, why in self.screen.race_menu if why},
        )
        if where is None:
            where = self.task_dots.mapToGlobal(QPoint(0, self.task_dots.height()))
        widgets.run_menu(menu, where)
        return True

    def visible_buttons(self) -> list[str]:
        """The buttons on the surface now, by label, for the tests."""
        return [b.text() for b in self._buttons() if b.isVisibleTo(self)]
