"""The event dialogs: New Event, Open Event, Copy File, and the PDF export."""

from collections.abc import Sequence

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from madtracker.control.riders import and_list
from madtracker.dates import show_date
from madtracker.store import Store, StoreError
from madtracker.ui import icons, style
from madtracker.ui.look import APP_PT
from madtracker.ui.setup._shared import RACED, _refuse, _typed
from madtracker.ui.widgets import (
    ID_ROLE,
    Form,
    align_header,
    apply_style,
    button_row,
    date_edit,
    error_label,
    fit_popup,
    fit_to_screen,
    friendly_error,
    input_item,
    note_unprintable,
    selected_id,
    setup_table,
    show_message,
    why_label,
    with_why,
)


class NewEventDialog(QDialog):
    """File > New Event: a name and a date; the rest is on the Edit Event screen."""

    def __init__(self, store: Store, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.event_id: int | None = None
        self.setWindowTitle("New Event")
        apply_style(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Race Night 12")
        self.date = date_edit(QDate.currentDate())
        # An earlier event's program, with empty fields (design section 6).
        self.start_from = QComboBox()
        self.start_from.addItem("An Empty Program", None)
        for m in store.events():
            if store.races(m.event_id):
                self.start_from.addItem(f"{m.name} ({show_date(m.event_date)})", m.event_id)
        # The second night of a two-day event wants last night's riders,
        # bibs, fields, and teams as well; a weekly night wants the races
        # alone, so this is off until asked.
        self.copy_roster = QCheckBox("Copy roster, bibs, fields, and teams")
        self.copy_roster.setToolTip(
            "The riders with the bibs and groups they had, and each race's field and teams"
        )
        self.start_from.currentIndexChanged.connect(self._offer_roster)
        self._offer_roster()
        self.error = error_label()
        note_unprintable(self.name, self.error)
        form = Form()
        form.addRow("Name", self.name)
        form.addRow("Date", self.date)
        form.addRow("Start from", self.start_from)
        form.addRow("", self.copy_roster)
        buttons, _ = button_row("Create Event", self.create, self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.error)
        lay.addLayout(buttons)

    def create(self) -> bool:
        from madtracker.control import venue

        name = _typed(self.name)
        if not name:
            show_message(self.error, "The event needs a name.")
            return False
        try:
            event = self.store.add_event(
                name, self.date.date().toString("yyyy-MM-dd"), venue=venue.venue_name(self.store)
            )
        except (StoreError, ValueError) as exc:
            show_message(self.error, friendly_error(self.store, exc))
            return False
        self.event_id = event.event_id
        source = self.start_from.currentData()
        if source is not None:
            from madtracker.control.copying import copy_program

            copy_program(
                self.store, int(source), event.event_id, with_roster=self.copy_roster.isChecked()
            )
        self.accept()
        return True

    def _offer_roster(self) -> None:
        """The roster box means nothing without an earlier event: off, and cleared."""
        offered = self.start_from.currentData() is not None
        self.copy_roster.setEnabled(offered)
        if not offered:
            self.copy_roster.setChecked(False)


class OpenEventDialog(QDialog):
    """File > Open Event: the venue's events, newest first.

    A table rather than a drop-down: the series and the size of each
    event tell two nights with the same name apart at a glance.

    Delete is here, where events are listed, for one made by mistake or
    as a test. An event with a scored race keeps its place for good: its
    log is never edited, and its results may already be on paper or with
    USA Cycling. Delete says so under itself ("Has raced").
    """

    def __init__(self, store: Store, current: int | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.event_id: int | None = None
        # Events deleted while the dialog was open, so the app can leave
        # one it had open.
        self.deleted: list[int] = []
        self.setWindowTitle("Open Event")
        fit_to_screen(self, 720, 480)
        apply_style(self)
        self.table = QTableWidget()
        setup_table(self.table, ["Date", "Name", "Series", "Races", "Riders"])
        for col in (3, 4):
            align_header(self.table, col, Qt.AlignmentFlag.AlignRight)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_chosen())
        self.table.itemSelectionChanged.connect(self._update)
        buttons, made = button_row("Open", self.open_chosen, self.reject)
        self.open_button = made["primary"]
        self.delete = QPushButton("Delete")
        self.delete.setObjectName("danger")
        self.delete.clicked.connect(lambda: self.delete_selected())
        self.delete_why = why_label()
        # Apart from Open and Cancel, at the other end of the row; the row
        # lines up on the buttons' tops, since Delete's reason sits under it.
        buttons.insertLayout(0, with_why(self.delete, self.delete_why))
        for b in made.values():
            buttons.setAlignment(b, Qt.AlignmentFlag.AlignTop)
        self.status = error_label()
        self.status.setVisible(False)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.status)
        lay.addLayout(buttons)
        # Delete's reason line is held even when empty, so the buttons do
        # not jump as the selection moves. It hangs into the bottom margin,
        # so the space under Open and Cancel stays near every other dialog's.
        m = lay.contentsMargins()
        reason = self.delete_why.height() + style.XS // 2
        lay.setContentsMargins(m.left(), m.top(), m.right(), max(style.XS, m.bottom() - reason))
        self.refresh(current)
        self.table.setFocus()

    def refresh(self, select: int | None = None) -> None:
        store = self.store
        # store.events() is already newest first: tonight's event is on top.
        events = store.events()
        self.table.setRowCount(len(events))
        for row, m in enumerate(events):
            cells = [
                show_date(m.event_date),
                m.name,
                m.series,
                str(len(store.races(m.event_id))),
                str(len(store.entries(m.event_id))),
            ]
            for col, text in enumerate(cells):
                item = input_item(text, editable=False)
                if col == 0:
                    item.setData(ID_ROLE, m.event_id)
                if col >= 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, col, item)
        if events:
            self.table.selectRow(0)
        if select is not None:
            self.select_event(select)
        self._update()

    def select_event(self, event_id: int) -> None:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(ID_ROLE) == event_id:
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 0))
                return

    def _update(self) -> None:
        chosen = selected_id(self.table)
        self.open_button.setEnabled(chosen is not None)
        raced = chosen is not None and self.store.event_raced(int(chosen)) is not None
        self.delete.setEnabled(chosen is not None and not raced)
        self.delete_why.setText(RACED if raced else "")

    def delete_selected(self, confirm: bool = True) -> bool:
        chosen = selected_id(self.table)
        if chosen is None or not self.delete.isEnabled():
            return False
        event = self.store.event(int(chosen))
        races = len(self.store.races(event.event_id))
        riders = len(self.store.entries(event.event_id))
        what = [f"{races} race{'' if races == 1 else 's'}"] if races else []
        if riders:
            what.append(f"its roster of {riders} rider{'' if riders == 1 else 's'}")
        question = f"Delete {event.name}?"
        if what:
            # "1 race goes", "6 races go", "its roster goes", both "go".
            plural = len(what) > 1 or races > 1
            text = and_list(what)
            question += f" {text[0].upper()}{text[1:]} {'go' if plural else 'goes'} with it."
        question += " The riders themselves stay."
        if confirm and not icons.ask(self, "Delete Event", question, verb="Delete"):
            return False
        try:
            self.store.delete_event(event.event_id)
        except StoreError as exc:
            _refuse(self.status, friendly_error(self.store, exc))
            return False
        self.deleted.append(event.event_id)
        _refuse(self.status, "")
        self.refresh()
        return True

    def open_chosen(self) -> bool:
        chosen = selected_id(self.table)
        if chosen is None:
            return False
        self.event_id = int(chosen)
        self.accept()
        return True


