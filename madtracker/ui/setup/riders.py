"""All Riders: the rider list, the rider form, and Merge Riders."""

import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from madtracker import applog
from madtracker.control.program import is_scored
from madtracker.control.riders import (
    MATCH_TEXT,
    UCI_ID,
    USAC_LICENSE,
    MergeValue,
    and_list,
    candidates,
    merge_choices,
    merge_values,
)
from madtracker.control.roster import enter_on_roster, last_group
from madtracker.importers.bikereg import ImportFormatError, parse, plan_import
from madtracker.inputs import LICENSE_RULE, clean_line, is_blank, read_int, usac_license
from madtracker.store import Race, Rider, Store, StoreError
from madtracker.ui import icons, style
from madtracker.ui.look import APP_PT, DIALOG_BASE_PT
from madtracker.ui.setup._shared import (
    RACED,
    ValueLines,
    _fit_side,
    _refusal_line,
    _refuse,
    first_key,
    name_key,
)
from madtracker.ui.setup.importing import ImportPreview
from madtracker.ui.widgets import (
    ID_ROLE,
    ColumnSort,
    FilterBox,
    Form,
    RowToggleDelegate,
    apply_style,
    busy,
    button_row,
    close_on_shortcut,
    enter_activates,
    error_label,
    filling,
    fit_to_screen,
    friendly_error,
    id_label,
    input_item,
    note_unprintable,
    number_key,
    rider_name,
    run_dialog,
    selected_id,
    setup_table,
    show_message,
    why_label,
    with_why,
)


