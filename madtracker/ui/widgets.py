"""Small pieces the screens share: the look of a dialog, a message line, a table cell, a menu.

Gray marks where the scorer types, as in the spreadsheet the scorer
already uses ("only type in gray areas"); white is computed and
read-only. A row and a card open their actions the same way, from a ⋯
button.
"""

import re
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager

from PySide6.QtCore import QDate, QEvent, QLocale, QObject, QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCalendarWidget,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStylePainter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from madtracker.control.riders import ID_TIPS
from madtracker.store import NotFoundError, Store, StoreError
from madtracker.ui import style
from madtracker.ui.look import DIALOG_BASE_PT, dialog_font_rule

ID_ROLE = Qt.ItemDataRole.UserRole
# The result list's ⋯ glyph: the card strip's size, not a toolbar icon's.
# At 18 px it would be a small mark on a 36 px row and read as decoration.
DOTS_PX = 28


def apply_style(widget: QWidget, base_pt: float = DIALOG_BASE_PT) -> None:
    """The one look at one text size: the window's face, sized from this font."""
    widget.setStyleSheet(dialog_font_rule(base_pt) + style.stylesheet(base_pt))
    widget.setFont(style.ui_font(base_pt))


def close_on_shortcut(dialog: QWidget) -> QAction:
    """The platform's Close key (Command-W, Ctrl+W) closes the dialog, as it closes any window.

    Escape closes a dialog already; the Close key is what the hand
    reaches for on a window that stays open beside the race, such as
    the help, and it is the same key on every dialog so it never
    surprises.
    """
    action = QAction(dialog)
    action.setShortcut(QKeySequence.StandardKey.Close)
    action.triggered.connect(dialog.close)
    dialog.addAction(action)
    return action


def button_row(
    primary: str,
    on_primary: Callable[[], object],
    on_cancel: Callable[[], object] | None = None,
    *,
    cancel: str = "Cancel",
) -> tuple[QHBoxLayout, dict[str, QPushButton]]:
    """A dialog's buttons in one order on every platform.

    The primary action is rightmost and filled, and Cancel sits to its
    left. Qt's per platform button order is not used, so a scorer who moves between a
    Windows laptop and a Mac finds the buttons where they were.
    """
    row = QHBoxLayout()
    row.setSpacing(style.SM)
    buttons: dict[str, QPushButton] = {}
    width = style.control_height(DIALOG_BASE_PT) * 3
    row.addStretch(1)
    if on_cancel is not None:
        b = QPushButton(cancel)
        b.setMinimumWidth(width)
        b.clicked.connect(on_cancel)
        row.addWidget(b)
        buttons["cancel"] = b
    b = QPushButton(primary)
    b.setObjectName("primary")
    b.setMinimumWidth(width)
    b.setDefault(True)
    b.clicked.connect(on_primary)
    row.addWidget(b)
    buttons["primary"] = b
    return row, buttons


def error_label() -> QLabel:
    label = QLabel("")
    label.setObjectName("formError")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def show_message(label: QLabel, text: str) -> None:
    label.setText(text)


# Said, never refused: the name is the rider's or the team's own, and the
# sheets print a "?" for each run of letters they lack.
UNPRINTABLE_NOTE = 'Some letters in this name print as "?" on the PDF sheets.'


def note_unprintable(
    field: QLineEdit, label: QLabel, show: Callable[[str], None] | None = None
) -> None:
    """While ``field`` holds letters the PDF sheets cannot print, say so on ``label``.

    ``show`` puts a line on ``label`` where the owner does more than set
    the text (a form row shown only while it has something to say). The
    fields that share a line are asked together, so a first name's note
    stays up while the last name is typed, and the note is taken down
    only while it is the line's text, so a refusal standing there is left
    alone.
    """
    from madtracker.export.glyphs import prints

    show = show or (lambda text: show_message(label, text))
    # The fields that share this red line, kept with the line itself.
    fields = label.__dict__.setdefault("noted_fields", [])
    fields.append(field)

    def check() -> None:
        if not all(prints(f.text()) for f in fields):
            show(UNPRINTABLE_NOTE)
        elif label.text() == UNPRINTABLE_NOTE:
            show("")

    field.textChanged.connect(check)
    check()


def rider_name(store: Store, rider_id: int) -> str:
    try:
        r = store.rider(rider_id)
    except NotFoundError:
        return f"rider {rider_id}"
    return r.name


def friendly_error(store: Store, exc: Exception) -> str:
    """The store's message with row ids replaced by the names the scorer knows.

    The store speaks in ids because it has no business formatting names;
    the scorer under time pressure needs "Ann Alpha", not "rider 12".
    """
    text = str(exc)

    def rider(m: re.Match) -> str:
        return rider_name(store, int(m.group(1)))

    def team(m: re.Match) -> str:
        try:
            return f"team {store.team(int(m.group(1))).name}"
        except StoreError:
            return m.group(0)

    def race(m: re.Match) -> str:
        try:
            return f"race {store.race(int(m.group(1))).name}"
        except StoreError:
            return m.group(0)

    text = re.sub(r"\brider (\d+)", rider, text)
    text = re.sub(r"\bteam (\d+)", team, text)
    text = re.sub(r"\brace (\d+)", race, text)
    text = re.sub(r"\bin event \d+", "in this event", text)
    text = re.sub(r"\bmeet \d+", "this event", text)
    if text:
        text = text[0].upper() + text[1:]
    return text if text.endswith(".") else text + "."


