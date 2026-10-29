"""The points penalty dialog: who, the penalty in points, Record; and the omnium's.

A penalty is the one rider action with a number in it (USAC 8D5(b):
"loss of points"), so the card's and the row's **Points Penalty...**
open this instead of a question. The number is the rider's whole
penalty, shown as it stands and set to what the officials now say: the
result has one Penalty figure per rider, so that is the number the
scorer keeps, and a second ruling, a reversal, or a wrong rider is one
dialog each. It asks for nothing else: no reason and no article, since
the app keeps score and the officials' sheet keeps the why.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QVBoxLayout, QWidget

from madtracker.ui import style
from madtracker.ui.widgets import Form, apply_style, button_row, fit_popup, spin_box

TITLE = "Points Penalty"
MOST = 99
TIP = "The penalty in points. 0 takes it off."
OMNIUM_TITLE = "Omnium Penalty"
# USAC 2O3(e)'s deduction is 40; the cap leaves room for a venue's own.
OMNIUM_MOST = 999
OMNIUM_TIP = "The omnium penalty in points, off the rider's total. 0 takes it off."


class PointsPenaltyDialog(QDialog):
    """``who`` is the rider as Undo names them ("#12 Maya Petrakis"),
    ``current`` the penalty standing; ``points()`` is the penalty to set."""

    def __init__(self, who: str, current: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        apply_style(self)
        self.current = current
        name = QLabel(who)
        name.setFont(style.ui_font(bold=True))
        name.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.spin = spin_box(0, MOST)
        self.spin.setValue(current)
        self.spin.setToolTip(TIP)
        form = Form()
        form.addRow("Points", self.spin)
        # Record is the default, unlike a question's Cancel: the scorer
        # types the number and presses Enter expecting it to record.
        # The number is selected for typing.
        buttons, made = button_row("Record", self.accept, self.reject)
        self.record = made["primary"]
        # The same number records nothing, so Record waits for a change.
        self.spin.valueChanged.connect(self._changed)
        self._changed(current)
        lay = QVBoxLayout(self)
        lay.addWidget(name)
        lay.addSpacing(style.SM)
        lay.addLayout(form)
        lay.addSpacing(style.MD)
        lay.addLayout(buttons)
        self.spin.setFocus()
        self.spin.selectAll()

    def _changed(self, value: int) -> None:
        self.record.setEnabled(int(value) != self.current)

    def accept(self) -> None:
        # Enter in the spin box reaches here through the default button
        # even while it is grayed; an unchanged number stays a no-op.
        if self.record.isEnabled():
            super().accept()

    def points(self) -> int:
        return int(self.spin.value())


class OmniumPenaltyDialog(QDialog):
    """``riders`` are (rider_id, label, current penalty) for the standings' table.

    The omnium's penalty is on the standings, not on a race, so this
    asks who as well as how much: the preview's rows are read, never
    picked, and the button under it is the one door. ``rider_id()`` and
    ``points()`` are the answer once accepted.
    """

    def __init__(self, riders: list[tuple[int, str, int]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(OMNIUM_TITLE)
        apply_style(self)
        self.riders = riders
        self.who = QComboBox()
        for rider_id, label, _current in riders:
            self.who.addItem(label, rider_id)
        fit_popup(self.who)
        self.spin = spin_box(0, OMNIUM_MOST)
        self.spin.setToolTip(OMNIUM_TIP)
        form = Form()
        form.addRow("Rider", self.who)
        form.addRow("Points", self.spin)
        # Record is the default, as the Points Penalty dialog has it: the
        # number is typed and Enter records.
        buttons, made = button_row("Record", self.accept, self.reject)
        self.record = made["primary"]
        self.who.currentIndexChanged.connect(lambda _i: self._picked())
        self.spin.valueChanged.connect(lambda _v: self._changed())
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addSpacing(style.MD)
        lay.addLayout(buttons)
        self._picked()
        self.spin.setFocus()
        self.spin.selectAll()

    def current(self) -> int:
        """The chosen rider's penalty as it stands."""
        return self.riders[self.who.currentIndex()][2] if self.riders else 0

    def _picked(self) -> None:
        # The rider's own number, so a second ruling edits what stands.
        self.spin.setValue(self.current())
        self.spin.selectAll()
        self._changed()

    def _changed(self) -> None:
        self.record.setEnabled(bool(self.riders) and int(self.spin.value()) != self.current())

    def accept(self) -> None:
        if self.record.isEnabled():
            super().accept()

    def rider_id(self) -> int:
        return int(self.who.currentData())

    def points(self) -> int:
        return int(self.spin.value())