class RiderForm(QDialog):
    """Add a rider (rider_id None) or edit one. Errors stay on the form."""

    def __init__(self, store: Store, rider_id: int | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.rider_id = rider_id
        self.setWindowTitle("Edit Rider" if rider_id else "New Rider")
        apply_style(self)
        self.first = QLineEdit()
        self.last = QLineEdit()
        self.license = QLineEdit()
        self.uci_id = QLineEdit()
        self.birth_year = QLineEdit()
        self.birth_year.setPlaceholderText("1990")
        # Room for a long name or a license typed from a stranger's form;
        # a narrow field invites typos.
        for field in (self.first, self.last, self.license, self.uci_id):
            field.setMinimumWidth(style.control_height(APP_PT) * 7)
        self.error = error_label()
        note_unprintable(self.first, self.error)
        note_unprintable(self.last, self.error)
        form = Form()
        form.addRow("First name", self.first)
        form.addRow("Last name", self.last)
        form.addRow(id_label(USAC_LICENSE), self.license)
        form.addRow(id_label(UCI_ID), self.uci_id)
        form.addRow("Birth year", self.birth_year)
        buttons, _ = button_row("Save", self.save, self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.error)
        lay.addLayout(buttons)
        if rider_id is not None:
            r = store.rider(rider_id)
            self.first.setText(r.first_name)
            self.last.setText(r.last_name)
            self.license.setText(r.usac_license or "")
            self.uci_id.setText(r.uci_id or "")
            self.birth_year.setText("" if r.birth_year is None else str(r.birth_year))

    def save(self) -> bool:
        first, last = clean_line(self.first.text()), clean_line(self.last.text())
        # A name of spaces or zero-width characters would save a rider nobody
        # could see on a card or pick from a list.
        if is_blank(first) or is_blank(last):
            show_message(self.error, "First and last name are both needed.")
            return False
        year = self.birth_year.text().strip()
        this_year = datetime.date.today().year
        if year and read_int(year, 1900, this_year) is None:
            show_message(
                self.error, f"The birth year is a four-digit year from 1900 to {this_year}."
            )
            return False
        # "INTL-CAN" or "pending" is not a license: the USAC CSV carries
        # this column, so the form refuses it as the import leaves it out.
        try:
            usac_license(self.license.text())
        except ValueError:
            show_message(self.error, LICENSE_RULE)
            return False
        values = {
            "usac_license": self.license.text().strip() or None,
            "uci_id": self.uci_id.text().strip() or None,
            "birth_year": int(year) if year else None,
        }
        try:
            if self.rider_id is None:
                self.rider_id = self.store.add_rider(first, last, **values).rider_id
            else:
                self.store.update_rider(self.rider_id, first_name=first, last_name=last, **values)
        except (StoreError, ValueError) as exc:
            show_message(self.error, friendly_error(self.store, exc))
            return False
        self.accept()
        return True


# Merge riders, page 1's columns.
M_FIRST, M_LAST, M_LICENSE, M_BORN, M_MATCH = range(5)
PICK, KEEP_PAGE = range(2)


class MergeDialog(QDialog):
    """Merge riders: two records of one person become one, one question at a time.

    The scorer starts from a record. Page 1 asks which other record is
    the same person; page 2 shows the merged record a line per value and
    asks only about the values that differ, after JOSM's tag
    reconciliation. Nothing is answered for the scorer, and which record
    stays is never asked: that is the database's question, not the scorer's.

    Page 1 lists every other rider, likely matches first (control/riders.py)
    with the reason in Match. A record that has raced is history, its
    results name it, so two raced records are never merged: when the
    starting record has raced, the other raced records are off here
    rather than refused after they are picked.
    """

    def __init__(self, store: Store, rider_id: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.first = store.rider(rider_id)
        self.first_raced = store.raced_in(rider_id) is not None
        self.kept: int | None = None
        self.drop: Rider | None = None
        self.records: list[Rider] = []
        self.setWindowTitle("Merge Riders")
        fit_to_screen(self, 760, 540)
        apply_style(self)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._pick_page())
        self.stack.addWidget(self._keep_page())
        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)
        self._default(self.next_button)
        self.refresh()
        self.search.setFocus()

    # ----- page 1: who --------------------------------------------------------

    def _pick_page(self) -> QWidget:
        page = QWidget()
        self.search = FilterBox("Filter by name")
        self.search.textChanged.connect(self.refresh)
        # Enter in the filter is taken here, not passed on to the dialog,
        # so it can never also press the next page's Merge.
        self.search.installEventFilter(self)
        self.table = QTableWidget()
        setup_table(self.table, ["First", "Last", USAC_LICENSE, "Birth Year", "Match"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for col in (M_FIRST, M_LAST):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        # Unsorted until a header is clicked: likely matches first is the
        # order that finds the other record.
        self.sort = ColumnSort(
            self.table,
            {
                M_FIRST: first_key,
                M_LAST: name_key,
                M_LICENSE: lambda r: number_key(r.usac_license or ""),
                M_BORN: lambda r: r.birth_year,
                M_MATCH: lambda r: self.match.get(r.rider_id),
            },
            self.refresh,
        )
        self.match: dict[int, str] = {}
        self.table.itemSelectionChanged.connect(self._picked)
        self.table.cellDoubleClicked.connect(lambda *_: self.go_next())
        buttons, made = button_row("Next", self.go_next, self.reject)
        self.next_button = made["primary"]
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(f"Merge {self.first.name} with:")
        lay.addWidget(heading)
        lay.addWidget(self.search)
        lay.addWidget(self.table, 1)
        lay.addLayout(buttons)
        return page

    def refresh(self) -> None:
        f = self.first
        chosen = selected_id(self.table)
        others = [
            r for r in self.store.search_riders(self.search.text()) if r.rider_id != f.rider_id
        ]
        likely = candidates(f.first_name, f.last_name, f.birth_year, others, limit=None)
        self.match = {c.rider.rider_id: MATCH_TEXT[c.rank] for c in likely}
        if self.first_raced:
            for r in others:
                if self.store.raced_in(r.rider_id) is not None:
                    self.match[r.rider_id] = RACED
        top = [c.rider for c in likely]
        ids = {r.rider_id for r in top}
        riders = self.sort.sorted(top + [r for r in others if r.rider_id not in ids])
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(riders))
        for row, r in enumerate(riders):
            born = "" if r.birth_year is None else str(r.birth_year)
            match = self.match.get(r.rider_id, "")
            cells = [r.first_name, r.last_name, r.usac_license or "", born, match]
            for col, text in enumerate(cells):
                item = input_item(text, editable=False)
                if col == 0:
                    item.setData(ID_ROLE, r.rider_id)
                if match == RACED:
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        # A pick survives the filter while it is still listed; nothing is
        # ever picked for the scorer.
        if chosen is not None:
            self.select_rider(chosen)
        self._picked()

    def _pickable(self, row: int) -> bool:
        item = self.table.item(row, 0)
        return item is not None and bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)

    def select_rider(self, rider_id: int) -> None:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(ID_ROLE) == rider_id and self._pickable(row):
                self.table.selectRow(row)
                return

    def eventFilter(self, obj, event) -> bool:
        enter = (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if obj is self.search and event.type() == QEvent.Type.KeyPress and event.key() in enter:
            self._pick_top()
            self.go_next()
            return True
        return super().eventFilter(obj, event)

    def _pick_top(self) -> None:
        """Enter in the filter picks the first rider listed, unless one is already picked."""
        if selected_id(self.table) is not None:
            return
        for row in range(self.table.rowCount()):
            if self._pickable(row):
                self.table.selectRow(row)
                return

    def _picked(self) -> None:
        other = selected_id(self.table)
        self.next_button.setEnabled(other is not None)
        self.next_button.setToolTip("" if other is not None else "Select the other record.")
        self.records = [self.first] + ([self.store.rider(other)] if other is not None else [])
        self._fill_pair()

    def go_next(self) -> bool:
        if len(self.records) < 2:
            return False
        self.stack.setCurrentIndex(KEEP_PAGE)
        self._default(self.merge_button)
        self.merge_button.setFocus()
        return True

    def _default(self, button: QPushButton) -> None:
        """Enter presses the shown page's primary button, never the hidden page's."""
        self.next_button.setDefault(button is self.next_button)
        self.merge_button.setDefault(button is self.merge_button)

    # ----- page 2: the merged record -------------------------------------------

    def _keep_page(self) -> QWidget:
        page = QWidget()
        self.heading = QLabel("")
        self.values_table = ValueLines()
        self.values_table.changed.connect(self._update)
        self.error = error_label()
        self.left = QLabel("")
        self.left.setObjectName("hint")
        back = QPushButton("Back")
        back.setMinimumWidth(style.control_height(DIALOG_BASE_PT) * 3)
        back.clicked.connect(self.go_back)
        buttons, made = button_row("Merge", self.merge, self.reject)
        buttons.insertWidget(0, back)
        buttons.insertWidget(2, self.left)
        self.merge_button = made["primary"]
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.heading)
        lay.addWidget(self.values_table, 1)
        lay.addWidget(self.error)
        lay.addLayout(buttons)
        return page

    def go_back(self) -> None:
        self.stack.setCurrentIndex(PICK)
        self._default(self.next_button)
        self.table.setFocus()

    def _fill_pair(self) -> None:
        """Page 2 for the rider just picked; a new pick starts with nothing chosen."""
        if len(self.records) < 2:
            self.values_table.fill([])
            return
        first, other = self.records
        self.heading.setText(f"Merge {first.name} and {other.name}")
        # A value neither record has is typed here, so a merge tidies the
        # record in one pass.
        self.values_table.fill(
            merge_values(self.store, first.rider_id, other.rider_id), typeable=True
        )

    @property
    def lines(self) -> list[MergeValue]:
        return self.values_table.lines

    def chosen(self) -> dict[int, int]:
        """Each difference's pick, 0 for the starting record's value and 1 for the other's."""
        return self.values_table.chosen()

    def choose(self, label: str, text: str) -> None:
        self.values_table.choose(label, text)

    def type_value(self, label: str, text: str) -> None:
        self.values_table.type_value(label, text)

    def typed(self) -> tuple[dict[str, object], str]:
        """The values typed into lines neither record had, and what is wrong with them, or ""."""
        out: dict[str, object] = {}
        for row, line in enumerate(self.lines):
            if line.kind != "rider" or line.values:
                continue
            text = self.values_table.item(row, 1).text().strip()
            if not text:
                continue
            if line.key == "birth_year":
                this_year = datetime.date.today().year
                if read_int(text, 1900, this_year) is None:
                    return out, f"The birth year is a four-digit year from 1900 to {this_year}."
                out[line.key] = int(text)
                continue
            if line.key == "usac_license":
                try:
                    usac_license(text)
                except ValueError:
                    return out, LICENSE_RULE
                holder = self.store.find_rider_by_license(text)
                if holder is not None and holder.rider_id not in {r.rider_id for r in self.records}:
                    return out, f"{USAC_LICENSE} {text} is on file for {holder.name}."
            if line.key == "uci_id":
                holder = self.store.find_rider_by_uci(text)
                if holder is not None and holder.rider_id not in {r.rider_id for r in self.records}:
                    return out, f"{UCI_ID} {text} is on file for {holder.name}."
            out[line.key] = text
        return out, ""

    def survivor(self) -> tuple[Rider, Rider]:
        """(kept row, removed row): the one that has raced, else the one started from.

        Which row survives is not the scorer's question, since the merged
        record takes the values chosen on the page either way; a record
        that has raced is named by its race logs, so it is the row kept.
        """
        first, other = self.records
        if self.store.raced_in(other.rider_id) is not None:
            return other, first
        return first, other

    def _refusal(self) -> str:
        if len(self.records) < 2:
            return "Select the other record."
        keep, drop = self.survivor()
        problem = self.store.merge_refusal(drop.rider_id, keep.rider_id)
        if problem:
            return friendly_error(self.store, ValueError(problem))
        return ""

    def _update(self) -> None:
        left = self.values_table.left()
        self.left.setText(f"{left} to choose" if left else "")
        refusal = self._refusal() or self.typed()[1]
        reason = refusal or ("Choose a value on each tinted line." if left else "")
        self.merge_button.setEnabled(not reason)
        self.merge_button.setToolTip(reason)
        show_message(self.error, refusal if len(self.records) == 2 else "")

    def merge(self) -> bool:
        if not self.merge_button.isEnabled():
            return False
        keep, drop = self.survivor()
        values, entries, teams = merge_choices(self.lines, self.chosen())
        values.update(self.typed()[0])
        try:
            self.store.merge_riders(
                keep.rider_id, drop.rider_id, values=values, entries=entries, teams=teams
            )
        except StoreError as exc:
            show_message(self.error, friendly_error(self.store, exc))
            return False
        self.kept, self.drop = keep.rider_id, drop
        self.accept()
        return True