_read_only_flags: Qt.ItemFlag | None = None


def input_item(text: str = "", editable: bool = True) -> QTableWidgetItem:
    """A table cell: gray and editable where the scorer types, white otherwise."""
    global _read_only_flags
    item = QTableWidgetItem(text)
    if editable:
        item.setBackground(style.INPUT_GRAY)
    else:
        if _read_only_flags is None:
            # Worked out once: Python's flag arithmetic would be a third of the
            # cost of a 3000-rider table's 15,000 cells.
            _read_only_flags = item.flags() & ~Qt.ItemFlag.ItemIsEditable
        item.setFlags(_read_only_flags)
        item.setBackground(style.COMPUTED_WHITE)
    return item


@contextmanager
def busy() -> Iterator[None]:
    """The wait cursor over work the scorer waits on: a whole-event PDF takes
    seconds on a venue laptop and looks like a hang, inviting a second click."""
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


@contextmanager
def filling(table: QTableWidget) -> Iterator[None]:
    """Refill a shown table cell by cell, then measure its columns once.

    A column sized to its contents re-measures every row each time a cell
    is set, so refilling a 22-rider roster after one bib costs about 80,000
    style calls and most of a second on Windows. The measuring and the
    painting wait for the last cell; the table's own sizes and style are
    left alone (only the header's modes change, never from an event).
    """
    header = table.horizontalHeader()
    measured = [
        col
        for col in range(table.columnCount())
        if header.sectionResizeMode(col) == QHeaderView.ResizeMode.ResizeToContents
    ]
    for col in measured:
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
    # A fill inside another (a bulk tick whose check pass fills too) finds
    # the columns already fixed and updates already off, and leaves both
    # to the outer one, so the table is measured and painted once.
    painting = table.updatesEnabled()
    table.setUpdatesEnabled(False)
    try:
        yield
    finally:
        for col in measured:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        if painting:
            table.setUpdatesEnabled(True)


def setup_table(table: QTableWidget, headers: Sequence[str], *, selectable: bool = True) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    # The two ids read alike to someone new to them; the tip says which is which.
    for col, header in enumerate(headers):
        if header in ID_TIPS:
            table.horizontalHeaderItem(col).setToolTip(ID_TIPS[header])
    table.verticalHeader().setVisible(False)
    # A header sits where its cells do: left, as a cell's text is, unless
    # the table aligns a column otherwise and its header with it.
    table.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    if selectable:
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    else:
        # A row is selectable only when selecting it does something.
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setAlternatingRowColors(True)