class CopyFileDialog(QDialog):
    """File > New Data File while one is open: what the new file takes from it."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("New Data File")
        apply_style(self)
        intro = QLabel("Copy from the open file:")
        self.settings = QCheckBox(
            "Settings (venue name, backup folder, riders on the scoreboard, accent color,"
            " default ruleset)"
        )
        self.logo = QCheckBox("Logo")
        self.rulesets = QCheckBox("Rulesets")
        self.riders = QCheckBox("Riders")
        for box in (self.settings, self.logo, self.rulesets, self.riders):
            box.setChecked(True)
        buttons, _ = button_row("Create File", self.accept, self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        for box in (self.settings, self.logo, self.rulesets, self.riders):
            lay.addWidget(box)
        lay.addLayout(buttons)

    def choice(self):
        from madtracker.control.copying import CopyChoice

        return CopyChoice(
            settings=self.settings.isChecked(),
            logo=self.logo.isChecked(),
            rulesets=self.rulesets.isChecked(),
            riders=self.riders.isChecked(),
        )


class ExportPdfDialog(QDialog):
    """File > Export Results PDF: the whole event, or one race picked from a list.

    PDFs are wanted through the night as each race concludes, so the
    selected race is the default once it has started. The list holds the
    races that have started, the ones the whole event prints; with none,
    the race choice is off and its tooltip says why.
    """

    def __init__(
        self,
        races: Sequence[tuple[int, str]],
        *,
        default: int | None = None,
        race_first: bool = False,
        parent: QWidget | None = None,
    ):
        """``races``: (race id, name) in program order; ``default``: the race the list shows."""
        super().__init__(parent)
        self.setWindowTitle("Export Results PDF")
        apply_style(self)
        self.whole = QRadioButton("Whole event")
        self.race = QRadioButton("Race")
        self.choice = QComboBox()
        for race_id, name in races:
            self.choice.addItem(name, race_id)
        fit_popup(self.choice)
        # Room for a long race name beside the word Race.
        self.choice.setMinimumWidth(style.control_height(APP_PT) * 8)
        index = self.choice.findData(default)
        self.choice.setCurrentIndex(max(index, 0))
        # Picking a race from the list is choosing to export that race.
        self.choice.activated.connect(lambda _i: self.race.setChecked(True))
        if not races:
            self.race.setEnabled(False)
            self.choice.setEnabled(False)
            self.race.setToolTip("No race has started yet.")
            self.whole.setChecked(True)
        elif race_first:
            self.race.setChecked(True)
        else:
            self.whole.setChecked(True)
        grid = QGridLayout()
        grid.addWidget(self.whole, 0, 0, 1, 2)
        grid.addWidget(self.race, 1, 0)
        grid.addWidget(self.choice, 1, 1)
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(style.SM)
        buttons, _ = button_row("Export", self.accept, self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(grid)
        lay.addSpacing(style.MD)
        lay.addLayout(buttons)

    def whole_event(self) -> bool:
        return self.whole.isChecked()

    def race_id(self) -> int | None:
        """The race picked, or None for the whole event."""
        return None if self.whole_event() else self.choice.currentData()