def rider_refusal(store: Store, event_id: int, rider_id: int) -> tuple[str, list[Race]]:
    """Why the rider cannot come off the roster ("" when they can), and their races.

    One text serves Choose Riders' untick, the only way off a roster,
    and its refusal, so the two never disagree.
    """
    name = rider_name(store, rider_id)
    races = [
        race
        for race in store.races(event_id)
        if rider_id in {e.rider_id for e in store.race_entries(race.race_id)}
    ]
    scored = next((r for r in races if is_scored(store, r)), None)
    if scored is not None:
        return (
            f"{name} is in {scored.name}, which has been scored,"
            " and cannot be removed from this event.",
            races,
        )
    for race in races:
        team = next((t for t in store.teams(race.race_id) if rider_id in t.members), None)
        if team is not None:
            return (
                f"{name} is on team {team.name} in {race.name}. Edit that race first.",
                races,
            )
    return "", races


def remove_from_roster(
    parent: QWidget, store: Store, event_id: int, rider_id: int, confirm: bool = True
) -> tuple[bool, str]:
    """Take a rider off the roster, and out of the fields of unscored races.

    A scored race keeps the rider (the store refuses). A team is the
    race's to change, so a rider on one is refused until that race is
    edited; a rider only in fields is removed once the scorer agrees.
    Returns (removed, reason); the reason is "" when the rider came off,
    and when the scorer answered Cancel, which needs no message.
    """
    name = rider_name(store, rider_id)
    refusal, races = rider_refusal(store, event_id, rider_id)
    if refusal:
        return False, refusal
    if (
        confirm
        and races
        and not icons.ask(
            parent,
            "Remove Rider",
            f"Remove {name} from this event? They are in: "
            + ", ".join(r.name for r in races)
            + ".",
            verb="Remove",
        )
    ):
        return False, ""
    try:
        store.remove_entry(event_id, rider_id)
    except StoreError as exc:
        return False, friendly_error(store, exc)
    return True, ""