class Form(QFormLayout):
    """A form whose labels sit on their fields' middle line.

    QFormLayout puts a label at the top of its row at the label's own
    height, and ignores a vertical label alignment, so beside a field or
    a button taller than a line of text every label would ride 2 to 4 px high.
    Each label is moved down onto its field's middle once the layout has
    placed both. A tall field (a table, a box of text) has its label
    beside its first line instead, where a field's label is looked for.
    """

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        for row in range(self.rowCount()):
            label = self.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field = self.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if label is None or field is None or label.widget() is None:
                continue
            widget = label.widget()
            place, beside = widget.geometry(), field.geometry()
            if place.top() > beside.bottom() or place.bottom() < beside.top():
                continue  # a wrapped row: the label is above its field
            line = widget.fontMetrics().height()
            band = beside.height()
            if band > 3 * line:
                band = round(line * 2.2)  # style.control_height of this font
            top = beside.top() + max(0, (band - place.height()) // 2)
            widget.setGeometry(place.x(), top, place.width(), place.height())


class NameDialog(QDialog):
    """One name, taken or refused in place.

    ``take`` gets the typed name and answers None when it is taken, which
    closes the dialog, or the refusal, which goes on the dialog's own red
    line with the name still in the field: a slip costs one correction,
    not the whole name typed again after the parent's status line said
    why. An empty refusal keeps the dialog open and says nothing, for a
    question ``take`` asked that was declined.

    The field is a line edit, or a ``field`` the caller hands in (a
    GroupCombo that also lists the names to merge into).
    """

    def __init__(
        self,
        title: str,
        verb: str,
        take: Callable[[str], str | None],
        *,
        text: str = "",
        placeholder: str = "",
        field: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        apply_style(self)
        self.take = take
        if field is None:
            field = QLineEdit(text)
            field.setPlaceholderText(placeholder)
        self.field = field
        self.field.setMinimumWidth(style.control_height(DIALOG_BASE_PT) * 7)
        self.error = error_label()
        typed = field if isinstance(field, QLineEdit) else field.lineEdit()
        note_unprintable(typed, self.error)
        form = Form()
        form.addRow("Name", self.field)
        buttons, self.buttons = button_row(verb, self.submit, self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.error)
        lay.addLayout(buttons)
        self.field.setFocus()
        edit = self.field.lineEdit() if isinstance(self.field, QComboBox) else self.field
        if isinstance(edit, QLineEdit):
            edit.selectAll()

    def text(self) -> str:
        if isinstance(self.field, QComboBox):
            return self.field.currentText()
        return self.field.text()

    def submit(self) -> bool:
        """The primary button: the name taken (closes) or refused on the red line (stays)."""
        refusal = self.take(self.text())
        if refusal is None:
            self.accept()
            return True
        show_message(self.error, refusal)
        return False


def spin_box(lo: int, hi: int) -> QSpinBox:
    """A spin box whose number sits where a line edit's text does.

    The style sheet's padding moves a date edit's text but not a spin
    box's: Qt puts the spin box's own edit against its border, which
    would leave the number 9 px left of every other field's text. The inset is
    given to that edit instead; the height is the style sheet's.
    """
    box = QSpinBox()
    box.setRange(lo, hi)
    box.lineEdit().setTextMargins(style.SM + 1, 0, 0, 0)
    return box


def align_header(table: QTableWidget, col: int, align: Qt.AlignmentFlag) -> None:
    """Align column ``col``'s header as its cells are (setup_table makes them left)."""
    item = table.horizontalHeaderItem(col)
    if item is not None:
        item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)


def id_label(name: str) -> QLabel:
    """A form label for USAC License or UCI ID, with the tip that says which is which."""
    label = QLabel(name)
    label.setToolTip(ID_TIPS.get(name, ""))
    return label


def number_key(text: str) -> tuple | None:
    """Sort a cell as a number when it is one, after the numbers as text; blank is None."""
    text = text.strip()
    if not text:
        return None
    # ASCII digits only: "²" passes isdigit and fails int().
    if text.isascii() and text.isdigit():
        return (0, int(text), "")
    return (1, 0, text.casefold())


def text_key(text: str) -> str | None:
    """Sort a cell as text, ignoring case; blank is None."""
    return text.strip().casefold() or None


class ColumnSort:
    """Click a column header to sort by it, and again to reverse.

    The table is filled in the order this gives rather than sorted by
    Qt (setSortingEnabled): Qt compares cell text, so bib 12 would sort
    before bib 3, and it would move rows under the screens that find a
    rider by row. A key returns None for a blank, and blanks go last in
    both directions, since an empty cell is never what a scorer is
    looking for. Equal keys keep the order they came in, so the store's
    order is the tie-break. Columns without a key do not sort; with no
    column (None) the given order stands and no indicator shows.
    """

    def __init__(
        self,
        table: QTableWidget,
        keys: dict[int, Callable[[object], object]],
        changed: Callable[[], None],
        column: int | None = None,
        order: Qt.SortOrder = Qt.SortOrder.AscendingOrder,
    ) -> None:
        self.table = table
        self.keys = keys
        self.changed = changed
        self.column = column
        self.order = order
        header = table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(column is not None)
        header.setSortIndicator(-1 if column is None else column, order)
        header.sectionClicked.connect(self.clicked)

    def clicked(self, column: int) -> None:
        # Qt has already moved the indicator by the time this runs; the
        # state here is the one that counts, so it is set back from it.
        if column in self.keys:
            if column == self.column and self.order == Qt.SortOrder.AscendingOrder:
                self.order = Qt.SortOrder.DescendingOrder
            else:
                self.order = Qt.SortOrder.AscendingOrder
            self.column = column
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(self.column is not None)
        header.setSortIndicator(-1 if self.column is None else self.column, self.order)
        if column in self.keys:
            self.changed()

    def sorted(self, rows: Sequence) -> list:
        if self.column is None:
            return list(rows)
        key = self.keys[self.column]
        keyed = [(key(r), r) for r in rows]
        filled = [(k, r) for k, r in keyed if k is not None]
        filled.sort(key=lambda kr: kr[0], reverse=self.order == Qt.SortOrder.DescendingOrder)
        return [r for _, r in filled] + [r for k, r in keyed if k is None]


class RowToggleDelegate(QStyledItemDelegate):
    """A checkable item whose box Qt never toggles on its own.

    The view toggles the whole row instead (CheckList, the import
    preview's Import column): a click on the box and a click on the text
    must be one toggle, not two.
    """

    def editorEvent(self, event, model, option, index) -> bool:
        return False


PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 1


class PlaceholderDelegate(QStyledItemDelegate):
    """Paints an empty cell's default in dim text, the way a blank line edit shows its placeholder.

    The default sits in the item's PLACEHOLDER_ROLE data. The editor the
    cell opens gets the same text as its placeholder, so the hint does
    not vanish the moment the scorer clicks in.
    """

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)
        hint = index.data(PLACEHOLDER_ROLE)
        if not hint or (index.data() or "").strip():
            return
        painter.save()
        painter.setPen(QColor(style.DIM))
        rect = option.rect.adjusted(style.XS, 0, -style.XS, 0)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, hint)
        painter.restore()

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        hint = index.data(PLACEHOLDER_ROLE)
        if hint and hasattr(editor, "setPlaceholderText"):
            editor.setPlaceholderText(hint)
        return editor


