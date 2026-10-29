"""Helpers and constants that several Edit Event dialogs share."""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QWidget,
)

from madtracker.control.riders import ID_TIPS, MergeValue
from madtracker.inputs import clean_line, is_blank
from madtracker.store import Rider
from madtracker.ui import style
from madtracker.ui.widgets import error_label, input_item, setup_table, show_message


def name_key(rider: Rider) -> tuple[str, str]:
    """A name sorts by last name, then first, as the venue's lists do."""
    return (rider.last_name.casefold(), rider.first_name.casefold())


def first_key(rider: Rider) -> tuple[str, str]:
    """Sorted by first name, the last name breaks a tie."""
    return (rider.first_name.casefold(), rider.last_name.casefold())


def _refusal_line() -> QLabel:
    """A refusal line that takes no room until there is something to refuse.

    The lists keep their full height: routine activity shows nothing, so
    an empty line would be a blank strip under them most of the time.
    """
    label = error_label()
    label.setVisible(False)
    return label


def _refuse(label: QLabel, text: str) -> None:
    show_message(label, text)
    label.setVisible(bool(text))


def _typed(field: QLineEdit) -> str:
    """A typed name as the file keeps it; "" when it would show nothing (spaces, zero-width)."""
    text = field.text()
    return "" if is_blank(text) else clean_line(text)


class ValueLines(QTableWidget):
    """A rider record being settled, one line per value, as JOSM settles two ways' tags.

    What both sources agree on, or only one gives, is shown and kept; a
    value that differs is a Choose... list tinted until the scorer picks,
    and nothing is picked for them. Merge riders and an import's review
    of a rider on file are the same question, so they are one table.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        setup_table(self, ["", "Value"], selectable=False)
        # Not a list to scan but a form: a typeable cell takes the keyboard.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWordWrap(True)
        # A typeable value is one click from typing in its gray cell.
        self.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.itemChanged.connect(lambda *_: self._changed())
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        # A label and its value read without column titles.
        header.setVisible(False)
        self.lines: list[MergeValue] = []
        self.choices: dict[int, QComboBox] = {}

    def fill(
        self,
        lines: list[MergeValue],
        *,
        typeable: bool = False,
        picks: dict[int, int] | None = None,
    ) -> None:
        """Show ``lines``; ``typeable`` makes a rider value neither source has a cell to type in."""
        self.lines, self.choices = list(lines), {}
        self.blockSignals(True)
        self.clearContents()
        self.setRowCount(len(self.lines))
        for row, line in enumerate(self.lines):
            label = input_item(line.label, editable=False)
            label.setToolTip(ID_TIPS.get(line.label, ""))
            self.setItem(row, 0, label)
            if line.differs:
                combo = QComboBox()
                combo.setPlaceholderText("Choose...")
                combo.addItems(list(line.texts))
                combo.setCurrentIndex((picks or {}).get(row, -1))
                combo.currentIndexChanged.connect(lambda *_: self._changed())
                self.choices[row] = combo
                self.setItem(row, 1, input_item("", editable=False))
                self.setCellWidget(row, 1, combo)
            elif typeable and line.kind == "rider" and not line.values:
                self.setItem(row, 1, input_item(""))
            else:
                self.setItem(row, 1, input_item(line.texts[0] if line.texts else "", False))
        self.blockSignals(False)
        self.resizeRowsToContents()
        self._changed()

    def chosen(self) -> dict[int, int]:
        """Each difference's pick by line: 0 for the first value offered, 1 for the second."""
        return {row: c.currentIndex() for row, c in self.choices.items() if c.currentIndex() >= 0}

    def left(self) -> int:
        return len(self.choices) - len(self.chosen())

    def row_of(self, label: str) -> int:
        for row, line in enumerate(self.lines):
            if line.label == label:
                return row
        raise KeyError(label)

    def choose(self, label: str, text: str) -> None:
        """Pick ``text`` on the line labeled ``label``, as the scorer would."""
        row = self.row_of(label)
        self.choices[row].setCurrentIndex(self.lines[row].texts.index(text))

    def type_value(self, label: str, text: str) -> None:
        """Type ``text`` into the empty line labeled ``label``, as the scorer would."""
        self.item(self.row_of(label), 1).setText(text)

    def _changed(self) -> None:
        # A tint is an item change too; it must not set off another pass.
        self.blockSignals(True)
        for row, combo in self.choices.items():
            # The roster's tint for a value still missing, until it is chosen.
            tint = style.DANGER_TINT if combo.currentIndex() < 0 else style.COMPUTED_WHITE
            self.item(row, 0).setBackground(tint)
        self.blockSignals(False)
        self.changed.emit()


# Why Delete is off: a rider in a scored race is history.
RACED = "Has raced"
NO_GROUP = "No Group"


def _fit_side(side_box: QWidget, buttons: list[QPushButton]) -> None:
    """A column of buttons as wide as its widest, measured in the dialog's own style.

    Called once the column is in the dialog: a button measured before
    that has only the application's style and comes out too narrow for
    the padding the dialog's style sheet gives it, so its text clips.
    """
    for b in buttons:
        b.ensurePolished()
    side_box.setFixedWidth(max(b.sizeHint().width() for b in buttons))


class _TypingDelegate(QStyledItemDelegate):
    """Keys that end a typed cell hand the next cell to ``move``.

    The bibs come off a list from the venue, typed as a column of
    numbers, so the key that ends one number has to start the next, and
    Tab has to cross a row as in any form. Enter must never reach a
    dialog's default button while the scorer is still typing. ``move``
    gets the row, column and key once the typed value is committed and
    the editor closed, and decides which cell opens next.
    """

    KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab, Qt.Key.Key_Backtab)

    def __init__(self, table: QTableWidget, move):
        super().__init__(table)
        self.table = table
        self.move = move

    def eventFilter(self, editor, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() in self.KEYS:
            # An editable combo's keys arrive at its line edit, but the
            # view knows the editor as the combo.
            if isinstance(editor.parentWidget(), QComboBox):
                editor = editor.parentWidget()
            index = self.table.indexAt(editor.geometry().center())
            self.commit(editor)
            self.move(index.row(), index.column(), event.key())
            return True
        if isinstance(editor.parentWidget(), QComboBox):
            # The view handles focus-out for the combo itself; passing the
            # line edit on would commit an editor the view never opened.
            return False
        return super().eventFilter(editor, event)

    def updateEditorGeometry(self, editor, option, index) -> None:
        # A row grown tall by wrapped Details keeps a one-line box to type in.
        rect = option.rect
        height = min(rect.height(), editor.sizeHint().height())
        editor.setGeometry(rect.x(), rect.y() + (rect.height() - height) // 2, rect.width(), height)

    def commit(self, editor: QWidget) -> None:
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
