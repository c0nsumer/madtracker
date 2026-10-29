"""The Shorten Race box: the race's new sprint count, then Shorten.

The Chief Referee may shorten a race (USAC 1G4(b)), and the one fact
the scorer enters is the new count, so the task line's **Shorten
Race...** opens this instead of a question. The spin box runs from the
next sprint up to one below the count in force: a count at or below the
sprints ridden is a race stopped, which End Race Now, Result As-Is
records, and the count in force is no shortening.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from madtracker.ui import style
from madtracker.ui.widgets import Form, apply_style, button_row, spin_box

TITLE = "Shorten Race"
QUESTION = "Shorten the race to how many sprints?"
TIP = "The race's sprint count from now on; its last sprint is the final sprint."


class ShortenRaceDialog(QDialog):
    """``fewest`` and ``most`` bound the count; ``count()`` is the answer once accepted."""

    def __init__(self, fewest: int, most: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        apply_style(self)
        body = QLabel(QUESTION)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.spin = spin_box(fewest, most)
        self.spin.setValue(most)
        self.spin.setToolTip(TIP)
        form = Form()
        form.addRow("Sprints", self.spin)
        buttons, made = button_row("Shorten", self.accept, self.reject)
        self.shorten = made["primary"]
        self.cancel = made["cancel"]
        # Cancel is the default, as on every question: the race's own call
        # must not be made by a stray Enter on a button. Enter in the
        # number records, as the number boxes do: the scorer types the
        # count and presses Enter expecting it to take.
        self.shorten.setDefault(False)
        self.cancel.setDefault(True)
        lay = QVBoxLayout(self)
        lay.addWidget(body)
        lay.addSpacing(style.SM)
        lay.addLayout(form)
        lay.addSpacing(style.MD)
        lay.addLayout(buttons)
        self.spin.setFocus()
        self.spin.selectAll()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # The spin box passes Enter on to the dialog, which would press
        # the default button, Cancel.
        enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if enter and self.focusWidget() in (self.spin, self.spin.lineEdit()):
            self.spin.interpretText()
            self.accept()
            return
        super().keyPressEvent(event)

    def count(self) -> int:
        return int(self.spin.value())