class CheckList(QListWidget):
    """A list of things to tick, where a click anywhere on a row ticks it.

    The box alone is a small target, and a scorer who clicks the name
    expects the name to be the thing picked. The row is the control:
    one click on it ticks, another unticks, and ``itemChanged`` reports
    each change as it would for the box. No selection, since a selected
    row here would mean nothing.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("checkList")
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setItemDelegate(RowToggleDelegate(self))
        self.itemClicked.connect(self._toggle)

    def add(self, item_id: int, text: str, checked: bool = False) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setData(ID_ROLE, item_id)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        item.setSizeHint(QSize(0, style.control_height(DIALOG_BASE_PT, 1.7)))
        self.addItem(item)
        return item

    def _toggle(self, item: QListWidgetItem) -> None:
        if not self.isEnabled() or not item.flags() & Qt.ItemFlag.ItemIsEnabled:
            return
        on = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if on else Qt.CheckState.Checked)

    def set_checked(self, item_id: int, on: bool) -> None:
        for i in range(self.count()):
            item = self.item(i)
            if item.data(ID_ROLE) == item_id:
                item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)


def fit_popup(combo: QComboBox) -> None:
    """Open ``combo``'s list as wide as its longest item, and every item at once.

    The style sheet opens a combo's list below the box (style.py), and
    that kind of list is only as wide as the box: a box kept narrow on
    purpose (the import preview's Status) would cut its longer choices short.
    Called once the items are in; the list's frame, inset and a scroll
    bar's room are added to the rows' own width.
    """
    view = combo.view()
    # Measured with the sheet's row padding, which a view gets on its polish.
    view.ensurePolished()
    combo.setMaxVisibleItems(max(combo.maxVisibleItems(), combo.count()))
    frame = 2 * (style.XS + 1)
    view.setMinimumWidth(view.sizeHintForColumn(0) + frame + style.SCROLL_PX)


class FilterBox(QLineEdit):
    """A filter box: Esc clears what is typed before it closes the window.

    A scorer who typed a name and presses Esc to start over keeps the
    dialog; with the box empty, Esc goes on to the window.
    Enter is the box's own (``returnPressed``) and never reaches the
    dialog: in the race dialog it would press Save on a half-built race.
    """

    def __init__(self, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.text():
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()


class GroupCombo(QComboBox):
    """A box that offers a list and still takes a typed name.

    Qt's editable combo opens its list only from the arrow; a click on
    the text puts a cursor there and nothing else, which reads as a box
    that does nothing. Here a click anywhere opens the list; a letter
    typed while it is open closes it and goes into the box; Escape closes
    it and leaves the cursor for typing. Enter in the box never reaches
    Qt's own handling, which would add the typed text to the list and
    emit ``activated`` as if it had been picked, so ``activated`` here
    means one thing, a pick from the list. Instead Enter leaves the box
    (its text is read on save) and presses the dialog's default button,
    as Enter in a line edit does, so a race is saved from any of its
    fields once the list is closed.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.lineEdit().installEventFilter(self)
        self.view().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.lineEdit():
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and not self.view().isVisible()
                and self.count()
            ):
                self.showPopup()
                return True
            if event.type() == QEvent.Type.KeyPress and event.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
            ):
                self.clearFocus()
                window = self.window()
                if isinstance(window, QDialog):
                    QApplication.sendEvent(window, event)
                return True
        elif obj is self.view() and event.type() == QEvent.Type.KeyPress:
            text = event.text()
            if text and text.isprintable() and not text.isspace():
                self.hidePopup()
                edit = self.lineEdit()
                edit.setFocus()
                edit.setText(text)
                return True
        return super().eventFilter(obj, event)


def selected_id(table: QTableWidget) -> int | None:
    row = table.currentRow()
    if row < 0 or not table.selectionModel().hasSelection():
        return None
    item = table.item(row, 0)
    return None if item is None else item.data(ID_ROLE)


def swatch_icon(color: str | None, size: int = 16) -> QIcon:
    """A team's color chip, rendered at 1x and 2x as ``icons.mdi`` is.

    It is drawn at the 16 px every list, table and combo draws an icon
    at, so it is never rescaled and its outline stays on whole pixels.

    A 1x chip alone is scaled up on a Retina or 150% panel and its
    rounded corners turn to steps beside the card's sharp chip. The
    disabled mode keeps the color: a scored race's locked Teams list
    shows a team's name alone, and a gray chip would leave nothing
    saying which jersey it is.
    """
    icon = QIcon()
    for dpr in (1.0, 2.0):
        pix = QPixmap(round(size * dpr), round(size * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(color or "#9aa0a6"))
        p.setPen(QColor(0, 0, 0, 90))
        # On the half pixel, so the 1 px outline covers whole pixels.
        p.drawRoundedRect(QRectF(1.5, 1.5, size - 3, size - 3), 4, 4)
        p.end()
        icon.addPixmap(pix)
        icon.addPixmap(pix, QIcon.Mode.Disabled)
    return icon


class OneClickButton(QPushButton):
    """A button for which a double-click is one click.

    Qt turns the second press of a double-click into a double-click
    event, and QPushButton treats that as a press, so the release that
    follows clicks again: one more Undo, or one more rider placed by
    whichever card the first click moved under the pointer. Dropping the
    event leaves the release with no press, so it clicks nothing. Two
    presses far apart are never a double-click, so a fast scorer working
    down the cards loses nothing.
    """

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()


class ElidedLabel(QLabel):
    """A one-line label cut on the right, with an ellipsis, when its room is short.

    A race named with 160 characters would otherwise widen the operator
    window past the screen. ``text()`` stays whole
    and the tooltip carries it when it is cut.
    """

    MIN_CHARS = 8

    def setText(self, text: str) -> None:
        super().setText(text)
        self._tip()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._tip()

    def _tip(self) -> None:
        cut = self.fontMetrics().horizontalAdvance(self.text()) > self.contentsRect().width()
        self.setToolTip(self.text() if cut else "")

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        least = self.fontMetrics().averageCharWidth() * self.MIN_CHARS
        return QSize(min(hint.width(), least), hint.height())

    def paintEvent(self, event) -> None:
        room = self.contentsRect()
        shown = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, room.width()
        )
        painter = QPainter(self)
        self.style().drawItemText(
            painter,
            room,
            int(self.alignment()),
            self.palette(),
            self.isEnabled(),
            shown,
            self.foregroundRole(),
        )
        painter.end()