# A roster row's tick cell: checkable by the row's click, never typed in.
ROSTER_TICK_FLAGS = (
    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
)


class RidersDialog(QDialog):
    """The venue's riders: keep the list, or choose an event's roster.

    The Riders window (event_id None, File > Edit Riders) is the one door riders
    come in by and are kept from: New rider, Import from BikeReg, Edit,
    Merge with and Delete live there and nowhere else, so a record is
    always made and changed the same way. Deleting is refused only for
    a rider who has raced, and the button says so under it ("Has
    raced") so a Delete that is off says why without a hover; their
    results name them, so they stay in the list for good. Editing a
    rider applies everywhere.

    Opened for an event (Edit Event's Choose Riders) it is a choice,
    not a list to keep: the first column is a box per rider, ticked for
    those on the roster, and a click anywhere on the row toggles it. A
    roster is a subset of the venue's riders, and a tick per name is
    the shape of that. A tick writes the entry at once, with no bib and
    the group the rider had at their most recent event; an untick takes
    the rider off by the roster's own rules, which is the only way off
    a roster. Bibs are not
    asked here: the venue hands them out for each event, so the
    number is whatever is on the rider's back tonight, a guess from last
    time would be wrong more often than right, and a rider is often on
    the roster before the numbers exist. They are typed in the roster
    table afterward. Enter in the search box ticks the top match, so
    "type a name, Enter" still builds a roster from the keyboard.

    ``import_event`` is the event an import from the Riders window offers to
    put its riders on, the one open in the app.
    """

    def __init__(
        self,
        store: Store,
        event_id: int | None,
        parent: QWidget | None = None,
        import_event: int | None = None,
    ):
        super().__init__(parent)
        self.store = store
        self.event_id = event_id
        # Riders put on the roster while the dialog was open, in order,
        # so the setup screen can select the last one and count them.
        self.added: list[int] = []
        self.removed: list[int] = []
        self.import_event = import_event
        self.manage = event_id is None
        self.roster_mode = not self.manage
        if self.manage:
            self.setWindowTitle("Edit Riders")
        else:
            self.setWindowTitle(f"Choose Riders: {store.event(event_id).name}")
        fit_to_screen(self, 760, 520)
        apply_style(self)
        close_on_shortcut(self)
        self.search = FilterBox("Filter by name")
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.choose)
        if self.roster_mode:
            # The whole list at once, as any checklist offers; each acts on
            # the riders the filter shows. Built only for a roster, since a
            # widget no layout takes is never deleted with the dialog.
            self.select_all = QPushButton("Select All")
            self.select_all.clicked.connect(lambda: self.tick_all(True))
            self.select_none = QPushButton("Select None")
            self.select_none.clicked.connect(lambda: self.tick_all(False))
            self.roster_count = QLabel("")
            self.roster_count.setObjectName("hint")
        self.table = QTableWidget()
        # The name columns are first except for a roster, where the tick
        # is: the box is what the row is for there.
        self.first_col = 1 if self.roster_mode else 0
        self.last_col = self.first_col + 1
        headers = ["First", "Last", USAC_LICENSE, "Birth Year"]
        if self.roster_mode:
            headers = [""] + headers
        # A roster row is ticked, not selected: a blue selection there
        # would read as "on the roster" and compete with the tick.
        setup_table(self.table, headers, selectable=not self.roster_mode)
        # Birth year or the tick would otherwise take the spare width; the
        # names are the columns that want it.
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for col in (self.first_col, self.last_col):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        if self.roster_mode:
            # The whole row is the tick, not only the box inside it.
            self.table.setItemDelegateForColumn(0, RowToggleDelegate(self.table))
        # Last name ascending is the order the search returns; the tick
        # is not something to look a rider up by.
        n = self.first_col
        self.sort = ColumnSort(
            self.table,
            {
                n: first_key,
                n + 1: name_key,
                n + 2: lambda r: number_key(r.usac_license or ""),
                n + 3: lambda r: r.birth_year,
            },
            self.refresh,
            column=self.last_col,
        )
        enter_activates(self.table, self._double_clicked)
        self.table.cellClicked.connect(self._row_clicked)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        # Only the Riders window makes, imports, edits, merges or deletes a
        # rider; a pick for tonight's roster only picks.
        self.new = self.import_button = self.edit = self.merge = self.delete = None
        self.delete_why = None
        if self.manage:
            self.new = QPushButton("New Rider...")
            self.new.clicked.connect(self.new_rider)
            self.import_button = QPushButton("Import from BikeReg...")
            self.import_button.clicked.connect(self.import_bikereg)
            self.edit = QPushButton("Edit...")
            self.edit.clicked.connect(self.edit_selected)
            self.merge = QPushButton("Merge With...")
            self.merge.setToolTip("Join two records of one person")
            self.merge.clicked.connect(lambda: self.merge_selected())
            self.delete = QPushButton("Delete")
            self.delete.setObjectName("danger")
            self.delete.clicked.connect(lambda: self.delete_selected())
            # Why Delete or Merge is off, under it: a disabled button's
            # tooltip is found only by someone who already suspects there
            # is a reason.
            self.delete_why = why_label()
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        self.status = _refusal_line()
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        if self.roster_mode:
            # Nothing to do here but tick: the list takes the width, and
            # the count and Close sit under it.
            top.addWidget(self.select_all)
            top.addWidget(self.select_none)
            lay.addWidget(self.table, 1)
            lay.addWidget(self.status)
            # Only the count and Close: a second button beside Close would
            # read as confirming the ticks. Riders are made in File > Edit
            # Riders.
            bottom = QHBoxLayout()
            bottom.addWidget(self.roster_count)
            bottom.addStretch(1)
            bottom.addWidget(close)
            lay.addLayout(bottom)
        else:
            side = QVBoxLayout()
            side.setSpacing(style.SM)
            for b in (self.new, self.import_button, self.edit, self.merge):
                side.addWidget(b)
            # Apart from the everyday buttons, so it is never the one
            # a quick click lands on.
            side.addSpacing(style.XL - style.SM)
            side.addLayout(with_why(self.delete, self.delete_why))
            side.addStretch(1)
            side.addWidget(close)
            side_box = QWidget()
            side_box.setLayout(side)
            side.setContentsMargins(0, 0, 0, 0)
            body = QHBoxLayout()
            body.addWidget(self.table, 1)
            body.addWidget(side_box)
            lay.addLayout(body, 1)
            buttons = [self.new, self.import_button, self.edit, self.merge, self.delete, close]
            # Enter on a row is the row's: the table passes it up, and an
            # auto-default button would take it as New Rider....
            for b in buttons:
                b.setAutoDefault(False)
            _fit_side(side_box, buttons)
            lay.addWidget(self.status)
        self.refresh()
        self.search.setFocus()

    def _row_clicked(self, row: int, col: int) -> None:
        if self.roster_mode:
            item = self.table.item(row, 0)
            on = item.checkState() == Qt.CheckState.Checked
            self.set_on_roster(item.data(ID_ROLE), not on)

    def _double_clicked(self) -> None:
        # Two clicks on a roster row would be a tick and an untick; the
        # first click did the work, so the second changes nothing more.
        if self.manage:
            self.edit_selected()

    def refresh(self) -> None:
        """Fill the table with the riders the filter matches, in the sort's order.

        Runs on every keystroke in the filter, over a venue's whole list
        (3000 riders and more), so a row already in the table keeps its
        cells and takes the new rider's text, and only rows past the old
        end get new cells. Every cell of a row the table shows is set
        here, so a kept row reads as a new one would.
        """
        taken = set() if self.manage else {e.rider_id for e in self.store.entries(self.event_id)}
        riders = self.sort.sorted(self.store.search_riders(self.search.text()))
        checked, unchecked = Qt.CheckState.Checked, Qt.CheckState.Unchecked
        with filling(self.table):
            kept = self.table.rowCount()
            self.table.setRowCount(len(riders))
            self._count()
            for row, r in enumerate(riders):
                born = "" if r.birth_year is None else str(r.birth_year)
                cells = [r.first_name, r.last_name, r.usac_license or "", born]
                if self.roster_mode:
                    cells = [""] + cells
                for col, text in enumerate(cells):
                    item = self.table.item(row, col) if row < kept else None
                    if item is not None:
                        item.setText(text)
                        continue
                    item = input_item(text, editable=False)
                    if self.roster_mode and col == 0:
                        item.setFlags(ROSTER_TICK_FLAGS)
                    self.table.setItem(row, col, item)
                first = self.table.item(row, 0)
                first.setData(ID_ROLE, r.rider_id)
                if self.roster_mode:
                    first.setCheckState(checked if r.rider_id in taken else unchecked)
        if riders:
            self.table.selectRow(0)
        self._update_buttons()

    def _selected(self) -> Rider | None:
        rider_id = selected_id(self.table)
        return None if rider_id is None else self.store.rider(rider_id)

    def _rostered(self, rider_id: int) -> list[str]:
        """The events whose roster holds the rider, oldest first."""
        return [
            m.name
            for m in reversed(self.store.events())
            if any(e.rider_id == rider_id for e in self.store.entries(m.event_id))
        ]

    def _delete_refusal(self, rider_id: int) -> str:
        """Why Delete is off ("" when it is not): the rider has raced.

        Two words under the button, because the one rule is short: a
        rider in a scored race is history. A rider who is only on a
        roster can go, and the confirmation names the roster.
        """
        return RACED if self.store.raced_in(rider_id) is not None else ""

    def _count(self) -> None:
        """``22 of 35 riders on the roster``: the size of the choice, under it."""
        if not self.roster_mode:
            return
        on = len(self.store.entries(self.event_id))
        total = self.store.rider_count()
        text = f"{on} of {total} riders on the roster" if total else "No riders yet"
        self.roster_count.setText(text)

    def _update_buttons(self) -> None:
        if self.delete is None:
            return
        r = self._selected()
        for b in (self.edit, self.merge):
            b.setEnabled(r is not None)
        refusal = "" if r is None else self._delete_refusal(r.rider_id)
        self.delete.setEnabled(r is not None and not refusal)
        self.delete_why.setText(refusal)

    def select_rider(self, rider_id: int) -> None:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(ID_ROLE) == rider_id:
                self.table.selectRow(row)
                return

    def _box(self, rider_id: int) -> QTableWidgetItem | None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item.data(ID_ROLE) == rider_id:
                return item
        return None

    def _set_box(self, rider_id: int, on: bool) -> None:
        item = self._box(rider_id)
        if item is not None:
            item.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def set_on_roster(self, rider_id: int, on: bool, confirm: bool = True) -> bool:
        """Tick: on the roster at once, with last event's group. Untick: off it.

        The box ends up showing the truth either way: a refused untick
        goes back to ticked with the reason on the status line, and a
        tick the store refuses goes back to empty.
        """
        name = rider_name(self.store, rider_id)
        taken = {e.rider_id for e in self.store.entries(self.event_id)}
        if on:
            if rider_id in taken:
                self._set_box(rider_id, True)
                _refuse(self.status, f"{name} is already on the roster.")
                return False
            # The design's suggestion for a rider added by hand: the
            # group from their most recent event, changed on the roster.
            group = last_group(self.store, rider_id)
            try:
                enter_on_roster(self.store, self.event_id, rider_id, None, group)
            except (StoreError, ValueError) as exc:
                self._set_box(rider_id, False)
                _refuse(self.status, friendly_error(self.store, exc))
                return False
            if rider_id in self.removed:
                self.removed.remove(rider_id)
            elif rider_id not in self.added:
                self.added.append(rider_id)
            self._set_box(rider_id, True)
            self._count()
            # The tick is the confirmation; an old refusal no longer applies.
            _refuse(self.status, "")
            return True
        if rider_id not in taken:
            self._set_box(rider_id, False)
            return False
        done, reason = remove_from_roster(self, self.store, self.event_id, rider_id, confirm)
        if not done:
            self._set_box(rider_id, True)
            if reason:
                _refuse(self.status, reason)
            return False
        if rider_id in self.added:
            self.added.remove(rider_id)
        else:
            self.removed.append(rider_id)
        self._set_box(rider_id, False)
        self._count()
        _refuse(self.status, "")
        return True

    def shown_ids(self) -> list[int]:
        return [self.table.item(r, 0).data(ID_ROLE) for r in range(self.table.rowCount())]

    def tick_all(self, on: bool, confirm: bool = True) -> int:
        """Tick (or untick) every rider the list shows; how many changed.

        Select none asks once, naming how many come out of races not yet
        scored, rather than once a rider. A rider who cannot come off
        (in a scored race, or on a team) stays ticked, and the line
        under the list says how many and why the first one did.
        """
        taken = {e.rider_id for e in self.store.entries(self.event_id)}
        ids = [i for i in self.shown_ids() if (i in taken) != on]
        if not ids:
            return 0
        if on:
            return sum(self.set_on_roster(i, True) for i in ids)
        movable, refused = [], []
        for rider_id in ids:
            reason, races = rider_refusal(self.store, self.event_id, rider_id)
            (refused if reason else movable).append((rider_id, reason, races))
        in_races = sum(1 for _, _, races in movable if races)
        if confirm and in_races and movable:
            riders = f"{len(movable)} rider{'' if len(movable) == 1 else 's'}"
            some = f"{in_races} {'is' if in_races == 1 else 'are'}"
            question = (
                f"Take {riders} off the roster? {some} in races not yet run and come out of them."
            )
            if not icons.ask(self, "Remove Riders", question, verb="Remove"):
                return 0
        done = sum(self.set_on_roster(i, False, confirm=False) for i, _, _ in movable)
        if refused:
            stay = f"{len(refused)} rider{'' if len(refused) == 1 else 's'} stay"
            _refuse(self.status, f"{stay} on the roster. {refused[0][1]}")
        return done

    def choose(self) -> bool:
        if self.manage:
            # Nothing to pick with no event: Enter or a double click edits.
            self.edit_selected()
            return False
        # Enter ticks the top match and empties the search for the
        # next name, so a roster is still typed one name at a time.
        if self.table.rowCount() == 0:
            _refuse(self.status, "No rider matches.")
            return False
        done = self.set_on_roster(self.table.item(0, 0).data(ID_ROLE), True)
        self.search.clear()
        self.search.setFocus()
        return done

    def new_rider(self) -> None:
        form = RiderForm(self.store, parent=self)
        if run_dialog(form) != QDialog.DialogCode.Accepted:
            return
        # The new rider is selected, not added: for a roster the tick is
        # the add, and with no event there is nothing to add them to.
        self.search.clear()
        self.refresh()
        self.select_rider(form.rider_id)

    def import_bikereg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import from BikeReg", str(Path.home()), "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            preview = self.preview_for(path)
            if preview is not None:
                self.run_preview(preview)

    def preview_for(self, path: str | Path) -> "ImportPreview | None":
        try:
            rows = parse(Path(path))
        except (ImportFormatError, OSError, UnicodeDecodeError) as exc:
            reason = str(exc).rstrip(".")
            _refuse(self.status, f"Could not read {Path(path).name}: {reason}.")
            return None
        except Exception as exc:  # any file at all can be picked here
            # The file is untrusted input; whatever it does to the reader
            # is a file that cannot be read, said on the status line, and
            # the traceback goes to the log for whoever supports the scorer.
            applog.error(
                f"Import of {path} failed\n{applog.traceback_text(type(exc), exc, exc.__traceback__)}"
            )
            _refuse(self.status, f"Could not read {Path(path).name}.")
            return None
        if not rows:
            _refuse(self.status, f"{Path(path).name} has no registrations.")
            return None
        # A file that reads clears the complaint about the one before it.
        _refuse(self.status, "")
        event = self.import_event
        with busy():
            return ImportPreview(self.store, event, plan_import(self.store, event, rows), self)

    def run_preview(self, preview: "ImportPreview") -> None:
        if run_dialog(preview) == QDialog.DialogCode.Accepted:
            self.import_done(preview)

    def import_done(self, preview: "ImportPreview") -> None:
        self.refresh()
        if preview.result is not None:
            r = preview.result
            text = r.summary()
            notes = r.adjusted + r.skipped
            if notes:
                text += " " + " ".join(notes[:3]) + (" ..." if len(notes) > 3 else "")
            # A clean import shows in the table; rows it could not bring
            # in, or brought in other than the preview showed (an id held
            # back), are news the scorer has to read.
            _refuse(self.status, text if r.skipped or r.adjusted else "")

    def edit_selected(self) -> None:
        r = self._selected()
        if r is None:
            return
        if (
            run_dialog(RiderForm(self.store, r.rider_id, parent=self))
            == QDialog.DialogCode.Accepted
        ):
            self.refresh()
            _refuse(self.status, "")

    def delete_selected(self, confirm: bool = True) -> bool:
        r = self._selected()
        if r is None:
            return False
        if self._delete_refusal(r.rider_id):
            _refuse(self.status, f"{r.name} has raced, so they can't be deleted.")
            return False
        question = f"Delete {r.name} from the venue's riders?"
        events = self._rostered(r.rider_id)
        if events:
            question += f" They come off the roster of {and_list(events)}."
        if confirm and not icons.ask(self, "Delete Rider", question, verb="Delete"):
            return False
        try:
            self.store.delete_rider(r.rider_id)
        except StoreError as exc:
            _refuse(self.status, friendly_error(self.store, exc))
            return False
        self.refresh()
        _refuse(self.status, "")
        return True

    def merge_dialog(self) -> "MergeDialog | None":
        """Merge riders, starting from the selected record."""
        r = self._selected()
        return None if r is None else MergeDialog(self.store, r.rider_id, parent=self)

    def merge_selected(self) -> bool:
        dialog = self.merge_dialog()
        if dialog is None or run_dialog(dialog) != QDialog.DialogCode.Accepted:
            return False
        self.merge_done(dialog)
        return True

    def merge_done(self, dialog: "MergeDialog") -> None:
        self.refresh()
        self.select_rider(dialog.kept)
        _refuse(self.status, "")