class OneClickToolButton(QToolButton):
    """A tool button for which a double-click is one click, as for OneClickButton.

    A card's +1 or -1 double-clicked would record two laps, each worth points.
    """

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()


def dots_button(parent: QWidget | None = None) -> QToolButton:
    """The ⋯ that opens a row's actions, the card strip's glyph and tint.

    It fills the cell it is put in, and the style sheet's margin shapes
    its hover box, so the glyph sits on the row's middle at any row
    height.
    """
    from madtracker.ui.icons import mdi

    b = QToolButton(parent)
    b.setObjectName("dots")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setIcon(mdi("dots-horizontal", DOTS_PX, style.DIM))
    b.setIconSize(QSize(DOTS_PX, DOTS_PX))
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    return b


def fill_menu(
    menu: QMenu,
    items: Sequence[tuple[str, str]],
    slot: Callable[[str], None],
    fold: tuple[str, str, str] | None = None,
    closed: Mapping[str, str] | None = None,
) -> None:
    """Add ``items`` to ``menu``; a pick calls ``slot(key)``.

    ``fold`` is (key prefix, submenu title, label prefix to drop): the
    items whose key starts with the prefix go into one submenu, placed
    where the first of them was, so a long list of places is one item.
    ``closed`` maps a key to why it cannot be picked now: the item is
    grayed with the reason as its tooltip, so a menu keeps one shape
    and the scorer sees what will open up.
    """
    # No icons on menu items: Qt draws them in the check-mark slot.
    sub = None
    if closed:
        menu.setToolTipsVisible(True)
        menu.installEventFilter(_ClosedTips(menu))
    for key, label in items:
        if fold is not None and key.startswith(fold[0]):
            if sub is None:
                sub = menu.addMenu(fold[1])
                # A submenu is tapped as its parent is.
                sub.setObjectName(menu.objectName())
            label = label.removeprefix(fold[2])
            action = sub.addAction(label)
        else:
            action = menu.addAction(label)
        if closed and key in closed:
            action.setEnabled(False)
            action.setToolTip(closed[key])
        action.triggered.connect(lambda _checked=False, k=key: slot(k))


class _EnterActivates(QObject):
    """Return or Enter on a view's current row runs ``slot``, on every platform.

    Qt emits ``activated`` for Enter on Windows and Linux, but on macOS
    it tries to edit the item instead, and the key then reaches the
    dialog's default button (New Rider... over a rider's row). The key
    is taken here before the view sees it, so one path serves all three.
    """

    def __init__(self, view, slot: Callable[[], None]) -> None:
        super().__init__(view)
        self._view = view
        self._slot = slot

    def eventFilter(self, obj, event) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not (event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier)
            and self._view.currentIndex().isValid()
        ):
            self._slot()
            return True
        return False


def enter_activates(view, slot: Callable[[], None]) -> None:
    """A double-click or Enter on the view's current row runs ``slot``."""
    view.activated.connect(lambda _index: slot())
    view.installEventFilter(_EnterActivates(view, slot))


class _ClosedTips(QObject):
    """Shows a menu's tooltips on its grayed items only.

    With tooltips on, Qt shows every item's, and an item's default
    tooltip is its own text, which under the pointer would say nothing
    the item doesn't; the reason a grayed item carries is the one worth
    showing.
    """

    def eventFilter(self, menu, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            action = menu.actionAt(event.pos())
            if action is not None and action.isEnabled():
                QToolTip.hideText()
                return True
        return False


class _OutsideRightPress(QObject):
    """Remembers a right-press that closed the menu from outside it.

    Qt closes a popup on a press outside it and keeps that press, so a
    scorer who right-clicks one rider and then another would see the
    first menu close and nothing open. run_menu reads the
    point and sends the right-click on to whatever is under it.
    """

    def __init__(self, menu: QMenu) -> None:
        super().__init__(menu)
        self.menu = menu
        self.at: QPoint | None = None

    def eventFilter(self, obj, event) -> bool:
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.RightButton
            and not self.menu.rect().contains(event.position().toPoint())
        ):
            self.at = event.globalPosition().toPoint()
        return False


def run_menu(menu: QMenu, where) -> None:
    """Open a menu at a point. One place to open every menu, so a test can watch them."""
    exec_menu(menu, where)


def exec_menu(menu: QMenu, where) -> None:
    """The menu's own run: open at a point, and when a right-click outside it
    closed it, open the menu of the card or row under the pointer, posted
    rather than sent so the first menu's caller has returned first."""
    watch = _OutsideRightPress(menu)
    menu.installEventFilter(watch)
    menu.exec(where)
    # A pick can rebuild the grid during the menu's loop and take the
    # card, the menu's parent, with it; the point is read before the
    # menu goes, and a closed menu goes so menus do not pile up under a
    # parent that lives all night.
    at = watch.at if isValid(watch) else None
    if isValid(menu):
        menu.deleteLater()
    if at is not None:
        retarget_right_click(at)


def run_dialog(dialog: QDialog) -> int:
    """Run a modal dialog and let it go: the result code, and the dialog
    deleted once the caller is back at the event loop.

    The deletion is posted, and Qt delivers it only after the calling slot
    returns to the loop, not inside a nested ``exec`` or ``processEvents``
    in that slot. So the caller reads the dialog's fields in the same
    method after this returns, and never keeps the dialog on ``self`` for
    a later slot. Whoever runs the dialog ends its life, including one a
    caller passed in.
    """
    try:
        return dialog.exec()
    finally:
        if isValid(dialog):
            dialog.deleteLater()


def widget_at(at: QPoint) -> QWidget | None:
    """The widget under a point on screen; its own name so a test can stand in
    for it (the offscreen platform cannot say what is under a point)."""
    return QApplication.widgetAt(at)


def retarget_right_click(at: QPoint) -> None:
    """Send a right-click on to the widget under ``at`` as a context menu event."""
    target = widget_at(at)
    if target is None:
        return
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, target.mapFromGlobal(at), at)
    QApplication.postEvent(target, event)


def why_label() -> QLabel:
    """A small gray reason centered under a button that is off.

    Its one line is held even when empty, so the buttons below it do not
    jump as the selection moves.
    """
    label = QLabel("")
    label.setObjectName("hint")
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 0.85)
    label.setFont(font)
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
    label.setFixedHeight(label.fontMetrics().lineSpacing())
    return label


def with_why(button: QPushButton, why: QLabel) -> QVBoxLayout:
    """A button with its reason tight underneath, as one group.

    Proximity is what ties a note to a control: the note sits a hair
    under its own button and a full gap above the next one, so it never
    reads as a label floating between two.
    """
    group = QVBoxLayout()
    group.setSpacing(style.XS // 2)
    group.addWidget(button)
    group.addWidget(why)
    return group


# What a window's frame adds above and around its client area: the title
# bar (about 30 px on Windows 11 and macOS) and a border. The work area
# is measured without it, so a dialog sized to the work area alone would put
# its bottom buttons under the taskbar.
FRAME_ALLOWANCE = 40


def screen_room(window: QWidget) -> QSize | None:
    """The client size a top-level window can have on its screen; None with no screen.

    A dialog is not on a screen until it is shown, so the screen is its
    parent's, which is where Qt will open it.
    """
    parent = window.parentWidget()
    screen = (parent.screen() if parent is not None else None) or window.screen()
    screen = screen or QGuiApplication.primaryScreen()
    if screen is None:
        return None
    avail = screen.availableGeometry()
    return QSize(avail.width() - 2 * style.MD, avail.height() - FRAME_ALLOWANCE - style.MD)


def fit_to_screen(window: QWidget, width: int, height: int) -> None:
    """Resize to ``width`` by ``height``, or less where the screen is smaller.

    A 1366 by 768 laptop at 125% offers about 1090 by 570 to a window,
    less than several dialogs want; Windows does not shrink a dialog that
    is too big, so its Save or Close would sit off the screen.
    """
    room = screen_room(window)
    if room is not None:
        width = min(width, room.width())
        height = min(height, room.height())
    window.resize(width, height)


def center_on_parent(window: QWidget) -> None:
    """Put a dialog in the middle of the window it belongs to, kept on its screen.

    Qt centers a dialog when it first shows; one that sets its own height
    as it shows would grow downward from there and sit low over the window.
    """
    parent = window.parentWidget()
    if parent is None:
        center_on_screen(window)
        return
    frame = window.frameGeometry()
    frame.moveCenter(parent.window().frameGeometry().center())
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is not None:
        room = screen.availableGeometry()
        frame.moveTop(max(room.top(), min(frame.top(), room.bottom() - frame.height())))
        frame.moveLeft(max(room.left(), min(frame.left(), room.right() - frame.width())))
    window.move(frame.topLeft())


def center_on_screen(window: QWidget) -> None:
    """Put a top-level window in the middle of its screen's work area.

    The work area leaves out the taskbar or Dock: left to itself, Qt
    centers the splash on the whole screen.
    """
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return
    frame = window.frameGeometry()
    frame.moveCenter(screen.availableGeometry().center())
    window.move(frame.topLeft())


# The calendar's cells: a date is picked with a mouse, by people who are
# not young, so the targets are the size of a control, not of a digit.
CALENDAR_CELL = 40


class MonthDateEdit(QDateEdit):
    """A date field whose month, shown as a word, also takes a typed number.

    With the month as "Oct", Qt's field takes only the word, so "9" or
    "09" typed into the month would do nothing; numbers are accepted as
    well. Digits are read as one or two: "1" waits for a second digit
    that makes 10, 11 or 12, as a numeric field does.
    """

    def __init__(self, date: QDate) -> None:
        super().__init__(date)
        self._month_digits = ""

    def keyPressEvent(self, event) -> None:
        text = event.text()
        if (
            self.currentSection() != QDateEdit.Section.MonthSection
            or len(text) != 1
            or not ("0" <= text <= "9")
        ):
            self._month_digits = ""
            super().keyPressEvent(event)
            return
        digits = (self._month_digits + text)[-2:]
        month = int(digits)
        if not 1 <= month <= 12:
            digits, month = text, int(text)
        # A lone 0 or 1 may be the start of 01 to 12: keep it and wait.
        self._month_digits = digits if len(digits) == 1 and digits in "01" else ""
        if 1 <= month <= 12:
            d = self.date()
            day = min(d.day(), QDate(d.year(), month, 1).daysInMonth())
            self.setDate(QDate(d.year(), month, day))
            self.setCurrentSection(QDateEdit.Section.MonthSection)
        event.accept()

    def focusOutEvent(self, event) -> None:
        self._month_digits = ""
        super().focusOutEvent(event)


def settings_word() -> str:
    """What the venue settings are called here: Settings, or Preferences on macOS.

    On macOS Qt moves the File menu's Settings item into the application
    menu and names it "Preferences..." itself, so the window that opens
    from it says the same. Windows says Settings, and Linux keeps the
    item under File as Settings..., so the window matches what was
    clicked.
    """
    return "Preferences" if sys.platform == "darwin" else "Settings"


def date_edit(date: QDate) -> QDateEdit:
    """A date field shown as 2026-Oct-14 (madtracker.dates), with a calendar that looks like the app.

    Qt Widgets has no native date picker on any platform; its own
    calendar is drawn the same everywhere, which is what the app wants,
    but its stock look (red weekends, tiny arrows, cramped cells) is not
    the app's. The calendar takes the app's ink, accent, type and icons.
    """
    from madtracker.ui.icons import mdi

    edit = MonthDateEdit(date)
    edit.setCalendarPopup(True)
    # The month as a word, in English whatever the machine's language, so
    # the field reads as the rest of the app's dates do.
    edit.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    edit.setDisplayFormat("yyyy-MMM-dd")
    cal = QCalendarWidget()
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    cal.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
    cal.setGridVisible(False)
    # Weekends are ordinary days here: race nights fall on any of them.
    # Every day gets the same format, because Qt draws the weekday's
    # format over the header's too, and two dark headers would stand out.
    plain = QTextCharFormat()
    plain.setForeground(QColor(style.INK))
    for day in Qt.DayOfWeek:
        cal.setWeekdayTextFormat(day, plain)
    header = QTextCharFormat()
    header.setForeground(QColor(style.DIM))
    header.setFontWeight(QFont.Weight.DemiBold)
    cal.setHeaderTextFormat(header)
    today = QTextCharFormat()
    today.setForeground(QColor(style.ACCENT))
    today.setFontWeight(QFont.Weight.Bold)
    cal.setDateTextFormat(QDate.currentDate(), today)
    for name, icon in (
        ("qt_calendar_prevmonth", "chevron-left"),
        ("qt_calendar_nextmonth", "chevron-right"),
    ):
        button = cal.findChild(QToolButton, name)
        if button is not None:
            button.setIcon(mdi(icon, 24, style.INK))
            button.setIconSize(QSize(24, 24))
    cal.setStyleSheet(
        f"""
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background: {style.ACCENT_TINT_FAINT};
    border-bottom: 1px solid {style.ACCENT_TINT_STRONG};
}}
QCalendarWidget QToolButton {{
    color: {style.INK}; font-weight: 600; background: transparent; border: none;
    padding: {style.XS}px {style.SM}px; border-radius: 6px; min-height: {CALENDAR_CELL - 8}px;
}}
QCalendarWidget QToolButton:hover {{ background: {style.ACCENT_TINT}; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; width: 0; }}
QCalendarWidget QSpinBox {{ min-width: 64px; }}
QCalendarWidget QAbstractItemView {{
    selection-background-color: {style.ACCENT}; selection-color: white;
    outline: 0; background: white;
}}
QCalendarWidget QAbstractItemView:disabled {{ color: {style.DIM}; }}
"""
    )
    cal.setMinimumSize(CALENDAR_CELL * 7, CALENDAR_CELL * 7)
    edit.setCalendarWidget(cal)
    return edit


class ElidedButton(OneClickButton):
    """A button whose label is cut on the right, with an ellipsis, to its width.

    Undo names the action it takes back, rider and all, and a long name
    is wider than the pane on a laptop; Qt would center the overflow and
    cut both ends. ``text()`` stays whole; only the painted label is cut,
    so a resize re-cuts it. The whole label shows on hover only when it
    is cut: a tooltip repeating the button says nothing.
    """

    def _shown(self, opt: QStyleOptionButton) -> str:
        room = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, opt, self)
        width = room.width()
        if not opt.icon.isNull():
            # Qt sets the icon 4 px before the label.
            width -= opt.iconSize.width() + 4
        return self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, width)

    def is_cut(self) -> bool:
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        return self._shown(opt) != self.text()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            if self.is_cut():
                QToolTip.showText(event.globalPos(), self.text(), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def paintEvent(self, event) -> None:
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = self._shown(opt)
        QStylePainter(self).drawControl(QStyle.ControlElement.CE_PushButton, opt)

    def minimumSizeHint(self) -> QSize:
        # The label is cut to fit, so its length never widens the pane.
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        return QSize(0, super().sizeHint().height())


class UndoButton(ElidedButton):
    """Undo's label in two weights: "Undo:" bold, what it takes back plain.

    "Undo #51 Hana Yoon 10th" in one bold run would read as one word, and
    the rider's name in regular weight between two bold runs as pieces
    ("Undo Silver 4th"). So the label is a sentence, "Undo: #51 Hana Yoon
    placed 10th", with the verb bold and the rest plain. When the room
    runs out the rider's name is cut
    first and the end of the sentence last; the verb always shows whole.
    """

    def __init__(self, text: str = "Undo", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._who = ""

    def set_label(self, text: str, who: str = "") -> None:
        """``who`` is the rider or team ``text`` names, as it spells it, or ""."""
        self.setText(text)
        self._who = who if who and who in text else ""
        self.update()

    def who(self) -> str:
        return self._who

    def runs(self) -> list[tuple[str, bool]]:
        """The label as (text, bold) runs, in order: the verb, then the plain
        sentence split around the rider's name so the name can be cut first."""
        text = self.text()
        head = "Undo:"
        if not text.startswith(head):
            return [(text, True)]
        rest = text[len(head) :].strip()
        if not self._who or self._who not in rest:
            return [(head, True), (rest, False)]
        at = rest.index(self._who)
        before = rest[:at].strip()
        after = rest[at + len(self._who) :].strip()
        runs = [(head, True)]
        if before:
            runs.append((before, False))
        runs.append((self._who, False))
        if after:
            runs.append((after, False))
        return runs

    def _fonts(self) -> tuple[QFont, QFont]:
        bold = QFont(self.font())
        bold.setBold(True)
        plain = QFont(self.font())
        plain.setBold(False)
        return bold, plain

    def _gap(self) -> int:
        """The advance between runs: a space in the plain weight, so the runs
        read as the one sentence they are and never as pieces set apart."""
        return QFontMetrics(self._fonts()[1]).horizontalAdvance(" ")

    def _fitted(self, room: int) -> list[tuple[str, bool, int]]:
        """The runs cut to ``room`` pixels: the rider's name first, then the last run."""
        bold, plain = self._fonts()
        metrics = {True: QFontMetrics(bold), False: QFontMetrics(plain)}
        runs = [(t, b, metrics[b].horizontalAdvance(t)) for t, b in self.runs()]
        gaps = self._gap() * (len(runs) - 1)
        over = sum(w for _, _, w in runs) + gaps - room
        if over <= 0:
            return runs
        who = self._who
        for pick in (lambda r: bool(who) and r[0] == who and not r[1], lambda r: r is runs[-1]):
            for i, run in enumerate(runs):
                if not pick(run):
                    continue
                t, b, w = run
                want = max(0, w - over)
                cut = metrics[b].elidedText(t, Qt.TextElideMode.ElideRight, want)
                cut_w = metrics[b].horizontalAdvance(cut)
                over -= w - cut_w
                runs[i] = (cut, b, cut_w)
                break
            if over <= 0:
                break
        return runs

    def _room(self, opt: QStyleOptionButton) -> int:
        box = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, opt, self)
        width = box.width()
        if not opt.icon.isNull():
            width -= opt.iconSize.width() + 4
        return width

    def is_cut(self) -> bool:
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        fitted = self._fitted(self._room(opt))
        return [t for t, _, _ in fitted] != [t for t, _ in self.runs()]

    def shown_runs(self) -> list[str]:
        """The run texts as painted now, for the tests."""
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        return [t for t, _, _ in self._fitted(self._room(opt))]

    def paintEvent(self, event) -> None:
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        # A copy: the option's own icon is emptied so the style draws no label.
        icon = QIcon(opt.icon)
        opt.icon = QIcon()
        opt.text = ""
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_PushButton, opt)
        box = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, opt, self)
        room = box.width() - (opt.iconSize.width() + 4 if not icon.isNull() else 0)
        runs = self._fitted(room)
        gap = self._gap()
        total = sum(w for _, _, w in runs) + gap * (len(runs) - 1)
        if not icon.isNull():
            total += opt.iconSize.width() + 4
        x = box.x() + max(0, (box.width() - total) // 2)
        enabled = self.isEnabled()
        if not icon.isNull():
            mode = QIcon.Mode.Normal if enabled else QIcon.Mode.Disabled
            pix = icon.pixmap(opt.iconSize, mode)
            y = box.y() + (box.height() - opt.iconSize.height()) // 2
            painter.drawPixmap(x, y, pix)
            x += opt.iconSize.width() + 4
        bold, plain = self._fonts()
        # The style sheet's own ink for a button, enabled and disabled.
        painter.setPen(QColor(style.INK if enabled else "#9aa1ad"))
        for text, is_bold, width in runs:
            painter.setFont(bold if is_bold else plain)
            painter.drawText(
                QRect(x, box.y(), width, box.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                text,
            )
            x += width + gap
